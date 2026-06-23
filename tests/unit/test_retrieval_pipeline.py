from __future__ import annotations

import unittest

from retrieval_engine import DocumentChunk, HybridRetriever, RetrievalResult


class FakeRetriever:
    def __init__(self, name: str, results: list[RetrievalResult]) -> None:
        self.name = name
        self.results = results
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        self.calls.append((query, top_k))
        return self.results[:top_k]


class QueryAwareFakeRetriever:
    def __init__(self, name: str, results_by_query: dict[str, list[RetrievalResult]]) -> None:
        self.name = name
        self.results_by_query = results_by_query
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        self.calls.append((query, top_k))
        return self.results_by_query.get(query, [])[:top_k]


def _result(text: str, score: float, *, chunk_id: str, **metadata: object) -> RetrievalResult:
    return RetrievalResult(
        chunk=DocumentChunk.from_text(text, metadata={"chunk_id": chunk_id, **metadata}),
        score=score,
    )


class RetrievalPipelineTests(unittest.TestCase):
    def test_rrf_fusion_promotes_consensus_over_single_high_score(self) -> None:
        consensus = _result("shared compressor inspection", 0.2, chunk_id="shared")
        dense_only = _result("dense-only high score", 0.99, chunk_id="dense")
        dense = FakeRetriever("dense", [dense_only, consensus])
        keyword = FakeRetriever("keyword", [consensus])

        retriever = HybridRetriever([dense, keyword], fusion_mode="rrf", rrf_k=60)
        results = retriever.retrieve("compressor inspection", top_k=2)

        self.assertEqual([result.chunk_id for result in results], ["shared", "dense"])
        self.assertIn("rrf:dense", results[0].component_scores)
        self.assertIn("rrf:keyword", results[0].component_scores)
        self.assertEqual(retriever.last_diagnostics.fusion_mode, "rrf")

    def test_metadata_filters_accept_haystack_style_conditions(self) -> None:
        retriever = HybridRetriever(
            [
                FakeRetriever(
                    "keyword",
                    [
                        _result("pump inspection in pdf", 0.9, chunk_id="pdf", source_kind="PDF", year=2026),
                        _result("pump inspection in csv", 0.8, chunk_id="csv", source_kind="CSV", year=2026),
                    ],
                )
            ]
        )
        filters = {
            "operator": "AND",
            "conditions": [
                {"field": "meta.source_kind", "operator": "==", "value": "PDF"},
                {"field": "meta.year", "operator": ">=", "value": 2025},
            ],
        }

        results = retriever.retrieve("pump inspection", top_k=5, filters=filters)

        self.assertEqual([result.chunk_id for result in results], ["pdf"])
        self.assertEqual(retriever.last_diagnostics.filtered_candidate_count, 1)

    def test_query_rewriter_runs_multiple_queries_and_records_diagnostics(self) -> None:
        base = FakeRetriever(
            "dense",
            [_result("compressor blade inspection", 0.7, chunk_id="blade")],
        )

        def rewrite(query: str) -> list[str]:
            return [query, "compressor blade inspection"]

        retriever = HybridRetriever([base], query_rewriter=rewrite, fusion_mode="rrf")
        results = retriever.retrieve("叶片检查", top_k=1)

        self.assertEqual(base.calls, [("叶片检查", 1), ("compressor blade inspection", 1)])
        self.assertEqual([result.chunk_id for result in results], ["blade"])
        self.assertEqual(retriever.last_diagnostics.rewritten_queries, ("叶片检查", "compressor blade inspection"))

    def test_rrf_promotes_top_hits_from_rewritten_queries(self) -> None:
        base = QueryAwareFakeRetriever(
            "keyword",
            {
                "surface wording": [_result("surface match but wrong topic", 0.9, chunk_id="wrong")],
                "semantic rewrite": [_result("correct evidence from semantic rewrite", 0.4, chunk_id="correct")],
            },
        )

        retriever = HybridRetriever(
            [base],
            query_rewriter=lambda _query: ["semantic rewrite"],
            fusion_mode="rrf",
        )
        results = retriever.retrieve("surface wording", top_k=1)

        self.assertEqual([result.chunk_id for result in results], ["correct"])
        self.assertIn("rrf_rewrite_top_hit", results[0].component_scores)

    def test_reranker_error_is_visible_and_fallback_keeps_results(self) -> None:
        class FailingReranker:
            name = "failing"

            def rerank(self, query: str, documents: list[str], *, top_k: int | None = None) -> list[tuple[int, float]]:
                raise RuntimeError("reranker unavailable")

        retriever = HybridRetriever(
            [FakeRetriever("dense", [_result("compressor", 0.8, chunk_id="a")])],
            reranker=FailingReranker(),
        )

        results = retriever.retrieve("compressor", top_k=1)

        self.assertEqual([result.chunk_id for result in results], ["a"])
        self.assertIn("reranker unavailable", retriever.last_diagnostics.reranker_error or "")
        self.assertEqual(retriever.last_diagnostics.reranker_name, "failing")

    def test_reranker_can_promote_candidate_from_wider_pool(self) -> None:
        class AnswerReranker:
            name = "answer_reranker"

            def rerank(self, query: str, documents: list[str], *, top_k: int | None = None) -> list[tuple[int, float]]:
                scored = [
                    (index, 1.0 if "correct answer evidence" in document else 0.01)
                    for index, document in enumerate(documents)
                ]
                scored.sort(key=lambda item: item[1], reverse=True)
                return scored[:top_k] if top_k is not None else scored

        retriever = HybridRetriever(
            [
                FakeRetriever(
                    "dense",
                    [
                        _result("plausible but wrong context", 0.99, chunk_id="wrong-1"),
                        _result("another plausible wrong context", 0.98, chunk_id="wrong-2"),
                        _result("correct answer evidence", 0.30, chunk_id="correct"),
                    ],
                )
            ],
            per_retriever_k=3,
            reranker=AnswerReranker(),
        )

        results = retriever.retrieve("target question", top_k=1)

        self.assertEqual([result.chunk_id for result in results], ["correct"])
        self.assertEqual(retriever.last_diagnostics.reranker_name, "answer_reranker")
        self.assertIn("reranker", results[0].component_scores)

    def test_no_answer_policy_blocks_low_confidence_results(self) -> None:
        retriever = HybridRetriever(
            [FakeRetriever("dense", [_result("weak unrelated context", 0.05, chunk_id="weak")])],
            no_answer_min_score=0.2,
        )

        results = retriever.retrieve("specific maintenance question", top_k=1)

        self.assertEqual(results, [])
        self.assertTrue(retriever.last_diagnostics.no_answer)
        self.assertEqual(retriever.last_diagnostics.no_answer_reason, "best_score_below_threshold")


if __name__ == "__main__":
    unittest.main()
