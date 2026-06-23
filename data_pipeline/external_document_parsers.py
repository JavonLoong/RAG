from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONSOLE_SRC = _REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if _CONSOLE_SRC.exists() and str(_CONSOLE_SRC) not in sys.path:
    sys.path.insert(0, str(_CONSOLE_SRC))

from chroma_rag_poc.parsing import get_source_kind  # noqa: E402
from chroma_rag_poc.schemas import SourceRecord, TextBlock  # noqa: E402
from chroma_rag_poc.text_utils import normalize_text  # noqa: E402


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
    for index, part in enumerate(parts):
        block_type = "Title" if part.startswith("#") else "Para"
        text = part.lstrip("#").strip() if block_type == "Title" else part
        blocks.append(TextBlock(text=text, block_type=block_type, order=index))
    return blocks
