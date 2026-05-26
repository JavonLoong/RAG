"""Tests for reranker module (model_adapters/reranker.py)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_adapters.reranker import NoOpReranker


def test_noop_reranker_preserves_order() -> None:
    """NoOpReranker should return documents in original order with equal scores."""
    reranker = NoOpReranker()
    documents = [
        "连续介质模型是流体力学的基础。",
        "牛顿流体的剪应力与速度梯度成正比。",
        "NS方程描述粘性流体运动。",
    ]
    results = reranker.rerank("流体力学", documents, top_k=3)
    assert len(results) == 3
    # Results are (index, score) tuples
    indices = [r[0] for r in results]
    assert indices == [0, 1, 2]


def test_noop_reranker_top_k() -> None:
    """NoOpReranker should respect top_k limit."""
    reranker = NoOpReranker()
    documents = ["doc1", "doc2", "doc3", "doc4", "doc5"]
    results = reranker.rerank("query", documents, top_k=2)
    assert len(results) == 2


def test_noop_reranker_empty_docs() -> None:
    """NoOpReranker should handle empty document list."""
    reranker = NoOpReranker()
    results = reranker.rerank("query", [], top_k=5)
    assert results == []


def test_noop_reranker_returns_tuples() -> None:
    """NoOpReranker results should be (index, score) tuples."""
    reranker = NoOpReranker()
    documents = ["doc1", "doc2"]
    results = reranker.rerank("query", documents, top_k=2)
    for result in results:
        assert isinstance(result, tuple)
        assert len(result) == 2
        index, score = result
        assert isinstance(index, int)
        assert isinstance(score, float)
