from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
import time
from collections import Counter, defaultdict
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
DEFAULT_INPUT_ROOT = REPO_ROOT / "data_pipeline" / "ocr_layout_aware_tesseract_highres_refined_pass2" / "tsinghua_gas_turbine_books"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data_pipeline" / "ocr_layout_aware_tesseract_night_corrected" / "tsinghua_gas_turbine_books"
REPORT_DIR = REPO_ROOT / "data_pipeline" / "reports"
HUMAN_DIR = REPO_ROOT / "00_项目成果总览_先看这里" / "02_OCR结果_13本扫描PDF" / "04_夜间总检矫正"
LOG_DIR = REPO_ROOT / "observability" / "logs" / "ocr_night_correction"

PUNCTUATION = set("。！？；：，、,.!?;:)")
MOJIBAKE_MARKERS = ("�", "\x00", "锟", "�")


@dataclass(frozen=True)
class NightTarget:
    source_file: str
    doc_dir_name: str
    manifest_path: Path
    pages_jsonl: Path
    page_num: int
    flags: tuple[str, ...]
    priority: int
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


def is_cjk(char: str) -> bool:
    code = ord(char)
    return 0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF or 0xF900 <= code <= 0xFAFF


def line_texts(page: dict[str, Any]) -> list[str]:
    lines = page.get("lines") or []
    if lines and isinstance(lines[0], dict):
        return [str(item.get("text") or "") for item in lines]
    if lines:
        return [str(item) for item in lines]
    return str(page.get("text") or "").splitlines()


def page_confidence(page: dict[str, Any]) -> float:
    avg = float(page.get("avg_confidence") or 0.0)
    if avg:
        return avg
    values = [
        float(line.get("confidence") or 0.0)
        for line in page.get("lines") or []
        if isinstance(line, dict)
    ]
    return sum(values) / len(values) if values else 0.0


def page_flags(page: dict[str, Any], *, low_conf_threshold: float = 0.45) -> list[str]:
    text = str(page.get("text") or "")
    char_count = int(page.get("char_count") or len(text))
    texts = line_texts(page)
    line_count = int(page.get("line_count") or len(texts))
    confidence = page_confidence(page)
    layout = page.get("layout") or {}
    layout_risk = str(layout.get("layout_order_risk") or "unknown")
    punctuation_count = sum(1 for char in text if char in PUNCTUATION)
    short_lines = sum(1 for line in texts if len(line.strip()) <= 2)
    short_line_ratio = short_lines / max(line_count, 1)

    flags: list[str] = []
    if not text.strip() or char_count <= 0:
        flags.append("无文字")
    if 0 < char_count < 30:
        flags.append("文字极短")
    if confidence and confidence < low_conf_threshold:
        flags.append("平均置信度偏低")
    if char_count > 300 and punctuation_count < 3:
        flags.append("长文本但标点很少")
    if line_count >= 10 and short_line_ratio > 0.4:
        flags.append("短行过多")
    if any(marker in text for marker in MOJIBAKE_MARKERS):
        flags.append("疑似乱码")
    if layout_risk in {"high", "medium"}:
        flags.append(f"版面顺序{layout_risk}")
    return flags


def target_priority(flags: list[str]) -> int:
    score = 0
    weights = {
        "无文字": 1000,
        "平均置信度偏低": 650,
        "文字极短": 500,
        "疑似乱码": 450,
        "长文本但标点很少": 320,
        "短行过多": 260,
        "版面顺序high": 120,
        "版面顺序medium": 80,
    }
    for flag in flags:
        score += weights.get(flag, 0)
    return score


