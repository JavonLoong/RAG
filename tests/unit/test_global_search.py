"""Tests for global search orchestrator (rag_orchestrator/global_search.py)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from storage_layer.graph_store import GraphEdgeRecord, GraphStore
from rag_orchestrator.global_search import GlobalSearchOrchestrator


class MockLLMClient:
    """A mock LLM client that returns deterministic responses for testing."""

    def __init__(self, response: str = "这是一个测试回答。") -> None:
        self._response = response
        self.call_count = 0

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        self.call_count += 1
        # Check if this is a map or reduce call
        for msg in messages:
            content = msg.get("content", "")
            if "NOT_RELEVANT" in content:
                # Map phase - return a partial answer
                return f"偏答案 #{self.call_count}: {self._response}"
        return self._response


def _make_graph_with_communities(tmp_path: Path) -> GraphStore:
    """Create a graph with community summaries already stored."""
    store = GraphStore(tmp_path / "global_search_test.db")
    edges = [
        GraphEdgeRecord(triple_id="T1", subject="流体力学", predicate="包含", object_name="连续介质模型", confidence=0.9),
        GraphEdgeRecord(triple_id="T2", subject="流体力学", predicate="研究", object_name="粘性流动", confidence=0.9),
    ]
    store.import_edges(edges, reset=True)

    # Store community summaries directly
    store.store_communities(
        [
            {"community_id": "C0", "node_name": "流体力学"},
            {"community_id": "C0", "node_name": "连续介质模型"},
            {"community_id": "C0", "node_name": "粘性流动"},
        ],
        level=0,
    )
    store.store_community_summaries(
        [
            {
                "community_id": "C0",
                "title": "流体力学基础",
                "summary": "该社区涵盖流体力学的基础概念，包括连续介质模型和粘性流动。",
                "entity_count": 3,
                "edge_count": 2,
            },
        ],
        level=0,
    )
    return store


def test_global_search_returns_result(tmp_path: Path) -> None:
    store = _make_graph_with_communities(tmp_path)
    llm = MockLLMClient("流体力学是研究流体运动规律的学科。")
    searcher = GlobalSearchOrchestrator(graph_store=store, llm_client=llm, max_communities=10)
    result = searcher.search("什么是流体力学？", level=0)
    result_dict = result.to_dict()

    assert "answer" in result_dict
    assert len(result_dict["answer"]) > 0
    assert result_dict["communities_searched"] >= 1


def test_global_search_context_only(tmp_path: Path) -> None:
    store = _make_graph_with_communities(tmp_path)
    llm = MockLLMClient()
    searcher = GlobalSearchOrchestrator(graph_store=store, llm_client=llm, max_communities=10)
    result = searcher.search("什么是流体力学？", level=0, context_only=True)
    result_dict = result.to_dict()

    # In context_only mode, should still have context but may differ in answer format
    assert "answer" in result_dict


def test_global_search_no_communities(tmp_path: Path) -> None:
    """Global search with no community summaries should handle gracefully."""
    store = GraphStore(tmp_path / "empty_communities.db")
    store.initialize(reset=True)
    llm = MockLLMClient("无法回答。")
    searcher = GlobalSearchOrchestrator(graph_store=store, llm_client=llm, max_communities=10)
    result = searcher.search("什么是流体力学？", level=0)
    result_dict = result.to_dict()

    assert "answer" in result_dict
    assert result_dict["communities_searched"] == 0


def test_global_search_max_communities(tmp_path: Path) -> None:
    """Max communities parameter should limit the search scope."""
    store = _make_graph_with_communities(tmp_path)
    llm = MockLLMClient()
    searcher = GlobalSearchOrchestrator(graph_store=store, llm_client=llm, max_communities=1)
    result = searcher.search("什么是流体力学？", level=0)
    result_dict = result.to_dict()

    assert result_dict["communities_searched"] <= 1
