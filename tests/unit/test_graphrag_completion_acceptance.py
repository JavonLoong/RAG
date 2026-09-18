from __future__ import annotations

# ruff: noqa: RUF001
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core_domain.delivery import ContentStatus, GraphDomainSchema, ReviewDecision
from kg_pipeline.governed_extraction import extract_governed_statements
from rag_orchestrator.governed_graphrag import GovernedGraphRAGService
from scripts.run_graphrag_completion_delivery import run_delivery
from storage_layer.governance_store import GovernanceError, GovernanceStore
from storage_layer.governed_index import GovernedDocumentIndex
from storage_layer.graph_store import GraphStore, normalize_kg_payload

REPO_ROOT = Path(__file__).resolve().parents[2]
API_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from chroma_rag_poc.api import (  # noqa: E402
    _build_graph_quality_fallback_response,
    _mark_query_level_graphrag_fallback,
    create_app,
)
from chroma_rag_poc.embeddings import HashingEmbeddingFunction  # noqa: E402

FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "graphrag" / "gas_turbine_representative_material.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _published_representative_document(store: GovernanceStore):
    fixture = _fixture()
    source = fixture["source_document"]
    candidate = store.create_document_candidate(
        document_id=source["document_id"],
        source_name=source["source_file"],
        chunks=[
            {
                "chunk_id": item["chunk_id"],
                "text": item["reviewed_text"],
                "page": item["page"],
                "block_id": item["block_id"],
                "metadata": {
                    "original_ocr": item["original_ocr"],
                    "human_reviewed": True,
                    "source_path": source["source_path"],
                    "model": source["model"],
                },
            }
            for item in fixture["records"]
        ],
        metadata={"fixture_version": fixture["fixture_version"], "representative_material": True},
    )
    store.record_review(
        target_type="document",
        target_id=candidate.version_id,
        reviewer="燃机资料审核人",
        decision=ReviewDecision.APPROVE,
        comment="真实OCR摘录与人工校正文逐页核对通过",
    )
    return store.publish_document(candidate.version_id)


def test_model_extraction_records_provider_execution_metadata_without_raw_text(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "governance.sqlite3")
    document = _published_representative_document(store)

    def model_client(_prompt: str, *, temperature: float = 0.0) -> str:
        assert temperature == 0.2
        return json.dumps(
            {
                "statements": [
                    {
                        "subject": "润滑油系统",
                        "predicate": "HAS_FAILURE_MODE",
                        "object": "过滤器堵塞",
                        "subject_type": "COMPONENT",
                        "object_type": "FAILURE_MODE",
                        "confidence": 0.91,
                    }
                ]
            },
            ensure_ascii=False,
        )

    extraction = extract_governed_statements(
        [document],
        backend="llm",
        model_client=model_client,
        model_name="local-model-v1",
        prompt_version="gt-extract-v3",
        temperature=0.2,
        timeout_seconds=2.0,
        retries=1,
    )
    assert extraction.diagnostics["model"] == "local-model-v1"
    assert extraction.diagnostics["prompt_version"] == "gt-extract-v3"
    chunk = extraction.diagnostics["chunks"][0]
    assert chunk["attempt_count"] == 1
    assert chunk["duration_ms"] >= 0
    assert len(chunk["prompt_sha256"]) == 64
    assert len(chunk["raw_response_summary"]["sha256"]) == 64
    assert "raw_response" not in chunk


def _published_representative_graph(store: GovernanceStore):
    document = _published_representative_document(store)
    extraction = extract_governed_statements([document], backend="rules")
    candidate = store.create_graph_candidate(
        source_document_version_ids=[document.version_id],
        statements=extraction.statements,
        metadata={"fixture_version": _fixture()["fixture_version"], "extraction": extraction.diagnostics},
    )
    assert not candidate.quality_issues
    store.record_review(
        target_type="graph",
        target_id=candidate.graph_version_id,
        reviewer="燃机图谱审核人",
        decision=ReviewDecision.APPROVE,
        comment="知识类型、型号作用域、关系约束和原文证据审核通过",
    )
    return document, store.publish_graph(candidate.graph_version_id), extraction


def _index(tmp_path: Path) -> GovernedDocumentIndex:
    return GovernedDocumentIndex(
        tmp_path / "index",
        embedding_function=HashingEmbeddingFunction(),
        embedding_backend="hashing",
        embedding_model="hashing-384-acceptance",
        embedding_warning="Acceptance fixture backend",
    )