def collect_targets(
    input_root: str | Path,
    *,
    low_conf_threshold: float,
    include_layout_risk: bool,
    layout_only_limit: int,
) -> list[NightTarget]:
    root = resolve_repo_path(input_root)
    severe: list[NightTarget] = []
    layout_only: list[NightTarget] = []
    for manifest_path in sorted(root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pages_jsonl = manifest_pages_path(manifest_path, manifest)
        for page in load_jsonl(pages_jsonl):
            flags = page_flags(page, low_conf_threshold=low_conf_threshold)
            if not flags:
                continue
            if not include_layout_risk and all(flag.startswith("版面顺序") for flag in flags):
                continue
            target = NightTarget(
                source_file=str(page.get("source_file") or manifest["source_file"]),
                doc_dir_name=manifest_path.parent.name,
                manifest_path=manifest_path,
                pages_jsonl=pages_jsonl,
                page_num=int(page["page_num"]),
                flags=tuple(flags),
                priority=target_priority(flags),
                original_page=page,
            )
            if all(flag.startswith("版面顺序") for flag in flags):
                layout_only.append(target)
            else:
                severe.append(target)

    severe.sort(key=lambda item: (-item.priority, item.source_file, item.page_num))
    layout_only.sort(key=lambda item: (-item.priority, item.source_file, item.page_num))
    if layout_only_limit > 0:
        layout_only = layout_only[:layout_only_limit]
    return severe + layout_only


def text_quality_score(page: dict[str, Any]) -> float:
    text = str(page.get("text") or "")
    char_count = int(page.get("char_count") or len(text))
    confidence = page_confidence(page)
    non_space = [char for char in text if not char.isspace()]
    cjk_count = sum(1 for char in non_space if is_cjk(char))
    punctuation_count = sum(1 for char in text if char in PUNCTUATION)
    strange_count = sum(1 for char in text if ord(char) < 32 and char not in "\n\t")
    mojibake_hits = sum(text.count(marker) for marker in MOJIBAKE_MARKERS)
    texts = line_texts(page)
    line_count = int(page.get("line_count") or len(texts))
    short_lines = sum(1 for line in texts if len(line.strip()) <= 2)
    short_line_ratio = short_lines / max(line_count, 1)
    cjk_ratio = cjk_count / max(len(non_space), 1)
    symbol_count = sum(1 for char in non_space if not (char.isalnum() or is_cjk(char) or char in PUNCTUATION))
    symbol_ratio = symbol_count / max(len(non_space), 1)

    score = confidence * 100
    score += min(char_count, 1400) / 25
    score += cjk_ratio * 25
    score += min(punctuation_count, 24) * 0.45
    score -= short_line_ratio * 12
    score -= max(0.0, symbol_ratio - 0.35) * 80
    score -= mojibake_hits * 12
    score -= strange_count * 10
    if char_count == 0:
        score -= 100
    if len(non_space) < 20:
        score -= 10
    return round(score, 4)


def choose_best_candidate(
    original: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    min_score_gain: float = 8.0,
    min_char_ratio: float = 0.55,
) -> tuple[bool, str, dict[str, Any], dict[str, float]]:
    original_score = text_quality_score(original)
    original_chars = int(original.get("char_count") or len(str(original.get("text") or "")))
    scored = [(text_quality_score(candidate), candidate) for candidate in candidates]
    if not scored:
        return False, "no_candidate", dict(original), {"original": original_score, "best": original_score}
    best_score, best = max(scored, key=lambda item: item[0])
    best_chars = int(best.get("char_count") or len(str(best.get("text") or "")))
    if best_chars <= 0:
        return False, "candidate_empty", dict(original), {"original": original_score, "best": best_score}
    if original_chars >= 60 and best_chars < int(original_chars * min_char_ratio):
        return False, "candidate_lost_too_much_text", dict(original), {"original": original_score, "best": best_score}
    if best_score < original_score + min_score_gain:
        return False, "quality_not_improved_enough", dict(original), {"original": original_score, "best": best_score}
    return True, "quality_improved", dict(best), {"original": original_score, "best": best_score}


def strategies_for_flags(flags: tuple[str, ...]) -> list[tuple[float, int]]:
    severe = any(
        flag in flags
        for flag in ("无文字", "平均置信度偏低", "文字极短", "疑似乱码", "长文本但标点很少", "短行过多")
    )
    if severe:
        strategies = [(4.5, 6), (4.5, 4), (4.0, 3), (4.0, 11)]
        if "无文字" in flags or "文字极短" in flags:
            strategies.append((5.0, 6))
        return strategies
    return [(4.0, 4), (4.0, 6)]


def completed_results(path: Path) -> dict[tuple[str, int], dict[str, Any]]:
    if not path.exists():
        return {}
    results: dict[tuple[str, int], dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            results[(str(row["source_file"]), int(row["page_num"]))] = row
    return results


def write_log(path: Path, event: str, **fields: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": datetime.now().isoformat(timespec="seconds"), "event": event, **fields}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(json.dumps(payload, ensure_ascii=False))


def process_document_targets(
    source_file: str,
    targets: list[NightTarget],
    *,
    render_lang: str,
    min_score_gain: float,
    min_char_ratio: float,
    log_path: Path,
) -> list[dict[str, Any]]:
    import fitz

    pdf_path = RAW_DIR / source_file
    if not pdf_path.exists():
        raise FileNotFoundError(f"source PDF not found: {pdf_path}")
    doc = fitz.open(pdf_path)
    rows: list[dict[str, Any]] = []
    for index, target in enumerate(sorted(targets, key=lambda item: (-item.priority, item.page_num)), start=1):
        started = time.perf_counter()
        candidates: list[dict[str, Any]] = []
        candidate_errors: list[dict[str, str]] = []
        for scale, psm in strategies_for_flags(target.flags):
            try:
                candidate = ocr_page_tesseract(doc.load_page(target.page_num - 1), scale, render_lang, psm)
                candidate = {
                    "source_file": source_file,
                    "page_num": target.page_num,
                    **candidate,
                    "status": "ok",
                    "night_strategy": {"render_scale": scale, "psm": psm},
                }
                candidates.append(candidate)
            except Exception as exc:
                candidate_errors.append(
                    {
                        "render_scale": str(scale),
                        "psm": str(psm),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )

        accepted, reason, chosen, scores = choose_best_candidate(
            target.original_page,
            candidates,
            min_score_gain=min_score_gain,
            min_char_ratio=min_char_ratio,
        )
        chosen["source_file"] = source_file
        chosen["page_num"] = target.page_num
        chosen["status"] = chosen.get("status") or target.original_page.get("status") or "ok"
        chosen["night_correction"] = {
            "attempted": True,
            "accepted": accepted,
            "reason": reason,
            "flags": list(target.flags),
            "candidate_count": len(candidates),
            "candidate_errors": candidate_errors,
            "original_score": scores["original"],
            "best_score": scores["best"],
            "original_avg_confidence": round(page_confidence(target.original_page), 4),
            "chosen_avg_confidence": round(page_confidence(chosen), 4),
            "original_char_count": int(target.original_page.get("char_count") or 0),
            "chosen_char_count": int(chosen.get("char_count") or 0),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        row = {
            "source_file": source_file,
            "page_num": target.page_num,
            "flags": list(target.flags),
            "accepted": accepted,
            "reason": reason,
            "original_score": scores["original"],
            "best_score": scores["best"],
            "original_avg_confidence": round(page_confidence(target.original_page), 4),
            "chosen_avg_confidence": round(page_confidence(chosen), 4),
            "original_char_count": int(target.original_page.get("char_count") or 0),
            "chosen_char_count": int(chosen.get("char_count") or 0),
            "candidate_count": len(candidates),
            "elapsed_s": round(time.perf_counter() - started, 3),
            "replacement_page": chosen,
        }
        rows.append(row)
        if index % 10 == 0 or index == len(targets):
            write_log(
                log_path,
                "doc_progress",
                source_file=source_file,
                done=index,
                total=len(targets),
                accepted=sum(1 for item in rows if item["accepted"]),
            )
    return rows


def write_document_text(path: Path, pages: list[dict[str, Any]], pdf_name: str) -> None:
    lines = [f"# {pdf_name}", ""]
    for page in pages:
        lines.extend([f"## Page {page['page_num']}", "", str(page.get("text") or "").strip(), ""])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_output(input_root: Path, output_root: Path, results: dict[tuple[str, int], dict[str, Any]]) -> None:
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    for manifest_path in sorted(input_root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_file = str(manifest["source_file"])
        pages_jsonl = manifest_pages_path(manifest_path, manifest)
        pages: list[dict[str, Any]] = []
        attempted = 0
        accepted = 0
        for page in load_jsonl(pages_jsonl):
            key = (source_file, int(page["page_num"]))
            row = results.get(key)
            if row:
                attempted += 1
                if row.get("accepted"):
                    accepted += 1
                pages.append(row["replacement_page"])
            else:
                pages.append(page)

        doc_dir = output_root / manifest_path.parent.name
        doc_dir.mkdir(parents=True, exist_ok=True)
        out_pages = doc_dir / "pages.jsonl"
        out_text = doc_dir / "document.txt"
        out_manifest = doc_dir / "manifest.json"
        write_jsonl(out_pages, pages)
        write_document_text(out_text, pages, source_file)
        new_manifest = dict(manifest)
        new_manifest.update(
            {
                "output_dir": str(doc_dir),
                "pages_jsonl": str(out_pages),
                "document_txt": str(out_text),
                "refined_from": str(manifest_path.parent),
                "refinement": "night_multi_strategy_ocr_correction",
                "night_attempted_pages": attempted,
                "night_accepted_pages": accepted,
                "pages_with_text": sum(1 for page in pages if int(page.get("char_count") or 0) > 0),
                "char_count": sum(int(page.get("char_count") or 0) for page in pages),
                "line_count": sum(int(page.get("line_count") or 0) for page in pages),
                "error_count": sum(1 for page in pages if page.get("status") == "error"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        out_manifest.write_text(json.dumps(new_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_reports(
    *,
    report_stem: str,
    output_root: Path,
    targets: list[NightTarget],
    results: dict[tuple[str, int], dict[str, Any]],
    copy_to_human_dir: bool,
) -> dict[str, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows = list(results.values())
    accepted = [row for row in rows if row.get("accepted")]
    flag_counter: Counter[str] = Counter(flag for target in targets for flag in target.flags)
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "output_root": str(output_root),
        "target_pages": len(targets),
        "attempted_pages": len(rows),
        "accepted_pages": len(accepted),
        "flag_counts": dict(flag_counter),
        "avg_original_score": round(sum(float(row["original_score"]) for row in rows) / max(len(rows), 1), 4),
        "avg_best_score": round(sum(float(row["best_score"]) for row in rows) / max(len(rows), 1), 4),
        "avg_original_confidence": round(sum(float(row["original_avg_confidence"]) for row in rows) / max(len(rows), 1), 4),
        "avg_chosen_confidence": round(sum(float(row["chosen_avg_confidence"]) for row in rows) / max(len(rows), 1), 4),
        "results": [
            {
                key: row.get(key)
                for key in [
                    "source_file",
                    "page_num",
                    "flags",
                    "accepted",
                    "reason",
                    "original_score",
                    "best_score",
                    "original_avg_confidence",
                    "chosen_avg_confidence",
                    "original_char_count",
                    "chosen_char_count",
                    "candidate_count",
                    "elapsed_s",
                ]
            }
            for row in rows
        ],
    }
    json_path = REPORT_DIR / f"{report_stem}.json"
    csv_path = REPORT_DIR / f"{report_stem}.csv"
    md_path = REPORT_DIR / f"{report_stem}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_file",
                "page_num",
                "flags",
                "accepted",
                "reason",
                "original_score",
                "best_score",
                "original_avg_confidence",
                "chosen_avg_confidence",
                "original_char_count",
                "chosen_char_count",
                "candidate_count",
                "elapsed_s",
            ],
        )
        writer.writeheader()
        for row in summary["results"]:
            out = dict(row)
            out["flags"] = "、".join(out["flags"] or [])
            writer.writerow(out)

    lines = [
        "# OCR 夜间总检矫正报告",
        "",
        f"- 生成时间：`{summary['generated_at']}`",
        f"- 输出目录：`{output_root}`",
        f"- 目标风险页：{summary['target_pages']}",
        f"- 已尝试页：{summary['attempted_pages']}",
        f"- 接受替换页：{summary['accepted_pages']}",
        f"- 原平均综合分：{summary['avg_original_score']}",
        f"- 最佳候选平均综合分：{summary['avg_best_score']}",
        f"- 原平均置信度：{summary['avg_original_confidence']}",
        f"- 选择后平均置信度：{summary['avg_chosen_confidence']}",
        "",
        "## 风险类型覆盖",
        "",
    ]
    for flag, count in sorted(flag_counter.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {flag}：{count}")
    lines.extend(
        [
            "",
            "## 前 40 条明细",
            "",
            "| 文件 | 页码 | 风险 | 替换 | 原分 | 新分 | 原置信 | 新置信 | 原因 |",
            "| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in summary["results"][:40]:
        source = " ".join(str(row["source_file"]).split())[:32].replace("|", "\\|")
        flags = "、".join(row["flags"] or []).replace("|", "\\|")
        lines.append(
            f"| {source} | {row['page_num']} | {flags} | {row['accepted']} | "
            f"{row['original_score']} | {row['best_score']} | {row['original_avg_confidence']} | "
            f"{row['chosen_avg_confidence']} | {row['reason']} |"
        )
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    copied: dict[str, Path] = {}
    if copy_to_human_dir:
        HUMAN_DIR.mkdir(parents=True, exist_ok=True)
        copied["human_md"] = HUMAN_DIR / "OCR夜间总检矫正报告.md"
        copied["human_json"] = HUMAN_DIR / "OCR夜间总检矫正报告.json"
        copied["human_csv"] = HUMAN_DIR / "OCR夜间总检矫正明细.csv"
        shutil.copy2(md_path, copied["human_md"])
        shutil.copy2(json_path, copied["human_json"])
        shutil.copy2(csv_path, copied["human_csv"])

    paths = {"md": md_path, "json": json_path, "csv": csv_path}
    paths.update(copied)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a comprehensive overnight OCR risk-page correction pass.")
    parser.add_argument("--input-root", default=str(DEFAULT_INPUT_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--low-conf-threshold", type=float, default=0.45)
    parser.add_argument("--include-layout-risk", action="store_true", default=True)
    parser.add_argument("--layout-only-limit", type=int, default=0, help="0 means all layout-only pages.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-targets", type=int, default=0)
    parser.add_argument("--tesseract-lang", default="chi_sim+eng")
    parser.add_argument("--min-score-gain", type=float, default=8.0)
    parser.add_argument("--min-char-ratio", type=float, default=0.55)
    parser.add_argument("--report-stem", default="ocr_night_correction")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--copy-to-human-dir", action="store_true")
    args = parser.parse_args()

    input_root = resolve_repo_path(args.input_root)
    output_root = resolve_repo_path(args.output_root)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{args.report_stem}.jsonl"
    checkpoint_path = REPORT_DIR / f"{args.report_stem}_results.jsonl"

    targets = collect_targets(
        input_root,
        low_conf_threshold=args.low_conf_threshold,
        include_layout_risk=args.include_layout_risk,
        layout_only_limit=args.layout_only_limit,
    )
    if args.max_targets:
        targets = targets[: args.max_targets]

    existing = completed_results(checkpoint_path) if args.resume else {}
    pending = [target for target in targets if (target.source_file, target.page_num) not in existing]
    by_source: dict[str, list[NightTarget]] = defaultdict(list)
    for target in pending:
        by_source[target.source_file].append(target)

    write_log(
        log_path,
        "night_correction_start",
        input_root=str(input_root),
        output_root=str(output_root),
        targets=len(targets),
        pending=len(pending),
        completed=len(existing),
        documents=len(by_source),
        workers=args.workers,
    )

    all_results = dict(existing)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                process_document_targets,
                source_file,
                doc_targets,
                render_lang=args.tesseract_lang,
                min_score_gain=args.min_score_gain,
                min_char_ratio=args.min_char_ratio,
                log_path=log_path,
            ): source_file
            for source_file, doc_targets in by_source.items()
        }
        for future in as_completed(futures):
            source_file = futures[future]
            rows = future.result()
            with checkpoint_path.open("a", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    all_results[(row["source_file"], int(row["page_num"]))] = row
            write_log(
                log_path,
                "document_done",
                source_file=source_file,
                pages=len(rows),
                accepted=sum(1 for row in rows if row["accepted"]),
                total_done=len(all_results),
                total_targets=len(targets),
            )

    build_output(input_root, output_root, all_results)
    report_paths = write_reports(
        report_stem=args.report_stem,
        output_root=output_root,
        targets=targets,
        results=all_results,
        copy_to_human_dir=args.copy_to_human_dir,
    )
    write_log(
        log_path,
        "night_correction_done",
        targets=len(targets),
        attempted=len(all_results),
        accepted=sum(1 for row in all_results.values() if row["accepted"]),
        output_root=str(output_root),
        reports={key: str(value) for key, value in report_paths.items()},
    )
    print(
        json.dumps(
            {
                "event": "night_correction_done",
                "targets": len(targets),
                "attempted": len(all_results),
                "accepted": sum(1 for row in all_results.values() if row["accepted"]),
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
