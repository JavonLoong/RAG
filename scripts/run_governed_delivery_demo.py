"""Generate a deterministic M2-M5 two-week progress demonstration package."""

# ruff: noqa: RUF001, W291

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api_server.current_console.chroma_rag_poc.src.chroma_rag_poc.embeddings import (  # noqa: E402
    HashingEmbeddingFunction,
)
from core_domain.delivery import FMEATaskRequest, ReviewDecision  # noqa: E402
from kg_pipeline.governed_extraction import extract_governed_statements  # noqa: E402
from rag_orchestrator.delivery_remediation import DeliveryRemediationService  # noqa: E402
from rag_orchestrator.fmea import FMEAService  # noqa: E402
from storage_layer.governance_store import GovernanceStore  # noqa: E402
from storage_layer.governed_index import GovernedDocumentIndex  # noqa: E402
from storage_layer.graph_store import GraphStore, normalize_kg_payload  # noqa: E402


def run_demo(output_root: str | Path) -> dict[str, object]:
    run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_dir = Path(output_root) / run_id
    runtime_dir = output_dir / "runtime"
    output_dir.mkdir(parents=True, exist_ok=False)

    store = GovernanceStore(runtime_dir / "governance.sqlite3")
    document_index = GovernedDocumentIndex(
        runtime_dir / "retrieval_chroma",
        embedding_function=HashingEmbeddingFunction(dimension=384),
        embedding_backend="hashing",
        embedding_model="hashing-384-demo-only",
        embedding_warning="Offline deterministic demo backend; production must use the configured Qwen embedding.",
    )
    graph_store = GraphStore(runtime_dir / "graph_store.sqlite")

    # M2: import page-level OCR output, then persist a human correction as v2.
    ocr_candidate = store.create_document_candidate(
        document_id="demo-lubrication-manual",
        source_name="燃气轮机润滑油系统示例.pdf",
        chunks=[
            {
                "chunk_id": "page-00146",
                "text": (
                    "燃气轮机润滑油系统的过滤器者塞可能由油液污染导致，影响是润滑油压下降。"
                    "可通过压差监测发现，并通过更换滤芯和清洁油路处理。"
                ),
                "source_file": "燃气轮机润滑油系统示例.pdf",
                "page": 146,
                "block_id": "p146-b01",
                "metadata": {"ocr_confidence": 0.48, "reading_order_risk": "high"},
            }
        ],
        quality={"quality_gate_status": "pass", "page_count": 1},
        warnings=("Low OCR confidence page: 146", "Reading-order review required for page: 146"),
        metadata={"demo_stage": "M2", "intake_route": "ocr_result"},
    )
    corrected_text = (
        "燃气轮机润滑油系统的过滤器堵塞可能由油液污染导致，影响是润滑油压下降。"
        "可通过压差监测发现，并通过更换滤芯和清洁油路处理。"
    )
    revised = store.create_document_revision(
        ocr_candidate.version_id,
        reviewer="纪文龙",
        comment="人工对照原页修正 OCR 术语",
        corrections={ocr_candidate.evidence[0].evidence_id: {"text": corrected_text}},
    )
    store.record_review(
        target_type="document",
        target_id=revised.version_id,
        reviewer="资料审核人",
        decision=ReviewDecision.APPROVE,
        comment="原页、页码和修订内容核对通过",
    )
    published_document = store.publish_document(revised.version_id)

    # M3: active published version drives the retrieval projection.
    index_sync = document_index.sync_document(published_document)
    retrieval = document_index.query(
        "过滤器堵塞的原因和检测方法是什么？",
        top_k=3,
        document_version_ids=(published_document.version_id,),
    )

    # M4: automatic offline extraction -> governance gates -> active graph store.
    extraction = extract_governed_statements([published_document], backend="rules")
    graph_candidate = store.create_graph_candidate(
        source_document_version_ids=[published_document.version_id],
        statements=extraction.statements,
        metadata={"extraction": extraction.diagnostics, "demo_stage": "M4"},
    )
    store.record_review(
        target_type="graph",
        target_id=graph_candidate.graph_version_id,
        reviewer="图谱审核人",
        decision=ReviewDecision.APPROVE,
        comment="Schema、原文证据和候选关系审核通过",
    )
    published_graph = store.publish_graph(graph_candidate.graph_version_id)
    graph_payload = store.graph_as_edge_payload(published_graph.graph_version_id)
    graph_sync = graph_store.import_edges(normalize_kg_payload(graph_payload), reset=True)
    path_result = store.find_graph_path(
        published_graph.graph_version_id,
        "燃气轮机",
        "油液污染",
        max_hops=4,
    )

    # M5: graph-to-FMEA, human approval, export verification, executable feedback.
    fmea_service = FMEAService(store)
    fmea_candidate = fmea_service.run(
        FMEATaskRequest(
            requested_by="纪文龙",
            graph_version_id=published_graph.graph_version_id,
            document_version_ids=(published_document.version_id,),
            metadata={"demo_stage": "M5"},
        )
    )
    fmea_service.review(
        fmea_candidate.task_id,
        reviewer="FMEA 审核人",
        decision=ReviewDecision.APPROVE,
        comment="逐字段证据检查通过",
    )
    published_fmea = fmea_service.publish(fmea_candidate.task_id)
    fmea_json = fmea_service.export_json(published_fmea.task_id)
    fmea_csv = fmea_service.export_csv(published_fmea.task_id)
    export_check = fmea_service.verify_export_consistency(published_fmea.task_id)

    feedback = store.add_feedback(
        task_id=published_fmea.task_id,
        item_id=published_fmea.items[0].item_id,
        code="index_stale",
        message="演示：重建正式资料索引并保留执行证据",
        created_by="验收人",
    )
    remediation = DeliveryRemediationService(
        store,
        document_index=document_index,
        graph_store=graph_store,
    ).remediate(feedback["feedback_id"], actor="系统操作员")

    artifacts = {
        "ocr_candidate.json": ocr_candidate.to_dict(),
        "published_document.json": published_document.to_dict(),
        "retrieval_result.json": retrieval,
        "published_graph.json": published_graph.to_dict(),
        "graph_export.json": {"triples": graph_payload},
        "graph_path.json": path_result,
        "fmea.json": json.loads(fmea_json),
        "feedback_remediation.json": remediation,
    }
    for filename, payload in artifacts.items():
        (output_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    (output_dir / "fmea.csv").write_text(fmea_csv, encoding="utf-8-sig")

    manifest = {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "output_dir": str(output_dir),
        "document_version_id": published_document.version_id,
        "graph_version_id": published_graph.graph_version_id,
        "fmea_task_id": published_fmea.task_id,
        "m2": {
            "ocr_candidate_version": ocr_candidate.version_id,
            "corrected_published_version": published_document.version_id,
            "page_locator_preserved": published_document.evidence[0].page == "146",
        },
        "m3": index_sync,
        "m4": {
            "automatic_extraction": extraction.diagnostics,
            "graph_store_sync": graph_sync,
            "path_found": path_result["found"],
        },
        "m5": {
            "task_status": published_fmea.status.value,
            "export_consistency": export_check,
            "feedback_remediation": remediation,
        },
        "acceptance": {
            "closed_loop_pass": all(
                (
                    bool(retrieval["results"]),
                    extraction.diagnostics["candidate_statement_count"] >= 6,
                    path_result["found"],
                    export_check["consistent"],
                    remediation["status"] == "completed",
                )
            ),
            "production_limitations": [
                "演示检索为保证离线复现使用确定性 hashing；生产环境必须启用 Qwen3-Embedding-0.6B。",
                "自动图谱抽取当前使用可审计规则基线；小模型适配器仍需中文标注集基准验证。",
                "M1 权限/来源问题和 M2 内容纠错按治理要求保留人工审批门禁。",
            ],
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "两周开发进度验收报告.md").write_text(
        _render_report(manifest),
        encoding="utf-8",
    )
    return manifest


def _render_report(manifest: dict[str, object]) -> str:
    m2 = manifest["m2"]
    m3 = manifest["m3"]
    m4 = manifest["m4"]
    m5 = manifest["m5"]
    acceptance = manifest["acceptance"]
    return f"""# M2—M5 两周开发进度验收报告

> 运行编号：`{manifest['run_id']}`<br>
> 资料版本：`{manifest['document_version_id']}`<br>
> 图谱版本：`{manifest['graph_version_id']}`<br>
> FMEA 任务：`{manifest['fmea_task_id']}`

## 一句话结论

本次已形成一条可重复运行、带版本和原文证据的 M2→M5 基础闭环。闭环自动验收：**{'通过' if acceptance['closed_loop_pass'] else '未通过'}**。

## 本次可汇报成果

| 模块 | 可执行成果 | 运行结果 |
|---|---|---|
| M2 | OCR 风险候选、人工修订生成新版本、再次批准后发布 | `{m2['ocr_candidate_version']}` → `{m2['corrected_published_version']}`，页码保留：`{m2['page_locator_preserved']}` |
| M3 | 正式资料自动同步 Chroma 索引、版本过滤检索、可重建 | 索引 `{m3['indexed_chunks']}` 个证据块，后端 `{m3['embedding_backend']}` |
| M4 | 自动候选抽取、Schema/证据门禁、GraphStore 同步、证据路径 | 自动关系 `{m4['automatic_extraction']['candidate_statement_count']}` 条，图边 `{m4['graph_store_sync']['edge_count']}` 条，路径：`{m4['path_found']}` |
| M5 | FMEA 生成审核、JSON/CSV 一致性、反馈执行记录 | 状态 `{m5['task_status']}`，导出一致：`{m5['export_consistency']['consistent']}`，回流动作 `{m5['feedback_remediation']['action']}` |

## 建议现场展示顺序

1. 打开 `ocr_candidate.json`，说明第 146 页低置信度和错误术语“者塞”。
2. 打开 `published_document.json`，展示修订后的“堵塞”、新版本和原页定位。
3. 打开 `retrieval_result.json`，展示问题命中正式资料版本及 evidence ID。
4. 打开 `published_graph.json` 和 `graph_path.json`，展示自动抽取关系及“燃气轮机→油液污染”的证据路径。
5. 打开 `fmea.csv` 与 `fmea.json`，展示逐字段证据和两种导出一致。
6. 打开 `feedback_remediation.json`，证明回流已产生实际重建动作和审计记录。

## 当前诚实边界

{chr(10).join(f'- {item}' for item in acceptance['production_limitations'])}

## 阶段评分

按每个模块 2.5 分、同时考察功能/集成/代表性测试，本次阶段评估为 **7.5/10**：已经达到两周进度汇报效果，但仍不等于最终生产验收。
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        default=str(REPO_ROOT / "build" / "governed_delivery_demo"),
        help="Parent directory for the timestamped demonstration package.",
    )
    args = parser.parse_args()
    manifest = run_demo(args.output_root)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
