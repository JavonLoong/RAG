from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any

from retrieval_engine import DocumentChunk, RetrievalResult
from rag_orchestrator.lightrag import LightRagQueryEngine


def _result(text: str, score: float, *, chunk_id: str, source_type: str | None = None) -> RetrievalResult:
    metadata = {"chunk_id": chunk_id}
    if source_type:
        metadata["source_type"] = source_type
    return RetrievalResult(
        chunk=DocumentChunk.from_text(text, metadata=metadata),
        score=score,
    )


class FakeRetriever:
    def __init__(self, name: str, results: list[RetrievalResult]) -> None:
        self.name = name
        self.results = results
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        self.calls.append((query, top_k))
        return self.results[:top_k]


@dataclass
class FakeGlobalResult:
    partial_answers: list[dict[str, Any]]


class FakeGlobalSearcher:
    def __init__(self, partial_answers: list[dict[str, Any]] | None = None, *, fail: bool = False) -> None:
        self.partial_answers = partial_answers or []
        self.fail = fail
        self.calls: list[tuple[str, bool]] = []

    def search(self, question: str, *, context_only: bool = False) -> FakeGlobalResult:
        self.calls.append((question, context_only))
        if self.fail:
            raise RuntimeError("global unavailable")
        return FakeGlobalResult(partial_answers=self.partial_answers)


class LightRagBaseTests(unittest.TestCase):
    def test_mix_mode_merges_naive_local_and_global_paths(self) -> None:
        text = FakeRetriever("text", [_result("text chunk about compressor", 0.8, chunk_id="text-1")])
        graph = FakeRetriever("graph", [_result("Compressor --USES--> Turbine", 0.7, chunk_id="edge-1")])
        global_searcher = FakeGlobalSearcher(
            [
                {
                    "community_id": "C1",
                    "title": "Compressor community",
                    "entity_count": 12,
                    "answer": "Compressor maintenance is connected to turbine safety.",
                }
            ]
        )

        engine = LightRagQueryEngine(
            text_retriever=text,
            graph_retriever=graph,
            global_searcher=global_searcher,
        )

        results = engine.retrieve("compressor maintenance", mode="mix", top_k=5)

        self.assertEqual({result.metadata["lightrag_path"] for result in results}, {"naive", "local", "global"})
        self.assertEqual(engine.last_diagnostics.mode, "mix")
        self.assertEqual(engine.last_diagnostics.naive_count, 1)
        self.assertEqual(engine.last_diagnostics.local_count, 1)
        self.assertEqual(engine.last_diagnostics.global_count, 1)
        self.assertEqual(engine.last_diagnostics.final_count, 3)

    def test_query_modes_call_expected_paths(self) -> None:
        text = FakeRetriever("text", [_result("text", 0.8, chunk_id="text")])
        graph = FakeRetriever("graph", [_result("graph", 0.7, chunk_id="graph")])
        global_searcher = FakeGlobalSearcher([{"community_id": "C1", "answer": "global"}])
        engine = LightRagQueryEngine(text_retriever=text, graph_retriever=graph, global_searcher=global_searcher)

        self.assertEqual({r.metadata["lightrag_path"] for r in engine.retrieve("q", mode="naive")}, {"naive"})
        self.assertEqual({r.metadata["lightrag_path"] for r in engine.retrieve("q", mode="local")}, {"local"})
        self.assertEqual({r.metadata["lightrag_path"] for r in engine.retrieve("q", mode="global")}, {"global"})
        self.assertEqual({r.metadata["lightrag_path"] for r in engine.retrieve("q", mode="hybrid")}, {"local", "global"})
        self.assertEqual({r.metadata["lightrag_path"] for r in engine.retrieve("q", mode="mix")}, {"naive", "local", "global"})

    def test_build_context_groups_evidence_by_lightrag_path(self) -> None:
        engine = LightRagQueryEngine(
            text_retriever=FakeRetriever("text", [_result("pump manual chunk", 0.8, chunk_id="text")]),
            graph_retriever=FakeRetriever("graph", [_result("Pump --HAS_RISK--> Vibration", 0.7, chunk_id="graph")]),
            global_searcher=FakeGlobalSearcher([{"community_id": "C1", "title": "Pump risks", "answer": "Pump risks group vibration and leakage."}]),
        )

        result = engine.build_context("pump risk", mode="mix", top_k=5)

        self.assertIn("## Naive text evidence", result.context)
        self.assertIn("## Local graph evidence", result.context)
        self.assertIn("## Global community evidence", result.context)
        self.assertEqual(result.to_dict()["diagnostics"]["mode"], "mix")

    def test_global_failure_is_visible_and_hybrid_keeps_local_results(self) -> None:
        engine = LightRagQueryEngine(
            text_retriever=FakeRetriever("text", []),
            graph_retriever=FakeRetriever("graph", [_result("local edge", 0.7, chunk_id="graph")]),
            global_searcher=FakeGlobalSearcher(fail=True),
        )

        results = engine.retrieve("q", mode="hybrid", top_k=5)

        self.assertEqual([result.metadata["lightrag_path"] for result in results], ["local"])
        self.assertIn("global unavailable", engine.last_diagnostics.global_error or "")


if __name__ == "__main__":
    unittest.main()
