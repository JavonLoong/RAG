from __future__ import annotations

import json
import sys
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core_domain.delivery import TaskStatus
from storage_layer.project_workspace import PROJECT_DIRECTORIES, ProjectWorkspaceRegistry

API_SRC = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from chroma_rag_poc import routes_delivery  # noqa: E402
from chroma_rag_poc.api import create_app  # noqa: E402


def _chunk(text: str) -> dict[str, object]:
    return {
        "chunk_id": "chunk-1",
        "text": text,
        "source_file": "manual.txt",
        "page": 1,
    }


def test_project_workspaces_are_physically_isolated_and_objects_expose_project_id(tmp_path: Path) -> None:
    registry = ProjectWorkspaceRegistry(tmp_path / "projects")
    registry.create_project(project_id="alpha", name="Alpha", created_by="owner-a")
    registry.create_project(project_id="beta", name="Beta", created_by="owner-b")

    for project_id in ("alpha", "beta"):
        workspace = registry.project_dir(project_id)
        assert all((workspace / relative).is_dir() for relative in PROJECT_DIRECTORIES)
        assert (workspace / "manifests" / "project.json").is_file()

    alpha = registry.governance_store("alpha").create_document_candidate(
        document_id="same-document-id",
        source_name="manual.txt",
        chunks=[_chunk("alpha evidence")],
        intake_status="parsed",
    )
    beta = registry.governance_store("beta").create_document_candidate(
        document_id="same-document-id",
        source_name="manual.txt",
        chunks=[_chunk("beta evidence")],
        intake_status="parsed",
    )

    assert alpha.project_id == "alpha"
    assert beta.project_id == "beta"
    assert alpha.evidence[0].text == "alpha evidence"
    assert beta.evidence[0].text == "beta evidence"
    assert registry.governance_store("alpha").db_path != registry.governance_store("beta").db_path