def test_versioned_schema_and_real_material_extraction_are_complete(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "governance.db")
    document, graph, extraction = _published_representative_graph(store)

    assert document.metadata["representative_material"] is True
    assert len(extraction.statements) == 18
    assert len(graph.statements) == 18
    assert "MODEL" in graph.schema.entity_types
    assert {"STRUCTURAL", "FAILURE", "CAUSAL", "EFFECT", "DETECTION", "MITIGATION"} <= set(
        graph.schema.knowledge_types
    )
    assert all(item.knowledge_type == graph.schema.knowledge_type_for_relation(item.predicate) for item in graph.statements)
    assert all(item.model_scope == ("M701F",) for item in graph.statements)
    assert {item.predicate for item in graph.statements} == {
        "PART_OF",
        "HAS_FAILURE_MODE",
        "CAUSED_BY",
        "HAS_EFFECT",
        "DETECTED_BY",
        "MITIGATED_BY",
    }
    evidence_audit = store.audit_graph_evidence(graph.graph_version_id)
    assert evidence_audit["pass"] is True
    assert evidence_audit["evidence_coverage"] == 1.0
    assert evidence_audit["resolved_statement_count"] == 18


def test_alias_duplicate_model_difference_conflict_and_professional_constraints(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "governance.db")
    document = _published_representative_document(store)
    ev1, ev2, ev3 = (item.evidence_id for item in document.evidence)
    schema = GraphDomainSchema(entity_aliases={"滑油滤网": "滑油过滤器"})
    candidate = store.create_graph_candidate(
        source_document_version_ids=[document.version_id],
        schema=schema,
        statements=[
            {
                "subject": "滑油滤网",
                "predicate": "故障模式",
                "object": "堵塞",
                "subject_type": "COMPONENT",
                "object_type": "FAILURE_MODE",
                "evidence_ids": [ev1],
                "model_scope": ["M701 F"],
                "confidence": 0.92,
            },
            {
                "subject": "滑油过滤器",
                "predicate": "HAS_FAILURE_MODE",
                "object": "堵塞",
                "subject_type": "COMPONENT",
                "object_type": "FAILURE_MODE",
                "evidence_ids": [ev2],
                "model_scope": ["M701F"],
                "confidence": 0.94,
            },
            {
                "subject": "堵塞",
                "predicate": "措施",
                "object": "切换过滤器",
                "subject_type": "FAILURE_MODE",
                "object_type": "ACTION",
                "evidence_ids": [ev1],
                "model_scope": ["M701F"],
                "confidence": 0.91,
            },
            {
                "subject": "堵塞",
                "predicate": "措施",
                "object": "在线清洗",
                "subject_type": "FAILURE_MODE",
                "object_type": "ACTION",
                "evidence_ids": [ev2],
                "model_scope": ["PG9351FA"],
                "confidence": 0.90,
            },
            {
                "subject": "堵塞",
                "predicate": "影响",
                "object": "油压降低",
                "subject_type": "FAILURE_MODE",
                "object_type": "EFFECT",
                "evidence_ids": [ev1],
                "model_scope": ["M701F"],
                "confidence": 0.90,
            },
            {
                "subject": "堵塞",
                "predicate": "影响",
                "object": "油温升高",
                "subject_type": "FAILURE_MODE",
                "object_type": "EFFECT",
                "evidence_ids": [ev3],
                "model_scope": ["M701F"],
                "confidence": 0.90,
            },
        ],
    )
    issue_codes = {item.code for item in candidate.quality_issues}
    assert {"model_difference", "source_conflict"} <= issue_codes
    failure_edges = [item for item in candidate.statements if item.predicate == "HAS_FAILURE_MODE"]
    assert len(failure_edges) == 1
    assert failure_edges[0].subject == "滑油过滤器"
    assert failure_edges[0].model_scope == ("M701F",)
    assert failure_edges[0].evidence_ids == (ev1, ev2)
    assert failure_edges[0].metadata["merged_duplicate_count"] == 2
    assert not any(
        item.code == "source_conflict" and item.metadata.get("predicate") == "MITIGATED_BY"
        for item in candidate.quality_issues
    )

    store.record_review(
        target_type="graph",
        target_id=candidate.graph_version_id,
        reviewer="型号审核人",
        decision=ReviewDecision.APPROVE,
        comment="型号差异保留，来源冲突已人工确认",
    )
    published = store.publish_graph(candidate.graph_version_id)
    assert store.audit_graph_evidence(published.graph_version_id)["pass"] is True

    invalid = store.create_graph_candidate(
        source_document_version_ids=[document.version_id],
        statements=[
            {
                "subject": "过滤器堵塞",
                "predicate": "PART_OF",
                "object": "切换过滤器",
                "subject_type": "CAUSE",
                "object_type": "ACTION",
                "knowledge_type": "CAUSAL",
                "evidence_ids": [ev1],
                "confidence": 0.95,
            }
        ],
    )
    invalid_codes = {item.code for item in invalid.quality_issues}
    assert {"invalid_relation_endpoints", "knowledge_relation_mismatch"} <= invalid_codes
    store.record_review(
        target_type="graph",
        target_id=invalid.graph_version_id,
        reviewer="审核人",
        decision=ReviewDecision.APPROVE,
    )
    with pytest.raises(GovernanceError, match="unresolved blocking issues"):
        store.publish_graph(invalid.graph_version_id)


