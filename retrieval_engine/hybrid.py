from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .core import BaseRetriever, RetrievalResult

_NO_RETRIEVERS = "HybridRetriever requires at least one explicit retriever."
_WEIGHT_COUNT_MISMATCH = "HybridRetriever weights must match the number of retrievers."
_SUPPORTED_FUSION_MODES = {"weighted_score", "rrf"}


@dataclass(slots=True)
class RetrievalDiagnostics:
    original_query: str = ""
    rewritten_queries: tuple[str, ...] = ()
    fusion_mode: str = "weighted_score"
    raw_candidate_count: int = 0
    filtered_candidate_count: int = 0
    final_candidate_count: int = 0
    filters_applied: bool = False
    reranker_name: str | None = None
    reranker_error: str | None = None
    no_answer: bool = False
    no_answer_reason: str | None = None


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
        query_rewriter: Any | None = None,
        include_original_query: bool = True,
        fusion_mode: str = "weighted_score",
        rrf_k: float = 60.0,
        no_answer_min_score: float | None = None,
        no_answer_min_results: int | None = None,
        name: str | None = None,
    ) -> None:
        if not retrievers:
            raise ValueError(_NO_RETRIEVERS)
        if fusion_mode not in _SUPPORTED_FUSION_MODES:
            raise ValueError(f"Unsupported fusion_mode: {fusion_mode}")
        self.retrievers = list(retrievers)
        self.weights = weights
        self.per_retriever_k = per_retriever_k
        self.reranker = reranker
        self.query_rewriter = query_rewriter
        self.include_original_query = include_original_query
        self.fusion_mode = fusion_mode
        self.rrf_k = float(rrf_k)
        self.no_answer_min_score = no_answer_min_score
        self.no_answer_min_results = no_answer_min_results
        self.name = name or self.name
        self.last_diagnostics = RetrievalDiagnostics(fusion_mode=fusion_mode)

        if isinstance(weights, Sequence) and not isinstance(weights, str | bytes) and len(weights) != len(retrievers):
            raise ValueError(_WEIGHT_COUNT_MISMATCH)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        diagnostics = RetrievalDiagnostics(
            original_query=query,
            fusion_mode=self.fusion_mode,
            filters_applied=filters is not None,
            reranker_name=_component_name(self.reranker) if self.reranker is not None else None,
        )
        self.last_diagnostics = diagnostics
        if top_k <= 0:
            return []

        request_k = self.per_retriever_k or top_k
        queries = _rewrite_queries(
            query,
            self.query_rewriter,
            include_original=self.include_original_query,
        )
        diagnostics.rewritten_queries = queries

        merged = self._retrieve_and_fuse(queries=queries, top_k=request_k, filters=filters, diagnostics=diagnostics)
        candidates = sorted(merged.values(), key=lambda item: (-item.score, item.component_scores.get("_first_seen", 0)))
        for candidate in candidates:
            candidate.component_scores.pop("_first_seen", None)

        diagnostics.filtered_candidate_count = len(candidates)

        candidates = self._apply_reranker(query=query, candidates=candidates, top_k=top_k, diagnostics=diagnostics)
        candidates = candidates[:top_k]

        no_answer_reason = self._no_answer_reason(candidates)
        if no_answer_reason:
            diagnostics.no_answer = True
            diagnostics.no_answer_reason = no_answer_reason
            diagnostics.final_candidate_count = 0
            return []

        diagnostics.final_candidate_count = len(candidates)
        return candidates

    def _retrieve_and_fuse(
        self,
        *,
        queries: tuple[str, ...],
        top_k: int,
        filters: Mapping[str, Any] | None,
        diagnostics: RetrievalDiagnostics,
    ) -> dict[tuple[str, str], RetrievalResult]:
        merged: dict[tuple[str, str], RetrievalResult] = {}
        first_seen: dict[tuple[str, str], int] = {}
        seen_index = 0

        for query_index, query_text in enumerate(queries):
            for index, retriever in enumerate(self.retrievers):
                retriever_name = str(getattr(retriever, "name", retriever.__class__.__name__))
                weight = self._weight_for(retriever_name, index)
                raw_results = _call_retriever(retriever, query_text, top_k, filters)
                diagnostics.raw_candidate_count += len(raw_results)
                filtered_results = [result for result in raw_results if _matches_filters(result, filters)]
                for rank, result in enumerate(filtered_results, start=1):
                    key = result.chunk.identity_key
                    score = self._fusion_score(result=result, rank=rank, weight=weight)
                    rewrite_boost = self._rewrite_top_hit_boost(
                        score=score,
                        query_index=query_index,
                        rank=rank,
                    )
                    score += rewrite_boost
                    component_name = (
                        f"rrf:{retriever_name}" if self.fusion_mode == "rrf" else retriever_name
                    )
                    if key not in merged:
                        first_seen[key] = seen_index
                        seen_index += 1
                        component_scores = {component_name: score, "_first_seen": float(first_seen[key])}
                        if rewrite_boost:
                            component_scores["rrf_rewrite_top_hit"] = rewrite_boost
                        merged[key] = RetrievalResult(
                            chunk=result.chunk,
                            score=score,
                            retriever_name=self.name,
                            component_scores=component_scores,
                        )
                        continue
                    merged[key].score += score
                    merged[key].component_scores[component_name] = (
                        merged[key].component_scores.get(component_name, 0.0) + score
                    )
                    if rewrite_boost:
                        merged[key].component_scores["rrf_rewrite_top_hit"] = (
                            merged[key].component_scores.get("rrf_rewrite_top_hit", 0.0) + rewrite_boost
                        )
        return merged

    def _fusion_score(self, *, result: RetrievalResult, rank: int, weight: float) -> float:
        if self.fusion_mode == "rrf":
            return weight * (1.0 / (self.rrf_k + rank))
        return float(result.score) * weight

    def _rewrite_top_hit_boost(self, *, score: float, query_index: int, rank: int) -> float:
        if self.fusion_mode != "rrf" or query_index <= 0 or rank > 3:
            return 0.0
        return score * (2.0 / rank)

    def _apply_reranker(
        self,
        *,
        query: str,
        candidates: list[RetrievalResult],
        top_k: int,
        diagnostics: RetrievalDiagnostics,
    ) -> list[RetrievalResult]:
        if self.reranker is not None and candidates:
            rerank_method = getattr(self.reranker, "rerank", None)
            if callable(rerank_method):
                rerank_pool = candidates[: max(top_k * 3, len(candidates))]
                texts = [r.chunk.text for r in rerank_pool]
                try:
                    reranked = rerank_method(query, texts, top_k=top_k)
                    return [
                        RetrievalResult(
                            chunk=rerank_pool[idx].chunk,
                            score=float(score),
                            retriever_name=self.name,
                            component_scores={
                                **rerank_pool[idx].component_scores,
                                "reranker": float(score),
                            },
                        )
                        for idx, score in reranked
                        if 0 <= idx < len(rerank_pool)
                    ]
                except Exception as exc:  # noqa: BLE001
                    diagnostics.reranker_error = f"{exc.__class__.__name__}: {exc}"
        return candidates

    def _no_answer_reason(self, candidates: list[RetrievalResult]) -> str | None:
        if not candidates:
            return "no_candidates"
        if self.no_answer_min_results is not None and len(candidates) < self.no_answer_min_results:
            return "not_enough_results"
        if self.no_answer_min_score is not None and candidates[0].score < self.no_answer_min_score:
            return "best_score_below_threshold"
        return None

    def _weight_for(self, retriever_name: str, index: int) -> float:
        if self.weights is None:
            return 1.0
        if isinstance(self.weights, Mapping):
            return float(self.weights.get(retriever_name, 1.0))
        return float(self.weights[index])


