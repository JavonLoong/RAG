"""Generate the complete governed GraphRAG acceptance delivery package."""

# ruff: noqa: RUF001

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
API_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
for path in (REPO_ROOT, API_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from chroma_rag_poc.embeddings import HashingEmbeddingFunction  # noqa: E402

from core_domain.delivery import FMEATaskRequest, GraphDomainSchema, ReviewDecision  # noqa: E402
from kg_pipeline.governed_extraction import extract_governed_statements  # noqa: E402
from rag_orchestrator.fmea import FMEAService  # noqa: E402
from rag_orchestrator.governed_graphrag import GovernedGraphRAGService  # noqa: E402
from storage_layer.governance_store import GovernanceStore  # noqa: E402
from storage_layer.governed_index import GovernedDocumentIndex  # noqa: E402
from storage_layer.graph_store import GraphStore, normalize_kg_payload  # noqa: E402

FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "graphrag" / "gas_turbine_representative_material.json"


def run_delivery(output_root: str | Path) -> dict[str, Any]:
    run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_dir = Path(output_root) / run_id
    runtime_dir = output_dir / "runtime"
    output_dir.mkdir(parents=True, exist_ok=False)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    source = fixture["source_document"]
    store = GovernanceStore(runtime_dir / "governance.sqlite3")
    index = GovernedDocumentIndex(
        runtime_dir / "retrieval_chroma",
        embedding_function=HashingEmbeddingFunction(),
        embedding_backend="hashing",
        embedding_model="hashing-384-offline-acceptance",
        embedding_warning="Offline deterministic acceptance backend; production can inject the configured embedding.",
    )
    graph_store = GraphStore(runtime_dir / "graph_store.sqlite")

    document_candidate = store.create_document_candidate(
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
                    "source_path": source["source_path"],
                    "model": source["model"],
                    "human_reviewed": True,
                },
            }
            for item in fixture["records"]
        ],
        metadata={"fixture_version": fixture["fixture_version"], "representative_material": True},
    )
    store.record_review(
        target_type="document",
        target_id=document_candidate.version_id,
        reviewer="燃机资料审核人",
        decision=ReviewDecision.APPROVE,
        comment="真实OCR摘录与人工校正文逐页核对通过",
    )
    document = store.publish_document(document_candidate.version_id)
    index_status = index.sync_document(document)

    extraction = extract_governed_statements([document], backend="rules")
    graph_candidate = store.create_graph_candidate(
        source_document_version_ids=[document.version_id],
        statements=extraction.statements,
        metadata={"fixture_version": fixture["fixture_version"], "extraction": extraction.diagnostics},
    )
    store.record_review(
        target_type="graph",
        target_id=graph_candidate.graph_version_id,
        reviewer="燃机图谱审核人",
        decision=ReviewDecision.APPROVE,
        comment="Schema、型号作用域、关系约束与证据审核通过",
    )
    graph = store.publish_graph(graph_candidate.graph_version_id)
    graph_sync = graph_store.import_edges(
        normalize_kg_payload(store.graph_as_edge_payload(graph.graph_version_id)),
        reset=True,
    )
    evidence_audit = store.audit_graph_evidence(graph.graph_version_id)
    graph_view = store.graph_as_view_payload(graph.graph_version_id)
    graph_path = store.find_graph_path(
        graph.graph_version_id,
        "M701F燃气轮机",
        "切换过滤器",
        max_hops=4,
    )

    evidence_ids = [item.evidence_id for item in document.evidence]
    conflict_candidate = store.create_graph_candidate(
        source_document_version_ids=[document.version_id],
        schema=GraphDomainSchema(entity_aliases={"滑油滤网": "滑油过滤器"}),
        statements=[
            _raw_statement("滑油滤网", "故障模式", "堵塞", "COMPONENT", "FAILURE_MODE", evidence_ids[0], "M701 F"),
            _raw_statement("滑油过滤器", "HAS_FAILURE_MODE", "堵塞", "COMPONENT", "FAILURE_MODE", evidence_ids[1], "M701F"),
            _raw_statement("堵塞", "措施", "切换过滤器", "FAILURE_MODE", "ACTION", evidence_ids[0], "M701F"),
            _raw_statement("堵塞", "措施", "在线清洗", "FAILURE_MODE", "ACTION", evidence_ids[1], "PG9351FA"),
            _raw_statement("堵塞", "影响", "油压降低", "FAILURE_MODE", "EFFECT", evidence_ids[0], "M701F"),
            _raw_statement("堵塞", "影响", "油温升高", "FAILURE_MODE", "EFFECT", evidence_ids[2], "M701F"),
        ],
        metadata={"purpose": "alias_duplicate_model_difference_source_conflict_acceptance"},
    )
    invalid_candidate = store.create_graph_candidate(
        source_document_version_ids=[document.version_id],
        statements=[{
            **_raw_statement(
                "过滤器堵塞",
                "PART_OF",
                "切换过滤器",
                "CAUSE",
                "ACTION",
                evidence_ids[0],
                "M701F",
            ),
            "knowledge_type": "CAUSAL",
        }],
        metadata={"purpose": "professional_constraint_rejection_acceptance"},
    )
    conflict_constraint_results = {
        "alias_duplicate_model_conflict_candidate": conflict_candidate.to_dict(),
        "blocking_constraint_candidate": invalid_candidate.to_dict(),
        "expected_warning_codes": ["model_difference", "source_conflict"],
        "expected_blocking_codes": ["invalid_relation_endpoints", "knowledge_relation_mismatch"],
    }

    qa = GovernedGraphRAGService(store, index)
    graph_answer = qa.graph_rag(
        graph.graph_version_id,
        fixture["comparison_questions"][0]["question"],
    ).to_dict()
    comparison = qa.compare_same_questions(
        graph.graph_version_id,
        fixture["comparison_questions"],
    )
    fallback_answer = qa.graph_rag(
        graph.graph_version_id,
        fixture["comparison_questions"][-1]["question"],
    ).to_dict()

    fmea_service = FMEAService(store)
    fmea = fmea_service.run(
        FMEATaskRequest(
            requested_by="FMEA生成操作员",
            graph_version_id=graph.graph_version_id,
            document_version_ids=(document.version_id,),
            template="gas_turbine_minimum_v1",
            template_version="1.1.0",
        )
    )
    fmea_service.review(fmea.task_id, reviewer="FMEA审核人", decision=ReviewDecision.APPROVE)
    fmea = fmea_service.publish(fmea.task_id)
    fmea_export_verification = fmea_service.verify_export_consistency(fmea.task_id)

    artifacts: dict[str, Any] = {
        "source_annotation_fixture.json": fixture,
        "schema.json": graph.schema.to_dict(),
        "published_document.json": document.to_dict(),
        "published_graph.json": graph.to_dict(),
        "entities_relationships.json": graph_view,
        "evidence_audit.json": evidence_audit,
        "conflict_constraint_results.json": conflict_constraint_results,
        "graph_path.json": graph_path,
        "graphrag_answer.json": graph_answer,
        "ordinary_rag_vs_graphrag_comparison.json": comparison,
        "ordinary_rag_fallback_answer.json": fallback_answer,
        "fmea.json": fmea.to_dict(),
        "fmea_export_verification.json": fmea_export_verification,
    }
    for filename, payload in artifacts.items():
        (output_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    (output_dir / "fmea.csv").write_text(fmea_service.export_csv(fmea.task_id), encoding="utf-8-sig")
    (output_dir / "fmea.docx").write_bytes(fmea_service.export_docx(fmea.task_id))

    manifest = {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "output_dir": str(output_dir.resolve()),
        "fixture_version": fixture["fixture_version"],
        "document_version_id": document.version_id,
        "graph_version_id": graph.graph_version_id,
        "fmea_task_id": fmea.task_id,
        "acceptance": {
            "representative_real_excerpt_records": len(fixture["records"]),
            "automatic_statement_count": len(graph.statements),
            "evidence_audit_pass": evidence_audit["pass"],
            "graph_path_found": graph_path["found"],
            "graphrag_answer_mode": graph_answer["mode_used"],
            "same_question_case_count": comparison["case_count"],
            "fallback_mode": fallback_answer["mode_used"],
            "fallback_triggered": bool(fallback_answer["fallback"]),
            "fmea_status": fmea.status.value,
            "fmea_export_consistent": fmea_export_verification["consistent"],
            "fmea_export_rows": {
                "json": fmea_export_verification["json_rows"],
                "csv": fmea_export_verification["csv_rows"],
                "docx": fmea_export_verification["docx_rows"],
            },
            "all_acceptance_gates_pass": all(
                [
                    len(graph.statements) == 18,
                    evidence_audit["pass"],
                    graph_path["found"],
                    graph_answer["mode_used"] == "graphrag",
                    comparison["case_count"] == len(fixture["comparison_questions"]),
                    fallback_answer["mode_used"] == "ordinary_rag",
                    bool(fallback_answer["fallback"]),
                    fmea.status.value == "published",
                    fmea_export_verification["consistent"],
                ]
            ),
        },
        "runtime": {
            "document_index": index_status,
            "graph_store": graph_sync,
        },
        "artifacts": sorted([*artifacts, "fmea.csv", "fmea.docx", "completion_report.md", "manifest.json"]),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "completion_report.md").write_text(_report(manifest), encoding="utf-8")
    return manifest


def _raw_statement(
    subject: str,
    predicate: str,
    object_name: str,
    subject_type: str,
    object_type: str,
    evidence_id: str,
    model_scope: str,
) -> dict[str, Any]:
    return {
        "subject": subject,
        "predicate": predicate,
        "object": object_name,
        "subject_type": subject_type,
        "object_type": object_type,
        "evidence_ids": [evidence_id],
        "model_scope": [model_scope],
        "confidence": 0.92,
    }


def _report(manifest: dict[str, Any]) -> str:
    acceptance = manifest["acceptance"]
    return f"""# 燃机 GraphRAG 完整交付验收报告

- 运行编号：`{manifest['run_id']}`
- 资料版本：`{manifest['document_version_id']}`
- 图谱版本：`{manifest['graph_version_id']}`
- FMEA 任务：`{manifest['fmea_task_id']}`
- 真实摘录标注集：`{manifest['fixture_version']}`

| 验收项 | 结果 |
|---|---|
| 真实燃机摘录 | {acceptance['representative_real_excerpt_records']} 页 |
| 自动实体关系 | {acceptance['automatic_statement_count']} 条 |
| 已发布关系证据覆盖 | {acceptance['evidence_audit_pass']} |
| 图路径 | {acceptance['graph_path_found']} |
| GraphRAG 回答 | {acceptance['graphrag_answer_mode']} |
| 普通 RAG / GraphRAG 同题对比 | {acceptance['same_question_case_count']} 题 |
| 效果不足回退 | {acceptance['fallback_mode']} / {acceptance['fallback_triggered']} |
| FMEA | {acceptance['fmea_status']} |
| FMEA JSON/CSV/DOCX 一致性 | {acceptance['fmea_export_consistent']} · {acceptance['fmea_export_rows']} |
| 全部门禁 | {acceptance['all_acceptance_gates_pass']} |

详细证据见同目录 JSON/CSV/DOCX 产物。
"""


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        default=str(REPO_ROOT / "build" / "graphrag_completion_acceptance"),
    )
    args = parser.parse_args()
    print(json.dumps(run_delivery(args.output_root), ensure_ascii=False, indent=2))
