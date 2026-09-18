from __future__ import annotations

# ruff: noqa: RUF001
import csv
import io
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core_domain.delivery import GraphStatement, ReviewDecision, TaskStatus
from rag_orchestrator.fmea import build_fmea_items
from storage_layer.governance_store import GovernanceError, GovernanceStore

API_SRC = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from chroma_rag_poc.api import create_app  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fmea" / "gas_turbine_fmea_review_sample_v1.csv"


def _sample_rows() -> list[dict[str, str]]:
    with FIXTURE.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _app_store_client(tmp_path: Path) -> tuple[object, GovernanceStore, TestClient]:
    persist_dir = tmp_path / "persist"
    app = create_app(persist_dir=persist_dir, upload_dir=tmp_path / "uploads")
    app.state.delivery_embedding_backend = "hashing"
    app.state.delivery_embedding_model = "hashing-384"
    store = GovernanceStore(persist_dir / "governance" / "delivery.sqlite3")
    app.state.governance_store = store
    return app, store, TestClient(app)


def _publish_sample_document(store: GovernanceStore, rows: list[dict[str, str]] | None = None):
    rows = rows or _sample_rows()
    candidate = store.create_document_candidate(
        document_id="human-fmea-sample",
        source_name="gas_turbine_fmea_review_sample_v1.csv",
        chunks=[
            {
                "chunk_id": row["sample_id"],
                "text": row["source_excerpt"],
                "source_file": row["source_file"],
                "page": row["page"],
                "block_id": f"{row['sample_id']}:evidence",
                "metadata": {"fixture_review_status": row["review_status"]},
            }
            for row in rows
        ],
        metadata={"fixture": "manually_curated_fmea_review_sample_v1"},
    )
    store.record_review(
        target_type="document",
        target_id=candidate.version_id,
        reviewer="fixture-reviewer",
        decision=ReviewDecision.APPROVE,
    )
    return store.publish_document(candidate.version_id)


def _statements_for_rows(document, rows: list[dict[str, str]], *, include_failure: bool = True):
    statements: list[dict[str, object]] = []
    for row, locator in zip(rows, document.evidence, strict=True):
        evidence_ids = [locator.evidence_id]
        statements.append({
            "subject": row["component"],
            "predicate": "PART_OF",
            "object": row["equipment"],
            "subject_type": "COMPONENT",
            "object_type": "EQUIPMENT",
            "evidence_ids": evidence_ids,
            "confidence": 0.98,
        })
        if not include_failure:
            continue
        statements.extend([
            {
                "subject": row["component"],
                "predicate": "HAS_FAILURE_MODE",
                "object": row["failure_mode"],
                "subject_type": "COMPONENT",
                "object_type": "FAILURE_MODE",
                "evidence_ids": evidence_ids,
                "confidence": 0.97,
            },
            {
                "subject": row["failure_mode"],
                "predicate": "CAUSED_BY",
                "object": row["cause"],
                "subject_type": "FAILURE_MODE",
                "object_type": "CAUSE",
                "evidence_ids": evidence_ids,
                "confidence": 0.96,
            },
            {
                "subject": row["failure_mode"],
                "predicate": "HAS_EFFECT",
                "object": row["effect"],
                "subject_type": "FAILURE_MODE",
                "object_type": "EFFECT",
                "evidence_ids": evidence_ids,
                "confidence": 0.95,
            },
            {
                "subject": row["failure_mode"],
                "predicate": "DETECTED_BY",
                "object": row["detection_method"],
                "subject_type": "FAILURE_MODE",
                "object_type": "DETECTION_METHOD",
                "evidence_ids": evidence_ids,
                "confidence": 0.94,
            },
            {
                "subject": row["failure_mode"],
                "predicate": "MITIGATED_BY",
                "object": row["recommended_action"],
                "subject_type": "FAILURE_MODE",
                "object_type": "ACTION",
                "evidence_ids": evidence_ids,
                "confidence": 0.93,
            },
        ])
    return statements


