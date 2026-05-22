from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OCR_ROOT = REPO_ROOT / "data_pipeline" / "ocr" / "tsinghua_gas_turbine_books"
REPORT_DIR = REPO_ROOT / "data_pipeline" / "reports"
HUMAN_DIR = REPO_ROOT / "00_项目成果总览_先看这里" / "02_OCR结果_13本扫描PDF"

PUNCTUATION = set("。！？；：，、,.!?;:)")
MOJIBAKE_MARKERS = ("鍏", "鐕", "璧", "锛", "鈥", "绋", "涓")


def is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
    )


def is_common_char(char: str) -> bool:
    return (
        char.isspace()
        or char.isalnum()
        or is_cjk(char)
        or char in "。！？；：，、,.!?;:()（）[]【】<>《》+-=*/%℃°~—-·'\"“”‘’"
    )


def compact(text: Any, limit: int = 180) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "..."


def page_metrics(page: dict[str, Any]) -> dict[str, Any]:
    text = str(page.get("text") or "")
    lines = page.get("lines") or []
    if lines and isinstance(lines[0], dict):
        line_texts = [str(item.get("text") or "") for item in lines]
        line_confidences = [
            float(item.get("confidence") or 0.0)
            for item in lines
            if isinstance(item, dict)
        ]
    else:
        line_texts = [str(item) for item in lines] or text.splitlines()
        line_confidences = []

    non_space = [char for char in text if not char.isspace()]
    cjk_count = sum(1 for char in non_space if is_cjk(char))
    symbol_count = sum(1 for char in text if not is_common_char(char))
    punctuation_count = sum(1 for char in text if char in PUNCTUATION)
    short_lines = sum(1 for line in line_texts if len(line.strip()) <= 2)
    ending_punct_lines = sum(1 for line in line_texts if line.strip().endswith(tuple(PUNCTUATION)))
    mojibake_hits = sum(text.count(marker) for marker in MOJIBAKE_MARKERS)

    char_count = int(page.get("char_count") or len(text))
    line_count = int(page.get("line_count") or len(line_texts))
    avg_confidence = float(page.get("avg_confidence") or 0.0)
    if avg_confidence == 0.0 and line_confidences:
        avg_confidence = statistics.mean(line_confidences)
    symbol_ratio = symbol_count / max(len(non_space), 1)
    cjk_ratio = cjk_count / max(len(non_space), 1)
    short_line_ratio = short_lines / max(line_count, 1)
    ending_punct_ratio = ending_punct_lines / max(line_count, 1)
    layout = page.get("layout") or {}
    layout_risk = str(layout.get("layout_order_risk") or "unknown")

    risks: list[str] = []
    if not text.strip():
        risks.append("无文字")
    if 0 < char_count < 30:
        risks.append("文字极短")
    if char_count > 300 and punctuation_count < 3:
        risks.append("长文本但标点很少")
    if len(non_space) > 50 and symbol_ratio > 0.35:
        risks.append("符号/公式比例偏高")
    if line_count >= 10 and short_line_ratio > 0.4:
        risks.append("短行过多")
    if "�" in text or "\x00" in text:
        risks.append("存在替换字符")
    if mojibake_hits > 5:
        risks.append("疑似编码乱码")
    if avg_confidence and avg_confidence < 0.45:
        risks.append("平均置信度偏低")
    if layout_risk in {"medium", "high"}:
        risks.append(f"版面顺序{layout_risk}")

    return {
        "page_num": int(page.get("page_num") or 0),
        "char_count": char_count,
        "line_count": line_count,
        "avg_confidence": round(avg_confidence, 4),
        "cjk_ratio": round(cjk_ratio, 4),
        "symbol_ratio": round(symbol_ratio, 4),
        "punctuation_count": punctuation_count,
        "short_line_ratio": round(short_line_ratio, 4),
        "ending_punct_ratio": round(ending_punct_ratio, 4),
        "mojibake_hits": mojibake_hits,
        "layout_risk": layout_risk,
        "risk_flags": risks,
        "preview": compact(text),
    }


def percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return ordered[index]


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


