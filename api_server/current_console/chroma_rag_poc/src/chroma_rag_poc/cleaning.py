"""
数据清洗 — 来自项目1

短文本合并：<min_chars 的碎片合并到相邻块。
解决 OCR 双栏切割产生的 "程体系。" "建方法" 等残留碎片。
项目2 没有此功能。
"""
from __future__ import annotations

from .schemas import SourceRecord, TextBlock
from .text_utils import normalize_text


def clean_records(records: list[SourceRecord], min_chars: int = 10) -> list[SourceRecord]:
    """
    对所有 records 执行短文本合并清洗。
    返回清洗后的 records（不修改原始数据）。
    """
    cleaned_records: list[SourceRecord] = []
    for record in records:
        cleaned_blocks = _merge_short_blocks(record.blocks, min_chars=min_chars)
        cleaned_records.append(
            SourceRecord(
                source_file=record.source_file,
                record_id=record.record_id,
                filename=record.filename,
                page_num=record.page_num,
                text=_rebuild_text(cleaned_blocks),
                blocks=cleaned_blocks,
                metadata=record.metadata,
                total_pages=record.total_pages,
                doc_id=record.doc_id,
            )
        )
    return cleaned_records


def _merge_short_blocks(blocks: list[TextBlock], min_chars: int = 10) -> list[TextBlock]:
    """
    短文本合并算法（来自项目1 clean_blocks）。
    <min_chars 的碎片自动合并到相邻块。
    """
    if not blocks:
        return blocks

    # 按 (page_num, y, order) 排序
    sorted_blocks = sorted(blocks, key=lambda b: (b.page_num, b.y, b.order))

    cleaned: list[TextBlock] = []
    pending_short: TextBlock | None = None

    for block in sorted_blocks:
        text = normalize_text(block.text)
        if not text:
            continue

        if len(text) < min_chars:
            if pending_short is None:
                pending_short = TextBlock(
                    text=text,
                    block_type=block.block_type,
                    order=block.order,
                    page_num=block.page_num,
                    doc_id=block.doc_id,
                    x=block.x,
                    y=block.y,
                )
            else:
                # 连续短块合并
                pending_short = TextBlock(
                    text=pending_short.text + text,
                    block_type=pending_short.block_type,
                    order=pending_short.order,
                    page_num=pending_short.page_num,
                    doc_id=pending_short.doc_id,
                    x=pending_short.x,
                    y=pending_short.y,
                )
        else:
            if pending_short is not None:
                # 把短块合并到当前块前面
                text = pending_short.text + text
                pending_short = None
            cleaned.append(
                TextBlock(
                    text=text,
                    block_type=block.block_type,
                    order=block.order,
                    page_num=block.page_num,
                    doc_id=block.doc_id,
                    x=block.x,
                    y=block.y,
                )
            )

    # 最后如果还有短块，合并到最后一个块
    if pending_short is not None:
        if cleaned:
            last = cleaned[-1]
            cleaned[-1] = TextBlock(
                text=last.text + pending_short.text,
                block_type=last.block_type,
                order=last.order,
                page_num=last.page_num,
                doc_id=last.doc_id,
                x=last.x,
                y=last.y,
            )
        else:
            cleaned.append(pending_short)

    return cleaned


def _rebuild_text(blocks: list[TextBlock]) -> str:
    """从 blocks 重建结构化文本"""
    parts: list[str] = []
    for block in blocks:
        text = normalize_text(block.text)
        if not text:
            continue
        if block.block_type.lower() == "list":
            parts.append(f"- {text}")
        else:
            parts.append(text)
    return "\n\n".join(parts)
