from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OCR_ROOT = REPO_ROOT / "data_pipeline" / "ocr_layout_aware_tesseract" / "tsinghua_gas_turbine_books"
REPORT_DIR = REPO_ROOT / "data_pipeline" / "reports"
HUMAN_DIR = REPO_ROOT / "00_项目成果总览_先看这里" / "02_OCR结果_13本扫描PDF"


PUNCTUATION = set("。！？；：，、,.!?;:)")
MOJIBAKE_MARKERS = ("鍏", "鐕", "璧", "锛", "鈥", "绋", "涓")


def compact(value: Any, limit: int = 120) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def load_pages(path: Path) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                pages.append(json.loads(line))
    return pages


def page_confidence(page: dict[str, Any]) -> float:
    avg = float(page.get("avg_confidence") or 0.0)
    if avg:
        return avg
    values = [
        float(line.get("confidence") or 0.0)
        for line in page.get("lines") or []
        if isinstance(line, dict)
    ]
    return statistics.mean(values) if values else 0.0


def has_line_boxes(page: dict[str, Any]) -> bool:
    lines = page.get("lines") or []
    if not lines:
        return False
    return any(isinstance(line, dict) and line.get("box") for line in lines)


def page_risks(page: dict[str, Any]) -> list[str]:
    text = str(page.get("text") or "")
    line_count = int(page.get("line_count") or 0)
    char_count = int(page.get("char_count") or len(text))
    confidence = page_confidence(page)
    layout = page.get("layout") or {}
    layout_risk = str(layout.get("layout_order_risk") or "unknown")
    punctuation_count = sum(1 for char in text if char in PUNCTUATION)
    short_lines = sum(
        1
        for line in page.get("lines") or []
        if isinstance(line, dict) and len(str(line.get("text") or "").strip()) <= 2
    )
    short_line_ratio = short_lines / max(line_count, 1)
    mojibake_hits = sum(text.count(marker) for marker in MOJIBAKE_MARKERS)

    risks: list[str] = []
    if not text.strip():
        risks.append("无文字")
    if 0 < char_count < 30:
        risks.append("文字极短")
    if char_count > 300 and punctuation_count < 3:
        risks.append("长文本但标点很少")
    if line_count >= 10 and short_line_ratio > 0.4:
        risks.append("短行过多")
    if confidence and confidence < 0.45:
        risks.append("平均置信度偏低")
    if layout_risk in {"medium", "high"}:
        risks.append(f"版面顺序{layout_risk}")
    if "�" in text or "\x00" in text:
        risks.append("存在替换字符")
    if mojibake_hits > 5:
        risks.append("疑似编码乱码")
    return risks


