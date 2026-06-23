from __future__ import annotations

import pytest

from data_pipeline.document_intake import (
    DocumentIntakeOptions,
    classify_document,
    run_document_intake,
)


def test_classifies_pdf_as_deepdoc_ready_route() -> None:
    profile = classify_document("manual.pdf", b"%PDF-1.4\n")

    assert profile.source_kind == "PDF"
    assert profile.parser_route == "pdf_deepdoc_ready"
    assert profile.requires_layout_analysis is True
    assert profile.requires_table_structure_recognition is True
    assert "page_metadata" in profile.quality_gates
    assert "citation_metadata" in profile.quality_gates


def test_text_intake_returns_records_chunks_and_required_metadata() -> None:
    raw = (
        "Boiler Control Manual\n\n"
        "Combustion stability depends on fuel pressure, airflow, and chamber temperature. "
        "Operators should record abnormal flame signals and inspect the safety interlock. "
        "The maintenance section explains sensor calibration and alarm recovery steps."
    ).encode("utf-8")

    result = run_document_intake("manual.txt", raw, chunk_size=80, overlap=10)

    assert result.status == "parsed"
    assert result.records
    assert result.chunks
    assert result.quality["chunk_count"] == len(result.chunks)
    for chunk in result.chunks:
        assert chunk.chunk_id
        assert chunk.text
        assert chunk.metadata["source_file"] == "manual.txt"
        assert chunk.metadata["record_id"]
        assert chunk.metadata["page_nums"]
        assert chunk.metadata["source_kind"] == "Text"
        assert chunk.metadata["char_count"] > 0
        assert chunk.metadata["estimated_tokens"] > 0


def test_passage_delimited_text_preserves_passage_boundary_in_every_chunk() -> None:
    raw = (
        "PASSAGE_ID: 1.2-c2-s2\n"
        "TITLE: Juror impartiality\n"
        "TEXT:\n"
        + "The judge may excuse a juror if impartiality is doubtful. " * 12
        + "\n\nPASSAGE_ID: 1.5-c1-s1\n"
        "TITLE: Jury room experiments\n"
        "TEXT:\n"
        "Jurors should be warned about experiments in the jury room."
    ).encode("utf-8")

    result = run_document_intake("legal-rag-bench-corpus.txt", raw, chunk_size=120, overlap=20)

    assert result.status == "parsed"
    first_passage_chunks = [
        chunk for chunk in result.chunks if chunk.metadata.get("passage_id") == "1.2-c2-s2"
    ]
    assert len(first_passage_chunks) > 1
    for chunk in first_passage_chunks:
        assert chunk.text.startswith("PASSAGE_ID: 1.2-c2-s2")
        assert chunk.metadata["section_id"] == "1.2-c2"
        assert chunk.metadata["section_path"] == "1.2 > c2 > s2"
        assert chunk.metadata["citation_anchor"] == "legal-rag-bench-corpus.txt#passage=1.2-c2-s2"
        assert "1.5-c1-s1" not in chunk.text


def test_sentence_delimited_text_drops_query_header_and_indexes_sentence_anchors() -> None:
    raw = (
        "RAGBENCH_ID: sample-1\n"
        "QUESTION: This should not be copied into every evidence chunk.\n"
        "SENTENCES:\n"
        "SENTENCE_ID: 0a\n"
        "Checking digital channel signal info and strength.\n"
        "SENTENCE_ID: 1b\n"
        "Reset Sound resets current sound settings to the default settings."
    ).encode("utf-8")

    result = run_document_intake("ragbench-sample.txt", raw, chunk_size=200, overlap=20)

    assert result.status == "parsed"
    assert {chunk.metadata.get("sentence_id") for chunk in result.chunks} == {"0a", "1b"}
    assert all(chunk.text.startswith("SENTENCE_ID:") for chunk in result.chunks)
    assert all("This should not be copied" not in chunk.text for chunk in result.chunks)


def test_scanned_pdf_failure_is_reported_as_needs_ocr() -> None:
    result = run_document_intake("scan.pdf", b"%PDF-1.4\nimage-only placeholder", allow_partial=True)

    assert result.status == "needs_ocr"
    assert result.profile.requires_ocr is True
    assert "scanned_pdf_or_image_only" in result.profile.risks
    assert result.errors
    assert not result.records
    assert not result.chunks


def test_jsonl_is_routed_as_structured_json_lines() -> None:
    profile = classify_document("records.jsonl", b'{"title":"A"}\n{"title":"B"}\n')

    assert profile.source_kind == "JSON"
    assert profile.parser_route == "structured_json_lines"
    assert profile.requires_ocr is False
    assert "structured_record_boundaries" in profile.quality_gates


def test_jsonl_intake_preserves_record_boundaries() -> None:
    raw = b'{"id": 1, "title": "Pump", "text": "Inspect vibration."}\n{"id": 2, "title": "Valve", "text": "Check leakage."}\n'

    result = run_document_intake("records.jsonl", raw, chunk_size=80, overlap=10)

    assert result.status == "parsed"
    assert len(result.records) == 2
    assert {record.record_id for record in result.records} == {"records.jsonl::item-1", "records.jsonl::item-2"}
    assert all(chunk.metadata["source_kind"] == "JSON" for chunk in result.chunks)


def test_csv_intake_marks_table_route_and_chunks_rows() -> None:
    result = run_document_intake("assets.csv", b"name,status\npump,ok\nvalve,inspect\n", chunk_size=80, overlap=10)

    assert result.status == "parsed"
    assert result.profile.parser_route == "tabular_document"
    assert result.profile.requires_table_structure_recognition is True
    assert result.chunks
    assert any("pump" in chunk.text for chunk in result.chunks)