def _component_name(component: Any) -> str:
    if component is None:
        return ""
    return str(getattr(component, "name", component.__class__.__name__))


def _rewrite_queries(query: str, rewriter: Any | None, *, include_original: bool) -> tuple[str, ...]:
    raw_queries: list[str] = [query] if include_original else []
    if rewriter is not None:
        rewrite_method = None
        for method_name in ("rewrite", "transform", "expand"):
            method = getattr(rewriter, method_name, None)
            if callable(method):
                rewrite_method = method
                break
        if rewrite_method is None and callable(rewriter):
            rewrite_method = rewriter
        if rewrite_method is not None:
            raw_queries.extend(_coerce_queries(rewrite_method(query)))

    seen: set[str] = set()
    queries: list[str] = []
    for item in raw_queries:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        queries.append(normalized)
    return tuple(queries)


def _coerce_queries(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        if "queries" in value:
            return _coerce_queries(value["queries"])
        if "query" in value:
            return _coerce_queries(value["query"])
        if "rewritten_query" in value:
            return _coerce_queries(value["rewritten_query"])
        return []
    if isinstance(value, Sequence) and not isinstance(value, bytes):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _call_retriever(
    retriever: BaseRetriever,
    query: str,
    top_k: int,
    filters: Mapping[str, Any] | None,
) -> list[RetrievalResult]:
    retrieve = retriever.retrieve
    if filters is not None and _accepts_filters(retrieve):
        return list(retrieve(query, top_k=top_k, filters=filters))
    return list(retrieve(query, top_k=top_k))


def _accepts_filters(method: Any) -> bool:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return False
    params = signature.parameters
    return "filters" in params or any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values())