def test_graph_version_list_compare_view_export_and_audited_rollback(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "governance.db")
    document, first, _ = _published_representative_graph(store)
    second_candidate = store.create_graph_candidate(
        source_document_version_ids=[document.version_id],
        statements=first.statements[:-1],
        schema=first.schema,
        metadata={"change": "removed one action for version comparison"},
    )
    store.record_review(
        target_type="graph",
        target_id=second_candidate.graph_version_id,
        reviewer="版本审核人",
        decision=ReviewDecision.APPROVE,
    )
    second = store.publish_graph(second_candidate.graph_version_id)
    comparison = store.compare_graph_versions(first.graph_version_id, second.graph_version_id)
    assert comparison["changed"] is True
    assert len(comparison["removed_statements"]) == 1

    rolled_back = store.rollback_graph(first.graph_version_id, reviewer="版本审核人")
    assert rolled_back.version == 3
    assert rolled_back.status is ContentStatus.PUBLISHED
    assert rolled_back.metadata["rollback_from_graph_version_id"] == first.graph_version_id
    assert len(rolled_back.statements) == len(first.statements)
    assert [item.version for item in store.list_graph_versions()] == [3, 2, 1]
    assert store.get_graph_version(second.graph_version_id).status is ContentStatus.RETIRED
    decisions = [item.decision for item in store.list_reviews("graph", rolled_back.graph_version_id)]
    assert decisions == [ReviewDecision.ROLLBACK, ReviewDecision.APPROVE]

    view = store.graph_as_view_payload(rolled_back.graph_version_id)
    assert len(view["edges"]) == 18
    assert all(item["evidence"] for item in view["edges"])
    exported = store.graph_as_edge_payload(rolled_back.graph_version_id)
    assert all(item["knowledge_type"] and item["model_scope"] == ["M701F"] for item in exported)


def test_graphrag_answer_paths_same_question_comparison_and_ordinary_rag_fallback(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "governance.db")
    document, graph, _ = _published_representative_graph(store)
    index = _index(tmp_path)
    index.sync_document(document)
    service = GovernedGraphRAGService(store, index)

    answer = service.graph_rag(
        graph.graph_version_id,
        "M701F滑油母管压力低的原因、影响和处理措施是什么？",
    )
    assert answer.mode_used == "graphrag"
    assert answer.no_answer is False
    assert answer.citations
    assert answer.paths
    assert all(item["evidence_ids"] and item["locators"] for item in answer.citations)
    assert "[G" in answer.answer
    assert answer.quality["evidence_audit"]["pass"] is True

    fallback = service.graph_rag(
        graph.graph_version_id,
        "M701F高压压气机叶片裂纹的维修限值是多少？",
    )
    assert fallback.mode_used == "ordinary_rag"
    assert fallback.fallback == {
        "triggered": True,
        "from": "graphrag",
        "to": "ordinary_rag",
        "reason": "no_relevant_evidence_bound_graph_path",
    }
    assert fallback.no_answer is True

    report = service.compare_same_questions(
        graph.graph_version_id,
        _fixture()["comparison_questions"],
    )
    assert report["case_count"] == 4
    assert report["evaluation_type"] == "ordinary_rag_vs_graphrag_same_questions"
    assert all("ordinary_rag" in item and "graphrag" in item for item in report["cases"])
    assert report["cases"][-1]["fallback_recommended"] is True
    assert report["cases"][-1]["graphrag"]["no_answer"] is True


