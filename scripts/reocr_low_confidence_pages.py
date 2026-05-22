from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_PACKAGES = REPO_ROOT / ".venv" / "Lib" / "site-packages"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(SITE_PACKAGES))

from scripts.ocr_scanned_pdfs import ocr_page_tesseract  # noqa: E402


RAW_DIR = REPO_ROOT / "data_pipeline" / "raw" / "tsinghua_gas_turbine_books"
DEFAULT_INPUT_ROOT = REPO_ROOT / "data_pipeline" / "ocr_layout_aware_tesseract" / "tsinghua_gas_turbine_books"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data_pipeline" / "ocr_layout_aware_tesseract_highres_refined" / "tsinghua_gas_turbine_books"
REPORT_DIR = REPO_ROOT / "data_pipeline" / "reports"
HUMAN_DIR = REPO_ROOT / "00_项目成果总览_先看这里" / "02_OCR结果_13本扫描PDF" / "03_低置信度页高分辨率重识别"


@dataclass(frozen=True)
class ReocrTarget:
    source_file: str
    doc_dir_name: str
    manifest_path: Path
    pages_jsonl: Path
    page_num: int
    original_page: dict[str, Any]


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def manifest_pages_path(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    raw_path = Path(str(manifest["pages_jsonl"]))
    if raw_path.exists():
        return raw_path
    fallback = manifest_path.parent / "pages.jsonl"
    if fallback.exists():
        return fallback
    return raw_path


def collect_reocr_targets(ocr_root: str | Path, threshold: float, include_empty: bool = False) -> list[ReocrTarget]:
    root = resolve_repo_path(ocr_root)
    targets: list[ReocrTarget] = []
    for manifest_path in sorted(root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pages_jsonl = manifest_pages_path(manifest_path, manifest)
        for page in load_jsonl(pages_jsonl):
            if page.get("status") == "error":
                continue
            confidence = float(page.get("avg_confidence") or 0.0)
            text = str(page.get("text") or "")
            char_count = int(page.get("char_count") or len(text))
            if confidence >= threshold:
                continue
            if not include_empty and char_count <= 0 and not text.strip():
                continue
            targets.append(
                ReocrTarget(
                    source_file=str(page.get("source_file") or manifest["source_file"]),
                    doc_dir_name=manifest_path.parent.name,
                    manifest_path=manifest_path,
                    pages_jsonl=pages_jsonl,
                    page_num=int(page["page_num"]),
                    original_page=page,
                )
            )
    return targets


def choose_page_result(
    original: dict[str, Any],
    candidate: dict[str, Any],
    *,
    min_confidence_gain: float = 0.03,
    min_char_ratio: float = 0.6,
) -> tuple[bool, str, dict[str, Any]]:
    original_confidence = float(original.get("avg_confidence") or 0.0)
    candidate_confidence = float(candidate.get("avg_confidence") or 0.0)
    original_chars = int(original.get("char_count") or len(str(original.get("text") or "")))
    candidate_chars = int(candidate.get("char_count") or len(str(candidate.get("text") or "")))

    if candidate_chars <= 0:
        return False, "candidate_empty", dict(original)
    if original_chars > 0 and candidate_chars < int(original_chars * min_char_ratio):
        return False, "candidate_lost_too_much_text", dict(original)
    if candidate_confidence + 1e-9 < original_confidence + min_confidence_gain:
        return False, "confidence_not_improved_enough", dict(original)
    return True, "confidence_improved", dict(candidate)


def write_document_text(path: Path, pages: list[dict[str, Any]], pdf_name: str) -> None:
    lines = [f"# {pdf_name}", ""]
    for page in pages:
        lines.extend([f"## Page {page['page_num']}", "", str(page.get("text") or "").strip(), ""])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def reocr_document_group(
    source_file: str,
    targets: list[ReocrTarget],
    *,
    raw_dir: Path,
    render_scale: float,
    language: str,
    psm: int,
    min_confidence_gain: float,
    min_char_ratio: float,
) -> list[dict[str, Any]]:
    import fitz

    pdf_path = raw_dir / source_file
    if not pdf_path.exists():
        raise FileNotFoundError(f"source PDF not found: {pdf_path}")

    results: list[dict[str, Any]] = []
    doc = fitz.open(pdf_path)
    for target in sorted(targets, key=lambda item: item.page_num):
        started = time.perf_counter()
        original = dict(target.original_page)
        try:
            candidate = ocr_page_tesseract(doc.load_page(target.page_num - 1), render_scale, language, psm)
            candidate = {
                "source_file": source_file,
                "page_num": target.page_num,
                **candidate,
                "elapsed_s": round(time.perf_counter() - started, 3),
                "status": "ok",
            }
            accepted, reason, chosen = choose_page_result(
                original,
                candidate,
                min_confidence_gain=min_confidence_gain,
                min_char_ratio=min_char_ratio,
            )
            chosen["source_file"] = source_file
            chosen["page_num"] = target.page_num
            chosen["status"] = chosen.get("status") or "ok"
            chosen["reocr"] = {
                "attempted": True,
                "accepted": accepted,
                "reason": reason,
                "original_avg_confidence": round(float(original.get("avg_confidence") or 0.0), 4),
                "candidate_avg_confidence": round(float(candidate.get("avg_confidence") or 0.0), 4),
                "original_char_count": int(original.get("char_count") or 0),
                "candidate_char_count": int(candidate.get("char_count") or 0),
                "render_scale": render_scale,
                "engine": "tesseract",
                "elapsed_s": candidate["elapsed_s"],
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            results.append(
                {
                    "source_file": source_file,
                    "page_num": target.page_num,
                    "accepted": accepted,
                    "reason": reason,
                    "replacement_page": chosen,
                    "original_avg_confidence": float(original.get("avg_confidence") or 0.0),
                    "candidate_avg_confidence": float(candidate.get("avg_confidence") or 0.0),
                    "original_char_count": int(original.get("char_count") or 0),
                    "candidate_char_count": int(candidate.get("char_count") or 0),
                    "elapsed_s": candidate["elapsed_s"],
                }
            )
        except Exception as exc:
            original["reocr"] = {
                "attempted": True,
                "accepted": False,
                "reason": "reocr_failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "render_scale": render_scale,
                "engine": "tesseract",
                "elapsed_s": round(time.perf_counter() - started, 3),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            results.append(
                {
                    "source_file": source_file,
                    "page_num": target.page_num,
                    "accepted": False,
                    "reason": "reocr_failed",
                    "replacement_page": original,
                    "original_avg_confidence": float(original.get("avg_confidence") or 0.0),
                    "candidate_avg_confidence": 0.0,
                    "original_char_count": int(original.get("char_count") or 0),
                    "candidate_char_count": 0,
                    "elapsed_s": original["reocr"]["elapsed_s"],
                    "error": str(exc),
                }
            )
        if len(results) % 20 == 0 or len(results) == len(targets):
            print(
                json.dumps(
                    {
                        "event": "reocr_doc_progress",
                        "source_file": source_file,
                        "pages_done": len(results),
                        "target_pages": len(targets),
                        "accepted": sum(1 for row in results if row["accepted"]),
                    },
                    ensure_ascii=False,
                )
            )
    return results


def write_reocr_report(
    *,
    report_stem: str,
    output_root: Path,
    threshold: float,
    render_scale: float,
    targets: list[ReocrTarget],
    results: list[dict[str, Any]],
    copy_to_human_dir: bool,
) -> dict[str, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    accepted = [row for row in results if row["accepted"]]
    failed = [row for row in results if row["reason"] == "reocr_failed"]
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "output_root": str(output_root),
        "threshold": threshold,
        "render_scale": render_scale,
        "target_pages": len(targets),
        "attempted_pages": len(results),
        "accepted_pages": len(accepted),
        "failed_pages": len(failed),
        "avg_confidence_before": round(
            sum(float(row["original_avg_confidence"]) for row in results) / max(len(results), 1),
            4,
        ),
        "avg_confidence_candidate": round(
            sum(float(row["candidate_avg_confidence"]) for row in results) / max(len(results), 1),
            4,
        ),
        "avg_confidence_after_accepted_only": round(
            sum(float(row["candidate_avg_confidence"]) for row in accepted) / max(len(accepted), 1),
            4,
        ),
        "results": [
            {
                key: row.get(key)
                for key in [
                    "source_file",
                    "page_num",
                    "accepted",
                    "reason",
                    "original_avg_confidence",
                    "candidate_avg_confidence",
                    "original_char_count",
                    "candidate_char_count",
                    "elapsed_s",
                    "error",
                ]
            }
            for row in results
        ],
    }

    json_path = REPORT_DIR / f"{report_stem}.json"
    md_path = REPORT_DIR / f"{report_stem}.md"
    csv_path = REPORT_DIR / f"{report_stem}.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_file",
                "page_num",
                "accepted",
                "reason",
                "original_avg_confidence",
                "candidate_avg_confidence",
                "original_char_count",
                "candidate_char_count",
                "elapsed_s",
                "error",
            ],
        )
        writer.writeheader()
        for row in report["results"]:
            writer.writerow(row)

    lines = [
        "# 低置信度页高分辨率重识别报告",
        "",
        f"- 生成时间：`{report['generated_at']}`",
        f"- 输出目录：`{output_root}`",
        f"- 低置信度阈值：`{threshold}`",
        f"- 高分辨率渲染比例：`{render_scale}`",
        "",
        "## 结果",
        "",
        f"- 需要重识别页：{report['target_pages']}",
        f"- 已尝试页：{report['attempted_pages']}",
        f"- 接受替换页：{report['accepted_pages']}",
        f"- 失败页：{report['failed_pages']}",
        f"- 重识别前平均置信度：{report['avg_confidence_before']}",
        f"- 高分辨率候选平均置信度：{report['avg_confidence_candidate']}",
        "",
        "## 说明",
        "",
        "只在高分辨率 OCR 的置信度明显更高、且没有丢掉大量文本时替换原页；否则保留原页，并记录原因。",
        "",
        "## 前 30 条结果",
        "",
        "| 文件 | 页码 | 是否替换 | 原置信度 | 新置信度 | 原字数 | 新字数 | 原因 |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report["results"][:30]:
        source = " ".join(str(row["source_file"]).split())[:36].replace("|", "\\|")
        lines.append(
            f"| {source} | {row['page_num']} | {row['accepted']} | "
            f"{row['original_avg_confidence']:.4f} | {row['candidate_avg_confidence']:.4f} | "
            f"{row['original_char_count']} | {row['candidate_char_count']} | {row['reason']} |"
        )
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    copied: dict[str, Path] = {}
    if copy_to_human_dir:
        HUMAN_DIR.mkdir(parents=True, exist_ok=True)
        copied["human_md"] = HUMAN_DIR / "低置信度页高分辨率重识别报告.md"
        copied["human_json"] = HUMAN_DIR / "低置信度页高分辨率重识别报告.json"
        copied["human_csv"] = HUMAN_DIR / "低置信度页高分辨率重识别明细.csv"
        shutil.copy2(md_path, copied["human_md"])
        shutil.copy2(json_path, copied["human_json"])
        shutil.copy2(csv_path, copied["human_csv"])

    paths = {"md": md_path, "json": json_path, "csv": csv_path}
    paths.update(copied)
    return paths


def build_refined_output(
    *,
    input_root: Path,
    output_root: Path,
    results: list[dict[str, Any]],
    threshold: float,
    render_scale: float,
) -> None:
    replacements = {
        (row["source_file"], int(row["page_num"])): row["replacement_page"]
        for row in results
    }
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    for manifest_path in sorted(input_root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_file = str(manifest["source_file"])
        pages_jsonl = manifest_pages_path(manifest_path, manifest)
        pages = []
        reocr_attempted = 0
        reocr_accepted = 0
        for page in load_jsonl(pages_jsonl):
            key = (source_file, int(page["page_num"]))
            refined_page = replacements.get(key, page)
            if refined_page.get("reocr", {}).get("attempted"):
                reocr_attempted += 1
            if refined_page.get("reocr", {}).get("accepted"):
                reocr_accepted += 1
            pages.append(refined_page)

        output_doc_dir = output_root / manifest_path.parent.name
        output_doc_dir.mkdir(parents=True, exist_ok=True)
        output_pages_jsonl = output_doc_dir / "pages.jsonl"
        output_document_txt = output_doc_dir / "document.txt"
        output_manifest = output_doc_dir / "manifest.json"
        write_jsonl(output_pages_jsonl, pages)
        write_document_text(output_document_txt, pages, source_file)

        new_manifest = dict(manifest)
        new_manifest.update(
            {
                "output_dir": str(output_doc_dir),
                "pages_jsonl": str(output_pages_jsonl),
                "document_txt": str(output_document_txt),
                "refined_from": str(manifest_path.parent),
                "refinement": "low_confidence_high_resolution_reocr",
                "reocr_threshold": threshold,
                "reocr_render_scale": render_scale,
                "reocr_attempted_pages": reocr_attempted,
                "reocr_accepted_pages": reocr_accepted,
                "pages_with_text": sum(1 for page in pages if int(page.get("char_count") or 0) > 0),
                "char_count": sum(int(page.get("char_count") or 0) for page in pages),
                "line_count": sum(int(page.get("line_count") or 0) for page in pages),
                "error_count": sum(1 for page in pages if page.get("status") == "error"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        output_manifest.write_text(json.dumps(new_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-OCR low-confidence pages at higher render resolution.")
    parser.add_argument("--input-root", default=str(DEFAULT_INPUT_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--threshold", type=float, default=0.45)
    parser.add_argument("--render-scale", type=float, default=3.0)
    parser.add_argument("--tesseract-lang", default="chi_sim+eng")
    parser.add_argument("--tesseract-psm", type=int, default=6)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--include-empty", action="store_true")
    parser.add_argument("--min-confidence-gain", type=float, default=0.03)
    parser.add_argument("--min-char-ratio", type=float, default=0.6)
    parser.add_argument("--report-stem", default="ocr_low_confidence_highres_reocr")
    parser.add_argument("--copy-to-human-dir", action="store_true")
    args = parser.parse_args()

    input_root = resolve_repo_path(args.input_root)
    output_root = resolve_repo_path(args.output_root)
    raw_dir = RAW_DIR
    targets = collect_reocr_targets(input_root, threshold=args.threshold, include_empty=args.include_empty)
    if args.max_pages:
        targets = targets[: args.max_pages]

    by_source: dict[str, list[ReocrTarget]] = defaultdict(list)
    for target in targets:
        by_source[target.source_file].append(target)

    print(
        json.dumps(
            {
                "event": "reocr_start",
                "targets": len(targets),
                "documents": len(by_source),
                "threshold": args.threshold,
                "render_scale": args.render_scale,
                "workers": args.workers,
            },
            ensure_ascii=False,
        )
    )

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                reocr_document_group,
                source_file,
                doc_targets,
                raw_dir=raw_dir,
                render_scale=args.render_scale,
                language=args.tesseract_lang,
                psm=args.tesseract_psm,
                min_confidence_gain=args.min_confidence_gain,
                min_char_ratio=args.min_char_ratio,
            ): source_file
            for source_file, doc_targets in by_source.items()
        }
        for future in as_completed(futures):
            source_file = futures[future]
            doc_results = future.result()
            results.extend(doc_results)
            print(
                json.dumps(
                    {
                        "event": "reocr_doc_done",
                        "source_file": source_file,
                        "pages": len(doc_results),
                        "accepted": sum(1 for row in doc_results if row["accepted"]),
                    },
                    ensure_ascii=False,
                )
            )

    results.sort(key=lambda row: (str(row["source_file"]), int(row["page_num"])))
    build_refined_output(
        input_root=input_root,
        output_root=output_root,
        results=results,
        threshold=args.threshold,
        render_scale=args.render_scale,
    )
    report_paths = write_reocr_report(
        report_stem=args.report_stem,
        output_root=output_root,
        threshold=args.threshold,
        render_scale=args.render_scale,
        targets=targets,
        results=results,
        copy_to_human_dir=args.copy_to_human_dir,
    )
    print(
        json.dumps(
            {
                "event": "reocr_done",
                "targets": len(targets),
                "attempted": len(results),
                "accepted": sum(1 for row in results if row["accepted"]),
                "output_root": str(output_root),
                "reports": {key: str(value) for key, value in report_paths.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