def test_delivery_http_metrics_are_project_scoped_secret_free_and_expose_p95(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    client = TestClient(app)
    assert client.post(
        "/api/delivery/projects",
        json={"project_id": "metric-pilot", "name": "Metric Pilot", "created_by": "owner"},
    ).status_code == 201
    health = client.get(
        "/api/delivery/projects/metric-pilot/health?api_key=must-not-be-logged",
        headers={"X-Project-ID": "metric-pilot", "X-Correlation-ID": "metric-correlation"},
    )
    assert health.status_code == 200, health.text
    assert float(health.headers["x-response-time-ms"]) >= 0
    assert health.headers["server-timing"].startswith("app;dur=")
    summary = client.get(
        "/api/delivery/projects/metric-pilot/metrics/http",
        headers={"X-Project-ID": "metric-pilot"},
    )
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["sample_count"] >= 1
    assert payload["duration_ms"]["p95"] is not None
    assert payload["latest"][-1]["path"] == "/api/delivery/projects/metric-pilot/health"
    assert "api_key" not in json.dumps(payload)
    registry = app.state.project_workspace_registry
    task = registry.create_task(
        project_id="metric-pilot",
        task_type="failure-log-test",
        stage="forced_failure",
        created_by="tester",
    )
    try:
        raise RuntimeError("controlled background failure")  # noqa: TRY003, TRY301
    except RuntimeError as exc:
        registry.record_task_failure("metric-pilot", task.task_id, exc)
    failure_log = registry.project_dir("metric-pilot") / "logs" / "task-errors.jsonl"
    failure_payload = json.loads(failure_log.read_text(encoding="utf-8").splitlines()[-1])
    assert failure_payload["task_id"] == task.task_id
    assert "RuntimeError: controlled background failure" in failure_payload["stacktrace"]


def test_all_small_delivery_writes_support_header_idempotency(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    client = TestClient(app)
    headers = {"Idempotency-Key": "project-create-http-v1"}
    payload = {"project_id": "idempotent-pilot", "name": "Idempotent Pilot", "created_by": "owner"}

    first = client.post("/api/delivery/projects", headers=headers, json=payload)
    second = client.post("/api/delivery/projects", headers=headers, json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert first.headers["x-idempotency-replayed"] == "false"
    assert second.headers["x-idempotency-replayed"] == "true"

    changed = client.post(
        "/api/delivery/projects",
        headers=headers,
        json={**payload, "name": "Different Request"},
    )
    assert changed.status_code == 409
    assert changed.json()["detail"]["code"] == "idempotency_key_reused"


def test_project_graph_schema_catalog_is_versioned_approved_and_bound_to_graph_lineage(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    client = TestClient(app)
    assert client.post(
        "/api/delivery/projects",
        json={"project_id": "schema-pilot", "name": "Schema Pilot", "created_by": "owner"},
    ).status_code == 201
    headers = {"X-Project-ID": "schema-pilot"}
    builtins = client.get("/api/delivery/projects/schema-pilot/graph-schemas").json()["items"]
    assert {item["schema_id"] for item in builtins} == {
        "gas_turbine_fmea",
        "electric_motor_fmea",
    }
    definition = dict(
        next(item for item in builtins if item["schema_id"] == "electric_motor_fmea")["definition"]
    )
    definition["description"] = "项目专用电机 Schema"
    registered = client.post(
        "/api/delivery/projects/schema-pilot/graph-schemas",
        json={
            "schema_id": "plant_motor_fmea",
            "version": "2026.1",
            "definition": definition,
            "actor": "knowledge-engineer",
        },
    )
    assert registered.status_code == 201, registered.text
    assert registered.json()["status"] == "draft"
    approved = client.post(
        "/api/delivery/projects/schema-pilot/graph-schemas/plant_motor_fmea/2026.1/approve",
        json={"actor": "domain-reviewer"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    store = app.state.project_workspace_registry.governance_store("schema-pilot")
    document = store.create_document_candidate(
        document_id="motor-manual",
        source_name="motor.txt",
        chunks=[_chunk("电机具有故障模式轴承过热。")],
        intake_status="parsed",
    )
    store.record_review(
        target_type="document",
        target_id=document.version_id,
        reviewer="domain-reviewer",
        decision="approve",
    )
    document = store.publish_document(document.version_id)
    graph = client.post(
        "/api/delivery/graphs/candidates",
        headers=headers,
        json={
            "source_document_version_ids": [document.version_id],
            "schema_id": "plant_motor_fmea",
            "schema_version": "2026.1",
            "statements": [
                {
                    "statement_id": "motor-statement-1",
                    "subject": "电机",
                    "predicate": "HAS_FAILURE_MODE",
                    "object": "轴承过热",
                    "subject_type": "EQUIPMENT",
                    "object_type": "FAILURE_MODE",
                    "evidence_ids": [document.evidence[0].evidence_id],
                    "confidence": 0.95,
                }
            ],
        },
    )
    assert graph.status_code == 200, graph.text
    lineage = graph.json()["metadata"]["schema_lineage"]
    assert lineage["schema_id"] == "plant_motor_fmea"
    assert lineage["version"] == "2026.1"
    assert lineage["content_hash"] == approved.json()["content_hash"]

    changed = {**definition, "min_confidence": 0.9}
    conflict = client.post(
        "/api/delivery/projects/schema-pilot/graph-schemas",
        json={
            "schema_id": "plant_motor_fmea",
            "version": "2026.1",
            "definition": changed,
            "actor": "knowledge-engineer",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "graph_schema_version_exists"


def test_p1_template_copy_assignment_comments_batch_retry_and_batch_review(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    client = TestClient(app)
    source = client.post(
        "/api/delivery/projects",
        json={
            "project_id": "template-source",
            "name": "Template Source",
            "created_by": "owner",
            "configuration": {"chunk_size": 700, "api_key": "must-not-copy"},
            "acceptance": {"recall_at_5": 0.8},
        },
    )
    assert source.status_code == 201, source.text
    registry = app.state.project_workspace_registry
    registry.upsert_provider(
        project_id="template-source",
        provider_id="custom-local-embed",
        capability="embedding",
        provider_type="local",
        actor="owner",
        model="embed-v2",
        health_status="ready",
        configuration={"endpoint": "http://127.0.0.1:9000", "api_key": "must-not-copy"},
    )
    copied = client.post(
        "/api/delivery/projects/template-source/copy-template",
        json={"project_id": "template-copy", "name": "Template Copy", "created_by": "owner"},
    )
    assert copied.status_code == 201, copied.text
    assert copied.json()["credentials_copied"] is False
    copied_project = client.get("/api/delivery/projects/template-copy").json()
    assert copied_project["configuration"] == {"chunk_size": 700}
    copied_provider = registry.get_provider("template-copy", "custom-local-embed")
    assert copied_provider["configuration"] == {"endpoint": "http://127.0.0.1:9000"}
    assert copied_provider["health_status"] == "unknown"

    headers = {"X-Project-ID": "template-copy"}
    task = client.post(
        "/api/delivery/projects/template-copy/tasks",
        headers=headers,
        json={"task_type": "index_rebuild", "stage": "queued", "created_by": "owner"},
    ).json()
    assigned = client.post(
        f"/api/delivery/tasks/{task['task_id']}/assign",
        headers=headers,
        json={"assignee": "knowledge-engineer", "actor": "owner"},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["assigned_to"] == "knowledge-engineer"
    comment = client.post(
        f"/api/delivery/tasks/{task['task_id']}/comments",
        headers=headers,
        json={"message": "Please validate the rebuilt snapshot", "actor": "reviewer"},
    )
    assert comment.status_code == 201, comment.text
    comments = client.get(f"/api/delivery/tasks/{task['task_id']}/comments", headers=headers).json()
    assert comments["count"] == 1
    assert comments["items"][0]["actor"] == client.get("/api/delivery/identity", headers=headers).json()["actor"]

    registry.claim_task(task["task_id"], worker_id="test-worker")
    registry.finish_task(
        task["task_id"],
        status=TaskStatus.FAILED,
        error_code="forced_failure",
        error_message="retry me",
        retryable=True,
        actor="test-worker",
    )
    batch_retry = client.post(
        "/api/delivery/tasks/batch-retry",
        headers=headers,
        json={"task_ids": [task["task_id"]], "actor": "owner", "idempotency_key": "batch-retry-v1"},
    )
    assert batch_retry.status_code == 200, batch_retry.text
    assert len(batch_retry.json()["items"]) == 1
    retried = client.get(
        f"/api/delivery/tasks/{batch_retry.json()['items'][0]['task_id']}",
        headers=headers,
    ).json()
    assert retried["status"] == "completed"

    upload = client.post(
        "/api/delivery/projects/template-copy/documents/upload",
        headers=headers,
        data={"document_id": "batch-review-doc"},
        files={"file": ("manual.txt", b"filter blockage due to contamination", "text/plain")},
    ).json()
    version_id = client.get(
        f"/api/delivery/tasks/{upload['task']['task_id']}", headers=headers
    ).json()["result"]["document_version"]["version_id"]
    batch_review = client.post(
        "/api/delivery/documents/batch-review",
        headers=headers,
        json={
            "version_ids": [version_id],
            "decision": "approve",
            "reviewer": "reviewer",
            "comment": "batch evidence checked",
            "idempotency_key": "batch-review-v1",
        },
    )
    assert batch_review.status_code == 200, batch_review.text
    assert batch_review.json()["publication_gate_bypassed"] is False
    assert client.get(f"/api/delivery/documents/{version_id}", headers=headers).json()["status"] != "published"


def test_task_center_enforces_idempotency_leases_filters_retry_and_audit(tmp_path: Path) -> None:
    registry = ProjectWorkspaceRegistry(tmp_path / "projects")
    registry.create_project(project_id="pilot", name="Pilot", created_by="owner")
    task = registry.create_task(
        project_id="pilot",
        task_type="document_intake",
        stage="queued",
        created_by="operator",
        payload={"document_id": "manual-1"},
        idempotency_key="upload-001",
        correlation_id="corr-001",
    )
    repeated = registry.create_task(
        project_id="pilot",
        task_type="document_intake",
        stage="queued",
        created_by="operator",
        idempotency_key="upload-001",
    )
    assert repeated.task_id == task.task_id

    running = registry.claim_task(task.task_id, worker_id="worker-1", lease_seconds=60)
    assert running.status is TaskStatus.RUNNING
    heartbeat = registry.heartbeat_task(
        task.task_id,
        worker_id="worker-1",
        progress=0.5,
        stage="parsing",
    )
    assert heartbeat.progress == 0.5
    assert heartbeat.stage == "parsing"
    failed = registry.finish_task(
        task.task_id,
        status=TaskStatus.FAILED,
        error_code="parser_timeout",
        error_message="Parser timed out",
        retryable=True,
        actor="worker-1",
    )
    assert failed.status is TaskStatus.FAILED
    assert failed.error_code == "parser_timeout"

    retried = registry.retry_task(task.task_id, actor="operator", idempotency_key="retry-001")
    assert retried.task_id != task.task_id
    assert retried.payload["retry_of"] == task.task_id
    assert retried.correlation_id == "corr-001"

    listed = registry.list_tasks(project_id="pilot", statuses=("failed",), stage="parsing")
    assert [item["task_id"] for item in listed["items"]] == [task.task_id]
    audit = registry.list_audit(project_id="pilot", object_type="delivery_task")
    assert {item["action"] for item in audit["items"]} >= {"queue", "failed"}


def test_project_api_uploads_without_base64_and_completes_background_intake(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    client = TestClient(app)
    created = client.post(
        "/api/delivery/projects",
        json={"project_id": "gt-pilot", "name": "Gas Turbine Pilot", "created_by": "owner"},
    )
    assert created.status_code == 201, created.text

    upload = client.post(
        "/api/delivery/projects/gt-pilot/documents/upload",
        data={
            "document_id": "manual-001",
            "created_by": "knowledge-engineer",
            "idempotency_key": "manual-001-upload-v1",
            "chunk_size": "200",
            "overlap": "20",
        },
        files={
            "file": (
                "manual.txt",
                "燃气轮机润滑油系统过滤器堵塞由油液污染导致。".encode(),
                "text/plain",
            )
        },
    )
    assert upload.status_code == 202, upload.text
    payload = upload.json()
    assert payload["project_id"] == "gt-pilot"
    assert payload["source_asset"]["byte_size"] > 0
    assert payload["source_asset"]["mime_type"] == "text/plain"
    assert payload["source_asset"]["page_count"] == 1
    assert payload["source_asset"]["duplicate"] is False
    assert Path(payload["source_asset"]["path"]).is_file()

    duplicate = client.post(
        "/api/delivery/projects/gt-pilot/documents/upload",
        data={
            "document_id": "manual-001-copy",
            "created_by": "knowledge-engineer",
            "idempotency_key": "manual-001-duplicate",
        },
        files={
            "file": (
                "manual-copy.txt",
                "燃气轮机润滑油系统过滤器堵塞由油液污染导致。".encode(),
                "text/plain",
            )
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "duplicate_source_asset"
    assert duplicate.json()["detail"]["details"]["duplicate_of"]["asset_id"] == payload["source_asset"]["asset_id"]

    task_id = payload["task"]["task_id"]
    task = client.get(f"/api/delivery/tasks/{task_id}", params={"project_id": "gt-pilot"})
    assert task.status_code == 200, task.text
    task_payload = task.json()
    assert task_payload["status"] == "needs_review"
    version = task_payload["result"]["document_version"]
    assert version["project_id"] == "gt-pilot"

    tasks = client.get("/api/delivery/projects/gt-pilot/tasks", params={"status": "needs_review"})
    assert tasks.status_code == 200
    assert tasks.json()["items"][0]["task_id"] == task_id
    audit = client.get("/api/delivery/projects/gt-pilot/audit")
    assert audit.status_code == 200
    assert audit.json()["count"] >= 3


def test_sixty_megabyte_multipart_upload_returns_a_queued_task_without_base64(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes_delivery, "_run_uploaded_intake", lambda **_kwargs: None)
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    client = TestClient(app)
    assert client.post(
        "/api/delivery/projects",
        json={"project_id": "large-file", "name": "Large File", "created_by": "owner"},
    ).status_code == 201
    payload = b"P" * (60 * 1024 * 1024)
    started = time.perf_counter()
    upload = client.post(
        "/api/delivery/projects/large-file/documents/upload",
        data={"document_id": "large-manual", "created_by": "engineer"},
        files={"file": ("large-manual.pdf", payload, "application/pdf")},
    )
    elapsed = time.perf_counter() - started
    assert upload.status_code == 202, upload.text
    assert elapsed < 20.0
    body = upload.json()
    assert body["source_asset"]["byte_size"] == len(payload)
    assert body["task"]["status"] == "queued"
    assert "content_base64" not in json.dumps(body)
    assert Path(body["source_asset"]["path"]).stat().st_size == len(payload)


def test_project_update_uses_optimistic_concurrency(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    client = TestClient(app)
    project = client.post(
        "/api/delivery/projects",
        json={"project_id": "concurrency", "name": "Initial", "created_by": "owner"},
    ).json()
    first = client.patch(
        "/api/delivery/projects/concurrency",
        json={
            "expected_version": project["updated_at"],
            "actor": "owner",
            "name": "Updated",
        },
    )
    assert first.status_code == 200, first.text
    conflict = client.patch(
        "/api/delivery/projects/concurrency",
        json={
            "expected_version": project["updated_at"],
            "actor": "owner",
            "name": "Stale update",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "version_conflict"


def test_catalog_review_queue_and_publish_contract_are_project_scoped(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    app.state.delivery_embedding_backend = "hashing"
    app.state.delivery_local_actor = "authenticated-operator"
    client = TestClient(app)
    assert client.post(
        "/api/delivery/projects",
        json={"project_id": "catalog", "name": "Catalog", "created_by": "owner"},
    ).status_code == 201
    upload = client.post(
        "/api/delivery/projects/catalog/documents/upload",
        data={"document_id": "manual-1", "created_by": "engineer"},
        files={"file": ("manual.txt", b"filter blockage caused by contamination", "text/plain")},
    ).json()
    version = client.get(
        f"/api/delivery/tasks/{upload['task']['task_id']}",
        params={"project_id": "catalog"},
    ).json()["result"]["document_version"]
    headers = {"X-Project-ID": "catalog", "X-Correlation-ID": "publish-correlation"}

    catalog = client.get("/api/delivery/documents", headers=headers)
    assert catalog.status_code == 200, catalog.text
    assert catalog.json()["items"][0]["project_id"] == "catalog"
    assert catalog.json()["items"][0]["version_id"] == version["version_id"]
    queue = client.get("/api/delivery/review-queue", headers=headers)
    assert queue.status_code == 200
    assert queue.json()["counts"]["documents"] == 1

    review = client.post(
        f"/api/delivery/documents/{version['version_id']}/review",
        headers=headers,
        json={"reviewer": "domain-reviewer", "decision": "approve", "comment": "checked"},
    )
    assert review.status_code == 200, review.text
    publish_body = {
        "actor": "release-operator",
        "comment": "publish approved material",
        "idempotency_key": "publish-manual-1-v1",
        "expected_version": version["version_id"],
    }
    first = client.post(
        f"/api/delivery/documents/{version['version_id']}/publish",
        headers=headers,
        json=publish_body,
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "published"
    for mode in ("keyword", "semantic", "hybrid"):
        retrieval = client.get(
            "/api/delivery/documents-search",
            headers=headers,
            params={"q": "filter blockage", "mode": mode},
        )
        assert retrieval.status_code == 200, retrieval.text
        assert retrieval.json()["retrieval_mode"] == mode
        assert retrieval.json()["results"][0]["locator"]["document_version_id"] == version["version_id"]
    index_status = client.get("/api/delivery/documents-index/status", headers=headers)
    assert index_status.status_code == 200, index_status.text
    assert index_status.json()["project_id"] == "catalog"
    assert index_status.json()["latest_snapshot"]["document_versions"][0]["version_id"] == version["version_id"]
    assert index_status.json()["latest_snapshot"]["config_hash"] == index_status.json()["config_hash"]
    rebuild = client.post(
        "/api/delivery/documents-index/rebuild?background=true",
        headers={**headers, "Idempotency-Key": "catalog-index-rebuild-v1"},
    )
    assert rebuild.status_code == 202, rebuild.text
    rebuild_task = client.get(
        f"/api/delivery/tasks/{rebuild.json()['task']['task_id']}",
        params={"project_id": "catalog"},
    )
    assert rebuild_task.json()["status"] == "completed"
    assert rebuild_task.json()["result"]["index_snapshot"]["operation"] == "rebuild"
    repeated = client.post(
        f"/api/delivery/documents/{version['version_id']}/publish",
        headers=headers,
        json=publish_body,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == first.json()

    stale = client.patch(
        "/api/delivery/projects/catalog",
        json={
            "expected_version": "stale",
            "actor": "owner",
            "name": "Should conflict",
        },
    )
    assert stale.status_code == 409
    audit = client.get("/api/delivery/projects/catalog/audit")
    publish_events = [item for item in audit.json()["items"] if item["action"] == "publish"]
    assert len(publish_events) == 1
    assert publish_events[0]["actor"] == "authenticated-operator"
    assert publish_events[0]["correlation_id"] == "publish-correlation"


def test_project_package_verifies_and_restores_into_an_isolated_workspace(tmp_path: Path) -> None:
    registry = ProjectWorkspaceRegistry(tmp_path / "projects")
    registry.create_project(project_id="source", name="Source", created_by="owner")
    registry.governance_store("source").create_document_candidate(
        document_id="manual-restore",
        source_name="manual.txt",
        chunks=[_chunk("restorable evidence")],
        intake_status="parsed",
    )
    source_file = registry.project_dir("source") / "source_assets" / "manual.txt"
    source_file.write_text("source bytes", encoding="utf-8")
    empty_bin = registry.project_dir("source") / "retrieval" / "chroma" / "link_lists.bin"
    empty_bin.parent.mkdir(parents=True, exist_ok=True)
    empty_bin.write_bytes(b"")
    registry.upsert_provider(
        project_id="source",
        provider_id="private-llm",
        capability="graph_extraction",
        provider_type="local",
        actor="owner",
        model="private-model",
        version="2026.09",
        health_status="ready",
        configuration={"endpoint": "http://local-provider", "api_key": "must-not-leak"},
    )
    task = registry.create_task(
        project_id="source",
        task_type="index_rebuild",
        stage="index",
        created_by="owner",
        payload={"document_id": "manual-restore", "access_token": "must-not-leak"},
    )
    registry.assign_task(task.task_id, assignee="reviewer", actor="owner")
    registry.add_task_comment(task.task_id, actor="reviewer", message="复核通过")
    registry.finish_task(task.task_id, status="completed", result={"snapshot_id": "IDX-1"})
    registry.record_projection_state(
        "source",
        "governed_materials",
        status="ready",
        source_version_id="IDX-1",
        item_count=1,
    )

    package = registry.build_export_package("source")
    verification = registry.verify_export_package(package["path"])
    assert verification["valid"] is True
    assert verification["sha256"] == package["sha256"]
    with zipfile.ZipFile(package["path"]) as archive:
        control_plane = json.loads(archive.read("manifests/control-plane.json"))
        provider_manifest = json.loads(archive.read("manifests/providers.json"))
    assert control_plane["format"] == "powerrag-control-plane-v1"
    assert control_plane["tasks"][0]["assigned_to"] == "reviewer"
    assert control_plane["task_comments"][0]["message"] == "复核通过"
    assert {item["template_id"] for item in control_plane["fmea_templates"]} == {
        "gas_turbine_minimum_v1",
        "electric_motor_minimum_v1",
    }
    assert "access_token" not in control_plane["tasks"][0]["payload"]
    private_provider = next(item for item in provider_manifest["items"] if item["provider_id"] == "private-llm")
    assert "api_key" not in private_provider["configuration"]

    restored = registry.restore_export_package(
        package["path"],
        project_id="restored",
        name="Restored",
        actor="recovery-operator",
    )
    assert restored["source_project_id"] == "source"
    assert (registry.project_dir("restored") / "source_assets" / "manual.txt").read_text(
        encoding="utf-8"
    ) == "source bytes"
    assert (registry.project_dir("restored") / "retrieval" / "chroma" / "link_lists.bin").read_bytes() == b""
    restored_document = registry.governance_store("restored").list_document_catalog()[0]
    assert restored_document.project_id == "restored"
    assert restored_document.evidence[0].text == "restorable evidence"
    assert registry.get_provider("restored", "private-llm")["model"] == "private-model"
    restored_tasks = registry.list_tasks(project_id="restored")["items"]
    assert len(restored_tasks) == 1
    assert restored_tasks[0]["status"] == "completed"
    assert restored_tasks[0]["assigned_to"] == "reviewer"
    assert registry.list_task_comments(restored_tasks[0]["task_id"])[0]["message"] == "复核通过"
    assert registry.get_projection_state("restored", "governed_materials")["item_count"] == 1
    assert restored["restored_control_plane"]["tasks"] == 1
    assert restored["restored_control_plane"]["fmea_templates"] == 0
    assert registry.list_fmea_templates(project_id="restored")["count"] == 2


def test_project_package_rejects_path_traversal(tmp_path: Path) -> None:
    registry = ProjectWorkspaceRegistry(tmp_path / "projects")
    package_path = tmp_path / "unsafe.zip"
    manifest = {
        "format": "powerrag-project-package-v1",
        "project": {"project_id": "unsafe"},
        "files": [{"path": "../escape.txt", "byte_size": 6, "sha256": "ignored"}],
    }
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("../escape.txt", "escape")

    with pytest.raises(Exception) as error:
        registry.verify_export_package(package_path)
    assert getattr(error.value, "code", None) == "invalid_package_path"


def test_project_backup_and_restore_api_round_trip(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    client = TestClient(app)
    assert client.post(
        "/api/delivery/projects",
        json={"project_id": "backup-src", "name": "Backup Source", "created_by": "owner"},
    ).status_code == 201
    upload = client.post(
        "/api/delivery/projects/backup-src/documents/upload",
        data={"document_id": "manual-backup", "created_by": "engineer"},
        files={"file": ("manual.txt", b"backup evidence", "text/plain")},
    )
    assert upload.status_code == 202, upload.text

    exported = client.post("/api/delivery/projects/backup-src/export-package")
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"] == "application/zip"
    assert exported.headers["x-powerrag-package-sha256"]

    restored = client.post(
        "/api/delivery/projects/restore",
        data={"project_id": "backup-copy", "name": "Backup Copy", "actor": "recovery-operator"},
        files={"file": ("backup.zip", exported.content, "application/zip")},
    )
    assert restored.status_code == 201, restored.text
    assert restored.json()["source_project_id"] == "backup-src"
    catalog = client.get(
        "/api/delivery/documents",
        headers={"X-Project-ID": "backup-copy"},
    )
    assert catalog.status_code == 200, catalog.text
    assert catalog.json()["items"][0]["document_id"] == "manual-backup"


def test_graph_and_fmea_long_operations_use_delivery_tasks(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    app.state.delivery_embedding_backend = "hashing"
    client = TestClient(app)
    project_id = "async-chain"
    headers = {"X-Project-ID": project_id, "X-Correlation-ID": "async-chain-correlation"}
    assert client.post(
        "/api/delivery/projects",
        json={"project_id": project_id, "name": "Async Chain", "created_by": "owner"},
    ).status_code == 201
    sample = (
        Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "delivery" / "ui_gas_turbine_sample.txt"
    ).read_bytes()
    upload = client.post(
        f"/api/delivery/projects/{project_id}/documents/upload",
        data={"document_id": "async-manual", "created_by": "engineer"},
        files={"file": ("async.txt", sample, "text/plain")},
    ).json()
    intake_task = client.get(
        f"/api/delivery/tasks/{upload['task']['task_id']}",
        params={"project_id": project_id},
    ).json()
    document = intake_task["result"]["document_version"]
    assert client.post(
        f"/api/delivery/documents/{document['version_id']}/review",
        headers=headers,
        json={"reviewer": "reviewer", "decision": "approve", "comment": "evidence checked"},
    ).status_code == 200
    assert client.post(
        f"/api/delivery/documents/{document['version_id']}/publish",
        headers=headers,
        json={
            "actor": "publisher",
            "comment": "publish for graph",
            "idempotency_key": "publish-async-manual",
            "expected_version": document["version_id"],
        },
    ).status_code == 200

    registry = app.state.project_workspace_registry
    failed_rebuild = registry.create_task(
        project_id=project_id,
        task_type="index_rebuild",
        stage="queued",
        created_by="engineer",
        payload={"project_id": project_id},
        object_type="index",
        object_id="governed_materials",
        retryable=True,
    )
    registry.claim_task(failed_rebuild.task_id, worker_id="failed-worker")
    registry.finish_task(
        failed_rebuild.task_id,
        status=TaskStatus.FAILED,
        error_code="simulated_failure",
        error_message="simulated recoverable failure",
        retryable=True,
        actor="failed-worker",
    )
    retried = client.post(
        f"/api/delivery/tasks/{failed_rebuild.task_id}/retry",
        headers=headers,
        json={"actor": "engineer", "idempotency_key": "retry-index-rebuild-v1"},
    )
    assert retried.status_code == 201, retried.text
    retried_task = client.get(
        f"/api/delivery/tasks/{retried.json()['task_id']}",
        params={"project_id": project_id},
    ).json()
    assert retried_task["status"] == "completed"
    assert retried_task["payload"]["retry_of"] == failed_rebuild.task_id

    graph_run = client.post(
        "/api/delivery/graphs/extract?background=true",
        headers={**headers, "Idempotency-Key": "async-graph-v1"},
        json={
            "source_document_version_ids": [document["version_id"]],
            "backend": "rules",
            "metadata": {"actor": "engineer"},
        },
    )
    assert graph_run.status_code == 202, graph_run.text
    graph_task = client.get(
        f"/api/delivery/tasks/{graph_run.json()['task']['task_id']}",
        params={"project_id": project_id},
    ).json()
    assert graph_task["status"] == "needs_review"
    assert graph_task["progress"] == 1.0
    graph = graph_task["result"]["graph_version"]
    assert graph["project_id"] == project_id
    statements = client.get(
        f"/api/delivery/graphs/{graph['graph_version_id']}/statements",
        headers=headers,
        params={"evidence_status": "bound", "min_confidence": 0.1},
    )
    assert statements.status_code == 200, statements.text
    assert statements.json()["count"] == len(graph["statements"])
    assert client.post(
        f"/api/delivery/graphs/{graph['graph_version_id']}/review",
        headers=headers,
        json={"reviewer": "reviewer", "decision": "approve", "comment": "statements checked"},
    ).status_code == 200
    blocked_publish = client.post(
        f"/api/delivery/graphs/{graph['graph_version_id']}/publish",
        headers=headers,
        json={
            "actor": "publisher",
            "comment": "bulk approval must not bypass statement review",
            "expected_version": str(graph["version"]),
        },
    )
    assert blocked_publish.status_code == 409
    assert blocked_publish.json()["detail"]["code"] == "graph_statement_review_incomplete"
    decisions = {item["statement_id"]: "approve" for item in statements.json()["items"]}
    statement_review = client.post(
        f"/api/delivery/graphs/{graph['graph_version_id']}/statement-reviews",
        headers=headers,
        json={"reviewer": "reviewer", "comment": "reviewed one by one", "decisions": decisions},
    )
    assert statement_review.status_code == 200, statement_review.text
    published_graph = client.post(
        f"/api/delivery/graphs/{graph['graph_version_id']}/publish",
        headers=headers,
        json={
            "actor": "publisher",
            "comment": "publish graph",
            "idempotency_key": "publish-async-graph",
            "expected_version": str(graph["version"]),
        },
    )
    assert published_graph.status_code == 200, published_graph.text

    fmea_run = client.post(
        "/api/delivery/fmea/tasks?background=true",
        headers={**headers, "Idempotency-Key": "async-fmea-v1"},
        json={
            "requested_by": "engineer",
            "graph_version_id": graph["graph_version_id"],
            "document_version_ids": [document["version_id"]],
            "template": "gas_turbine_minimum_v1",
        },
    )
    assert fmea_run.status_code == 202, fmea_run.text
    fmea_task = client.get(
        f"/api/delivery/tasks/{fmea_run.json()['task']['task_id']}",
        params={"project_id": project_id},
    ).json()
    assert fmea_task["status"] == "needs_review"
    assert fmea_task["progress"] == 1.0
    fmea = fmea_task["result"]["fmea"]
    assert fmea["request"]["project_id"] == project_id
    generic_review = client.post(
        f"/api/delivery/fmea/tasks/{fmea['task_id']}/review",
        headers=headers,
        json={"reviewer": "reviewer", "decision": "approve", "comment": "bulk approval attempt"},
    )
    assert generic_review.status_code == 200, generic_review.text
    approved_fmea = generic_review.json()
    blocked_fmea_publish = client.post(
        f"/api/delivery/fmea/tasks/{fmea['task_id']}/publish",
        headers=headers,
        json={
            "actor": "publisher",
            "comment": "bulk approval must not bypass field review",
            "expected_version": approved_fmea["updated_at"],
        },
    )
    assert blocked_fmea_publish.status_code == 409
    assert blocked_fmea_publish.json()["detail"]["code"] == "fmea_field_review_incomplete"
    field_decisions = {
        item["item_id"]: {
            field: "approve"
            for field, value in item["fields"].items()
            if value not in (None, "")
        }
        for item in approved_fmea["items"]
    }
    field_review = client.post(
        f"/api/delivery/fmea/tasks/{fmea['task_id']}/field-reviews",
        headers=headers,
        json={
            "reviewer": "reviewer",
            "decisions": field_decisions,
            "comment": "reviewed every populated field with its evidence",
        },
    )
    assert field_review.status_code == 200, field_review.text
    assert field_review.json()["status"] == "approved"
    final_fmea = client.post(
        f"/api/delivery/fmea/tasks/{fmea['task_id']}/publish",
        headers=headers,
        json={
            "actor": "publisher",
            "comment": "publish field-reviewed FMEA",
            "idempotency_key": "publish-async-fmea",
            "expected_version": field_review.json()["updated_at"],
        },
    )
    assert final_fmea.status_code == 200, final_fmea.text
    assert final_fmea.json()["status"] == "published"
    docx_export = client.get(
        f"/api/delivery/fmea/tasks/{fmea['task_id']}/export",
        headers=headers,
        params={"format": "docx"},
    )
    assert docx_export.status_code == 200, docx_export.text
    assert docx_export.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    docx_path = tmp_path / "fmea.docx"
    docx_path.write_bytes(docx_export.content)
    with zipfile.ZipFile(docx_path) as archive:
        assert "word/document.xml" in archive.namelist()
    consistency = client.get(
        f"/api/delivery/fmea/tasks/{fmea['task_id']}/export-verify",
        headers=headers,
    )
    assert consistency.status_code == 200, consistency.text
    assert consistency.json()["consistent"] is True
    assert consistency.json()["docx_rows"] == consistency.json()["json_rows"]


def test_delivery_identity_and_project_authorization_are_backend_enforced(tmp_path: Path) -> None:
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    app.state.delivery_local_actor = "project-owner"
    client = TestClient(app)
    created = client.post(
        "/api/delivery/projects",
        json={
            "project_id": "locked-project",
            "name": "Locked Project",
            "created_by": "spoofed-creator",
            "configuration": {"allowed_actors": ["project-owner"]},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["created_by"] == "project-owner"
    allowed = client.get(
        "/api/delivery/projects/locked-project",
        headers={"X-Project-ID": "locked-project"},
    )
    assert allowed.status_code == 200
    assert allowed.headers["x-authenticated-actor"] == "project-owner"
    assert allowed.headers["x-correlation-id"]

    app.state.delivery_local_actor = "intruder"
    denied = client.get(
        "/api/delivery/projects/locked-project",
        headers={"X-Project-ID": "locked-project", "X-Correlation-ID": "denied-correlation"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == {
        "code": "project_access_denied",
        "message": "The authenticated identity is not authorized for this project",
        "stage": "authorization",
        "retryable": False,
        "details": {"project_id": "locked-project"},
        "correlation_id": "denied-correlation",
    }
    listed = client.get("/api/delivery/projects")
    assert all(item["project_id"] != "locked-project" for item in listed.json()["items"])

    app.state.delivery_auth_mode = "oidc"
    unauthenticated = client.get("/api/delivery/projects")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["detail"]["code"] == "delivery_authentication_required"


def test_provider_registry_enforces_project_data_egress_policy(tmp_path: Path) -> None:
    registry = ProjectWorkspaceRegistry(tmp_path / "projects")
    project = registry.create_project(
        project_id="provider-policy",
        name="Provider Policy",
        created_by="owner",
        data_policy={"external_providers_allowed": False},
    )
    registry.upsert_provider(
        project_id=project.project_id,
        provider_id="external-graph-llm",
        capability="graph_extraction",
        provider_type="external",
        actor="owner",
        model="graph-model",
        version="1.0",
        timeout_seconds=90,
        cost_class="metered",
        health_status="ready",
        capabilities={"structured_output": True},
        data_policy={"retention": "none"},
    )
    with pytest.raises(Exception) as blocked:
        registry.authorize_provider_call(
            project_id=project.project_id,
            provider_id="external-graph-llm",
            capability="graph_extraction",
            actor="engineer",
            data_scope={"document_version_ids": ["doc-v1"], "raw_text_included": True},
        )
    assert getattr(blocked.value, "code", None) == "external_provider_blocked"

    updated = registry.update_project(
        project.project_id,
        actor="owner",
        expected_updated_at=project.updated_at,
        data_policy={
            "external_providers_allowed": True,
            "allowed_provider_ids": ["external-graph-llm"],
        },
        reason="Approved no-retention provider for this project",
    )
    assert updated.data_policy["external_providers_allowed"] is True
    authorized = registry.authorize_provider_call(
        project_id=project.project_id,
        provider_id="external-graph-llm",
        capability="graph_extraction",
        actor="engineer",
        data_scope={"document_version_ids": ["doc-v1"], "raw_text_included": True},
        correlation_id="provider-call-correlation",
    )
    assert authorized["authorized"] is True
    assert authorized["timeout_seconds"] == 90
    audit = registry.list_audit(project_id=project.project_id, object_type="provider_call")
    assert audit["items"][0]["correlation_id"] == "provider-call-correlation"
    assert "raw text" not in json.dumps(audit["items"][0], ensure_ascii=False)
