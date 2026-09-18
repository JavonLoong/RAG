from __future__ import annotations

# ruff: noqa: RUF001
import csv
import io
import json
from pathlib import Path

import pytest

from core_domain.delivery import ContentStatus, FMEATaskRequest, ReviewDecision, TaskStatus
from data_pipeline.document_intake import run_document_intake
from rag_orchestrator.fmea import FMEAService
from storage_layer.governance_store import GovernanceError, GovernanceStore
from storage_layer.graph_store import GraphStore, normalize_kg_payload


def _published_document(store: GovernanceStore, *, document_id: str = "manual"):
    intake = run_document_intake(
        "manual.txt",
        (
            "燃气轮机润滑油系统的过滤器堵塞可能由油液污染导致，影响是润滑油压下降。"
            "可通过压差监测发现，并通过更换滤芯和清洁油路处理。"
        ).encode(),
        chunk_size=80,
        overlap=10,
    )
    candidate = store.create_document_candidate_from_intake(document_id, intake)
    assert candidate.evidence
    store.record_review(
        target_type="document",
        target_id=candidate.version_id,
        reviewer="reviewer-a",
        decision=ReviewDecision.APPROVE,
    )
    return store.publish_document(candidate.version_id)


def _published_graph(store: GovernanceStore, document) -> tuple[object, str]:
    evidence_id = document.evidence[0].evidence_id
    statements = [
        {
            "subject": "润滑油系统",
            "predicate": "属于",
            "object": "燃气轮机",
            "subject_type": "COMPONENT",
            "object_type": "EQUIPMENT",
            "evidence_ids": [evidence_id],
            "confidence": 0.96,
        },
        {
            "subject": "润滑油系统",
            "predicate": "故障模式",
            "object": "过滤器堵塞",
            "subject_type": "COMPONENT",
            "object_type": "FAILURE_MODE",
            "evidence_ids": [evidence_id],
            "confidence": 0.94,
        },
        {
            "subject": "过滤器堵塞",
            "predicate": "原因",
            "object": "油液污染",
            "subject_type": "FAILURE_MODE",
            "object_type": "CAUSE",
            "evidence_ids": [evidence_id],
            "confidence": 0.93,
        },
        {
            "subject": "过滤器堵塞",
            "predicate": "影响",
            "object": "润滑油压下降",
            "subject_type": "FAILURE_MODE",
            "object_type": "EFFECT",
            "evidence_ids": [evidence_id],
            "confidence": 0.92,
        },
        {
            "subject": "过滤器堵塞",
            "predicate": "检测方法",
            "object": "压差监测",
            "subject_type": "FAILURE_MODE",
            "object_type": "DETECTION_METHOD",
            "evidence_ids": [evidence_id],
            "confidence": 0.91,
        },
        {
            "subject": "过滤器堵塞",
            "predicate": "措施",
            "object": "更换滤芯并清洁油路",
            "subject_type": "FAILURE_MODE",
            "object_type": "ACTION",
            "evidence_ids": [evidence_id],
            "confidence": 0.90,
        },
    ]
    candidate = store.create_graph_candidate(
        source_document_version_ids=[document.version_id],
        statements=statements,
    )
    assert candidate.status is ContentStatus.CANDIDATE
    assert not candidate.quality_issues
    assert {item.predicate for item in candidate.statements} >= {"PART_OF", "HAS_FAILURE_MODE", "CAUSED_BY"}
    store.record_review(
        target_type="graph",
        target_id=candidate.graph_version_id,
        reviewer="domain-expert",
        decision="approve",
    )
    return store.publish_graph(candidate.graph_version_id), evidence_id


def test_m2_to_m5_delivery_closes_with_field_evidence_and_exports(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "governance.db")
    document = _published_document(store)
    graph, evidence_id = _published_graph(store, document)

    # The governed graph remains directly consumable by the existing GraphRAG store.
    graph_store = GraphStore(tmp_path / "retrieval_graph.db")
    graph_edges = normalize_kg_payload(store.graph_as_edge_payload(graph.graph_version_id))
    graph_store.import_edges(graph_edges)
    assert graph_store.summary()["edge_count"] == 6
    assert graph_store.search_evidence("过滤器堵塞")

    service = FMEAService(store)
    task = service.run(
        FMEATaskRequest(
            requested_by="纪文龙",
            graph_version_id=graph.graph_version_id,
            document_version_ids=(document.version_id,),
        )
    )
    assert task.status is TaskStatus.NEEDS_REVIEW
    assert len(task.items) == 1
    item = task.items[0]
    assert item.fields == {
        "equipment": "燃气轮机",
        "component": "润滑油系统",
        "failure_mode": "过滤器堵塞",
        "cause": "油液污染",
        "effect": "润滑油压下降",
        "detection_method": "压差监测",
        "recommended_action": "更换滤芯并清洁油路",
    }
    assert all(evidence_id in citations for citations in item.field_evidence.values())
    assert not item.issues

    approved = service.review(task.task_id, reviewer="fmea-expert", decision="approve")
    assert approved.status is TaskStatus.APPROVED
    published = service.publish(task.task_id)
    assert published.status is TaskStatus.PUBLISHED

    json_payload = json.loads(service.export_json(task.task_id))
    assert json_payload["items"][0]["field_evidence"]["failure_mode"] == [evidence_id]
    csv_rows = list(csv.DictReader(io.StringIO(service.export_csv(task.task_id))))
    assert csv_rows[0]["failure_mode"] == "过滤器堵塞"
    assert csv_rows[0]["failure_mode_evidence"] == evidence_id