def test_version_aware_graph_api_query_view_compare_and_rollback(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "governance.db")
    document, graph, _ = _published_representative_graph(store)
    index = _index(tmp_path)
    index.sync_document(document)
    graph_store = GraphStore(tmp_path / "active-graph.sqlite")
    graph_store.import_edges(normalize_kg_payload(store.graph_as_edge_payload(graph.graph_version_id)), reset=True)

    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    app.state.governance_store = store
    app.state.governed_document_index = index
    app.state.governed_graph_store = graph_store
    client = TestClient(app)

    listed = client.get("/api/delivery/graphs")
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"][0]["graph_version_id"] == graph.graph_version_id

    view = client.get(f"/api/delivery/graphs/{graph.graph_version_id}/view")
    assert view.status_code == 200, view.text
    assert len(view.json()["edges"]) == 18
    assert client.get(f"/api/delivery/graphs/{graph.graph_version_id}/evidence-audit").json()["pass"] is True

    answer = client.post(
        f"/api/delivery/graphs/{graph.graph_version_id}/query",
        json={"question": "防喘放气阀故障通过什么路径影响M701F燃气轮机？"},
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["mode_used"] == "graphrag"
    assert answer.json()["paths"]

    comparison = client.post(
        f"/api/delivery/graphs/{graph.graph_version_id}/compare-rag",
        json={"questions": _fixture()["comparison_questions"]},
    )
    assert comparison.status_code == 200, comparison.text
    assert comparison.json()["case_count"] == 4
    background_comparison = client.post(
        f"/api/delivery/graphs/{graph.graph_version_id}/compare-rag?background=true",
        headers={"Idempotency-Key": "representative-graph-eval-v1"},
        json={"questions": _fixture()["comparison_questions"]},
    )
    assert background_comparison.status_code == 202, background_comparison.text
    evaluation_task = client.get(
        f"/api/delivery/tasks/{background_comparison.json()['task']['task_id']}"
    ).json()
    assert evaluation_task["status"] == "completed"
    assert evaluation_task["result"]["evaluation"]["case_count"] == 4

    rollback = client.post(
        "/api/delivery/graphs/rollback",
        json={"target_graph_version_id": graph.graph_version_id, "reviewer": "API版本审核人"},
    )
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["version"] == 2
    assert rollback.json()["graph_store_sync"]["edge_count"] == 18


def test_main_query_graph_quality_and_effect_fallback_use_full_ordinary_rag() -> None:
    class TextRetriever:
        def retrieve(self, _question: str, top_k: int = 5):
            return [
                {
                    "id": "ev-1",
                    "text": "过滤器堵塞会造成滑油压力降低。",
                    "source": "manual.pdf",
                    "score": 0.95,
                }
            ][:top_k]

    class LLM:
        def generate(self, _prompt: str, **_kwargs):
            return "过滤器堵塞会导致滑油压力降低 [T1]。"

    fallback = _build_graph_quality_fallback_response(
        question="滑油压力低的原因是什么？",
        text_retriever=TextRetriever(),
        top_k=3,
        graph_quality={"quality_gate": {"failures": [{"metric": "evidence_coverage"}]}},
        gate_message="graph evidence coverage failed",
        llm=LLM(),
    )
    assert fallback["fallback_from"] == "graphrag"
    assert fallback["fallback_to"] == "ordinary_rag"
    assert fallback["ordinary_rag_answer_generated"] is True
    assert "Ordinary RAG answer" in fallback["answer"]
    assert "[T1]" in fallback["answer"]

    marked = _mark_query_level_graphrag_fallback(
        {
            "answer": "文本回答 [T1]",
            "citations": [{"id": "T1", "source_type": "text", "text": "文本证据"}],
        }
    )
    assert marked["graphrag_effect_fallback"] is True
    assert marked["effective_mode"] == "ordinary_rag"


def test_completion_delivery_package_contains_all_required_outputs(tmp_path: Path) -> None:
    manifest = run_delivery(tmp_path / "delivery")
    output_dir = Path(manifest["output_dir"])
    assert manifest["acceptance"]["all_acceptance_gates_pass"] is True
    assert manifest["acceptance"]["automatic_statement_count"] == 18
    assert manifest["acceptance"]["same_question_case_count"] == 4
    for filename in (
        "schema.json",
        "published_graph.json",
        "entities_relationships.json",
        "conflict_constraint_results.json",
        "evidence_audit.json",
        "graph_path.json",
        "graphrag_answer.json",
        "ordinary_rag_vs_graphrag_comparison.json",
        "ordinary_rag_fallback_answer.json",
        "fmea.json",
        "fmea.csv",
        "completion_report.md",
    ):
        assert (output_dir / filename).is_file(), filename
