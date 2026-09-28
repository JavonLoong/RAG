from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONSOLE_SRC = _REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if _CONSOLE_SRC.exists() and str(_CONSOLE_SRC) not in sys.path:
    sys.path.insert(0, str(_CONSOLE_SRC))

from chroma_rag_poc.parsing import get_source_kind  # noqa: E402
from chroma_rag_poc.schemas import SourceRecord, TextBlock  # noqa: E402
from chroma_rag_poc.text_utils import normalize_text, stable_hash  # noqa: E402


class ExternalParserUnavailable(RuntimeError):
    pass


def load_docling_records(
    raw_bytes: bytes,
    *,
    source_name: str,
    converter_factory: Callable[[], Any] | None = None,
) -> list[SourceRecord]:
    converter_factory = converter_factory or _load_docling_converter_factory()
    suffix = Path(source_name).suffix or ".bin"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw_bytes)
            temp_path = Path(tmp.name)

        conversion = converter_factory().convert(str(temp_path))
        document = getattr(conversion, "document", None)
        markdown = _export_docling_document(document)
        blocks = _markdown_to_blocks(markdown)
        text = "\n\n".join(block.text for block in blocks)
        if not text:
            raise ValueError("Docling conversion produced no readable text")
        return [
            SourceRecord(
                source_file=source_name,
                record_id=f"{source_name}::docling",
                filename=source_name,
                page_num=None,
                text=text,
                blocks=blocks,
                metadata={
                    "source_kind": get_source_kind(source_name),
                    "parser_backend": "docling",
                    "external_runtime": "docling",
                    "external_runtime_status": "used",
                },
            )
        ]
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _load_docling_converter_factory() -> Callable[[], Any]:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise ExternalParserUnavailable("Docling is not installed. Install the `external-docs` extra or `docling`.") from exc
    return DocumentConverter


def _export_docling_document(document: Any) -> str:
    if document is None:
        return ""
    for method_name in ("export_to_markdown", "export_to_text"):
        method = getattr(document, method_name, None)
        if callable(method):
            return normalize_text(str(method()))
    return normalize_text(str(document))


def _markdown_to_blocks(markdown: str) -> list[TextBlock]:
    parts = [normalize_text(part) for part in markdown.replace("\r\n", "\n").split("\n\n")]
    parts = [part for part in parts if part]
    blocks: list[TextBlock] = []
    last_visual_id: str | None = None
    for index, part in enumerate(parts):
        block_type = "Title" if part.startswith("#") else "Para"
        table_id: str | None = None
        image_id: str | None = None
        caption_for: str | None = None
        metadata: dict[str, Any] = {}
        if part.startswith("![") and "](" in part:
            block_type = "Image"
            image_id = f"IMG-{stable_hash(part)[:16]}"
            text = part[2 : part.find("](")].strip() or "Embedded image"
            metadata["markdown_image"] = part
            last_visual_id = image_id
        elif part.startswith("|") and "|" in part.strip("|"):
            block_type = "Table"
            table_id = f"TBL-{stable_hash(part)[:16]}"
            rows = [row for row in part.splitlines() if row.strip()]
            widths = [len(row.strip().strip("|").split("|")) for row in rows]
            text = part
            metadata.update({"table_row_count": len(rows), "table_column_counts": str(widths)})
            last_visual_id = table_id
        elif part.lower().startswith(("figure ", "fig. ", "table ")) or part.startswith(("图", "表")):
            block_type = "Caption"
            text = part
            caption_for = last_visual_id
        else:
            text = part.lstrip("#").strip() if block_type == "Title" else part
        blocks.append(
            TextBlock(
                text=text,
                block_type=block_type,
                order=index,
                block_id=f"BLK-{stable_hash(f'{index}:{block_type}:{text}')[:16]}",
                table_id=table_id,
                image_id=image_id,
                caption_for=caption_for,
                metadata=metadata,
            )
        )
    return blocks
