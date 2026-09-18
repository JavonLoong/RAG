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
BOUNDARY_METADATA_KEYS = (
    "passage_id",
    "passage_title",
    "section_id",
    "section_path",
    "sentence_id",
    "document_id",
    "ragbench_id",
)


def _scalar_metadata(metadata: dict) -> dict[str, str | int | float | bool]:
    return {
        str(key): value
        for key, value in metadata.items()
        if isinstance(value, (str, int, float, bool))
    }


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
    active_section_title = str(record.metadata.get("passage_title") or "")
    record_boundary_type = str(record.metadata.get("boundary_type") or "record")
    chunk_index = 0

    def _flush(*, keep_tail: bool = True):
        nonlocal current_text, current_pages, current_labels, chunk_index
        text = normalize_text(current_text)
        if not text:
            return

        # 如果文本仍然过长，使用多级断点进一步切分
        sub_texts = split_text_with_overlap(text, chunk_size=chunk_size, overlap=overlap)
        for sub_text in sub_texts:
            page_nums = sorted(current_pages) if current_pages else [-1]
            base_metadata = _build_chunk_metadata(
                record=record,
                text=sub_text,
                chunk_index=chunk_index,
                page_nums=page_nums,
                block_count=len(blocks),
                labels=current_labels,
                source_ext=source_ext,
                source_kind=source_kind,
                section_title=active_section_title,
            )
            stored_text = _attach_boundary_prefix(sub_text, base_metadata)
            text_hash = stable_hash(stored_text)
            chunk_id = stable_hash(f"{record.record_id}:{chunk_index}:{text_hash}")
            base_metadata["chunk_id"] = chunk_id
            base_metadata["citation_anchor"] = _citation_anchor(base_metadata)

            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    text=stored_text,
                    metadata=base_metadata,
                )
            )
            chunk_index += 1

        # 保留 overlap
        tail = current_text[-overlap:] if keep_tail and len(current_text) > overlap else ""
        retained_pages = set(current_pages) if tail else set()
        current_text = tail
        current_pages = retained_pages
        current_labels = dict(current_labels) if tail else {}

    for block in blocks:
        # 项目1 核心逻辑：Title 触发新 chunk
        if block.block_type == "Title" and current_text.strip() and record_boundary_type not in {"passage", "sentence"}:
            _flush(keep_tail=False)
        if block.block_type == "Title":
            active_section_title = block.text

        # 累积超限时也触发
        metadata_only_boundary_prefix = (
            record_boundary_type in {"passage", "sentence"}
            and current_labels
            and set(current_labels).issubset({"Title"})
            and block.block_type != "Title"
        )
        if (
            len(current_text) + len(block.text) + 1 > chunk_size
            and current_text.strip()
            and not metadata_only_boundary_prefix
        ):
            _flush(keep_tail=True)

        current_text += (("\n" if current_text else "") + block.text)
        if block.page_num >= 0:
            current_pages.add(block.page_num)
        current_labels[block.block_type] = current_labels.get(block.block_type, 0) + 1

    _flush(keep_tail=False)
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
        page_num = record.page_num if record.page_num is not None else -1
        base_metadata = _build_chunk_metadata(
            record=record,
            text=text,
            chunk_index=chunk_index,
            page_nums=[page_num],
            block_count=len(record.blocks),
            labels={},
            source_ext=source_ext,
            source_kind=source_kind,
            section_title=str(record.metadata.get("passage_title") or ""),
        )
        stored_text = _attach_boundary_prefix(text, base_metadata)
        text_hash = stable_hash(stored_text)
        chunk_id = stable_hash(f"{record.record_id}:{chunk_index}:{text_hash}")
        base_metadata["chunk_id"] = chunk_id
        base_metadata["citation_anchor"] = _citation_anchor(base_metadata)

        chunks.append(
            ChunkRecord(
                chunk_id=chunk_id,
                text=stored_text,
                metadata=base_metadata,
            )
        )

    return chunks


def _build_chunk_metadata(
    *,
    record: SourceRecord,
    text: str,
    chunk_index: int,
    page_nums: list[int],
    block_count: int,
    labels: dict[str, int],
    source_ext: str,
    source_kind: str,
    section_title: str = "",
) -> dict[str, str | int | float | bool]:
    boundary_type = str(record.metadata.get("boundary_type") or "record")
    passage_id = str(record.metadata.get("passage_id") or "")
    sentence_id = str(record.metadata.get("sentence_id") or "")
    boundary_id = passage_id or sentence_id or record.record_id
    metadata: dict[str, str | int | float | bool] = {
        **_scalar_metadata(record.metadata),
        "source_file": record.source_file,
        "record_id": record.record_id,
        "filename": record.filename,
        "doc_id": record.doc_id if record.doc_id != -1 else -1,
        "page_nums": str(page_nums),
        "chunk_index": chunk_index,
        "boundary_type": boundary_type,
        "boundary_id": boundary_id,
        "boundary_chunk_index": chunk_index,
        "section_title": section_title,
        "block_count": block_count,
        "char_count": len(text),
        "estimated_tokens": estimate_token_count(text),
        "labels": str(dict(labels)) if labels else "{}",
        "source_ext": source_ext or "unknown",
        "source_kind": source_kind,
    }
    for key in BOUNDARY_METADATA_KEYS:
        value = record.metadata.get(key)
        if value is not None and value != "":
            metadata[key] = value
    return metadata


def _attach_boundary_prefix(text: str, metadata: dict[str, str | int | float | bool]) -> str:
    prefix = _boundary_prefix(metadata)
    cleaned = normalize_text(text)
    if not prefix:
        return cleaned
    cleaned = _strip_leading_boundary_headers(cleaned)
    if cleaned.startswith(prefix):
        return cleaned
    return f"{prefix}\n{cleaned}"


def _strip_leading_boundary_headers(text: str) -> str:
    lines = text.splitlines()
    header_prefixes = ("PASSAGE_ID:", "TITLE:", "SECTION_PATH:", "SENTENCE_ID:")
    while lines and lines[0].strip().startswith(header_prefixes):
        lines.pop(0)
    return "\n".join(lines).strip()


def _boundary_prefix(metadata: dict[str, str | int | float | bool]) -> str:
    lines: list[str] = []
    passage_id = str(metadata.get("passage_id") or "").strip()
    if passage_id:
        lines.append(f"PASSAGE_ID: {passage_id}")
    passage_title = str(metadata.get("passage_title") or "").strip()
    if passage_title:
        lines.append(f"TITLE: {passage_title}")
    section_path = str(metadata.get("section_path") or "").strip()
    if section_path:
        lines.append(f"SECTION_PATH: {section_path}")
    sentence_id = str(metadata.get("sentence_id") or "").strip()
    if sentence_id:
        lines.append(f"SENTENCE_ID: {sentence_id}")
    return "\n".join(lines)


def _citation_anchor(metadata: dict[str, str | int | float | bool]) -> str:
    source = str(metadata.get("source_file") or metadata.get("filename") or "source")
    passage_id = str(metadata.get("passage_id") or "").strip()
    sentence_id = str(metadata.get("sentence_id") or "").strip()
    if passage_id:
        return f"{source}#passage={passage_id}"
    if sentence_id:
        return f"{source}#sentence={sentence_id}"
    page_nums = str(metadata.get("page_nums") or "").strip()
    chunk_index = str(metadata.get("chunk_index") or "0")
    return f"{source}#pages={page_nums}#chunk={chunk_index}"


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
