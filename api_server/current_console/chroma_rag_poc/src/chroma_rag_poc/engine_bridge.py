"""Bridge layer: connects the POC system to the root-level abstraction modules.

This module solves the "dual-track" problem identified in the evaluation report:
the POC (`chroma_rag_poc/`) was a self-contained system that did not call
the root-level `retrieval_engine/`, `rag_orchestrator/`, or `model_adapters/`.

This bridge wraps the root-level modules so the POC API can use them directly,
ensuring a single unified code path.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure the repo root is on the Python path for imports
_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def get_chroma_retriever(
    persist_path: str | Path,
    collection_name: str,
    *,
    embedding_function: Any | None = None,
    name: str = "chroma",
) -> Any:
    """Create a ChromaRetriever from retrieval_engine/ for the POC to use.

    This replaces the POC's internal query_collection() with the root-level
    ChromaRetriever, ensuring consistent retrieval behavior.
    """
    from retrieval_engine.chroma import ChromaRetriever

    return ChromaRetriever(
        persist_path=persist_path,
        collection_name=collection_name,
        embedding_function=embedding_function,
        name=name,
    )


def get_keyword_retriever(
    chunks: list[dict[str, Any]],
    *,
    name: str = "keyword",
) -> Any:
    """Create a KeywordRetriever from retrieval_engine/ for BM25 search."""
    from retrieval_engine.keyword import KeywordRetriever

    return KeywordRetriever(chunks, name=name)


def get_hybrid_retriever(
    retrievers: list[Any],
    *,
    weights: list[float] | None = None,
    name: str = "hybrid",
) -> Any:
    """Create a HybridRetriever from retrieval_engine/ for merged results."""
    from retrieval_engine.hybrid import HybridRetriever

    return HybridRetriever(retrievers, weights=weights, name=name)


def get_graphrag_orchestrator(
    *,
    text_retriever: Any,
    graph_retriever: Any,
    global_searcher: Any | None = None,
    llm: Any | None = None,
) -> Any:
    """Create a GraphRagQAOrchestrator from rag_orchestrator/ for QA."""
    from rag_orchestrator.graphrag_qa import GraphRagQAOrchestrator

    return GraphRagQAOrchestrator(
        text_retriever=text_retriever,
        graph_retriever=graph_retriever,
        global_searcher=global_searcher,
        llm=llm,
    )


def get_global_search(
    *,
    graph_store: Any,
    llm_client: Any,
    max_communities: int = 20,
) -> Any:
    """Create a GlobalSearchOrchestrator from rag_orchestrator/ for global QA."""
    from rag_orchestrator.global_search import GlobalSearchOrchestrator

    return GlobalSearchOrchestrator(
        graph_store=graph_store,
        llm_client=llm_client,
        max_communities=max_communities,
    )


def get_graph_store(db_path: str | Path) -> Any:
    """Get a GraphStore from storage_layer/ for graph operations."""
    from storage_layer.graph_store import GraphStore

    store = GraphStore(db_path)
    store.initialize(reset=False)
    return store


def get_llm_client(
    *,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4.1-mini",
) -> Any:
    """Create an LLM client from model_adapters/ for answer generation."""
    from model_adapters.llm import OpenAICompatibleLLMClient

    return OpenAICompatibleLLMClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )


def get_embedding_adapter(
    *,
    backend: str = "hashing",
    model: str = "text-embedding-3-small",
    api_key: str = "",
) -> Any:
    """Create an embedding adapter from model_adapters/ for vector embedding."""
    from model_adapters.embedding import (
        HashingEmbeddingAdapter,
        OpenAIEmbeddingAdapter,
        SentenceTransformerAdapter,
    )

    if backend == "openai" and api_key:
        return OpenAIEmbeddingAdapter(api_key=api_key, model=model)
    elif backend == "sentence_transformer":
        return SentenceTransformerAdapter(model_name=model)
    else:
        return HashingEmbeddingAdapter()


def run_community_detection(
    db_path: str | Path,
    *,
    resolution: float = 1.0,
    level: int = 0,
) -> dict[str, Any]:
    """Run community detection on an existing graph database.

    Bridge to kg_pipeline/community_detection.py.
    """
    from kg_pipeline.community_detection import run_louvain_detection

    store = get_graph_store(db_path)
    result = run_louvain_detection(store, resolution=resolution, level=level)
    return result.to_dict()


def run_community_summary(
    db_path: str | Path,
    llm_client: Any,
    *,
    level: int = 0,
    min_community_size: int = 2,
) -> dict[str, Any]:
    """Run community summarization on an existing graph database.

    Bridge to kg_pipeline/community_summary.py.
    """
    from kg_pipeline.community_summary import summarize_communities

    store = get_graph_store(db_path)
    result = summarize_communities(
        store, llm_client, level=level, min_community_size=min_community_size
    )
    return result.to_dict()


def run_evaluation(
    rag_system: Any,
    test_suite_path: str | Path,
    *,
    llm_client: Any | None = None,
    max_questions: int | None = None,
) -> dict[str, Any]:
    """Run evaluation on a RAG system against a test suite.

    Bridge to evaluation/.
    """
    from evaluation.runner import EvaluationRunner, EvaluationSuite

    suite = EvaluationSuite.from_json(test_suite_path)
    runner = EvaluationRunner(rag_system=rag_system, llm_client=llm_client)
    report = runner.run(suite, max_questions=max_questions)
    return report.to_dict()
