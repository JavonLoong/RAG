from __future__ import annotations

import base64
import json
import sys
import time
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core_domain.delivery import FMEATaskRequest
from data_pipeline.document_intake import DocumentIntakeOptions, run_document_intake
from rag_orchestrator.delivery_remediation import DeliveryRemediationService
from rag_orchestrator.fmea import FMEAService
from storage_layer.governance_store import GovernanceStore
from storage_layer.graph_store import GraphStore

fitz = pytest.importorskip("fitz")
docx = pytest.importorskip("docx")
pil_image = pytest.importorskip("PIL.Image")


API_SRC = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from chroma_rag_poc.api import create_app  # noqa: E402


def _scanned_pdf_bytes() -> bytes:
    image = pil_image.new("RGB", (480, 180), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    document = fitz.open()
    page = document.new_page(width=480, height=180)
    page.insert_image(page.rect, stream=output.getvalue())
    return document.tobytes()


def _structural_docx_bytes() -> bytes:
    document = docx.Document()
    document.add_heading("Maintenance Manual", level=1)
    document.add_paragraph("Paragraph before table.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Failure mode"
    table.cell(0, 1).text = "Cause"
    table.cell(1, 0).text = "Filter blockage"
    table.cell(1, 1).text = "Oil contamination"
    document.add_paragraph("Paragraph after table.")
    image = pil_image.new("RGB", (32, 32), "blue")
    image_bytes = BytesIO()
    image.save(image_bytes, format="PNG")
    image_bytes.seek(0)
    document.add_picture(image_bytes)
    document.add_paragraph("Figure 1 Lubrication filter", style="Caption")
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _good_ocr(_image: bytes, page: int, _source: str) -> dict:
    return {
        "text": "Lubrication filter blockage may be caused by contamination.",
        "confidence": 0.94,
        "blocks": [
            {
                "block_id": f"p{page}-title",
                "type": "Title",
                "order": 0,
                "text": "Lubrication System",
                "bbox": [10, 10, 220, 35],
            },
            {
                "block_id": f"p{page}-table-row",
                "type": "Table",
                "order": 1,
                "text": "Filter blockage | Oil contamination",
                "table_id": f"p{page}-table-1",
                "bbox": [10, 50, 440, 110],
            },
            {
                "block_id": f"p{page}-image",
                "type": "Image",
                "order": 2,
                "text": "Filter location diagram",
                "image_id": f"p{page}-image-1",
                "bbox": [10, 115, 180, 165],
            },
            {
                "block_id": f"p{page}-caption",
                "type": "Caption",
                "order": 3,
                "text": "Figure 1 Filter location",
                "caption_for": f"p{page}-image-1",
            },
        ],
        "tables": [
            {
                "table_id": f"p{page}-table-1",
                "expected_columns": 2,
                "rows": [["Failure mode", "Cause"], ["Filter blockage", "Oil contamination"]],
            }
        ],
    }


def test_language_repair_preserves_original_and_generates_aligned_translation() -> None:
    calls: list[tuple[str, str, str]] = []

    def translator(text: str, source: str, target: str) -> str:
        calls.append((text, source, target))
        return "燃气轮机过滤器堵塞。"

    intake = run_document_intake(
        "manual.txt",
        b"Gas tur-\nbine filter blockage.",
        options=DocumentIntakeOptions(translation_target="zh"),
        translator=translator,
    )

    assert intake.status == "parsed"
    record = intake.records[0]
    assert record.metadata["detected_language"] == "en"
    assert record.metadata["original_text"] == "Gas tur-\nbine filter blockage."
    assert "Gas turbine" in record.text
    alignment = json.loads(record.metadata["translation_alignment_json"])
    assert alignment[0]["source_text"] == "Gas turbine filter blockage."
    assert alignment[0]["translated_text"] == "燃气轮机过滤器堵塞。"
    assert alignment[0]["block_id"] == record.blocks[0].block_id
    assert calls == [("Gas turbine filter blockage.", "en", "zh")]
    assert intake.quality["annotation"]["translation_target"] == "zh"

    chinese = run_document_intake("中文资料.txt", "燃气轮机过滤器堵塞。".encode())
    assert chinese.records[0].metadata["detected_language"] == "zh"
    assert chinese.records[0].metadata["original_text"] == "燃气轮机过滤器堵塞。"


def test_docx_preserves_interleaved_table_image_caption_and_chunk_locators() -> None:
    intake = run_document_intake("manual.docx", _structural_docx_bytes(), chunk_size=180, overlap=20)

    assert intake.status == "parsed"
    blocks = intake.records[0].blocks
    block_types = [block.block_type for block in blocks]
    assert block_types.index("Table") < block_types.index("Para", block_types.index("Table"))
    table_blocks = [block for block in blocks if block.table_id]
    image_blocks = [block for block in blocks if block.image_id]
    caption_blocks = [block for block in blocks if block.caption_for]
    assert len({block.table_id for block in table_blocks}) == 1
    assert image_blocks and caption_blocks
    assert caption_blocks[0].caption_for == image_blocks[0].image_id
    assert all(block.block_id for block in blocks)
    assert any(chunk.metadata.get("table_id") for chunk in intake.chunks)
    assert any(chunk.metadata.get("image_id") for chunk in intake.chunks)
    assert intake.quality["structural_locators"]["captions"] == 1


def test_delivery_api_connects_requested_translation_to_evidence_metadata(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    app.state.m2_translation_provider = lambda _text, _source, _target: "燃气轮机过滤器堵塞。"
    client = TestClient(app)
    response = client.post(
        "/api/delivery/documents/intake",
        json={
            "document_id": "translated-manual",
            "source_name": "manual.txt",
            "content_base64": base64.b64encode(b"Gas turbine filter blockage.").decode("ascii"),
            "translation_target": "zh",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["intake"]["quality"]["annotation"]["translation_target"] == "zh"
    version = client.get(
        f"/api/delivery/documents/{payload['document_version']['version_id']}"
    ).json()
    alignment = json.loads(version["evidence"][0]["metadata"]["translation_alignment_json"])
    assert alignment[0]["translated_text"] == "燃气轮机过滤器堵塞。"
    assert version["evidence"][0]["metadata"]["detected_language"] == "en"


def test_auto_ocr_job_persists_source_and_builds_page_comparison_package(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    app.state.m2_ocr_provider = _good_ocr
    client = TestClient(app)
    source = _scanned_pdf_bytes()

    response = client.post(
        "/api/delivery/documents/intake",
        json={
            "document_id": "scan-auto",
            "source_name": "scan.pdf",
            "content_base64": base64.b64encode(source).decode("ascii"),
            "auto_run_ocr": True,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ocr_job"]["status"] == "completed"
    assert payload["ocr_job"]["attempts"] == 1
    version = payload["document_version"]
    assert version["version"] == 2
    assert {item["table_id"] for item in version["evidence"] if item["table_id"]} == {"p1-table-1"}
    assert {item["image_id"] for item in version["evidence"] if item["image_id"]} == {"p1-image-1"}

    citation = client.get(
        f"/api/delivery/evidence/{version['evidence'][0]['evidence_id']}/open"
    )
    assert citation.status_code == 200, citation.text
    assert citation.json()["source"]["page"] == 1
    assert citation.json()["source"]["mime_type"] == "image/png"
    assert citation.json()["source"]["content_base64"]

    review = client.get(
        f"/api/delivery/documents/{version['version_id']}/review-package",
        params={"page": 1},
    )
    assert review.status_code == 200, review.text
    review_payload = review.json()
    assert review_payload["source_preview"]["mime_type"] == "image/png"
    assert base64.b64decode(review_payload["source_preview"]["content_base64"])
    assert review_payload["editable_candidate"]
    assert review_payload["review_tasks"][0]["status"] == "open"

    asset_page = client.get(
        f"/api/delivery/documents/source-assets/{payload['source_asset']['asset_id']}/pages/1"
    )
    assert asset_page.status_code == 200
    assert asset_page.headers["content-type"].startswith("image/png")


def test_table_misalignment_is_blocking_and_bound_to_table_evidence(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    client = TestClient(app)
    source = _scanned_pdf_bytes()
    response = client.post(
        "/api/delivery/documents/intake/ocr-result",
        json={
            "document_id": "bad-table",
            "source_name": "bad-table.pdf",
            "source_content_base64": base64.b64encode(source).decode("ascii"),
            "expected_pages": 1,
            "pages": [
                {
                    "page": 1,
                    "text": "A | B\nC",
                    "confidence": 0.9,
                    "blocks": [
                        {
                            "block_id": "p1-table-row",
                            "type": "Table",
                            "text": "A | B\nC",
                            "table_id": "table-1",
                        }
                    ],
                    "tables": [
                        {
                            "table_id": "table-1",
                            "expected_columns": 2,
                            "rows": [["A", "B"], ["C"]],
                        }
                    ],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ocr_quality"]["quality_gate_status"] == "fail"
    issues = [
        item for item in payload["document_version"]["quality_issues"] if item["code"] == "table_misalignment"
    ]
    assert len(issues) == 1
    assert issues[0]["metadata"]["table_id"] == "table-1"
    assert issues[0]["evidence_ids"]


def test_ocr_timeout_is_audited_and_job_can_be_retried(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")

    def slow_ocr(_image: bytes, _page: int, _source: str) -> dict:
        time.sleep(0.08)
        return {"text": "late", "confidence": 0.9}

    app.state.m2_ocr_provider = slow_ocr
    client = TestClient(app)
    response = client.post(
        "/api/delivery/documents/intake",
        json={
            "document_id": "scan-timeout",
            "source_name": "scan.pdf",
            "content_base64": base64.b64encode(_scanned_pdf_bytes()).decode("ascii"),
            "ocr_page_timeout_seconds": 0.01,
        },
    )
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["ocr_job"]["status"] == "needs_review"
    assert first["ocr_quality"]["timeout_pages"] == [1]
    issue_codes = {item["code"] for item in first["document_version"]["quality_issues"]}
    assert "ocr_timeout" in issue_codes

    app.state.m2_ocr_provider = _good_ocr
    retried = client.post(f"/api/delivery/documents/ocr-jobs/{first['ocr_job']['job_id']}/run")
    assert retried.status_code == 200, retried.text
    retry_payload = retried.json()
    assert retry_payload["ocr_job"]["attempts"] == 2
    assert retry_payload["ocr_job"]["status"] == "completed"
    assert retry_payload["ocr_quality"]["timeout_pages"] == []


def test_ocr_failed_page_can_be_retried_as_background_task(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")

    def failing_ocr(_image: bytes, page: int, _source: str) -> dict:
        raise RuntimeError(f"page {page} failed")  # noqa: TRY003

    app.state.m2_ocr_provider = failing_ocr
    client = TestClient(app)
    first = client.post(
        "/api/delivery/documents/intake",
        json={
            "document_id": "scan-page-retry",
            "source_name": "scan.pdf",
            "content_base64": base64.b64encode(_scanned_pdf_bytes()).decode("ascii"),
        },
    ).json()
    job = first["ocr_job"]
    assert job["pages"][0]["status"] == "error"
    assert job["pages"][0]["ocr_engine"] == "failing_ocr"
    assert job["pages"][0]["duration_ms"] >= 0

    app.state.m2_ocr_provider = _good_ocr
    queued = client.post(
        f"/api/delivery/documents/ocr-jobs/{job['job_id']}/retry-pages",
        json={"pages": [1], "idempotency_key": "retry-page-one"},
    )
    assert queued.status_code == 202, queued.text
    delivery_task = client.get(
        f"/api/delivery/tasks/{queued.json()['task']['task_id']}"
    ).json()
    assert delivery_task["status"] == "needs_review"
    result = delivery_task["result"]
    assert result["retried_pages"] == [1]
    assert result["ocr_job"]["pages"][0]["status"] == "ok"
    assert result["ocr_job"]["pages"][0]["ocr_engine"] == "_good_ocr"
    assert result["document_version"]["metadata"]["retry_of_version_id"]


def test_reject_decision_is_durable_and_closes_review_task(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    client = TestClient(app)
    intake = client.post(
        "/api/delivery/documents/intake",
        json={
            "document_id": "reject-manual",
            "source_name": "manual.txt",
            "content_base64": base64.b64encode(b"Pump manual and inspection steps.").decode("ascii"),
        },
    ).json()
    version_id = intake["document_version"]["version_id"]
    rejected = client.post(
        f"/api/delivery/documents/{version_id}/review",
        json={"reviewer": "reviewer", "decision": "reject", "comment": "Source is not authoritative."},
    )
    assert rejected.status_code == 200, rejected.text
    review_package = client.get(f"/api/delivery/documents/{version_id}/review-package").json()
    assert review_package["review_history"][-1]["decision"] == "reject"
    assert review_package["review_tasks"][0]["status"] == "rejected"
    publish = client.post(f"/api/delivery/documents/{version_id}/publish")
    assert publish.status_code == 400


def test_m2_feedback_rebuilds_index_graph_and_fmea_after_human_gates(tmp_path: Path) -> None:
    class RecordingIndex:
        def __init__(self) -> None:
            self.rebuilds: list[list[str]] = []

        def rebuild(self, documents, *, created_by="system"):
            versions = [item.version_id for item in documents]
            self.rebuilds.append(versions)
            return {"operation": "rebuild", "document_versions": versions, "indexed_chunks": len(versions)}

    store = GovernanceStore(tmp_path / "governance.sqlite3")
    document = store.create_document_candidate(
        document_id="feedback-manual",
        source_name="manual.txt",
        chunks=[
            {
                "chunk_id": "chunk-1",
                "text": "lubrication system filter blockage may be caused by dirty oil.",
                "page": 1,
            }
        ],
    )
    store.record_review(
        target_type="document", target_id=document.version_id, reviewer="reviewer", decision="approve"
    )
    document = store.publish_document(document.version_id)
    evidence_id = document.evidence[0].evidence_id
    graph = store.create_graph_candidate(
        source_document_version_ids=[document.version_id],
        statements=[
            {
                "subject": "lubrication system",
                "predicate": "HAS_FAILURE_MODE",
                "object": "filter blockage",
                "subject_type": "COMPONENT",
                "object_type": "FAILURE_MODE",
                "evidence_ids": [evidence_id],
                "confidence": 0.95,
            }
        ],
    )
    store.record_review(target_type="graph", target_id=graph.graph_version_id, reviewer="reviewer", decision="approve")
    graph = store.publish_graph(graph.graph_version_id)
    task = FMEAService(store).run(
        FMEATaskRequest(
            requested_by="reviewer",
            graph_version_id=graph.graph_version_id,
            document_version_ids=(document.version_id,),
        )
    )
    feedback = store.add_feedback(
        task_id=task.task_id,
        code="ocr_text_error",
        message="Correct the OCR cause and rebuild downstream artifacts.",
        created_by="reviewer",
    )
    assert feedback["routed_module"] == "M2"

    index = RecordingIndex()
    remediation = DeliveryRemediationService(
        store,
        document_index=index,  # type: ignore[arg-type]
        graph_store=GraphStore(tmp_path / "graph.sqlite3"),
    )
    correction = remediation.remediate(
        feedback["feedback_id"],
        actor="ocr-reviewer",
        document_version_id=document.version_id,
        corrections={
            evidence_id: {
                "text": (
                    "lubrication system filter blockage may be caused by oil contamination, "
                    "leading to pressure loss, detected by a pressure sensor, mitigated by filter replacement."
                )
            }
        },
    )
    revised_id = correction["result"]["document_version"]["version_id"]
    assert correction["result"]["review_task"]["status"] == "open"
    store.record_review(target_type="document", target_id=revised_id, reviewer="reviewer", decision="approve")
    store.publish_document(revised_id)

    rebuilt = remediation.remediate(
        feedback["feedback_id"], actor="reviewer", document_version_id=revised_id
    )
    graph_candidate_id = rebuilt["result"]["graph_candidate"]["graph_version_id"]
    assert rebuilt["action"] == "rebuild_index_and_create_graph_candidate"
    assert index.rebuilds[-1] == [revised_id]
    store.record_review(
        target_type="graph", target_id=graph_candidate_id, reviewer="graph-reviewer", decision="approve"
    )
    store.publish_graph(graph_candidate_id)

    completed = remediation.remediate(
        feedback["feedback_id"], actor="graph-reviewer", graph_version_id=graph_candidate_id
    )
    assert completed["status"] == "completed"
    assert completed["feedback_status"] == "resolved"
    assert list(completed["result"]["new_fmea_task"]["request"]["document_version_ids"]) == [revised_id]
