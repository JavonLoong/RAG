from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rag_orchestrator.advanced_query import AdvancedQueryExecutor
from rag_orchestrator.query_understanding import QueryIntent, QueryRouteName, TaskSpec


class RecordingTextRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.scan_calls: list[int] = []

    def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        self.calls.append((query, top_k))
        return [
            {
                "id": f"text-{len(self.calls)}",
                "text": f"text evidence for {query}",
                "source": "manual.md",
                "score": 0.91,
                "metadata": {"query": query},
            }
        ]

    def scan_all(self, limit: int = 1000) -> list[dict[str, Any]]:
        self.scan_calls.append(limit)
        return [
            {
                "id": "scan-1",
                "text": "full corpus scan evidence",
                "source": "corpus.md",
                "score": 1.0,
                "metadata": {"chunk_index": 0},
            }
        ]


class RecordingGraphRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        self.calls.append((query, top_k))
        return [
            {
                "id": f"graph-{len(self.calls)}",
                "subject": query,
                "predicate": "SUPPORTS",
                "object": "answer",
                "evidence": f"graph evidence for {query}",
                "source": "graph.sqlite",
                "confidence": 0.82,
            }
        ]


class RecordingLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str, **_: Any) -> str:
        self.prompts.append(prompt)
        return "advanced grounded answer [T1] [G1]"


@dataclass
class FakeGlobalResult:
    partial_answers: list[dict[str, Any]]
    communities_searched: int = 1
    communities_relevant: int = 1
    context_only: bool = True


class RecordingGlobalSearcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def search(self, question: str, *, context_only: bool = False, **_: Any) -> FakeGlobalResult:
        self.calls.append((question, context_only))
        return FakeGlobalResult(
            partial_answers=[
                {
                    "community_id": "C1",
                    "title": "Fleet risk",
                    "entity_count": 12,
                    "answer": "community evidence for fleet risk",
                    "source_evidence": [
                        {
                            "triple_id": "triple-1",
                            "text": "source span from community summary",
                            "source_file": "community.md",
                        }
                    ],
                }
            ]
        )


def _task_spec(
    route: QueryRouteName,
    *,
    question: str = "original question",
    objects: list[str] | None = None,
    high_level_keywords: list[str] | None = None,
    sub_questions: list[str] | None = None,
) -> TaskSpec:
    return TaskSpec(
        original_question=question,
        rewritten_question=question,
        intent={
            QueryRouteName.MULTI_HOP: QueryIntent.CAUSAL,
            QueryRouteName.COMPARE_SYNTHESIS: QueryIntent.COMPARE,
            QueryRouteName.COMPREHENSIVE_ANALYSIS: QueryIntent.COMPREHENSIVE,
        }.get(route, QueryIntent.FACT),
        route=route,
        objects=objects or [],
        high_level_keywords=high_level_keywords or [],
        sub_questions=sub_questions or [],
    )


def test_multi_hop_executes_each_sub_question_and_records_steps() -> None:
    text = RecordingTextRetriever()
    graph = RecordingGraphRetriever()
    llm = RecordingLLM()
    executor = AdvancedQueryExecutor(text_retriever=text, graph_retriever=graph, llm=llm)
    spec = _task_spec(
        QueryRouteName.MULTI_HOP,
        question="why did A cause B",
        sub_questions=["find A evidence", "connect A to B"],
    )

    result = executor.execute(spec, top_k=2)
    payload = result.to_dict()

    assert text.calls == [("find A evidence", 2), ("connect A to B", 2)]
    assert graph.calls == [("find A evidence", 2), ("connect A to B", 2)]
    assert payload["advanced_mode"] == "MULTI_HOP"
    assert [step["query"] for step in payload["steps"]] == ["find A evidence", "connect A to B"]
    assert all(step["evidence_count"] == 2 for step in payload["steps"])
    assert payload["answer"] == "advanced grounded answer [T1] [G1]"
    assert "## Advanced execution plan" in payload["context"]
    assert "MULTI_HOP" in llm.prompts[0]


def test_compare_synthesis_builds_rows_per_object_and_markdown_table() -> None:
    text = RecordingTextRetriever()
    graph = RecordingGraphRetriever()
    executor = AdvancedQueryExecutor(text_retriever=text, graph_retriever=graph, llm=None)
    spec = _task_spec(
        QueryRouteName.COMPARE_SYNTHESIS,
        question="compare pump and combustor risk",
        objects=["pump", "combustor"],
        high_level_keywords=["risk"],
    )

    result = executor.execute(spec, top_k=3, context_only=True)
    payload = result.to_dict()

    assert text.calls == [("pump risk", 3), ("combustor risk", 3)]
    assert graph.calls == [("pump risk", 3), ("combustor risk", 3)]
    assert payload["answer"] is None
    assert payload["advanced_mode"] == "COMPARE_SYNTHESIS"
    assert [row["object"] for row in payload["comparison_table"]] == ["pump", "combustor"]
    assert all(row["citations"] for row in payload["comparison_table"])
    assert "| Object | Evidence count | Key evidence | Citations |" in payload["context"]


def test_comprehensive_analysis_uses_full_scan_global_context_and_coverage_report() -> None:
    text = RecordingTextRetriever()
    graph = RecordingGraphRetriever()
    global_searcher = RecordingGlobalSearcher()
    executor = AdvancedQueryExecutor(
        text_retriever=text,
        graph_retriever=graph,
        global_searcher=global_searcher,
        llm=None,
        full_scan_limit=7,
    )
    spec = _task_spec(
        QueryRouteName.COMPREHENSIVE_ANALYSIS,
        question="analyze the full fleet corpus",
        objects=["fleet"],
        sub_questions=["find categories", "find mitigations"],
    )

    result = executor.execute(spec, top_k=2, context_only=True)
    payload = result.to_dict()

    assert text.calls == [("find categories", 2), ("find mitigations", 2)]
    assert graph.calls == [("find categories", 2), ("find mitigations", 2)]
    assert text.scan_calls == [7]
    assert global_searcher.calls == [("analyze the full fleet corpus", True)]
    assert payload["advanced_mode"] == "COMPREHENSIVE_ANALYSIS"
    assert payload["coverage_report"]["planned_queries"] == 2
    assert payload["coverage_report"]["answered_queries"] == 2
    assert payload["coverage_report"]["full_scan"]["available"] is True
    assert payload["coverage_report"]["global_search"]["available"] is True
    assert "## Full-corpus scan sample" in payload["context"]
    assert "## Global context (community-level analysis)" in payload["context"]
