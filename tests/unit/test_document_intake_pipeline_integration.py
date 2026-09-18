from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from chroma_rag_poc.pipeline import ingest_source_payloads  # noqa: E402


def test_ingest_source_payloads_reports_document_intake_summary(tmp_path: Path) -> None:
    raw = b"Pump Manual\n\nInspect vibration and bearing temperature every shift."

    result = ingest_source_payloads(
        payloads=[("manual.txt", raw)],
        persist_dir=tmp_path / "chroma",
        collection_name="intake-demo",
        chunk_size=80,
        overlap=10,
        backend="hashing",
    )

    summary = result["file_summaries"][0]
    assert summary["status"] == "ok"
    assert summary["intake_status"] == "parsed"
    assert summary["parser_route"] == "text_document"
    assert summary["processing_plan"]["parse_chunk_decoupled"] is True
    assert summary["chunk_preview"]
    assert result["document_intake"]["files_parsed"] == 1
    assert result["document_intake"]["files_needing_ocr"] == 0


def test_ingest_source_payloads_reports_pdf_needs_ocr_without_indexing(tmp_path: Path) -> None:
    result = ingest_source_payloads(
        payloads=[("scan.pdf", b"%PDF-1.4\nimage-only placeholder")],
        persist_dir=tmp_path / "chroma",
        collection_name="ocr-demo",
        backend="hashing",
    )

    summary = result["file_summaries"][0]
    assert result["files_processed"] == 1
    assert result["files_succeeded"] == 0
    assert result["files_needing_ocr"] == 1
    assert result["chunks_written"] == 0
    assert summary["status"] == "needs_ocr"
    assert summary["intake_status"] == "needs_ocr"
    assert summary["processing_plan"]["next_queue"] == [
        "ocr",
        "document_layout_recognition",
        "table_structure_recognition",
        "table_auto_rotation",
    ]


def test_ingest_source_payloads_accepts_docling_parser_backend(tmp_path: Path) -> None:
    result = ingest_source_payloads(
        payloads=[("manual.md", b"# Pump\n\nInspect vibration.")],
        persist_dir=tmp_path / "chroma",
        collection_name="docling-demo",
        backend="hashing",
        parser_backend="docling",
    )

    summary = result["file_summaries"][0]
    assert result["parser_backend"] == "docling"
    assert result["document_intake"]["parser_backends"] == ["docling"]
    assert summary["processing_plan"]["parser_backend"] == "docling"
    assert summary["processing_plan"]["runtime"]["name"] == "docling"