def test_intake_result_to_dict_is_product_ui_ready() -> None:
    result = run_document_intake("note.md", b"# Pump\n\nCheck vibration every shift.", chunk_size=80, overlap=10)

    payload = result.to_dict()

    assert payload["status"] == "parsed"
    assert payload["profile"]["source_name"] == "note.md"
    assert payload["profile"]["parser_route"] == "text_document"
    assert payload["records_count"] == len(result.records)
    assert payload["chunk_count"] == len(result.chunks)
    assert payload["quality"]["quality_gate_status"] == "pass"
    assert payload["chunks"][0]["chunk_id"] == result.chunks[0].chunk_id
    assert payload["errors"] == []


def test_data_pipeline_package_exports_intake_entrypoint() -> None:
    from data_pipeline import run_document_intake as exported

    assert exported is run_document_intake


def test_pdf_needs_ocr_result_contains_ragflow_visual_task_plan() -> None:
    options = DocumentIntakeOptions(parser_backend="deepdoc", chunking_method="paper")

    result = run_document_intake("scan.pdf", b"%PDF-1.4\nimage-only placeholder", options=options)
    payload = result.to_dict()

    assert result.status == "needs_ocr"
    assert payload["processing_plan"]["parser_backend"] == "deepdoc"
    assert payload["processing_plan"]["chunking_method"] == "paper"
    assert payload["processing_plan"]["parse_chunk_decoupled"] is True
    assert payload["processing_plan"]["visual_tasks"] == [
        "ocr",
        "document_layout_recognition",
        "table_structure_recognition",
        "table_auto_rotation",
    ]
    assert payload["processing_plan"]["next_queue"] == [
        "ocr",
        "document_layout_recognition",
        "table_structure_recognition",
        "table_auto_rotation",
    ]
    assert payload["quality"]["pending_visual_tasks"] == payload["processing_plan"]["next_queue"]


def test_parsed_result_exposes_page_diagnostics_and_chunk_preview() -> None:
    result = run_document_intake(
        "manual.txt",
        b"Pump Manual\n\nInspect vibration and bearing temperature every shift.",
        chunk_size=80,
        overlap=10,
    )
    payload = result.to_dict()

    assert payload["page_diagnostics"][0]["record_id"] == "manual.txt::text"
    assert payload["page_diagnostics"][0]["page_num"] == -1
    assert payload["page_diagnostics"][0]["block_count"] >= 1
    assert payload["chunk_preview"]
    assert payload["chunk_preview"][0]["chunk_id"] == result.chunks[0].chunk_id
    assert payload["chunk_preview"][0]["citation_anchor"].startswith("manual.txt#")
    assert "text_preview" in payload["chunk_preview"][0]


def test_one_chunking_method_keeps_document_together() -> None:
    raw = (
        "Manual\n\n"
        + "Inspect vibration, temperature, pressure, oil level, alarm history, and interlock status. " * 8
    ).encode("utf-8")

    result = run_document_intake(
        "manual.txt",
        raw,
        chunk_size=80,
        overlap=10,
        options=DocumentIntakeOptions(chunking_method="one"),
    )

    assert result.status == "parsed"
    assert len(result.chunks) == 1
    assert result.to_dict()["processing_plan"]["chunking_method"] == "one"


def test_docling_only_formats_are_classified_as_first_class_documents() -> None:
    slides = classify_document("deck.pptx", b"PK\x03\x04")
    sheet = classify_document("assets.xlsx", b"PK\x03\x04")
    image = classify_document("scan.png", b"\x89PNG\r\n")

    assert slides.source_kind == "PPTX"
    assert slides.parser_route == "presentation_document"
    assert slides.requires_layout_analysis is True
    assert sheet.source_kind == "Spreadsheet"
    assert sheet.parser_route == "spreadsheet_document"
    assert sheet.requires_table_structure_recognition is True
    assert image.source_kind == "Image"
    assert image.parser_route == "image_document"
    assert image.requires_ocr is True


def test_auto_backend_uses_docling_for_presentation_documents(monkeypatch) -> None:
    import data_pipeline.document_intake as document_intake

    def fake_docling_records(raw_bytes: bytes, source_name: str):
        assert source_name == "deck.pptx"
        return [
            document_intake.SourceRecord(
                source_file=source_name,
                record_id=f"{source_name}::docling",
                filename=source_name,
                page_num=None,
                text="Slide Title\n\nInspect vibration.",
                blocks=[
                    document_intake.TextBlock(text="Slide Title", block_type="Title", order=0),
                    document_intake.TextBlock(text="Inspect vibration.", block_type="Para", order=1),
                ],
                metadata={
                    "source_kind": "PPTX",
                    "parser_backend": "docling",
                    "external_runtime": "docling",
                },
            )
        ]

    monkeypatch.setattr(document_intake, "load_docling_records", fake_docling_records)

    result = run_document_intake("deck.pptx", b"PK\x03\x04")
    payload = result.to_dict()

    assert result.status == "parsed"
    assert payload["processing_plan"]["parser_backend"] == "docling"
    assert payload["processing_plan"]["runtime"]["status"] == "used"
    assert payload["records"][0]["metadata"]["external_runtime"] == "docling"


def test_native_parser_rejects_docling_only_binary_formats() -> None:
    import data_pipeline.document_intake as document_intake

    with pytest.raises(ValueError, match="external parser"):
        document_intake.load_source_payload(b"PK\x03\x04", source_name="deck.pptx")