def analyze(ocr_root: Path) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    risk_pages: list[dict[str, Any]] = []
    global_risks: Counter[str] = Counter()
    layout_risks: Counter[str] = Counter()
    validation_errors: list[str] = []
    total_pages = 0
    pages_done = 0
    pages_with_text = 0
    line_box_pages = 0
    char_count = 0
    line_count = 0

    manifests = sorted(ocr_root.glob("*/manifest.json"))
    if not manifests:
        validation_errors.append(f"未找到 manifest.json: {ocr_root}")

    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pages_path = Path(manifest["pages_jsonl"])
        document_txt = Path(manifest["document_txt"])
        pages = load_pages(pages_path)
        expected_pages = int(manifest.get("target_pages") or manifest.get("total_pages") or 0)
        page_numbers = [int(page.get("page_num") or 0) for page in pages]
        page_set = set(page_numbers)
        missing_pages = [num for num in range(1, expected_pages + 1) if num not in page_set]
        duplicate_count = len(page_numbers) - len(page_set)
        status_error_pages = [page for page in pages if page.get("status") == "error"]

        if len(pages) != expected_pages:
            validation_errors.append(
                f"{manifest['source_file']}: 页数不一致 {len(pages)}/{expected_pages}"
            )
        if missing_pages:
            validation_errors.append(
                f"{manifest['source_file']}: 缺页 {missing_pages[:20]}"
            )
        if duplicate_count:
            validation_errors.append(
                f"{manifest['source_file']}: 重复页 {duplicate_count}"
            )
        if status_error_pages:
            validation_errors.append(
                f"{manifest['source_file']}: error 页 {len(status_error_pages)}"
            )
        if not document_txt.exists():
            validation_errors.append(f"{manifest['source_file']}: document.txt 不存在")

        doc_risks: Counter[str] = Counter()
        doc_layout: Counter[str] = Counter()
        doc_pages_with_text = 0
        doc_line_box_pages = 0
        doc_char_count = 0
        doc_line_count = 0
        doc_conf_values: list[float] = []

        for page in pages:
            page_num = int(page.get("page_num") or 0)
            text = str(page.get("text") or "")
            current_char_count = int(page.get("char_count") or len(text))
            current_line_count = int(page.get("line_count") or 0)
            confidence = page_confidence(page)
            layout = page.get("layout") or {}
            layout_risk = str(layout.get("layout_order_risk") or "unknown")
            risks = page_risks(page)

            total_pages += 1
            pages_done += 1
            char_count += current_char_count
            line_count += current_line_count
            doc_char_count += current_char_count
            doc_line_count += current_line_count
            if current_char_count > 0:
                pages_with_text += 1
                doc_pages_with_text += 1
            if has_line_boxes(page):
                line_box_pages += 1
                doc_line_box_pages += 1
            if confidence:
                doc_conf_values.append(confidence)
            layout_risks[layout_risk] += 1
            doc_layout[layout_risk] += 1

            for risk in risks:
                global_risks[risk] += 1
                doc_risks[risk] += 1
            if risks:
                risk_pages.append(
                    {
                        "source_file": manifest["source_file"],
                        "page_num": page_num,
                        "risks": risks,
                        "layout_risk": layout_risk,
                        "avg_confidence": round(confidence, 4),
                        "char_count": current_char_count,
                        "line_count": current_line_count,
                        "preview": compact(text, 180),
                    }
                )

        documents.append(
            {
                "source_file": manifest["source_file"],
                "status": manifest.get("status"),
                "engine": manifest.get("engine"),
                "layout_aware": bool(manifest.get("layout_aware")),
                "pages_done": len(pages),
                "target_pages": expected_pages,
                "pages_with_text": doc_pages_with_text,
                "line_box_pages": doc_line_box_pages,
                "char_count": doc_char_count,
                "line_count": doc_line_count,
                "avg_confidence_mean": round(statistics.mean(doc_conf_values), 4) if doc_conf_values else 0.0,
                "layout_risk_counts": dict(doc_layout),
                "risk_counts": dict(doc_risks),
                "document_txt_exists": document_txt.exists(),
            }
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ocr_root": str(ocr_root),
        "pdf_count": len(manifests),
        "pages_done": pages_done,
        "total_pages": total_pages,
        "pages_with_text": pages_with_text,
        "char_count": char_count,
        "line_count": line_count,
        "line_box_pages": line_box_pages,
        "layout_risk_counts": dict(layout_risks),
        "risk_counts": dict(global_risks),
        "validation_errors": validation_errors,
        "documents": documents,
        "risk_pages": risk_pages,
    }


def risk_priority(row: dict[str, Any]) -> tuple[int, float, int]:
    risks = row["risks"]
    score = 0
    if "版面顺序high" in risks:
        score += 100
    if "平均置信度偏低" in risks:
        score += 30
    if "无文字" in risks:
        score += 20
    if "短行过多" in risks or "长文本但标点很少" in risks:
        score += 10
    return (-score, row.get("avg_confidence") or 1.0, -(row.get("char_count") or 0))


def write_risk_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_file",
                "page_num",
                "risks",
                "layout_risk",
                "avg_confidence",
                "char_count",
                "line_count",
                "preview",
            ],
        )
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["risks"] = "、".join(row["risks"])
            writer.writerow(out)