def _matches_filters(result: RetrievalResult, filters: Mapping[str, Any] | None) -> bool:
    if not filters:
        return True
    if "conditions" in filters:
        operator = str(filters.get("operator") or "AND").upper()
        conditions = filters.get("conditions") or []
        matches = [_matches_filters(result, condition) for condition in conditions if isinstance(condition, Mapping)]
        if operator == "OR":
            return any(matches)
        if operator == "NOT":
            return not all(matches)
        return all(matches)
    if "field" in filters:
        field = str(filters.get("field") or "")
        operator = str(filters.get("operator") or "==")
        expected = filters.get("value")
        actual = _field_value(result, field)
        return _compare(actual, operator, expected)
    return all(_compare(_field_value(result, key), "==", value) for key, value in filters.items())


def _field_value(result: RetrievalResult, field: str) -> Any:
    normalized = field.removeprefix("meta.").removeprefix("metadata.")
    if normalized == "source":
        return result.source
    if normalized == "page":
        return result.page
    if normalized == "chunk_id":
        return result.chunk_id
    value: Any = result.metadata
    for part in normalized.split("."):
        if isinstance(value, Mapping):
            value = value.get(part)
        else:
            return None
    return value


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    operator = operator.lower()
    if operator in {"==", "=", "eq"}:
        return actual == expected
    if operator in {"!=", "ne"}:
        return actual != expected
    if operator == "in":
        if isinstance(expected, Sequence) and not isinstance(expected, str | bytes):
            if isinstance(actual, Sequence) and not isinstance(actual, str | bytes):
                return any(item in expected for item in actual)
            return actual in expected
        return actual == expected
    if operator in {"not in", "nin"}:
        return not _compare(actual, "in", expected)
    if operator in {">", ">=", "<", "<="}:
        left = _as_number(actual)
        right = _as_number(expected)
        if left is None or right is None:
            return False
        if operator == ">":
            return left > right
        if operator == ">=":
            return left >= right
        if operator == "<":
            return left < right
        return left <= right
    if operator == "contains":
        if isinstance(actual, str):
            return str(expected) in actual
        if isinstance(actual, Sequence):
            return expected in actual
        return False
    return False


def _as_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
