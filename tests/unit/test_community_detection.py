"""Tests for community detection (kg_pipeline/community_detection.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from storage_layer.graph_store import GraphEdgeRecord, GraphStore


def _make_two_cluster_graph(tmp_path: Path) -> GraphStore:
    """Create a graph with two clearly separate clusters for testing community detection."""
    store = GraphStore(tmp_path / "community_test.db")
    edges = [
        # Cluster A: fluid mechanics basics
        GraphEdgeRecord(triple_id="A1", subject="连续介质", predicate="属于", object_name="流体力学", confidence=0.9),
        GraphEdgeRecord(triple_id="A2", subject="流体力学", predicate="研究", object_name="粘性流动", confidence=0.9),
        GraphEdgeRecord(triple_id="A3", subject="连续介质", predicate="前提", object_name="克努森数", confidence=0.8),
        GraphEdgeRecord(triple_id="A4", subject="粘性流动", predicate="描述", object_name="NS方程", confidence=0.85),
        # Cluster B: thermodynamics (separate topic)
        GraphEdgeRecord(triple_id="B1", subject="热力学", predicate="包含", object_name="熵", confidence=0.9),
        GraphEdgeRecord(triple_id="B2", subject="热力学", predicate="研究", object_name="热传导", confidence=0.9),
        GraphEdgeRecord(triple_id="B3", subject="熵", predicate="量化", object_name="无序度", confidence=0.8),
        GraphEdgeRecord(triple_id="B4", subject="热传导", predicate="遵循", object_name="傅里叶定律", confidence=0.85),
    ]
    store.import_edges(edges, reset=True)
    return store


def _has_community_module() -> bool:
    """Check if community detection dependencies are available."""
    try:
        import community  # python-louvain
        import networkx

        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _has_community_module(), reason="python-louvain or networkx not installed")
def test_louvain_detects_communities(tmp_path: Path) -> None:
    from kg_pipeline.community_detection import run_louvain_detection

    store = _make_two_cluster_graph(tmp_path)
    result = run_louvain_detection(store, resolution=1.0, level=0)
    result_dict = result.to_dict()

    assert result_dict["num_communities"] >= 2, "Should detect at least 2 communities"
    assert result_dict["total_nodes"] == 10  # 8 edges create 10 unique nodes
    assert result_dict["total_edges"] == 8


@pytest.mark.skipif(not _has_community_module(), reason="python-louvain or networkx not installed")
def test_communities_stored_in_db(tmp_path: Path) -> None:
    from kg_pipeline.community_detection import run_louvain_detection

    store = _make_two_cluster_graph(tmp_path)
    run_louvain_detection(store, resolution=1.0, level=0)

    communities = store.get_communities(level=0)
    assert len(communities) >= 2


@pytest.mark.skipif(not _has_community_module(), reason="python-louvain or networkx not installed")
def test_community_entities_are_retrievable(tmp_path: Path) -> None:
    from kg_pipeline.community_detection import run_louvain_detection

    store = _make_two_cluster_graph(tmp_path)
    run_louvain_detection(store, resolution=1.0, level=0)

    communities = store.get_communities(level=0)
    for comm in communities:
        entities = store.get_community_entities(comm["community_id"], level=0)
        assert len(entities) > 0, f"Community {comm['community_id']} should have entities"


def test_empty_graph_detection(tmp_path: Path) -> None:
    """Community detection on an empty graph should not crash."""
    if not _has_community_module():
        pytest.skip("python-louvain or networkx not installed")

    from kg_pipeline.community_detection import run_louvain_detection

    store = GraphStore(tmp_path / "empty.db")
    store.initialize(reset=True)
    result = run_louvain_detection(store, resolution=1.0)
    assert result.to_dict()["num_communities"] == 0
