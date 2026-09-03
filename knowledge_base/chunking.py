"""Evidence-preserving, deterministic document chunking."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .models import DocumentInput, EvidenceLocator, StoredChunk

_BREAK_RE = re.compile(r"[\n。！？；;.!?]\s*|[,，]\s*|\s+")


@dataclass(frozen=True, slots=True)
class NormalizedBlock:
    page_number: int
    block_id: str
    block_type: str
    ordinal: int
    text: str
    parent_block_id: str | None
    metadata: dict[str, object]


def stable_sha256(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def normalize_blocks(document: DocumentInput) -> tuple[NormalizedBlock, ...]:
    blocks: list[NormalizedBlock] = []
    for page in sorted(document.pages, key=lambda item: item.page_number):
        for position, block in enumerate(sorted(page.blocks, key=lambda item: item.ordinal)):
            text = _normalize_text(block.text)
            if not text:
                continue
            ordinal = block.ordinal if block.ordinal >= 0 else position
            block_id = block.block_id or (
                "blk_"
                + stable_sha256(f"{document.document_id}|{page.page_number}|{ordinal}|{block.block_type}|{text}")[:24]
            )
            blocks.append(
                NormalizedBlock(
                    page_number=page.page_number,
                    block_id=block_id,
                    block_type=block.block_type.strip().lower() or "paragraph",
                    ordinal=ordinal,
                    text=text,
                    parent_block_id=block.parent_block_id,
                    metadata=dict(block.metadata),
                )
            )
    return tuple(blocks)


def chunk_document(
    *,
    document_id: str,
    revision_id: str,
    blocks: tuple[NormalizedBlock, ...],
    chunk_size: int = 800,
    overlap: int = 100,
) -> tuple[StoredChunk, ...]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between 0 and chunk_size - 1")
    if not blocks:
        return ()

    flattened, spans, heading_boundaries = _flatten_blocks(blocks)
    ranges = _split_ranges(flattened, heading_boundaries, chunk_size, overlap)
    chunks: list[StoredChunk] = []
    for ordinal, (start, end) in enumerate(ranges):
        text = flattened[start:end].strip()
        if not text:
            continue
        left_trim = len(flattened[start:end]) - len(flattened[start:end].lstrip())
        right_trim = len(flattened[start:end].rstrip())
        effective_start = start + left_trim
        effective_end = start + right_trim
        evidence: list[EvidenceLocator] = []
        for block, block_start, block_end in spans:
            intersection_start = max(effective_start, block_start)
            intersection_end = min(effective_end, block_end)
            if intersection_start >= intersection_end:
                continue
            evidence.append(
                EvidenceLocator(
                    document_id=document_id,
                    revision_id=revision_id,
                    page_number=block.page_number,
                    block_id=block.block_id,
                    char_start=intersection_start - block_start,
                    char_end=intersection_end - block_start,
                )
            )
        content_hash = stable_sha256(text)
        chunk_id = "chk_" + stable_sha256(f"{revision_id}|{ordinal}|{content_hash}")[:28]
        chunks.append(
            StoredChunk(
                chunk_id=chunk_id,
                revision_id=revision_id,
                ordinal=ordinal,
                text=text,
                content_sha256=content_hash,
                evidence=tuple(evidence),
                metadata={
                    "page_numbers": sorted({item.page_number for item in evidence}),
                    "block_ids": [item.block_id for item in evidence],
                    "char_count": len(text),
                },
            )
        )
    return tuple(chunks)


def _flatten_blocks(
    blocks: tuple[NormalizedBlock, ...],
) -> tuple[str, list[tuple[NormalizedBlock, int, int]], set[int]]:
    parts: list[str] = []
    spans: list[tuple[NormalizedBlock, int, int]] = []
    heading_boundaries: set[int] = set()
    cursor = 0
    for index, block in enumerate(blocks):
        if index:
            separator = "\n\n"
            parts.append(separator)
            cursor += len(separator)
        if index and block.block_type in {"title", "heading", "header"}:
            heading_boundaries.add(cursor)
        start = cursor
        parts.append(block.text)
        cursor += len(block.text)
        spans.append((block, start, cursor))
    return "".join(parts), spans, heading_boundaries


def _split_ranges(
    text: str,
    heading_boundaries: set[int],
    chunk_size: int,
    overlap: int,
) -> list[tuple[int, int]]:
    output: list[tuple[int, int]] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        hard_end = min(start + chunk_size, text_length)
        candidates = [point for point in heading_boundaries if start < point <= hard_end]
        heading_end = max(candidates, default=-1)
        if heading_end >= start + max(1, chunk_size // 3):
            end = heading_end
        elif hard_end == text_length:
            end = text_length
        else:
            minimum = start + max(1, chunk_size // 2)
            breakpoints = [match.end() for match in _BREAK_RE.finditer(text, minimum, hard_end)]
            end = max(breakpoints, default=hard_end)
        output.append((start, end))
        if end >= text_length:
            break
        next_start = max(start + 1, end - overlap)
        while next_start < end and text[next_start].isspace():
            next_start += 1
        start = next_start
    return output


def _normalize_text(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value.replace("\r\n", "\n").replace("\r", "\n")).strip()
