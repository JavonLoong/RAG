from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any


DOMAIN_TERMS = (
    "燃机",
    "燃气轮机",
    "压气机",
    "涡轮",
    "燃烧",
    "故障",
    "振动",
    "叶片",
    "轴承",
    "滑油",
    "机匣",
    "转子",
    "温度",
    "压力",
    "机理",
)


@dataclass(frozen=True)
class TextBlock:
    task_id: str
    filename: str
    doc_id: str
    page_num: int | None
    total_pages: int | None
    block_id: str
    label: str
    text: str
    x: float | None
    y: float | None
    width: float | None
    height: float | None


def load_json(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path} top-level JSON must be a list")
    return [item for item in data if isinstance(item, dict)]


def coerce_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_blocks(task: dict[str, Any]) -> tuple[list[TextBlock], list[str]]:
    data = task.get("data") if isinstance(task.get("data"), dict) else {}
    annotations = task.get("annotations") if isinstance(task.get("annotations"), list) else []
    task_id = str(task.get("id", ""))
    filename = str(data.get("filename") or "")
    doc_id = str(data.get("doc_id") or filename)
    page_num = coerce_int(data.get("page_num"))
    total_pages = coerce_int(data.get("total_pages"))
    issues: list[str] = []

    if not annotations:
        return [], ["missing_annotation"]

    annotation = annotations[0] if isinstance(annotations[0], dict) else {}
    if annotation.get("was_cancelled"):
        issues.append("cancelled_annotation")
    results = annotation.get("result") if isinstance(annotation.get("result"), list) else []
    if not results:
        return [], issues + ["empty_result"]

    by_id: dict[str, dict[str, Any]] = defaultdict(dict)
    for result in results:
        if not isinstance(result, dict):
            continue
        rid = str(result.get("id") or "")
        value = result.get("value") if isinstance(result.get("value"), dict) else {}
        rtype = result.get("type")
        if rtype == "rectanglelabels":
            labels = value.get("rectanglelabels") if isinstance(value.get("rectanglelabels"), list) else []
            by_id[rid]["label"] = str(labels[0]) if labels else ""
            for key in ("x", "y", "width", "height"):
                by_id[rid][key] = value.get(key)
        elif rtype == "textarea":
            text_value = value.get("text")
            if isinstance(text_value, list):
                by_id[rid]["text"] = "\n".join(str(x) for x in text_value if x is not None)
            elif text_value is not None:
                by_id[rid]["text"] = str(text_value)

    blocks: list[TextBlock] = []
    for block_id, payload in by_id.items():
        label = str(payload.get("label") or "")
        text = normalize_text(str(payload.get("text") or ""))
        if not label:
            issues.append("missing_label")
        if not text:
            issues.append("missing_text")
        blocks.append(
            TextBlock(
                task_id=task_id,
                filename=filename,
                doc_id=doc_id,
                page_num=page_num,
                total_pages=total_pages,
                block_id=block_id,
                label=label,
                text=text,
                x=as_float(payload.get("x")),
                y=as_float(payload.get("y")),
                width=as_float(payload.get("width")),
                height=as_float(payload.get("height")),
            )
        )
    return blocks, issues


def as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()


def symbol_ratio(text: str) -> float:
    if not text:
        return 1.0
    meaningful = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff" or ch.isalnum())
    return 1.0 - meaningful / max(len(text), 1)


def has_domain_term(text: str) -> bool:
    return any(term in text for term in DOMAIN_TERMS)


