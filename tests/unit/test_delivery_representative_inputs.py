from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from data_pipeline.document_intake import run_document_intake

fitz = pytest.importorskip("fitz")
docx = pytest.importorskip("docx")
pil_image = pytest.importorskip("PIL.Image")
pil_draw = pytest.importorskip("PIL.ImageDraw")


def _native_pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    return document.tobytes()


def _image_bytes(text: str) -> bytes:
    image = pil_image.new("RGB", (640, 240), "white")
    pil_draw.Draw(image).text((24, 96), text, fill="black")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _scanned_pdf_bytes(text: str) -> bytes:
    image_bytes = _image_bytes(text)
    document = fitz.open()
    page = document.new_page(width=640, height=240)
    page.insert_image(page.rect, stream=image_bytes)
    return document.tobytes()


def _docx_bytes() -> bytes:
    output = BytesIO()
    document = docx.Document()
    document.add_heading("Lubrication System", level=1)
    document.add_paragraph("Filter blockage may be caused by oil contamination.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Failure mode"
    table.cell(0, 1).text = "Cause"
    table.cell(1, 0).text = "Filter blockage"
    table.cell(1, 1).text = "Oil contamination"
    document.save(output)
    return output.getvalue()


def test_representative_native_pdf_docx_and_multilingual_text_are_parsed() -> None:
    native_pdf = run_document_intake(
        "native.pdf",
        _native_pdf_bytes("Gas turbine filter blockage causes pressure loss."),
        chunk_size=120,
        overlap=10,
    )
    assert native_pdf.status == "parsed"
    assert native_pdf.profile.parser_route == "pdf_deepdoc_ready"
    assert native_pdf.records[0].page_num == 1

    office = run_document_intake("manual.docx", _docx_bytes(), chunk_size=160, overlap=20)
    assert office.status == "parsed"
    assert office.profile.parser_route == "office_document"
    assert any("Filter blockage" in item.text for item in office.records)

    chinese = run_document_intake(
        "中文资料.txt",
        "燃气轮机润滑油系统的过滤器堵塞可能由油液污染导致。".encode(),
        chunk_size=100,
        overlap=10,
    )
    english = run_document_intake(
        "english.txt",
        b"Gas turbine bearing wear can cause vibration.",
        chunk_size=100,
        overlap=10,
    )
    assert chinese.status == english.status == "parsed"
    assert chinese.chunks and english.chunks


def test_scanned_pdf_and_image_are_routed_to_ocr_instead_of_silent_indexing() -> None:
    scanned = run_document_intake(
        "scan.pdf",
        _scanned_pdf_bytes("SCANNED GAS TURBINE PAGE"),
        chunk_size=120,
        overlap=10,
    )
    assert scanned.status == "needs_ocr"
    assert scanned.profile.requires_ocr is True
    assert not scanned.chunks

    image = run_document_intake(
        "page.png",
        _image_bytes("GAS TURBINE IMAGE PAGE"),
        chunk_size=120,
        overlap=10,
    )
    assert image.status == "failed"
    assert image.profile.requires_ocr is True
    assert not image.chunks
    assert any("external parser" in message for message in image.errors)


def test_partial_ocr_pages_create_blocking_quality_evidence(tmp_path: Path) -> None:
    api_src = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
    import sys

    if str(api_src) not in sys.path:
        sys.path.insert(0, str(api_src))
    from chroma_rag_poc.api import create_app

    client = TestClient(create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads"))
    response = client.post(
        "/api/delivery/documents/intake/ocr-result",
        json={
            "document_id": "partial-scan",
            "source_name": "partial.pdf",
            "expected_pages": 3,
            "pages": [
                {"page": 1, "text": "第一页", "confidence": 0.9},
                {"page": 3, "text": "第三页", "confidence": 0.9},
            ],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ocr_quality"]["missing_pages"] == [2]
    assert payload["ocr_quality"]["quality_gate_status"] == "fail"
    issue_codes = {item["code"] for item in payload["document_version"]["quality_issues"]}
    assert {"intake_not_parsed", "quality_gate_failed", "intake_error"} <= issue_codes


def test_two_week_demo_package_closes_the_m2_m5_loop(tmp_path: Path) -> None:
    from scripts.run_governed_delivery_demo import run_demo

    manifest = run_demo(tmp_path / "demo")
    output_dir = Path(manifest["output_dir"])

    assert manifest["acceptance"]["closed_loop_pass"] is True
    assert manifest["m2"]["page_locator_preserved"] is True
    assert manifest["m4"]["path_found"] is True
    assert manifest["m5"]["export_consistency"]["consistent"] is True
    assert (output_dir / "两周开发进度验收报告.md").is_file()
    assert (output_dir / "fmea.json").is_file()
    assert (output_dir / "fmea.csv").is_file()
    assert (output_dir / "feedback_remediation.json").is_file()
