from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

API_SRC = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from chroma_rag_poc.api import create_app  # noqa: E402


def test_acceptance_workbench_collects_versioned_evidence_and_builds_package(
    tmp_path: Path,
) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    app.state.acceptance_input_dir = tmp_path / "acceptance-inputs"
    app.state.acceptance_output_dir = tmp_path / "acceptance-output"
    client = TestClient(app)

    for static_path in (
        "/modules/pages/acceptance-page.js",
        "/styles/console.css",
        "/demo_data/power_equipment_demo.json",
    ):
        static_response = client.get(static_path)
        assert static_response.status_code == 200, static_path

    schema = client.get("/api/delivery/acceptance/schema")
    assert schema.status_code == 200, schema.text
    assert {item["key"] for item in schema.json()["artifacts"]} >= {
        "ocr_coverage",
        "retrieval_gold",
        "graph_gold",
        "large_file",
    }
    initial = client.get("/api/delivery/acceptance/status")
    assert initial.status_code == 200, initial.text
    assert initial.json()["work_items"]["open_item_count"] == 12

    candidates = app.state.acceptance_input_dir / "candidates"
    candidates.mkdir(parents=True)
    (candidates / "performance_candidate.json").write_text(
        json.dumps({"_status": "pending_human_review"}),
        encoding="utf-8",
    )
    with_candidate = client.get("/api/delivery/acceptance/status")
    tech15 = next(
        item
        for item in with_candidate.json()["work_items"]["items"]
        if item["acceptance_id"] == "TECH-15"
    )
    assert tech15["candidate_status"] == "pending_human_review"
    assert tech15["candidate_files"] == ["candidates/performance_candidate.json"]
    loaded_candidate = client.get("/api/delivery/acceptance/candidates/TECH-15")
    assert loaded_candidate.status_code == 200, loaded_candidate.text
    assert loaded_candidate.json()["artifact_key"] == "performance"
    assert loaded_candidate.json()["formal_sha256"] is None
    assert loaded_candidate.json()["payload"]["_status"] == "pending_human_review"
    assert len(loaded_candidate.json()["sources"][0]["sha256"]) == 64

    evidence = client.post(
        "/api/delivery/acceptance/evidence",
        data={"gate_id": "TECH-16"},
        files={"file": ("browser-observation.txt", b"progress visible; browser responsive", "text/plain")},
    )
    assert evidence.status_code == 201, evidence.text
    evidence_payload = evidence.json()
    assert len(evidence_payload["sha256"]) == 64
    evidence_ref = evidence_payload["evidence_ref"]
    downloaded = client.get(f"/api/delivery/acceptance/evidence/{evidence_ref}")
    assert downloaded.status_code == 200
    assert downloaded.content == b"progress visible; browser responsive"

    large_file_payload = {
        "file_size_mb": 60,
        "task_id": "task-upload-60mb",
        "source_sha256": "a" * 64,
        "asynchronous": True,
        "progress_visible": True,
        "browser_frozen": False,
        "request_timed_out": False,
        "review": {
            "reviewer": "ui-observer-a",
            "reviewed_at": "2026-09-02T00:00:00Z",
            "evidence_refs": [evidence_ref],
        },
    }
    saved = client.put(
        "/api/delivery/acceptance/artifacts/large_file",
        json={"payload": large_file_payload},
    )
    assert saved.status_code == 200, saved.text
    artifact_sha256 = saved.json()["sha256"]
    assert saved.json()["status"]["gates"]["TECH-16"]["status"] == "passed"

    lost_update = client.put(
        "/api/delivery/acceptance/artifacts/large_file",
        json={"payload": large_file_payload},
    )
    assert lost_update.status_code == 409
    assert lost_update.json()["detail"]["code"] == "acceptance_expected_sha256_required"
    updated = client.put(
        "/api/delivery/acceptance/artifacts/large_file",
        json={"payload": large_file_payload, "expected_sha256": artifact_sha256},
    )
    assert updated.status_code == 200, updated.text

    built = client.post("/api/delivery/acceptance/build-package")
    assert built.status_code == 200, built.text
    assert built.json()["overall_status"] == "not_accepted"
    assert built.json()["work_items"]["open_item_count"] == 11
    package_files = {item["filename"] for item in built.json()["package_files"]}
    assert "human_review_handoff.md" in package_files
    handoff = client.get("/api/delivery/acceptance/handoff")
    assert handoff.status_code == 200, handoff.text
    assert "PowerRAG PRD 人工验收交接包" in handoff.json()["content"]
    assert len(handoff.json()["sha256"]) == 64
    downloaded_handoff = client.get(
        "/api/delivery/acceptance/package-files/human_review_handoff.md"
    )
    assert downloaded_handoff.status_code == 200, downloaded_handoff.text
    assert "人工验收交接包" in downloaded_handoff.text
    assert client.get("/api/delivery/acceptance/package-files/secret.txt").status_code == 404
    manifest = json.loads(
        (app.state.acceptance_output_dir / "manifest.json").read_text(encoding="utf-8")
    )
    manifest_paths = {item["path"] for item in manifest["inputs"]}
    assert evidence_ref in manifest_paths
    assert "acceptance_audit.jsonl" in manifest_paths
