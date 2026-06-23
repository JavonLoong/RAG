"""One-command ingest, search, and evaluation smoke run."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from .harness import EvaluationThresholds, RAGEvaluationCase, RAGEvaluationHarness
from rag_orchestrator import GraphQualityThresholds, evaluate_graph_quality
from storage_layer.graph_store import GraphEdgeRecord, GraphStore


SMOKE_COLLECTION = "rag_smoke"
SMOKE_PAYLOADS: tuple[tuple[str, bytes], ...] = (
    (
        "combined_cycle_smoke.md",
        (
            "# Combined Cycle Smoke Manual\n\n"
            "Combined cycle systems improve efficiency by using waste heat recovery. "
            "The heat recovery steam generator captures exhaust energy and turns it "
            "into additional power. Every answer must keep a citation to this manual."
        ).encode("utf-8"),
    ),
)
SMOKE_CASES: tuple[RAGEvaluationCase, ...] = (
    RAGEvaluationCase(
        id="smoke-001",
        question="How does combined cycle improve efficiency?",
        reference_answer="Combined cycle improves efficiency through waste heat recovery.",
        expected_evidence_keywords=["combined cycle", "waste heat recovery", "efficiency"],
        task_type="ordinary_rag",
        source_scope="smoke_manual",
        grading_notes="The smoke run must retrieve the core evidence and keep a citation.",
        expected_modes=["semantic"],
    ),
)
SMOKE_GRAPH_EDGES: tuple[GraphEdgeRecord, ...] = (
    GraphEdgeRecord(
        triple_id="smoke-g1",
        subject="Combined Cycle",
        predicate="IMPROVES",
        object_name="Efficiency",
        evidence="Combined cycle systems improve efficiency by using waste heat recovery.",
        confidence=0.95,
        source_file="combined_cycle_smoke.md",
        source_page="1",
    ),
    GraphEdgeRecord(
        triple_id="smoke-g2",
        subject="Waste Heat Recovery",
        predicate="SUPPORTS",
        object_name="Combined Cycle",
        evidence="Waste heat recovery captures exhaust energy for additional power.",
        confidence=0.91,
        source_file="combined_cycle_smoke.md",
        source_page="1",
    ),
)


class _PipelineSmokeRag:
    def __init__(
        self,
        *,
        persist_dir: Path,
        collection_name: str,
        top_k: int,
        query_collection: Any,
    ) -> None:
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.top_k = top_k
        self._query_collection = query_collection
        self.last_search: dict[str, Any] = {}

    def query(self, question: str) -> dict[str, Any]:
        search = self._query_collection(
            query_text=question,
            persist_dir=self.persist_dir,
            collection_name=self.collection_name,
            top_k=self.top_k,
            backend="hashing",
        )
        self.last_search = search
        hits = search.get("results", [])
        context = "\n\n".join(str(hit.get("text", "")) for hit in hits)
        citations = [
            {
                "source": (hit.get("metadata") or {}).get("source_file")
                or (hit.get("metadata") or {}).get("filename")
                or "smoke",
                "text": hit.get("text", ""),
            }
            for hit in hits
        ]
        return {
            "answer": context,
            "retrieval_results": hits,
            "citations": citations,
        }


class _SmokeGraphRagLLMClient:
    def __init__(self, *_: Any, **__: Any) -> None:
        self.prompts: list[str] = []

    @property
    def call_count(self) -> int:
        return len(self.prompts)

    def generate(self, prompt: str, **_: Any) -> str:
        self.prompts.append(prompt)
        if "## Community Summary:" in prompt:
            return "Combined Cycle improves Efficiency because Waste Heat Recovery captures exhaust energy."
        return "SMOKE_GLOBAL_ANSWER: Combined cycle improves efficiency through waste heat recovery [T1] [G1]."

    def complete(self, prompt: str, **kwargs: Any) -> str:
        return self.generate(prompt, **kwargs)

    def invoke(self, prompt: str, **kwargs: Any) -> str:
        return self.generate(prompt, **kwargs)


def run_ingest_search_evaluation_smoke(
    *,
    persist_dir: str | Path,
    report_dir: str | Path,
    collection_name: str = SMOKE_COLLECTION,
    top_k: int = 3,
) -> dict[str, Any]:
    """Run a tiny real ingest/search/evaluation smoke path against the local Chroma pipeline."""
    persist_path = Path(persist_dir)
    report_path = Path(report_dir)
    ingest_source_payloads, query_collection = _load_console_pipeline()

    ingest = ingest_source_payloads(
        payloads=list(SMOKE_PAYLOADS),
        persist_dir=persist_path,
        collection_name=collection_name,
        chunk_size=500,
        overlap=50,
        backend="hashing",
    )
    rag = _PipelineSmokeRag(
        persist_dir=persist_path,
        collection_name=collection_name,
        top_k=top_k,
        query_collection=query_collection,
    )
    harness = RAGEvaluationHarness(
        rag,
        thresholds=EvaluationThresholds(
            min_keyword_recall_at_k=1.0,
            min_answer_completeness=1.0,
            max_missing_citation_rate=0.0,
            max_medium_or_high_risk_rate=0.0,
            max_no_result_rate=0.0,
        ),
        top_k=top_k,
    )
    report = harness.run(SMOKE_CASES, run_name="smoke")
    report_paths = report.save(report_path)
    search = rag.last_search or query_collection(
        query_text=SMOKE_CASES[0].question,
        persist_dir=persist_path,
        collection_name=collection_name,
        top_k=top_k,
        backend="hashing",
    )
    evaluation = report.to_dict()
    graph_quality, graph_path = _run_graph_quality_smoke(persist_path)
    graphrag_query = _run_graphrag_query_smoke(
        persist_path=persist_path,
        collection_name=collection_name,
        graph_path=graph_path,
        top_k=top_k,
    )
    graphrag_global_answer = _run_graphrag_global_answer_smoke(
        persist_path=persist_path,
        collection_name=collection_name,
        graph_path=graph_path,
        top_k=top_k,
    )
    return {
        "ingest": ingest,
        "search": search,
        "evaluation": {
            "gate_status": report.gate_status,
            "metrics": evaluation.get("metrics", {}),
            "gate_failures": report.gate_failures,
            "failure_cases": report.failure_cases,
            "retrieval_default_policy": evaluation.get("retrieval_default_policy", {}),
        },
        "graph_quality": {
            "gate_status": graph_quality.gate_status,
            "metrics": graph_quality.metrics,
            "gate_failures": graph_quality.gate_failures,
        },
        "graphrag_query": graphrag_query,
        "graphrag_global_answer": graphrag_global_answer,
        "reports": {name: str(path) for name, path in report_paths.items()},
    }


def _load_console_pipeline() -> tuple[Any, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    package_src = repo_root / "api_server" / "current_console" / "chroma_rag_poc" / "src"
    if str(package_src) not in sys.path:
        sys.path.insert(0, str(package_src))
    from chroma_rag_poc.pipeline import ingest_source_payloads, query_collection

    return ingest_source_payloads, query_collection


def _run_graph_quality_smoke(persist_path: Path):
    graph_path = persist_path.parent / "smoke_graph.sqlite"
    graph_store = GraphStore(graph_path)
    graph_store.import_edges(list(SMOKE_GRAPH_EDGES), reset=True)
    graph_store.store_communities(
        [
            {"community_id": "SMOKE-C1", "node_name": "Combined Cycle"},
            {"community_id": "SMOKE-C1", "node_name": "Efficiency"},
            {"community_id": "SMOKE-C1", "node_name": "Waste Heat Recovery"},
        ]
    )
    graph_store.store_community_summaries(
        [
            {
                "community_id": "SMOKE-C1",
                "title": "Combined cycle efficiency",
                "summary": "Combined cycle efficiency is supported by waste heat recovery.",
                "entity_count": 3,
                "edge_count": 2,
                "metadata": {
                    "evidence_triple_ids": ["smoke-g1", "smoke-g2"],
                    "sentence_evidence": [
                        {
                            "sentence_index": 0,
                            "evidence_triple_ids": ["smoke-g1", "smoke-g2"],
                            "source_evidence": [
                                {
                                    "triple_id": "smoke-g1",
                                    "text": "Combined cycle systems improve efficiency by using waste heat recovery.",
                                    "source_file": "combined_cycle_smoke.md",
                                    "source_page": "1",
                                },
                                {
                                    "triple_id": "smoke-g2",
                                    "text": "Waste heat recovery captures exhaust energy for additional power.",
                                    "source_file": "combined_cycle_smoke.md",
                                    "source_page": "1",
                                },
                            ],
                        }
                    ],
                },
            }
        ]
    )
    return (
        evaluate_graph_quality(
            graph_store,
            thresholds=GraphQualityThresholds(
                min_evidence_coverage=1.0,
                min_edge_confidence=0.7,
                max_isolated_node_rate=0.0,
                min_community_assignment_coverage=1.0,
                min_community_summary_coverage=1.0,
                min_summary_evidence_coverage=1.0,
            ),
        ),
        graph_path,
    )


def _run_graphrag_query_smoke(
    *,
    persist_path: Path,
    collection_name: str,
    graph_path: Path,
    top_k: int,
) -> dict[str, Any]:
    _load_console_pipeline()
    from fastapi.testclient import TestClient
    from chroma_rag_poc.api import create_app

    app = create_app(
        persist_dir=persist_path,
        upload_dir=persist_path.parent / "uploads",
    )
    client = TestClient(app)
    response = client.post(
        "/api/query",
        json={
            "question": SMOKE_CASES[0].question,
            "collection": collection_name,
            "graph_db_path": str(graph_path),
            "mode": "local",
            "top_k": top_k,
            "context_only": True,
        },
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_body": response.text}

    if response.status_code != 200:
        return {
            "status_code": response.status_code,
            "passed": False,
            "error": payload,
            "graph_db_path": str(graph_path),
        }

    citations = list(payload.get("citations") or [])
    graph_citation_count = sum(1 for item in citations if item.get("source_type") == "graph")
    graph_quality = payload.get("graph_quality") or {}
    gate_status = (graph_quality.get("quality_gate") or {}).get("status")
    context = str(payload.get("context") or "")
    passed = (
        response.status_code == 200
        and payload.get("route", {}).get("strategy") == "LOCAL_SEARCH"
        and gate_status == "pass"
        and graph_citation_count >= 1
        and "## Graph retrieval evidence" in context
    )
    return {
        "status_code": response.status_code,
        "passed": passed,
        "route": payload.get("route"),
        "graph_quality_gate_status": gate_status,
        "graph_citation_count": graph_citation_count,
        "context_has_graph_evidence": "## Graph retrieval evidence" in context,
        "graph_db_path": str(graph_path),
    }


def _run_graphrag_global_answer_smoke(
    *,
    persist_path: Path,
    collection_name: str,
    graph_path: Path,
    top_k: int,
) -> dict[str, Any]:
    _load_console_pipeline()
    from fastapi.testclient import TestClient
    import chroma_rag_poc.api as api_module

    app = api_module.create_app(
        persist_dir=persist_path,
        upload_dir=persist_path.parent / "uploads",
    )
    client = TestClient(app)
    fake_llm = _SmokeGraphRagLLMClient()
    with patch.object(api_module, "OpenAICompatibleLLMClient", return_value=fake_llm):
        response = client.post(
            "/api/query",
            json={
                "question": SMOKE_CASES[0].question,
                "collection": collection_name,
                "graph_db_path": str(graph_path),
                "mode": "global",
                "top_k": top_k,
                "llm_api_key": "smoke-test-key",
                "llm_model": "smoke-fake-llm",
            },
        )
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_body": response.text}

    if response.status_code != 200:
        return {
            "status_code": response.status_code,
            "passed": False,
            "error": payload,
            "llm_call_count": fake_llm.call_count,
            "graph_db_path": str(graph_path),
        }

    graph_quality = payload.get("graph_quality") or {}
    gate_status = (graph_quality.get("quality_gate") or {}).get("status")
    answer = str(payload.get("answer") or "")
    context = str(payload.get("context") or "")
    route = payload.get("route") or {}
    answer_generated = "SMOKE_GLOBAL_ANSWER" in answer
    global_context_present = "## Global context" in context and "Combined Cycle improves Efficiency" in context
    passed = (
        route.get("strategy") == "GLOBAL_SEARCH"
        and gate_status == "pass"
        and answer_generated
        and global_context_present
        and fake_llm.call_count >= 2
    )
    return {
        "status_code": response.status_code,
        "passed": passed,
        "route": route,
        "graph_quality_gate_status": gate_status,
        "answer_generated": answer_generated,
        "global_context_present": global_context_present,
        "llm_call_count": fake_llm.call_count,
        "graph_db_path": str(graph_path),
    }