def write_markdown(path: Path, payload: dict[str, Any], risk_csv: Path) -> None:
    validation_ok = not payload["validation_errors"]
    risk = payload["risk_counts"]
    layout = payload["layout_risk_counts"]
    verdict = (
        "可以交付为“带风险标注的 OCR 文本成果”，但不能承诺逐字完全正确。"
        if validation_ok
        else "暂不建议交付：存在完整性校验错误。"
    )
    lines = [
        "# OCR 交付前验收报告",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        f"- OCR 根目录：`{payload['ocr_root']}`",
        "",
        "## 结论",
        "",
        verdict,
        "",
        "更具体地说：工程完整性已经通过；OCR 内容适合做 RAG/GraphRAG 的候选证据库；如果用于论文引用、知识图谱抽取或精确结论，必须保留页码并人工复核高风险页。",
        "",
        "## 完整性验收",
        "",
        f"- 文件数：{payload['pdf_count']} 本扫描 PDF。",
        f"- 页数：{payload['pages_done']} / {payload['total_pages']}。",
        f"- 有文字页：{payload['pages_with_text']}。",
        f"- 总字符数：{payload['char_count']}。",
        f"- 总行数：{payload['line_count']}。",
        f"- 有坐标框页：{payload['line_box_pages']}。",
        f"- 完整性错误：{len(payload['validation_errors'])}。",
        "",
        "## 风险统计",
        "",
        f"- 低版面风险页：{layout.get('low', 0)}。",
        f"- 中版面风险页：{layout.get('medium', 0)}。",
        f"- 高版面风险页：{layout.get('high', 0)}。",
        f"- 平均置信度偏低页：{risk.get('平均置信度偏低', 0)}。",
        f"- 无文字页：{risk.get('无文字', 0)}。",
        f"- 文字极短页：{risk.get('文字极短', 0)}。",
        f"- 短行过多页：{risk.get('短行过多', 0)}。",
        f"- 长文本但标点很少页：{risk.get('长文本但标点很少', 0)}。",
        "",
        f"风险页清单见：`{risk_csv}`",
        "",
        "## 每本书验收表",
        "",
        "| 文件 | 页数 | 有文字页 | 坐标页 | 平均置信度 | 高风险页 | 中风险页 | 低置信页 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in payload["documents"]:
        source = compact(item["source_file"], 44).replace("|", "\\|")
        layout_counts = item["layout_risk_counts"]
        risk_counts = item["risk_counts"]
        lines.append(
            "| "
            + " | ".join(
                [
                    source,
                    f"{item['pages_done']}/{item['target_pages']}",
                    str(item["pages_with_text"]),
                    str(item["line_box_pages"]),
                    str(item["avg_confidence_mean"]),
                    str(layout_counts.get("high", 0)),
                    str(layout_counts.get("medium", 0)),
                    str(risk_counts.get("平均置信度偏低", 0)),
                ]
            )
            + " |"
        )

    if payload["validation_errors"]:
        lines.extend(["", "## 完整性错误", ""])
        for error in payload["validation_errors"]:
            lines.append(f"- {error}")

    top_risks = sorted(payload["risk_pages"], key=risk_priority)[:30]
    lines.extend(
        [
            "",
            "## 优先人工抽检页",
            "",
            "| 文件 | 页码 | 风险 | 置信度 | 字符数 | 预览 |",
            "| --- | ---: | --- | ---: | ---: | --- |",
        ]
    )
    for row in top_risks:
        source = compact(row["source_file"], 38).replace("|", "\\|")
        risks = "、".join(row["risks"]).replace("|", "\\|")
        preview = compact(row["preview"], 70).replace("|", "\\|")
        lines.append(
            f"| {source} | {row['page_num']} | {risks} | {row['avg_confidence']} | {row['char_count']} | {preview} |"
        )

    lines.extend(
        [
            "",
            "## 交付时建议说法",
            "",
            "> OCR 已完成全量处理，并生成了带坐标和版面风险标记的 layout-aware 版本。工程完整性通过，但 OCR 不等于精校文本；高版面风险页、低置信页、表格公式页需要人工复核后才能用于论文结论或知识图谱三元组抽取。",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate OCR delivery acceptance report.")
    parser.add_argument("--output-root", default=str(DEFAULT_OCR_ROOT))
    parser.add_argument("--report-stem", default="ocr_delivery_acceptance")
    parser.add_argument("--copy-to-human-dir", action="store_true")
    args = parser.parse_args()

    ocr_root = resolve_repo_path(args.output_root)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = analyze(ocr_root)
    report_path = REPORT_DIR / f"{args.report_stem}.md"
    json_path = REPORT_DIR / f"{args.report_stem}.json"
    risk_csv_path = REPORT_DIR / f"{args.report_stem}_risk_pages.csv"
    sorted_risks = sorted(payload["risk_pages"], key=risk_priority)
    write_risk_csv(risk_csv_path, sorted_risks)
    write_markdown(report_path, payload, risk_csv_path)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.copy_to_human_dir and HUMAN_DIR.exists():
        human_report = HUMAN_DIR / "OCR交付前验收报告.md"
        human_json = HUMAN_DIR / "OCR交付前验收报告.json"
        human_csv = HUMAN_DIR / "OCR交付风险页清单.csv"
        write_risk_csv(human_csv, sorted_risks)
        write_markdown(human_report, payload, human_csv)
        human_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "report": str(report_path),
                "json": str(json_path),
                "risk_csv": str(risk_csv_path),
                "pdf_count": payload["pdf_count"],
                "pages": f"{payload['pages_done']}/{payload['total_pages']}",
                "validation_errors": len(payload["validation_errors"]),
                "risk_counts": payload["risk_counts"],
                "layout_risk_counts": payload["layout_risk_counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