def is_probable_page_noise(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if re.fullmatch(r"[-—_]*\d{1,4}[-—_]*", compact):
        return True
    if re.fullmatch(r"第?\d{1,4}页", compact):
        return True
    if len(compact) <= 2:
        return True
    return False


def classify(block: TextBlock, duplicate_count: int) -> tuple[str, str]:
    text = block.text
    label = block.label
    length = len(text)
    noise = symbol_ratio(text)

    if not text:
        return "reject", "empty_text"
    if is_probable_page_noise(text):
        return "reject", "page_or_tiny_noise"
    if duplicate_count >= 8 and length <= 40:
        return "reject", "repeated_header_footer"
    if noise > 0.45:
        return "review", "high_symbol_noise"
    if label in {"Para", "Title"} and length >= 20:
        return "accept", "main_text"
    if label == "List" and length >= 20:
        return "accept", "list_text"
    if label == "Para" and 8 <= length < 20 and has_domain_term(text):
        return "review", "short_domain_text"
    if label == "List" and 8 <= length < 20 and has_domain_term(text):
        return "review", "short_domain_list"
    if label == "Title" and 4 <= length < 20:
        return "metadata", "title_metadata"
    if label == "Figure":
        if length >= 12 and has_domain_term(text):
            return "review", "figure_caption_with_domain_term"
        return "metadata", "figure_caption"
    if label == "Formula":
        return "review", "formula_needs_context"
    if label == "Table":
        if length >= 30 and has_domain_term(text):
            return "review", "table_needs_manual_check"
        return "reject", "table_too_short_or_no_domain_term"
    if length < 20:
        return "reject", "too_short"
    return "review", "unknown_label_or_rule_gap"


def audit_snapshots(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_ids: set[str] | None = None
    for path in paths:
        data = load_json(path)
        ids = {str(item.get("id")) for item in data}
        rows.append(
            {
                "file": path.name,
                "size_mb": round(path.stat().st_size / 1024 / 1024, 2),
                "tasks": len(data),
                "unique_task_ids": len(ids),
                "new_vs_previous": len(ids - previous_ids) if previous_ids is not None else len(ids),
                "contains_previous": previous_ids.issubset(ids) if previous_ids is not None else "",
            }
        )
        previous_ids = ids
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_report(
    path: Path,
    latest_path: Path,
    snapshot_rows: list[dict[str, Any]],
    book_rows: list[dict[str, Any]],
    label_counts: Counter[str],
    decision_counts: Counter[str],
    reason_counts: Counter[str],
    issue_counts: Counter[str],
    length_by_label: dict[str, list[int]],
    top_duplicates: list[tuple[str, int]],
    total_blocks: int,
    total_tasks: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# 公开书籍 Label Studio JSON 入库前检测报告")
    lines.append("")
    lines.append(f"- 检测时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 使用快照：`{latest_path.name}`")
    lines.append(f"- 快照任务数：{total_tasks}")
    lines.append(f"- 抽取文本块数：{total_blocks}")
    lines.append("")
    lines.append("## 结论")
    lines.append("")
    lines.append("1. 这 27 个 JSON 是同一项目的连续导出快照，后一个基本包含前一个；入库时应使用最新快照，避免重复入库。")
    lines.append("2. JSON 里人工标注是图片页上的框和转写文本，不能直接把整页 JSON 入库；必须先按框抽出文本块，再筛掉表格噪声、图片说明、页眉页脚和过短片段。")
    lines.append("3. 当前正文 `Para` 不是完整自然段，很多是按行切开的短片段；入 ChromaDB 前必须按同一页的坐标顺序合并相邻 `Para`，否则检索会碎。")
    lines.append("4. `Table`、`Figure`、`Formula` 不能默认作为正文入库；建议进入人工复核或只作为 metadata/caption。")
    lines.append("")
    lines.append("## 快照检查")
    lines.append("")
    lines.append("| 文件 | 大小MB | 任务数 | 新增任务 | 是否包含上一版 |")
    lines.append("|---|---:|---:|---:|---|")
    for row in snapshot_rows:
        lines.append(
            f"| {row['file']} | {row['size_mb']} | {row['tasks']} | {row['new_vs_previous']} | {row['contains_previous']} |"
        )
    lines.append("")
    lines.append("## 每本书/文件覆盖情况")
    lines.append("")
    lines.append("| 文件 | 页数 | 标注页 | 文本块 | 可直接入库 | 需复核 | 建议不入库 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for row in book_rows:
        lines.append(
            f"| {row['filename']} | {row['pages']} | {row['annotated_pages']} | {row['blocks']} | {row['accept']} | {row['review']} | {row['reject']} |"
        )
    lines.append("")
    lines.append("## 标签分布")
    lines.append("")
    lines.append("| 标签 | 数量 | 中位长度 |")
    lines.append("|---|---:|---:|")
    for label, count in label_counts.most_common():
        lengths = length_by_label.get(label) or [0]
        lines.append(f"| {label or '(空)'} | {count} | {int(median(lengths))} |")
    lines.append("")
    lines.append("## 入库筛选结果")
    lines.append("")
    lines.append("| 结果 | 数量 |")
    lines.append("|---|---:|")
    for decision, count in decision_counts.most_common():
        lines.append(f"| {decision} | {count} |")
    lines.append("")
    lines.append("## 主要风险原因")
    lines.append("")
    lines.append("| 原因 | 数量 |")
    lines.append("|---|---:|")
    for reason, count in reason_counts.most_common(20):
        lines.append(f"| {reason} | {count} |")
    lines.append("")
    lines.append("## 标注结构问题")
    lines.append("")
    if issue_counts:
        lines.append("| 问题 | 次数 |")
        lines.append("|---|---:|")
        for issue, count in issue_counts.most_common():
            lines.append(f"| {issue} | {count} |")
    else:
        lines.append("未发现明显的空 annotation、空 result、缺 label 或缺 text。")
    lines.append("")
    lines.append("## 高频重复短文本")
    lines.append("")
    lines.append("| 文本 | 次数 | 处理建议 |")
    lines.append("|---|---:|---|")
    for text, count in top_duplicates:
        safe = text.replace("|", "\\|")
        lines.append(f"| {safe[:80]} | {count} | 若是页眉页脚/重复标题，应加入 reject 规则 |")
    lines.append("")
    lines.append("## 给标注人员的反馈")
    lines.append("")
    lines.append("1. `Para` 只标正文，不要把页码、页眉、单位署名、目录碎片、无意义短词标成正文。")
    lines.append("2. 一段正文如果被 OCR 拆成多行，可以保持行级框，但要保证阅读顺序从上到下、从左到右稳定；入库侧会按坐标合并。")
    lines.append("3. `Title` 只用于章节标题/小节标题，后续主要作为 metadata，不直接当正文证据。")
    lines.append("4. `Figure` 只标图题或图注，不要框整张图；图题可保留为 caption，但默认不作为核心正文。")
    lines.append("5. `Table` 只在表格内容对故障、机理、参数有价值时保留；复杂表格建议人工复核，不要默认入库。")
    lines.append("6. `Formula` 只标公式本体；如果公式没有前后解释，默认不单独入库。")
    lines.append("7. `List` 可以作为正文候选，但要保证不是目录、编号清单或空泛条目。")
    lines.append("8. 如果发现 OCR 转写明显错字、乱码、左右栏串行，标注时应加 `needs_ocr_fix` 或在备注里说明，不能直接进入 ChromaDB。")
    lines.append("")
    lines.append("## 建议入库规则")
    lines.append("")
    lines.append("- 直接入库：`Para`，长度不少于 20 字，非重复页眉页脚，符号噪声比例不高。")
    lines.append("- 元数据：短 `Title`、普通 `Figure` caption。")
    lines.append("- 人工复核：`Table`、`Formula`、含领域词的短句、图注、符号比例偏高的文本。")
    lines.append("- 不入库：空文本、页码、过短碎片、高频重复页眉页脚、无领域信息的表格/图注/公式。")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output-dir", default="data_pipeline/reports")
    args = parser.parse_args()

    root = Path(args.input_root)
    output_dir = Path(args.output_dir)
    paths = sorted(root.rglob("*.json"))
    if not paths:
        raise SystemExit(f"No JSON files found under {root}")

    snapshot_rows = audit_snapshots(paths)
    latest_path = paths[-1]
    tasks = load_json(latest_path)

    blocks: list[TextBlock] = []
    issue_counts: Counter[str] = Counter()
    page_annotated: Counter[str] = Counter()
    pages_by_file: dict[str, set[int]] = defaultdict(set)
    total_pages_by_file: dict[str, int] = {}
    for task in tasks:
        data = task.get("data") if isinstance(task.get("data"), dict) else {}
        filename = str(data.get("filename") or "")
        page = coerce_int(data.get("page_num"))
        total_pages = coerce_int(data.get("total_pages"))
        if filename and page is not None:
            pages_by_file[filename].add(page)
        if filename and total_pages is not None:
            total_pages_by_file[filename] = max(total_pages_by_file.get(filename, 0), total_pages)
        extracted, issues = extract_blocks(task)
        blocks.extend(extracted)
        issue_counts.update(issues)
        if extracted:
            page_annotated[filename] += 1

    text_counts = Counter(block.text for block in blocks if block.text)
    label_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    length_by_label: dict[str, list[int]] = defaultdict(list)
    screened_rows: list[dict[str, Any]] = []
    per_file = defaultdict(lambda: Counter())

    for block in blocks:
        duplicate_count = text_counts.get(block.text, 0)
        decision, reason = classify(block, duplicate_count)
        label_counts[block.label] += 1
        decision_counts[decision] += 1
        reason_counts[reason] += 1
        length_by_label[block.label].append(len(block.text))
        per_file[block.filename]["blocks"] += 1
        per_file[block.filename][decision] += 1
        screened_rows.append(
            {
                "decision": decision,
                "reason": reason,
                "label": block.label,
                "filename": block.filename,
                "page_num": block.page_num,
                "task_id": block.task_id,
                "block_id": block.block_id,
                "text_len": len(block.text),
                "symbol_ratio": round(symbol_ratio(block.text), 3),
                "duplicate_count": duplicate_count,
                "text": block.text,
            }
        )

    book_rows: list[dict[str, Any]] = []
    for filename in sorted(set(list(pages_by_file) + list(per_file))):
        counter = per_file[filename]
        book_rows.append(
            {
                "filename": filename,
                "pages": total_pages_by_file.get(filename) or len(pages_by_file[filename]),
                "annotated_pages": page_annotated.get(filename, 0),
                "blocks": counter["blocks"],
                "accept": counter["accept"],
                "review": counter["review"],
                "metadata": counter["metadata"],
                "reject": counter["reject"],
            }
        )

    duplicate_rows = [
        {"text": text, "count": count}
        for text, count in text_counts.most_common(100)
        if count >= 5 and len(text) <= 80
    ]
    top_duplicates = [(row["text"], row["count"]) for row in duplicate_rows[:30]]

    write_csv(
        output_dir / "public_books_snapshot_audit_20260522.csv",
        snapshot_rows,
        ["file", "size_mb", "tasks", "unique_task_ids", "new_vs_previous", "contains_previous"],
    )
    write_csv(
        output_dir / "public_books_file_summary_20260522.csv",
        book_rows,
        ["filename", "pages", "annotated_pages", "blocks", "accept", "review", "metadata", "reject"],
    )
    write_csv(
        output_dir / "public_books_screened_blocks_20260522.csv",
        screened_rows,
        [
            "decision",
            "reason",
            "label",
            "filename",
            "page_num",
            "task_id",
            "block_id",
            "text_len",
            "symbol_ratio",
            "duplicate_count",
            "text",
        ],
    )
    write_csv(output_dir / "public_books_duplicate_text_20260522.csv", duplicate_rows, ["text", "count"])
    write_report(
        output_dir / "public_books_json_audit_20260522.md",
        latest_path,
        snapshot_rows,
        book_rows,
        label_counts,
        decision_counts,
        reason_counts,
        issue_counts,
        length_by_label,
        top_duplicates,
        len(blocks),
        len(tasks),
    )

    print(f"latest={latest_path}")
    print(f"tasks={len(tasks)} blocks={len(blocks)}")
    print(f"decisions={dict(decision_counts)}")
    print(f"report={output_dir / 'public_books_json_audit_20260522.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
