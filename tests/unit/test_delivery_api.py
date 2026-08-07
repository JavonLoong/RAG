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
    assert client.post(f"/api/delivery/documents/{version_id}/publish").json()["status"] == "published"

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
    assert client.post(f"/api/delivery/graphs/{graph_version_id}/publish").json()["status"] == "published"

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


def test_delivery_api_rejects_invalid_base64(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    response = TestClient(app).post(
        "/api/delivery/documents/intake",
        json={"document_id": "bad", "source_name": "bad.txt", "content_base64": "%%%"},
    )
    assert response.status_code == 400
