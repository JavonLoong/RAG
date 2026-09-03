"""Adapters for the parsed SourceRecord objects already produced by M2."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import BlockInput, DocumentInput, PageInput


def document_from_source_records(
    records: Iterable[Any],
    *,
    document_id: str,
    title: str | None = None,
    source_uri: str | None = None,
    media_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> DocumentInput:
    """Convert current-console ``SourceRecord`` instances without importing its package."""

    values = list(records)
    if not values:
        raise ValueError("records must not be empty")
    first = values[0]
    source_name = str(getattr(first, "source_file", "") or getattr(first, "filename", ""))
    pages: dict[int, list[BlockInput]] = defaultdict(list)
    for record_index, record in enumerate(values, start=1):
        record_page = getattr(record, "page_num", None)
        page_number = int(record_page) if isinstance(record_page, int) and record_page > 0 else record_index
        blocks = list(getattr(record, "blocks", ()) or ())
        if blocks:
            for position, block in enumerate(blocks):
                block_page = getattr(block, "page_num", None)
                resolved_page = int(block_page) if isinstance(block_page, int) and block_page > 0 else page_number
                pages[resolved_page].append(
                    BlockInput(
                        text=str(getattr(block, "text", "")),
                        block_type=str(getattr(block, "block_type", "paragraph")),
                        ordinal=int(getattr(block, "order", position)),
                        metadata={
                            "x": float(getattr(block, "x", 0.0)),
                            "y": float(getattr(block, "y", 0.0)),
                            "source_record_id": str(getattr(record, "record_id", "")),
                        },
                    )
                )
        else:
            pages[page_number].append(
                BlockInput(
                    text=str(getattr(record, "text", "")),
                    ordinal=0,
                    metadata={"source_record_id": str(getattr(record, "record_id", ""))},
                )
            )
    extension = Path(source_name).suffix.lower()
    default_media_type = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".json": "application/json",
    }.get(extension, "application/octet-stream")
    return DocumentInput(
        document_id=document_id,
        title=title or str(getattr(first, "filename", "") or source_name or document_id),
        source_uri=source_uri or source_name,
        media_type=media_type or default_media_type,
        pages=tuple(
            PageInput(page_number=page_number, blocks=tuple(blocks)) for page_number, blocks in sorted(pages.items())
        ),
        metadata={**dict(getattr(first, "metadata", {}) or {}), **dict(metadata or {})},
    )
