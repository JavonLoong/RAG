"""Integration tests for GraphRagQAOrchestrator.

Tests the full pipeline: text + graph retrieval + global search → LLM → answer with citations.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rag_orchestrator.graphrag_qa import (
    GraphRagConfigurationError,
    GraphRagQAOrchestrator,
)
from storage_layer.graph_store import GraphEdgeRecord, GraphStore
from retrieval_engine.graph import SQLiteGraphRetriever
from retrieval_engine.keyword import KeywordRetriever
from retrieval_engine.core import DocumentChunk, RetrievalResult


# ── Helpers ──────────────────────────────────────────────────────────


class MockLLM:
    """Deterministic LLM mock that returns a fixed answer."""

    def __init__(self, answer: str = "根据检索到的证据，答案如下 [T1] [G1]。") -> None:
        self._answer = answer
        self.prompts: list[str] = []

    def generate(self, prompt: str, **_: Any) -> str:
        self.prompts.append(prompt)
        return self._answer


class MockGlobalSearcher:
    """Mock GlobalSearchOrchestrator for testing the third retrieval path."""

    def __init__(self, partial_answers: list[dict[str, Any]] | None = None) -> None:
        from dataclasses import dataclass, field

        @dataclass
        class FakeResult:
            question: str = ""
            answer: str = ""
            communities_searched: int = 1
            communities_relevant: int = 1
            partial_answers: list[dict[str, Any]] = field(default_factory=list)
            context_only: bool = True

        self._partial = partial_answers or [
            {
                "community_id": "C0",
                "title": "流体力学基础",
                "entity_count": 5,
                "answer": "连续介质模型是流体力学的基础假设，假定流体是连续分布的介质。",
            }
        ]
        self._result_cls = FakeResult
        self.call_count = 0

    def search(self, question: str, *, context_only: bool = False, **_: Any) -> Any:
        self.call_count += 1
        return self._result_cls(
            question=question,
            partial_answers=self._partial,
            context_only=context_only,
        )


def _make_graph(tmp_path: Path) -> GraphStore:
    """Create a small test graph."""
    store = GraphStore(tmp_path / "test_graph.db")
    edges = [
        GraphEdgeRecord(
            triple_id="T001",
            subject="连续介质模型",
            predicate="属于",
            object_name="流体力学基本概念",
            confidence=0.95,
        ),
        GraphEdgeRecord(
            triple_id="T002",
            subject="牛顿流体",
            predicate="遵循",
            object_name="牛顿内摩擦定律",
            confidence=0.9,
        ),
    ]
    store.import_edges(edges, reset=True)
    return store


def _make_text_retriever() -> KeywordRetriever:
    """Create a keyword retriever with sample chunks."""
    chunks = [
        {
            "text": "连续介质模型是流体力学最基础的模型，假定流体可以连续充满所占空间。",
            "metadata": {"source_file": "fluid_ch1.pdf", "page": 5},
        },
        {
            "text": "牛顿流体的剪应力τ与速度梯度du/dy成正比，比例系数为动力粘度μ。",
            "metadata": {"source_file": "fluid_ch2.pdf", "page": 12},
        },
    ]
    return KeywordRetriever(chunks)


# ── Tests ────────────────────────────────────────────────────────────


def test_full_pipeline_text_graph_llm(tmp_path: Path) -> None:
    """Integration: text + graph → LLM → answer with citations."""
    store = _make_graph(tmp_path)
    text_retriever = _make_text_retriever()
    graph_retriever = SQLiteGraphRetriever(store, include_community_summaries=False)
    llm = MockLLM()

    qa = GraphRagQAOrchestrator(
        text_retriever=text_retriever,
        graph_retriever=graph_retriever,
        llm=llm,
    )
    result = qa.answer("连续介质模型", top_k=3)

    assert result.answer is not None
    assert "[T1]" in result.answer or "[G1]" in result.answer
    assert result.context_only is False
    assert len(result.citations) > 0
    # Should have text citations (T*) and graph citations (G*)
    text_citations = [c for c in result.citations if c["source_type"] == "text"]
    graph_citations = [c for c in result.citations if c["source_type"] == "graph"]
    assert len(text_citations) > 0, "Should have text evidence"
    assert len(graph_citations) > 0, "Should have graph evidence"
    assert "## Text retrieval evidence" in result.context
    assert "## Graph retrieval evidence" in result.context
    assert len(llm.prompts) == 1


def test_global_search_integrated_into_context(tmp_path: Path) -> None:
    """Integration: global search context appears in the final prompt."""
    store = _make_graph(tmp_path)
    text_retriever = _make_text_retriever()
    graph_retriever = SQLiteGraphRetriever(store, include_community_summaries=False)
    global_searcher = MockGlobalSearcher()
    llm = MockLLM()

    qa = GraphRagQAOrchestrator(
        text_retriever=text_retriever,
        graph_retriever=graph_retriever,
        global_searcher=global_searcher,
        llm=llm,
    )
    result = qa.answer("什么是连续介质模型？", top_k=3)

    assert result.answer is not None
    assert global_searcher.call_count == 1
    assert "## Global context (community-level analysis)" in result.context
    assert "流体力学基础" in result.context
    assert "连续介质模型是流体力学的基础假设" in result.context


def test_global_search_none_is_backward_compatible(tmp_path: Path) -> None:
    """Without global_searcher, the pipeline should work exactly as before."""
    store = _make_graph(tmp_path)
    text_retriever = _make_text_retriever()
    graph_retriever = SQLiteGraphRetriever(store, include_community_summaries=False)
    llm = MockLLM()

    qa = GraphRagQAOrchestrator(
        text_retriever=text_retriever,
        graph_retriever=graph_retriever,
        global_searcher=None,
        llm=llm,
    )
    result = qa.answer("什么是连续介质模型？", top_k=3)

    assert result.answer is not None
    # No global context section
    assert "## Global context" not in result.context


def test_global_search_failure_gracefully_skipped(tmp_path: Path) -> None:
    """If global search raises an exception, the pipeline should continue."""

    class ExplodingSearcher:
        def search(self, question: str, **_: Any) -> Any:
            raise RuntimeError("Global search failed!")

    store = _make_graph(tmp_path)
    text_retriever = _make_text_retriever()
    graph_retriever = SQLiteGraphRetriever(store, include_community_summaries=False)
    llm = MockLLM()

    qa = GraphRagQAOrchestrator(
        text_retriever=text_retriever,
        graph_retriever=graph_retriever,
        global_searcher=ExplodingSearcher(),
        llm=llm,
    )
    result = qa.answer("什么是连续介质模型？", top_k=3)

    # Should still produce a valid answer without global context
    assert result.answer is not None
    assert "## Global context" not in result.context


def test_context_only_with_global_search(tmp_path: Path) -> None:
    """Context-only mode should include global context without calling LLM."""

    class ExplodingLLM:
        def generate(self, prompt: str, **_: Any) -> str:
            raise AssertionError("LLM should not be called in context-only mode")

    store = _make_graph(tmp_path)
    text_retriever = _make_text_retriever()
    graph_retriever = SQLiteGraphRetriever(store, include_community_summaries=False)
    global_searcher = MockGlobalSearcher()

    qa = GraphRagQAOrchestrator(
        text_retriever=text_retriever,
        graph_retriever=graph_retriever,
        global_searcher=global_searcher,
        llm=ExplodingLLM(),
    )
    result = qa.answer("什么是连续介质模型？", top_k=3, context_only=True)

    assert result.answer is None
    assert result.context_only is True
    assert "## Global context (community-level analysis)" in result.context


def test_missing_llm_raises_error(tmp_path: Path) -> None:
    """Missing LLM should raise a clear error (not in context_only mode)."""
    store = _make_graph(tmp_path)
    qa = GraphRagQAOrchestrator(
        text_retriever=_make_text_retriever(),
        graph_retriever=SQLiteGraphRetriever(store, include_community_summaries=False),
        llm=None,
    )
    with pytest.raises(GraphRagConfigurationError, match="LLM.*required"):
        qa.answer("什么是连续介质模型？", top_k=3)
