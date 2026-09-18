"""Reranker adapters for RAG retrieval refinement.

Provides reranking capabilities to improve retrieval precision by
re-scoring and re-ordering candidate results using a cross-encoder
or other reranking model.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from .local_models import DEFAULT_RERANKER_MODEL, require_local_model_path

logger = logging.getLogger(__name__)


class BaseReranker(ABC):
    """Base interface for all reranker adapters."""

    name = "base"

    @abstractmethod
    def rerank(
        self, query: str, documents: list[str], *, top_k: int | None = None
    ) -> list[tuple[int, float]]:
        """Rerank documents for a query.

        Returns list of (original_index, score) tuples, sorted by score descending.
        """


class CrossEncoderReranker(BaseReranker):
    """Reranker using a cross-encoder model from sentence-transformers."""

    name = "cross_encoder"

    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL, device: str | None = None) -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers required for CrossEncoderReranker. "
                "Install with: pip install sentence-transformers"
            ) from exc
        resolved_model = require_local_model_path(
            model_name,
            env_var="RAG_RERANKER_MODEL_PATH",
            default_model=DEFAULT_RERANKER_MODEL,
        )
        self.model_name = resolved_model
        self.model = CrossEncoder(resolved_model, device=device)
        logger.info("CrossEncoderReranker loaded: %s", resolved_model)

    def rerank(
        self, query: str, documents: list[str], *, top_k: int | None = None
    ) -> list[tuple[int, float]]:
        if not documents:
            return []

        pairs = [[query, doc] for doc in documents]
        scores = self.model.predict(pairs)

        indexed_scores = list(enumerate(scores.tolist()))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        if top_k is not None:
            indexed_scores = indexed_scores[:top_k]

        return indexed_scores


class LLMReranker(BaseReranker):
    """Reranker using an LLM to score relevancy (slower but more flexible)."""

    name = "llm"

    PROMPT = """Rate the relevance of the following document to the query on a scale of 0.0 to 1.0.
Query: {query}
Document: {document}
Respond with ONLY a number between 0.0 and 1.0."""

    def __init__(self, llm_client: Any) -> None:
        self.llm_client = llm_client

    def rerank(
        self, query: str, documents: list[str], *, top_k: int | None = None
    ) -> list[tuple[int, float]]:
        if not documents:
            return []

        scored: list[tuple[int, float]] = []
        for index, doc in enumerate(documents):
            prompt = self.PROMPT.format(query=query, document=doc[:1000])
            try:
                response = self._call_llm(prompt)
                score = float(response.strip())
                score = max(0.0, min(1.0, score))
            except (ValueError, TypeError, Exception):
                score = 0.5
            scored.append((index, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        if top_k is not None:
            scored = scored[:top_k]
        return scored

    def _call_llm(self, prompt: str) -> str:
        for method_name in ("generate", "complete", "invoke"):
            method = getattr(self.llm_client, method_name, None)
            if callable(method):
                return str(method(prompt))
        if callable(self.llm_client):
            return str(self.llm_client(prompt))
        raise TypeError("LLM client must be callable or expose generate/complete/invoke.")


class NoOpReranker(BaseReranker):
    """Pass-through reranker that preserves original order (for testing/baseline)."""

    name = "noop"

    def rerank(
        self, query: str, documents: list[str], *, top_k: int | None = None
    ) -> list[tuple[int, float]]:
        results = [(i, 1.0 - i * 0.01) for i in range(len(documents))]
        if top_k is not None:
            results = results[:top_k]
        return results
