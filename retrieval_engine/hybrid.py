from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .core import BaseRetriever, RetrievalResult

_NO_RETRIEVERS = "HybridRetriever requires at least one explicit retriever."
_WEIGHT_COUNT_MISMATCH = "HybridRetriever weights must match the number of retrievers."


class HybridRetriever(BaseRetriever):
    """Merge results from explicitly supplied retrievers.

    An optional ``reranker`` can be supplied to refine the final ranking
    after score-based merging.  The reranker receives the merged
    candidates and re-scores them using a cross-encoder or LLM.
    """

    name = "hybrid"

    def __init__(
        self,
        retrievers: Sequence[BaseRetriever],
        *,
        weights: Sequence[float] | Mapping[str, float] | None = None,
        per_retriever_k: int | None = None,
        reranker: Any | None = None,
        name: str | None = None,
    ) -> None:
        if not retrievers:
            raise ValueError(_NO_RETRIEVERS)
        self.retrievers = list(retrievers)
        self.weights = weights
        self.per_retriever_k = per_retriever_k
        self.reranker = reranker
        self.name = name or self.name

        if isinstance(weights, Sequence) and not isinstance(weights, str | bytes) and len(weights) != len(retrievers):
            raise ValueError(_WEIGHT_COUNT_MISMATCH)

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        if top_k <= 0:
            return []

        request_k = self.per_retriever_k or top_k
        merged: dict[tuple[str, str], RetrievalResult] = {}
        first_seen: dict[tuple[str, str], int] = {}
        seen_index = 0

        for index, retriever in enumerate(self.retrievers):
            retriever_name = str(getattr(retriever, "name", retriever.__class__.__name__))
            weight = self._weight_for(retriever_name, index)
            for result in retriever.retrieve(query, top_k=request_k):
                key = result.chunk.identity_key
                weighted_score = float(result.score) * weight
                if key not in merged:
                    first_seen[key] = seen_index
                    seen_index += 1
                    merged[key] = RetrievalResult(
                        chunk=result.chunk,
                        score=weighted_score,
                        retriever_name=self.name,
                        component_scores={retriever_name: weighted_score},
                    )
                    continue
                merged[key].score += weighted_score
                merged[key].component_scores[retriever_name] = (
                    merged[key].component_scores.get(retriever_name, 0.0) + weighted_score
                )

        candidates = sorted(merged.values(), key=lambda item: (-item.score, first_seen[item.chunk.identity_key]))

        # Apply reranker if available
        if self.reranker is not None and candidates:
            rerank_method = getattr(self.reranker, "rerank", None)
            if callable(rerank_method):
                # Collect more candidates for reranking, then trim to top_k
                rerank_pool = candidates[: max(top_k * 3, len(candidates))]
                texts = [r.chunk.text for r in rerank_pool]
                try:
                    reranked = rerank_method(query, texts, top_k=top_k)
                    return [
                        RetrievalResult(
                            chunk=rerank_pool[idx].chunk,
                            score=float(score),
                            retriever_name=self.name,
                            component_scores=rerank_pool[idx].component_scores,
                        )
                        for idx, score in reranked
                    ]
                except Exception:
                    pass  # Fall through to default sorting

        return candidates[:top_k]

    def _weight_for(self, retriever_name: str, index: int) -> float:
        if self.weights is None:
            return 1.0
        if isinstance(self.weights, Mapping):
            return float(self.weights.get(retriever_name, 1.0))
        return float(self.weights[index])