def test_document_version_compare_and_audited_rollback(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "governance.db")
    first = _published_document(store, document_id="manual")
    second = store.create_document_candidate(
        document_id="manual",
        source_name="manual.txt",
        chunks=[{"chunk_id": "replacement", "text": "新的错误内容"}],
    )
    store.record_review(target_type="document", target_id=second.version_id, reviewer="reviewer-b", decision="approve")
    second = store.publish_document(second.version_id)

    diff = store.compare_document_versions(first.version_id, second.version_id)
    assert diff["content_changed"] is True
    assert diff["added_chunks"] == ["replacement"]

    rolled_back = store.rollback_document("manual", first.version_id, reviewer="reviewer-c")
    assert rolled_back.version == 3
    assert rolled_back.status is ContentStatus.PUBLISHED
    assert rolled_back.content_hash == first.content_hash
    assert store.get_document_version(second.version_id).status is ContentStatus.RETIRED
    decisions = [review.decision for review in store.list_reviews("document", rolled_back.version_id)]
    assert decisions == [ReviewDecision.ROLLBACK, ReviewDecision.APPROVE]


def test_document_human_revision_creates_new_content_version(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "governance.db")
    original = _published_document(store, document_id="revision-manual")
    source_evidence = original.evidence[0]

    revised = store.create_document_revision(
        original.version_id,
        reviewer="ocr-reviewer",
        comment="Corrected OCR term and retained the source locator",
        corrections={
            source_evidence.evidence_id: {
                "text": source_evidence.text.replace("过滤器堵塞", "润滑油过滤器堵塞"),
                "metadata": {"correction_reason": "OCR terminology review"},
            }
        },
    )

    assert revised.version == 2
    assert revised.supersedes_version_id == original.version_id
    assert "润滑油过滤器堵塞" in revised.evidence[0].text
    assert revised.evidence[0].page == source_evidence.page
    assert revised.evidence[0].metadata["revised_from_evidence_id"] == source_evidence.evidence_id
    assert store.get_document_version(original.version_id).evidence[0].text == source_evidence.text
    assert [item.decision for item in store.list_reviews("document", revised.version_id)] == [
        ReviewDecision.MODIFY
    ]

    with pytest.raises(GovernanceError, match="latest human approval"):
        store.publish_document(revised.version_id)
    store.record_review(
        target_type="document",
        target_id=revised.version_id,
        reviewer="domain-reviewer",
        decision=ReviewDecision.APPROVE,
    )
    published = store.publish_document(revised.version_id)
    assert published.status is ContentStatus.PUBLISHED
    assert store.get_document_version(original.version_id).status is ContentStatus.RETIRED


def test_graph_blocks_unknown_or_unbound_facts_even_after_review(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "governance.db")
    document = _published_document(store)
    graph = store.create_graph_candidate(
        source_document_version_ids=[document.version_id],
        statements=[
            {
                "subject": "润滑油系统",
                "predicate": "未经定义的关系",
                "object": "过滤器堵塞",
                "subject_type": "COMPONENT",
                "object_type": "FAILURE_MODE",
                "evidence_ids": ["EV-does-not-exist"],
                "confidence": 0.9,
            }
        ],
    )
    assert graph.status is ContentStatus.NEEDS_REVIEW
    assert {issue.code for issue in graph.quality_issues} >= {"unknown_relation_type", "missing_source_evidence"}
    store.record_review(target_type="graph", target_id=graph.graph_version_id, reviewer="expert", decision="approve")
    with pytest.raises(GovernanceError, match="unresolved blocking issues"):
        store.publish_graph(graph.graph_version_id)


def test_fmea_human_correction_and_feedback_routing(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "governance.db")
    document = _published_document(store)
    evidence_id = document.evidence[0].evidence_id
    graph_candidate = store.create_graph_candidate(
        source_document_version_ids=[document.version_id],
        statements=[
            {
                "subject": "润滑油系统",
                "predicate": "故障模式",
                "object": "过滤器堵塞",
                "subject_type": "COMPONENT",
                "object_type": "FAILURE_MODE",
                "evidence_ids": [evidence_id],
                "confidence": 0.95,
            }
        ],
    )
    store.record_review(
        target_type="graph", target_id=graph_candidate.graph_version_id, reviewer="expert", decision="approve"
    )
    graph = store.publish_graph(graph_candidate.graph_version_id)
    service = FMEAService(store)
    task = service.run(
        FMEATaskRequest(
            requested_by="user",
            graph_version_id=graph.graph_version_id,
            document_version_ids=(document.version_id,),
        )
    )
    assert any(issue.code == "missing_field" for issue in task.items[0].issues)

    corrected = service.review(
        task.task_id,
        reviewer="expert",
        decision="modify",
        corrections={
            task.items[0].item_id: {
                "cause": {"value": "油液污染", "evidence_ids": [evidence_id]},
            }
        },
    )
    assert corrected.items[0].fields["cause"] == "油液污染"
    assert corrected.items[0].field_evidence["cause"] == (evidence_id,)
    assert corrected.items[0].metadata["human_modified_fields"] == ["cause"]

    feedback = store.add_feedback(
        task_id=task.task_id,
        item_id=task.items[0].item_id,
        code="entity_conflict",
        message="实体别名需要合并",
        created_by="expert",
    )
    assert feedback["routed_module"] == "M4"
