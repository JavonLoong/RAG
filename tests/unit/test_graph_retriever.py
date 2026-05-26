"""Tests for the SQLiteGraphRetriever (retrieval_engine/graph.py)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from storage_layer.graph_store import GraphEdgeRecord, GraphStore
from retrieval_engine.graph import SQLiteGraphRetriever


def _make_graph(tmp_path: Path) -> GraphStore:
    """Create a small test graph with known entities and edges."""
    store = GraphStore(tmp_path / "test_graph.db")
    edges = [
        GraphEdgeRecord(
            triple_id="T001",
            subject="连续介质模型",
            predicate="属于",
            object_name="流体力学基本概念",
            subject_type="概念",
            object_type="学科分支",
            evidence="流体的连续介质模型是流体力学最基础的简化模型。",
            confidence=0.95,
        ),
        GraphEdgeRecord(
            triple_id="T002",
            subject="牛顿流体",
            predicate="遵循",
            object_name="牛顿内摩擦定律",
            subject_type="流体类型",
            object_type="物理定律",
            evidence="牛顿流体的剪应力与速度梯度成正比。",
            confidence=0.9,
        ),
        GraphEdgeRecord(
            triple_id="T003",
            subject="纳维-斯托克斯方程",
            predicate="描述",
            object_name="粘性流体运动",
            subject_type="方程",
            object_type="物理现象",
            evidence="N-S方程是描述粘性流体运动的基本方程。",
            confidence=0.85,
        ),
        GraphEdgeRecord(
            triple_id="T004",
            subject="连续介质模型",
            predicate="前提条件",
            object_name="克努森数",
            subject_type="概念",
            object_type="无量纲数",
            confidence=0.88,
        ),
    ]
    store.import_edges(edges, reset=True)
    return store


def test_retrieve_returns_results(tmp_path: Path) -> None:
    store = _make_graph(tmp_path)
    retriever = SQLiteGraphRetriever(store, include_community_summaries=False)
    results = retriever.retrieve("连续介质模型", top_k=5)
    assert len(results) > 0
    texts = [r.text for r in results]
    # Should find edges involving "连续介质模型"
    assert any("连续介质模型" in t for t in texts)


def test_retrieve_empty_query(tmp_path: Path) -> None:
    store = _make_graph(tmp_path)
    retriever = SQLiteGraphRetriever(store, include_community_summaries=False)
    assert retriever.retrieve("", top_k=5) == []
    assert retriever.retrieve("   ", top_k=5) == []


def test_retrieve_zero_top_k(tmp_path: Path) -> None:
    store = _make_graph(tmp_path)
    retriever = SQLiteGraphRetriever(store, include_community_summaries=False)
    assert retriever.retrieve("连续介质模型", top_k=0) == []


def test_retrieve_no_matches(tmp_path: Path) -> None:
    store = _make_graph(tmp_path)
    retriever = SQLiteGraphRetriever(store, include_community_summaries=False)
    results = retriever.retrieve("量子力学薛定谔方程", top_k=5)
    assert len(results) == 0


def test_retrieve_respects_top_k(tmp_path: Path) -> None:
    store = _make_graph(tmp_path)
    retriever = SQLiteGraphRetriever(store, include_community_summaries=False)
    results = retriever.retrieve("连续介质模型", top_k=1)
    assert len(results) <= 1


def test_retriever_name_default(tmp_path: Path) -> None:
    store = _make_graph(tmp_path)
    retriever = SQLiteGraphRetriever(store, include_community_summaries=False)
    assert retriever.name == "graph"


def test_retriever_name_custom(tmp_path: Path) -> None:
    store = _make_graph(tmp_path)
    retriever = SQLiteGraphRetriever(store, name="my_graph", include_community_summaries=False)
    assert retriever.name == "my_graph"


def test_results_contain_metadata(tmp_path: Path) -> None:
    store = _make_graph(tmp_path)
    retriever = SQLiteGraphRetriever(store, include_community_summaries=False)
    results = retriever.retrieve("牛顿流体", top_k=5)
    assert len(results) > 0
    for r in results:
        assert r.chunk is not None
        assert r.score > 0
        assert r.retriever_name == "graph"
        assert "subject" in r.chunk.metadata
        assert "predicate" in r.chunk.metadata
        assert "object" in r.chunk.metadata