def _publish_graph(store: GovernanceStore, document, rows, *, include_failure: bool = True, conflict: bool = False):
    statements = _statements_for_rows(document, rows, include_failure=include_failure)
    if conflict:
        statements.append({
            "subject": rows[0]["failure_mode"],
            "predicate": "CAUSED_BY",
            "object": "维护不当",
            "subject_type": "FAILURE_MODE",
            "object_type": "CAUSE",
            "evidence_ids": [document.evidence[-1].evidence_id],
            "confidence": 0.82,
        })
    candidate = store.create_graph_candidate(
        source_document_version_ids=[document.version_id],
        statements=statements,
        metadata={"fixture": "human_fmea_sample"},
    )
    store.record_review(
        target_type="graph",
        target_id=candidate.graph_version_id,
        reviewer="graph-reviewer",
        decision=ReviewDecision.APPROVE,
    )
    return store.publish_graph(candidate.graph_version_id)


def _run_task(client: TestClient, graph, document) -> dict[str, object]:
    response = client.post(
        "/api/delivery/fmea/tasks",
        json={
            "requested_by": "m5-acceptance",
            "graph_version_id": graph.graph_version_id,
            "document_version_ids": [document.version_id],
            "template": "gas_turbine_minimum_v1",
            "template_version": "1.1.0",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_m5_template_structured_errors_and_full_state_history(tmp_path: Path) -> None:
    _, store, client = _app_store_client(tmp_path)
    templates = client.get("/api/delivery/fmea/templates").json()["items"]
    assert [(item["template_id"], item["version"], item["status"]) for item in templates] == [
        ("electric_motor_minimum_v1", "1.0.0", "approved"),
        ("gas_turbine_minimum_v1", "1.1.0", "approved")
    ]
    assert all(
        item["graph_constraints"]["equipment_hierarchy"]["relation"] == "PART_OF"
        for item in templates
    )
    assert {item["report_layout"]["report_template_id"] for item in templates} == {
        "electric_motor_formal_docx_v1",
        "gas_turbine_formal_docx_v1",
    }

    rows = _sample_rows()[:1]
    document = _publish_sample_document(store, rows)
    graph = _publish_graph(store, document, rows, include_failure=False)
    task = _run_task(client, graph, document)
    assert task["status"] == "failed"
    assert task["errors"] == [
        {
            "code": "fmea_failure_mode_missing",
            "message": "No HAS_FAILURE_MODE statements were available for the selected graph version.",
            "stage": "M5",
            "retryable": False,
            "details": {"graph_version_id": graph.graph_version_id},
        }
    ]
    assert [item["to_status"] for item in task["state_history"]] == ["queued", "running", "failed"]
    history = client.get(f"/api/delivery/fmea/tasks/{task['task_id']}/status-history").json()
    assert [item["reason"] for item in history["items"]] == [
        "task_created",
        "generation_started",
        "generation_failed",
    ]
    with pytest.raises(GovernanceError, match="Invalid FMEA task transition"):
        store.save_fmea_result(
            str(task["task_id"]),
            status=TaskStatus.RUNNING,
            items=(),
            reason="invalid_retry_without_new_task",
        )

    blocked_export = client.get(f"/api/delivery/fmea/tasks/{task['task_id']}/export")
    assert blocked_export.status_code == 400
    assert blocked_export.json()["detail"]["code"] == "fmea_not_published"

    bad_template = client.post(
        "/api/delivery/fmea/tasks",
        json={
            "requested_by": "m5-acceptance",
            "graph_version_id": graph.graph_version_id,
            "document_version_ids": [document.version_id],
            "template": "does_not_exist",
        },
    )
    assert bad_template.status_code == 400
    assert bad_template.json()["detail"]["code"] == "fmea_template_not_found"


def test_human_fmea_sample_resolves_evidence_reviews_and_round_trip_exports(tmp_path: Path) -> None:
    _, store, client = _app_store_client(tmp_path)
    rows = _sample_rows()
    document = _publish_sample_document(store, rows)
    graph = _publish_graph(store, document, rows)
    task = _run_task(client, graph, document)
    assert task["status"] == "needs_review"
    assert len(task["items"]) == len(rows)
    for expected, actual in zip(rows, task["items"], strict=True):
        assert actual["fields"]["failure_mode"] == expected["failure_mode"]
        assert actual["fields"]["recommended_action"] == expected["recommended_action"]
        cause_evidence = actual["field_evidence_details"]["cause"]
        assert cause_evidence[0]["text"] == expected["source_excerpt"]
        assert cause_evidence[0]["page"] == expected["page"]
        assert cause_evidence[0]["source_file"] == expected["source_file"]

    task_id = str(task["task_id"])
    item_id = task["items"][0]["item_id"]
    invalid_evidence = client.post(
        f"/api/delivery/fmea/tasks/{task_id}/review",
        json={
            "reviewer": "fmea-reviewer",
            "decision": "modify",
            "corrections": {item_id: {"cause": {"value": "人工原因", "evidence_ids": ["EV-missing"]}}},
        },
    )
    assert invalid_evidence.status_code == 400
    assert invalid_evidence.json()["detail"]["code"] == "unknown_fmea_evidence"

    evidence_id = task["items"][0]["field_evidence"]["cause"][0]
    modified = client.post(
        f"/api/delivery/fmea/tasks/{task_id}/review",
        json={
            "reviewer": "fmea-reviewer",
            "decision": "modify",
            "comment": "人工核对术语",
            "corrections": {
                item_id: {"cause": {"value": "油液污染（人工确认）", "evidence_ids": [evidence_id]}}
            },
        },
    )
    assert modified.status_code == 200, modified.text
    assert modified.json()["items"][0]["fields"]["cause"] == "油液污染（人工确认）"
    rejected = client.post(
        f"/api/delivery/fmea/tasks/{task_id}/review",
        json={"reviewer": "second-reviewer", "decision": "reject", "comment": "要求再次确认"},
    )
    assert rejected.json()["status"] == "needs_review"
    confirmed = client.post(
        f"/api/delivery/fmea/tasks/{task_id}/review",
        json={"reviewer": "domain-owner", "decision": "confirm", "comment": "最终确认"},
    )
    assert confirmed.json()["status"] == "approved"
    reviews = client.get(f"/api/delivery/fmea/tasks/{task_id}/reviews").json()["items"]
    assert [item["decision"] for item in reviews] == ["modify", "reject", "confirm"]

    published = client.post(f"/api/delivery/fmea/tasks/{task_id}/publish")
    assert published.status_code == 200, published.text
    json_export = client.get(f"/api/delivery/fmea/tasks/{task_id}/export?format=json").json()
    assert [item["decision"] for item in json_export["reviews"]] == ["modify", "reject", "confirm"]
    assert json_export["items"][0]["field_evidence_details"]["cause"][0]["page"] == rows[0]["page"]
    csv_export = client.get(f"/api/delivery/fmea/tasks/{task_id}/export?format=csv")
    csv_rows = list(csv.DictReader(io.StringIO(csv_export.text.lstrip("\ufeff"))))
    assert json.loads(csv_rows[0]["cause_evidence_details"])[0]["text"] == rows[0]["source_excerpt"]
    assert [item["decision"] for item in json.loads(csv_rows[0]["review_history"])] == [
        "modify",
        "reject",
        "confirm",
    ]
    assert client.get(f"/api/delivery/fmea/tasks/{task_id}/export-verify").json()["consistent"] is True


def test_m5_conflict_and_insufficient_evidence_are_executable_quality_gates(tmp_path: Path) -> None:
    _, store, client = _app_store_client(tmp_path)
    rows = _sample_rows()
    document = _publish_sample_document(store, rows)
    conflict_graph = _publish_graph(store, document, rows, conflict=True)
    task = _run_task(client, conflict_graph, document)
    conflicts = [issue for issue in task["items"][0]["issues"] if issue["code"] == "field_conflict"]
    assert conflicts
    assert set(conflicts[0]["metadata"]["values"]) == {rows[0]["cause"], "维护不当"}

    unsupported = build_fmea_items((
        GraphStatement(
            statement_id="S1",
            subject="润滑油系统",
            predicate="HAS_FAILURE_MODE",
            object_name="过滤器堵塞",
            subject_type="COMPONENT",
            object_type="FAILURE_MODE",
            evidence_ids=(),
        ),
    ))
    assert {issue.code for issue in unsupported[0].issues} >= {"missing_field", "insufficient_evidence"}

    clean_graph = _publish_graph(store, document, rows)
    clean_task = _run_task(client, clean_graph, document)
    item_id = clean_task["items"][0]["item_id"]
    task_id = clean_task["task_id"]
    assert client.post(
        f"/api/delivery/fmea/tasks/{task_id}/review",
        json={
            "reviewer": "fmea-reviewer",
            "decision": "modify",
            "corrections": {item_id: {"cause": {"value": "无证据人工值", "evidence_ids": []}}},
        },
    ).status_code == 200
    assert client.post(
        f"/api/delivery/fmea/tasks/{task_id}/review",
        json={"reviewer": "domain-owner", "decision": "confirm"},
    ).json()["status"] == "approved"
    blocked = client.post(f"/api/delivery/fmea/tasks/{task_id}/publish")
    assert blocked.status_code == 400
    assert blocked.json()["detail"]["code"] == "fmea_evidence_required"


def test_feedback_routes_m1_m2_and_m4_to_audited_revalidation(tmp_path: Path) -> None:
    _, store, client = _app_store_client(tmp_path)
    rows = _sample_rows()[:1]
    document = _publish_sample_document(store, rows)
    graph = _publish_graph(store, document, rows)
    task = _run_task(client, graph, document)
    task_id = task["task_id"]

    m1 = client.post(
        f"/api/delivery/fmea/tasks/{task_id}/feedback",
        json={"code": "source_permission_missing", "message": "来源授权待确认", "created_by": "reviewer"},
    ).json()
    m1_run = client.post(
        f"/api/delivery/fmea/feedback/{m1['feedback_id']}/remediate",
        json={"actor": "source-owner"},
    ).json()
    assert m1_run["routed_module"] == "M1"
    assert m1_run["status"] == "needs_human_input"
    assert len(m1_run["result"]["next_actions"]) == 3

    m2 = client.post(
        f"/api/delivery/fmea/tasks/{task_id}/feedback",
        json={"code": "ocr_term_error", "message": "OCR 术语需纠正", "created_by": "reviewer"},
    ).json()
    source_evidence = document.evidence[0]
    revision_run = client.post(
        f"/api/delivery/fmea/feedback/{m2['feedback_id']}/remediate",
        json={
            "actor": "ocr-reviewer",
            "document_version_id": document.version_id,
            "corrections": {
                source_evidence.evidence_id: {
                    "text": source_evidence.text.replace("可能由", "由")
                }
            },
        },
    ).json()
    revised_id = revision_run["result"]["document_version"]["version_id"]
    store.record_review(
        target_type="document",
        target_id=revised_id,
        reviewer="domain-reviewer",
        decision=ReviewDecision.APPROVE,
    )
    store.publish_document(revised_id)
    graph_candidate_run = client.post(
        f"/api/delivery/fmea/feedback/{m2['feedback_id']}/remediate",
        json={"actor": "pipeline-operator", "document_version_id": revised_id},
    )
    assert graph_candidate_run.status_code == 200, graph_candidate_run.text
    graph_candidate_id = graph_candidate_run.json()["result"]["graph_candidate"]["graph_version_id"]
    store.record_review(
        target_type="graph",
        target_id=graph_candidate_id,
        reviewer="graph-reviewer",
        decision=ReviewDecision.APPROVE,
    )
    store.publish_graph(graph_candidate_id)
    m2_complete = client.post(
        f"/api/delivery/fmea/feedback/{m2['feedback_id']}/remediate",
        json={
            "actor": "pipeline-operator",
            "document_version_id": revised_id,
            "graph_version_id": graph_candidate_id,
        },
    )
    assert m2_complete.status_code == 200, m2_complete.text
    assert m2_complete.json()["status"] == "completed"
    assert m2_complete.json()["feedback_status"] == "resolved"
    assert m2_complete.json()["result"]["revalidation"]["lineage_consistent"] is True

    m4 = client.post(
        f"/api/delivery/fmea/tasks/{task_id}/feedback",
        json={"code": "entity_conflict", "message": "实体冲突", "created_by": "reviewer"},
    ).json()
    gate = client.post(
        f"/api/delivery/fmea/feedback/{m4['feedback_id']}/remediate",
        json={"actor": "graph-reviewer"},
    ).json()
    assert gate["status"] == "needs_human_input"
    revised_document = store.get_document_version(revised_id)
    corrected_graph = _publish_graph(store, revised_document, rows)
    m4_complete = client.post(
        f"/api/delivery/fmea/feedback/{m4['feedback_id']}/remediate",
        json={"actor": "graph-reviewer", "graph_version_id": corrected_graph.graph_version_id},
    )
    assert m4_complete.status_code == 200, m4_complete.text
    assert m4_complete.json()["feedback_status"] == "resolved"
    assert m4_complete.json()["result"]["revalidation"]["lineage_consistent"] is True
