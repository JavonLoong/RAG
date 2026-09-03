from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONSOLE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(CONSOLE_SRC) not in sys.path:
    sys.path.insert(0, str(CONSOLE_SRC))

from chroma_rag_poc.schemas import SourceRecord, TextBlock  # noqa: E402

from knowledge_base import KnowledgeBaseStore, ReviewDecision, SearchMode  # noqa: E402
from knowledge_base.adapters import document_from_source_records  # noqa: E402
from knowledge_base.query import KnowledgeBaseQueryService  # noqa: E402
from retrieval_engine import KnowledgeBaseRetriever  # noqa: E402
from workflow_runtime import (  # noqa: E402
    PowerRagHandlers,
    RunStatus,
    WorkflowRunner,
    WorkflowStore,
    build_local_to_fmea_workflow,
)


class EvidenceEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(text.count("积垢")), float(text.count("压气机")), float(text.count("清洗"))] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


class M3M6EndToEndTests(unittest.TestCase):
    def test_m2_records_publish_to_versioned_store_and_feed_rag_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kb_store = KnowledgeBaseStore(root / "knowledge.sqlite3")
            workflow_store = WorkflowStore(root / "workflow.sqlite3")
            records = [
                SourceRecord(
                    source_file="compressor-manual.pdf",
                    record_id="record-1",
                    filename="压气机维护手册.pdf",
                    page_num=7,
                    text="",
                    blocks=[
                        TextBlock("压气机污染", "Title", 0, page_num=7),
                        TextBlock("叶片积垢会降低效率，可按维护规程实施在线清洗。", "Para", 1, page_num=7),
                    ],
                    metadata={"review_batch": "batch-1"},
                )
            ]
            parsed_document = document_from_source_records(
                records,
                document_id="compressor-manual",
                source_uri="approved/compressor-manual.pdf",
            )

            def m3_publish(_context):
                revision = kb_store.create_candidate(parsed_document, created_by="m2-adapter")
                kb_store.submit_for_review(revision.revision_id, actor="m2-adapter")
                kb_store.record_review(
                    revision.revision_id,
                    decision=ReviewDecision.APPROVED,
                    reviewer="domain-reviewer",
                )
                kb_store.index_embeddings(
                    revision_ids=[revision.revision_id],
                    embedding_model="evidence-test-v1",
                    embedder=EvidenceEmbedder(),
                )
                release = kb_store.publish(
                    [revision.revision_id],
                    actor="m3-publisher",
                    require_embeddings=True,
                    embedding_model="evidence-test-v1",
                )
                quality = kb_store.verify_version(
                    release.version,
                    require_embeddings=True,
                    embedding_model="evidence-test-v1",
                )
                return {
                    "knowledge_base_version": release.version,
                    "manifest_sha256": release.manifest_sha256,
                    "quality_passed": quality.passed,
                }

            def m4_fallback(context):
                version = context.dependency_outputs["m3_publish"]["knowledge_base_version"]
                service = KnowledgeBaseQueryService(kb_store)
                retriever = KnowledgeBaseRetriever(service, version=version, mode=SearchMode.KEYWORD)
                hits = retriever.retrieve("压气机积垢如何处理", top_k=3)
                context.save_checkpoint("retrieved_chunk_ids", [item.chunk_id for item in hits])
                return {
                    "knowledge_base_version": version,
                    "graph_version": None,
                    "graph_ready": False,
                    "evidence_coverage": 0.0,
                    "rag_fallback_ready": bool(hits and hits[0].metadata["evidence"]),
                    "evidence_chunk_id": hits[0].chunk_id,
                }

            handlers = PowerRagHandlers(
                ingest=lambda _ctx: {"files_received": 1, "files_registered": 1, "files_failed": 0},
                parse_and_review=lambda _ctx: {
                    "review_status": "approved",
                    "evidence_coverage": 1.0,
                    "unresolved_quality_issues": 0,
                },
                publish_knowledge_base=m3_publish,
                build_graphrag=m4_fallback,
                generate_and_review_fmea=lambda context: {
                    "knowledge_base_version": context.dependency_outputs["m3_publish"]["knowledge_base_version"],
                    "artifact_version": "fmea-candidate-reviewed-v1",
                    "review_status": "approved",
                    "field_evidence_coverage": 1.0,
                },
            )
            definition = build_local_to_fmea_workflow(handlers)
            result = WorkflowRunner(workflow_store).start(
                definition,
                {"source_paths": ["compressor-manual.pdf"]},
                idempotency_key="approved-batch-1",
            )

            self.assertEqual(result.status, RunStatus.SUCCEEDED)
            self.assertTrue(kb_store.verify_version(1).passed)
            checkpoint = workflow_store.load_checkpoint(result.run_id, "m4_graphrag", "retrieved_chunk_ids")
            self.assertTrue(checkpoint)


if __name__ == "__main__":
    unittest.main()
