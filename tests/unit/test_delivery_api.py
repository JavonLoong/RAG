from __future__ import annotations

# ruff: noqa: RUF001
import base64
import sys
from pathlib import Path

from fastapi.testclient import TestClient

API_SRC = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from chroma_rag_poc.api import create_app  # noqa: E402


def test_delivery_api_exposes_reviewed_document_graph_and_fmea_flow(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    client = TestClient(app)
    text = "燃气轮机润滑油系统的过滤器堵塞由油液污染导致，影响润滑油压。使用压差监测检测，并采用更换滤芯措施。"
    intake = client.post(
        "/api/delivery/documents/intake",
        json={
            "document_id": "api-manual",
            "source_name": "manual.txt",
            "content_base64": base64.b64encode(text.encode()).decode(),
            "chunk_size": 80,
            "overlap": 10,
        },
    )
    assert intake.status_code == 200, intake.text
    version_id = intake.json()["document_version"]["version_id"]
    detail = client.get(f"/api/delivery/documents/{version_id}").json()
    evidence_id = detail["evidence"][0]["evidence_id"]

    review = client.post(
        f"/api/delivery/documents/{version_id}/review",
        json={"reviewer": "document-expert", "decision": "approve"},
    )
    assert review.status_code == 200
    published_document = client.post(f"/api/delivery/documents/{version_id}/publish").json()
    assert published_document["status"] == "published"
    assert published_document["retrieval_index"]["indexed_chunks"] >= 1
    indexed = client.get(
        "/api/delivery/documents-search",
        params={"q": "过滤器堵塞", "version_ids": version_id},
    )
    assert indexed.status_code == 200, indexed.text
    assert indexed.json()["results"][0]["locator"]["document_version_id"] == version_id

    facts = [
        ("润滑油系统", "属于", "燃气轮机", "COMPONENT", "EQUIPMENT"),
        ("润滑油系统", "故障模式", "过滤器堵塞", "COMPONENT", "FAILURE_MODE"),
        ("过滤器堵塞", "原因", "油液污染", "FAILURE_MODE", "CAUSE"),
        ("过滤器堵塞", "影响", "润滑油压下降", "FAILURE_MODE", "EFFECT"),
        ("过滤器堵塞", "检测方法", "压差监测", "FAILURE_MODE", "DETECTION_METHOD"),
        ("过滤器堵塞", "措施", "更换滤芯", "FAILURE_MODE", "ACTION"),
    ]
    graph_response = client.post(
        "/api/delivery/graphs/candidates",
        json={
            "source_document_version_ids": [version_id],
            "statements": [
                {
                    "subject": subject,
                    "predicate": predicate,
                    "object": obj,
                    "subject_type": subject_type,
                    "object_type": object_type,
                    "evidence_ids": [evidence_id],
                    "confidence": 0.9,
                }
                for subject, predicate, obj, subject_type, object_type in facts
            ],
        },
    )
    assert graph_response.status_code == 200, graph_response.text
    graph_version_id = graph_response.json()["graph_version_id"]
    assert (
        client.post(
            f"/api/delivery/graphs/{graph_version_id}/review",
            json={"reviewer": "graph-expert", "decision": "approve"},
        ).status_code
        == 200
    )
    published_graph = client.post(f"/api/delivery/graphs/{graph_version_id}/publish").json()
    assert published_graph["status"] == "published"
    assert published_graph["graph_store_sync"]["edge_count"] == 6

    task_response = client.post(
        "/api/delivery/fmea/tasks",
        json={
            "requested_by": "纪文龙",
            "graph_version_id": graph_version_id,
            "document_version_ids": [version_id],
        },
    )
    assert task_response.status_code == 200, task_response.text
    task = task_response.json()
    task_id = task["task_id"]
    assert task["items"][0]["fields"]["failure_mode"] == "过滤器堵塞"
    assert task["items"][0]["field_evidence"]["cause"] == [evidence_id]
    assert (
        client.post(
            f"/api/delivery/fmea/tasks/{task_id}/review",
            json={"reviewer": "fmea-expert", "decision": "approve"},
        ).json()["status"]
        == "approved"
    )
    assert client.post(f"/api/delivery/fmea/tasks/{task_id}/publish").json()["status"] == "published"
    exported = client.get(f"/api/delivery/fmea/tasks/{task_id}/export?format=csv")
    assert exported.status_code == 200
    assert "过滤器堵塞" in exported.text
    export_check = client.get(f"/api/delivery/fmea/tasks/{task_id}/export-verify")
    assert export_check.status_code == 200, export_check.text
    assert export_check.json() == {
        "task_id": task_id,
        "status": "published",
        "consistent": True,
        "json_rows": 1,
        "csv_rows": 1,
        "mismatches": [],
    }

    feedback = client.post(
        f"/api/delivery/fmea/tasks/{task_id}/feedback",
        json={
            "code": "index_stale",
            "message": "Published material index should be rebuilt",
            "created_by": "reviewer",
        },
    )
    assert feedback.status_code == 200, feedback.text
    feedback_id = feedback.json()["feedback_id"]
    assert feedback.json()["routed_module"] == "M3"
    remediation = client.post(
        f"/api/delivery/fmea/feedback/{feedback_id}/remediate",
        json={"actor": "index-operator"},
    )
    assert remediation.status_code == 200, remediation.text
    assert remediation.json()["action"] == "rebuild_published_material_index"
    assert remediation.json()["status"] == "completed"
    assert remediation.json()["feedback_status"] == "resolved"
    runs = client.get(f"/api/delivery/fmea/feedback/{feedback_id}/runs")
    assert runs.status_code == 200
    assert runs.json()["items"][0]["result"]["operation"] == "rebuild"


def test_delivery_api_automatically_extracts_syncs_and_paths_graph(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    client = TestClient(app)
    text = (
        "燃气轮机润滑油系统的过滤器堵塞可能由油液污染导致，影响是润滑油压下降。"
        "可通过压差监测发现，并通过更换滤芯和清洁油路处理。"
    )
    intake = client.post(
        "/api/delivery/documents/intake",
        json={
            "document_id": "auto-manual",
            "source_name": "auto-manual.txt",
            "content_base64": base64.b64encode(text.encode()).decode(),
            "chunk_size": 200,
            "overlap": 20,
        },
    )
    assert intake.status_code == 200, intake.text
    version_id = intake.json()["document_version"]["version_id"]
    assert client.post(
        f"/api/delivery/documents/{version_id}/review",
        json={"reviewer": "document-expert", "decision": "approve"},
    ).status_code == 200
    assert client.post(f"/api/delivery/documents/{version_id}/publish").status_code == 200

    extracted = client.post(
        "/api/delivery/graphs/extract",
        json={
            "source_document_version_ids": [version_id],
            "backend": "rules",
            "metadata": {"purpose": "two-week-demo"},
        },
    )
    assert extracted.status_code == 200, extracted.text
    graph = extracted.json()
    assert graph["extraction"]["automatic_extraction"] is True
    assert graph["extraction"]["candidate_statement_count"] == 6
    graph_version_id = graph["graph_version_id"]
    assert {item["predicate"] for item in graph["statements"]} == {
        "PART_OF",
        "HAS_FAILURE_MODE",
        "CAUSED_BY",
        "HAS_EFFECT",
        "DETECTED_BY",
        "MITIGATED_BY",
    }

    assert client.post(
        f"/api/delivery/graphs/{graph_version_id}/review",
        json={"reviewer": "graph-expert", "decision": "approve"},
    ).status_code == 200
    published = client.post(f"/api/delivery/graphs/{graph_version_id}/publish")
    assert published.status_code == 200, published.text
    assert published.json()["graph_store_sync"]["edge_count"] == 6

    active_graph = client.get("/api/delivery/graphs-active/status")
    assert active_graph.status_code == 200, active_graph.text
    assert active_graph.json()["edge_count"] == 6

    path = client.get(
        f"/api/delivery/graphs/{graph_version_id}/path",
        params={"source": "燃气轮机", "target": "油液污染", "max_hops": 4},
    )
    assert path.status_code == 200, path.text
    path_payload = path.json()
    assert path_payload["found"] is True
    assert path_payload["nodes"] == ["燃气轮机", "润滑油系统", "过滤器堵塞", "油液污染"]
    assert all(edge["evidence"] for edge in path_payload["edges"])

    rebuilt = client.post("/api/delivery/documents-index/rebuild")
    assert rebuilt.status_code == 200, rebuilt.text
    assert rebuilt.json()["document_versions"] == [version_id]


def test_delivery_api_rejects_invalid_base64(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    response = TestClient(app).post(
        "/api/delivery/documents/intake",
        json={"document_id": "bad", "source_name": "bad.txt", "content_base64": "%%%"},
    )
    assert response.status_code == 400


def test_delivery_api_accepts_page_level_ocr_quality_and_revision(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    client = TestClient(app)
    response = client.post(
        "/api/delivery/documents/intake/ocr-result",
        json={
            "document_id": "ocr-manual",
            "source_name": "scan.pdf",
            "expected_pages": 2,
            "low_confidence_threshold": 0.6,
            "pages": [
                {
                    "page": 1,
                    "text": "润滑油系统的过滤器者塞可能由油液污染导致。",
                    "confidence": 0.45,
                    "reading_order_risk": "high",
                    "block_id": "p1-b1",
                },
                {
                    "page": 2,
                    "text": "可以通过压差监测发现。",
                    "confidence": 0.92,
                    "reading_order_risk": "low",
                    "block_id": "p2-b1",
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ocr_quality"]["low_confidence_pages"] == [1]
    assert payload["ocr_quality"]["layout_risk_pages"] == [1]
    version = payload["document_version"]
    assert version["status"] == "needs_review"
    assert version["evidence"][0]["page"] == "1"

    revised = client.post(
        f"/api/delivery/documents/{version['version_id']}/revise",
        json={
            "reviewer": "ocr-reviewer",
            "corrections": {
                version["evidence"][0]["evidence_id"]: {
                    "text": "润滑油系统的过滤器堵塞可能由油液污染导致。"
                }
            },
        },
    )
    assert revised.status_code == 200, revised.text
    revised_payload = revised.json()
    assert revised_payload["document_version"]["version"] == 2
    assert revised_payload["document_version"]["evidence"][0]["page"] == "1"
    assert revised_payload["reviews"][0]["decision"] == "modify"
