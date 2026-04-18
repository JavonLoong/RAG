"""
分块模块 — 合并两版最优算法

项目2: 多级断点查找（句号>叹号>问号>分号>逗号>空格）
项目1: Title 自动触发新 chunk + label 分布统计

合并后：Title 触发 + 多级断点 = 最优分块质量
"""
from __future__ import annotations

from pathlib import Path

from .schemas import ChunkRecord, SourceRecord, TextBlock
from .text_utils import estimate_token_count, normalize_text, stable_hash

# 项目2 的多级断点标记（优先级从高到低）
BREAK_MARKERS = ("\n\n", "\n", "。", "！", "？", "；", ";", "，", ",", " ")


def chunk_records(
    records: list[SourceRecord],
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[ChunkRecord]:
    """
    对所有 records 进行分块。
    
    合并策略：
    - 项目1 的 Title 触发：遇到 Title 块自动开始新 chunk
    - 项目2 的多级断点：长文本按语义断点切分
    - 项目1 的 label 统计：chunk metadata 包含 label 分布
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between 0 and chunk_size - 1")

    chunks: list[ChunkRecord] = []

    for record in records:
        source_ext = Path(record.filename or record.source_file).suffix.lower() or Path(record.source_file).suffix.lower()
        source_kind = str(record.metadata.get("source_kind") or source_ext.lstrip(".").upper() or "Other")
        if record.blocks:
            # 有 blocks 信息时，使用 Title 触发分块策略
            record_chunks = _chunk_with_title_trigger(
                record,
                chunk_size=chunk_size,
                overlap=overlap,
                source_ext=source_ext,
                source_kind=source_kind,
            )
        else:
            # 无 blocks 时，使用纯文本分块
            record_chunks = _chunk_plain_text(
                record,
                chunk_size=chunk_size,
                overlap=overlap,
                source_ext=source_ext,
                source_kind=source_kind,
            )
        chunks.extend(record_chunks)

    return chunks


def _chunk_with_title_trigger(
    record: SourceRecord,
    chunk_size: int = 500,
    overlap: int = 50,
    source_ext: str = "",
    source_kind: str = "Other",
) -> list[ChunkRecord]:
    """
    Title 触发分块（来自项目1）+ 多级断点（来自项目2）

    策略：
    1. Title 标签自动触发新 chunk（标题不会粘在上一段尾巴上）
    2. 累积文本超过 chunk_size 时，按多级断点切分
    3. overlap 保持上下文连续性
    """
    blocks = sorted(record.blocks, key=lambda b: (b.page_num, b.y, b.order))
    chunks: list[ChunkRecord] = []
    current_text = ""
    current_pages: set[int] = set()
    current_labels: dict[str, int] = {}
    chunk_index = 0

    def _flush():
        nonlocal current_text, current_pages, current_labels, chunk_index
        text = normalize_text(current_text)
        if not text:
            return

        # 如果文本仍然过长，使用多级断点进一步切分
        sub_texts = split_text_with_overlap(text, chunk_size=chunk_size, overlap=overlap)
        for sub_text in sub_texts:
            text_hash = stable_hash(sub_text)
            chunk_id = stable_hash(f"{record.record_id}:{chunk_index}:{text_hash}")
            page_nums = sorted(current_pages) if current_pages else [-1]

            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    text=sub_text,
                    metadata={
                        "source_file": record.source_file,
                        "record_id": record.record_id,
                        "filename": record.filename,
                        "doc_id": record.doc_id if record.doc_id != -1 else -1,
                        "page_nums": str(page_nums),
                        "chunk_index": chunk_index,
                        "block_count": len(blocks),
                        "char_count": len(sub_text),
                        "estimated_tokens": estimate_token_count(sub_text),
                        "labels": str(dict(current_labels)),
                        "source_ext": source_ext or "unknown",
                        "source_kind": source_kind,
                    },
                )
            )
            chunk_index += 1

        # 保留 overlap
        tail = current_text[-overlap:] if len(current_text) > overlap else ""
        current_text = tail
        current_pages = set()
        current_labels = {}

    for block in blocks:
        # 项目1 核心逻辑：Title 触发新 chunk
        if block.block_type == "Title" and current_text.strip():
            _flush()

        # 累积超限时也触发
        if len(current_text) + len(block.text) + 1 > chunk_size and current_text.strip():
            _flush()

        current_text += (("\n" if current_text else "") + block.text)
        if block.page_num >= 0:
            current_pages.add(block.page_num)
        current_labels[block.block_type] = current_labels.get(block.block_type, 0) + 1

    _flush()
    return chunks


def _chunk_plain_text(
    record: SourceRecord,
    chunk_size: int = 500,
    overlap: int = 50,
    source_ext: str = "",
    source_kind: str = "Other",
) -> list[ChunkRecord]:
    """纯文本分块（无 blocks 信息时使用）"""
    chunks: list[ChunkRecord] = []
    sub_texts = split_text_with_overlap(record.text, chunk_size=chunk_size, overlap=overlap)

    for chunk_index, text in enumerate(sub_texts):
        text_hash = stable_hash(text)
        chunk_id = stable_hash(f"{record.record_id}:{chunk_index}:{text_hash}")
        page_num = record.page_num if record.page_num is not None else -1

        chunks.append(
            ChunkRecord(
                chunk_id=chunk_id,
                text=text,
                metadata={
                    "source_file": record.source_file,
                    "record_id": record.record_id,
                    "filename": record.filename,
                    "doc_id": record.doc_id if record.doc_id != -1 else -1,
                    "page_nums": str([page_num]),
                    "chunk_index": chunk_index,
                    "block_count": len(record.blocks),
                    "char_count": len(text),
                    "estimated_tokens": estimate_token_count(text),
                    "source_ext": source_ext or "unknown",
                    "source_kind": source_kind,
                },
            )
        )

    return chunks


# ============================================================
# 多级断点分块（来自项目2 split_text_with_overlap）
# ============================================================


def split_text_with_overlap(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    带 overlap 的文本切分，使用多级断点查找最佳切分位置。
    断点优先级：段落 > 换行 > 句号 > 叹号 > 问号 > 分号 > 逗号 > 空格
    """
    cleaned = normalize_text(text)
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    output: list[str] = []
    start = 0
    text_length = len(cleaned)

    while start < text_length:
        max_end = min(start + chunk_size, text_length)
        if max_end == text_length:
            end = text_length
        else:
            min_end = min(start + max(chunk_size // 2, chunk_size - overlap), max_end)
            end = _choose_breakpoint(cleaned, start=start, min_end=min_end, max_end=max_end)

        chunk = cleaned[start:end].strip()
        if chunk:
            output.append(chunk)
        if end >= text_length:
            break

        next_start = max(end - overlap, start + 1)
        while next_start < text_length and cleaned[next_start].isspace():
            next_start += 1
        start = next_start

    return output


def _choose_breakpoint(text: str, start: int, min_end: int, max_end: int) -> int:
    """在 [min_end, max_end) 范围内按多级优先级查找最佳断点"""
    best = -1
    for marker in BREAK_MARKERS:
        idx = text.rfind(marker, min_end, max_end)
        if idx != -1:
            best = max(best, idx + len(marker))
    return best if best > start else max_end