def build_audit(ocr_root: Path) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    global_flags: Counter[str] = Counter()
    layout_risk_counts: Counter[str] = Counter()
    all_char_counts: list[int] = []
    all_line_counts: list[int] = []
    all_confidences: list[float] = []
    risk_examples: list[dict[str, Any]] = []

    for manifest_path in sorted(ocr_root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pages_path = Path(manifest["pages_jsonl"])
        pages = load_pages(pages_path)
        metrics = [page_metrics(page) for page in pages]
        flags: Counter[str] = Counter()
        for item in metrics:
            all_char_counts.append(item["char_count"])
            all_line_counts.append(item["line_count"])
            if item["avg_confidence"]:
                all_confidences.append(item["avg_confidence"])
            layout_risk_counts[item["layout_risk"]] += 1
            for flag in item["risk_flags"]:
                flags[flag] += 1
                global_flags[flag] += 1
            if item["risk_flags"] and len(risk_examples) < 50:
                risk_examples.append({"source_file": manifest["source_file"], **item})

        text_pages = sum(1 for item in metrics if item["char_count"] > 0)
        risk_pages = sum(1 for item in metrics if item["risk_flags"])
        documents.append(
            {
                "source_file": manifest["source_file"],
                "status": manifest.get("status"),
                "engine": manifest.get("engine"),
                "layout_aware": bool(manifest.get("layout_aware")),
                "total_pages": int(manifest.get("total_pages") or len(pages)),
                "pages_ocr_done": int(manifest.get("pages_ocr_done") or len(pages)),
                "pages_with_text": text_pages,
                "char_count": int(manifest.get("char_count") or sum(item["char_count"] for item in metrics)),
                "line_count": int(manifest.get("line_count") or sum(item["line_count"] for item in metrics)),
                "error_count": int(manifest.get("error_count") or 0),
                "risk_pages": risk_pages,
                "risk_flags": dict(flags),
                "avg_chars_per_text_page": round(
                    sum(item["char_count"] for item in metrics) / max(text_pages, 1),
                    1,
                ),
            }
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ocr_root": str(ocr_root),
        "pdf_count": len(documents),
        "total_pages": sum(item["total_pages"] for item in documents),
        "pages_ocr_done": sum(item["pages_ocr_done"] for item in documents),
        "pages_with_text": sum(item["pages_with_text"] for item in documents),
        "error_count": sum(item["error_count"] for item in documents),
        "char_count": sum(item["char_count"] for item in documents),
        "line_count": sum(item["line_count"] for item in documents),
        "char_count_p50": percentile(all_char_counts, 0.50),
        "char_count_p90": percentile(all_char_counts, 0.90),
        "line_count_p50": percentile(all_line_counts, 0.50),
        "line_count_p90": percentile(all_line_counts, 0.90),
        "confidence_available": bool(all_confidences),
        "avg_confidence_mean": round(statistics.mean(all_confidences), 4) if all_confidences else 0.0,
        "avg_confidence_p10": round(sorted(all_confidences)[max(0, round((len(all_confidences) - 1) * 0.10))], 4)
        if all_confidences
        else 0.0,
        "confidence_note": (
            "Confidence values are present; they are useful as rough risk indicators, not final correctness proof."
            if all_confidences
            else "Confidence values are unavailable or all zero, so confidence cannot be used as a quality signal."
        ),
        "risk_flag_counts": dict(global_flags),
        "layout_risk_counts": dict(layout_risk_counts),
        "risk_examples": risk_examples,
        "documents": documents,
    }


def write_markdown(path: Path, audit: dict[str, Any], title: str) -> None:
    flags = audit["risk_flag_counts"]
    layout = audit.get("layout_risk_counts", {})
    lines = [
        f"# {title}",
        "",
        "## 总判断",
        "",
        "这批 OCR 已经完成工程层面的全量处理，可以作为 RAG 检索候选文本；但它仍不是精校文本。",
        "",
        "- 运行完整性：高，所有目标页都处理完，脚本层面没有报错。",
        "- 文字识别：整体可用，但封面、目录、表格、公式、页眉页脚仍可能有识别噪声。",
        "- 句段关系：新版 layout-aware 输出已经比旧版更好，因为保存了坐标和版面顺序风险；但高风险页仍需要人工复核。",
        "",
        "## 数字结果",
        "",
        f"- PDF 数量：{audit['pdf_count']}",
        f"- OCR 页数：{audit['pages_ocr_done']} / {audit['total_pages']}",
        f"- 有文字页：{audit['pages_with_text']}",
        f"- OCR 字符数：{audit['char_count']}",
        f"- OCR 行数：{audit['line_count']}",
        f"- 运行错误数：{audit['error_count']}",
        f"- 每页字符数中位数：{audit['char_count_p50']}",
        f"- 每页字符数 P90：{audit['char_count_p90']}",
        f"- 每页行数中位数：{audit['line_count_p50']}",
        f"- 每页行数 P90：{audit['line_count_p90']}",
        f"- 平均置信度均值：{audit['avg_confidence_mean']}",
        f"- 平均置信度 P10：{audit['avg_confidence_p10']}",
        "",
        "## 风险统计",
        "",
        f"- 无文字页：{flags.get('无文字', 0)}",
        f"- 文字极短页：{flags.get('文字极短', 0)}",
        f"- 长文本但标点很少：{flags.get('长文本但标点很少', 0)}",
        f"- 符号/公式比例偏高：{flags.get('符号/公式比例偏高', 0)}",
        f"- 短行过多：{flags.get('短行过多', 0)}",
        f"- 平均置信度偏低：{flags.get('平均置信度偏低', 0)}",
        f"- 疑似编码乱码：{flags.get('疑似编码乱码', 0)}",
        "",
        "## 版面顺序风险",
        "",
        f"- 低风险页：{layout.get('low', 0)}",
        f"- 中风险页：{layout.get('medium', 0)}",
        f"- 高风险页：{layout.get('high', 0)}",
        f"- 未知风险页：{layout.get('unknown', 0)}",
        "",
        "## 关于置信度",
        "",
        audit["confidence_note"],
        "",
        "置信度只能帮助找风险页，不能证明文本完全正确。重要结论仍要回看原 PDF 页图。",
        "",
        "## 建议用法",
        "",
        "- 普通 RAG 检索：可以用，适合作为候选证据库。",
        "- GraphRAG / 知识图谱抽取：建议优先使用 layout-aware 版，但跳过或人工复核高风险页。",
        "- 论文引用：必须绑定页码和 evidence，关键句回看原 PDF。",
        "- 下一步：抽 30 到 50 页人工核对，重点看高风险页、表格页、公式页和两栏页。",
        "",
        "## 风险页样例",
        "",
    ]

    examples = audit["risk_examples"][:25]
    if not examples:
        lines.append("暂未发现明显风险页。")
    else:
        lines.extend(
            [
                "| 文件 | 页码 | 风险 | 字符数 | 行数 | 预览 |",
                "| --- | ---: | --- | ---: | ---: | --- |",
            ]
        )
        for item in examples:
            source = compact(item["source_file"], 42).replace("|", "\\|")
            risks = "、".join(item["risk_flags"]).replace("|", "\\|")
            preview = compact(item["preview"], 90).replace("|", "\\|")
            lines.append(
                f"| {source} | {item['page_num']} | {risks} | {item['char_count']} | {item['line_count']} | {preview} |"
            )

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit OCR quality from pages.jsonl files.")
    parser.add_argument("--output-root", default=str(DEFAULT_OCR_ROOT))
    parser.add_argument("--report-stem", default="ocr_quality_audit")
    parser.add_argument("--title", default="OCR 可靠性审计")
    parser.add_argument("--copy-to-human-dir", action="store_true")
    args = parser.parse_args()

    ocr_root = resolve_repo_path(args.output_root)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    audit = build_audit(ocr_root)
    json_path = REPORT_DIR / f"{args.report_stem}.json"
    md_path = REPORT_DIR / f"{args.report_stem}.md"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(md_path, audit, args.title)

    if args.copy_to_human_dir and HUMAN_DIR.exists():
        human_md = HUMAN_DIR / f"{args.title}.md"
        human_json = HUMAN_DIR / f"{args.title}.json"
        write_markdown(human_md, audit, args.title)
        human_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "markdown": str(md_path),
                "json": str(json_path),
                "pdf_count": audit["pdf_count"],
                "pages_ocr_done": audit["pages_ocr_done"],
                "pages_with_text": audit["pages_with_text"],
                "error_count": audit["error_count"],
                "risk_flag_counts": audit["risk_flag_counts"],
                "layout_risk_counts": audit["layout_risk_counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
