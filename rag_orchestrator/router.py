"""Adaptive Query Routing for GraphRAG.

Implements query classification to dynamically route queries to the most
cost-effective and appropriate retrieval path (Vector, Local Graph, or Global Map-Reduce).
This is a 2026 SOTA standard practice to balance performance and cost.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from .query_understanding import QueryRouteName, SemanticQueryAnalyzer

logger = logging.getLogger(__name__)


class RoutingDecision:
    VECTOR_ONLY = "VECTOR_ONLY"
    LOCAL_SEARCH = "LOCAL_SEARCH"
    GLOBAL_SEARCH = "GLOBAL_SEARCH"


@dataclass(slots=True)
class QueryRoute:
    strategy: str
    reason: str
    task_route: QueryRouteName | None = None


ROUTING_PROMPT = """You are a smart query router for a knowledge base.
You must analyze the user's question and decide the best retrieval strategy.

Available task routes:
1. LOCAL_RAG: simple local facts or one passage.
2. GRAPH_PATH: relationships between entities or graph paths.
3. GLOBAL_SUMMARY: high-level corpus/community summary.
4. MULTI_HOP: causal or multi-step reasoning.
5. COMPARE_SYNTHESIS: compare entities, documents, periods, or options.
6. COMPREHENSIVE_ANALYSIS: full-corpus sweep, planning, map-reduce, and coverage report.

Question:
{question}

Instructions:
Select the most appropriate strategy. Respond with ONLY a valid JSON object matching exactly this structure:
{{"strategy": "LOCAL_RAG" | "GRAPH_PATH" | "GLOBAL_SUMMARY" | "MULTI_HOP" | "COMPARE_SYNTHESIS" | "COMPREHENSIVE_ANALYSIS", "reason": "brief explanation"}}
"""


class AdaptiveQueryRouter:
    """Routes queries to the appropriate RAG strategy using an LLM."""

    def __init__(
        self,
        llm_client: Any,
        default_route: str = RoutingDecision.LOCAL_SEARCH,
    ) -> None:
        self.llm_client = llm_client
        self.default_route = default_route
        self.semantic_analyzer = SemanticQueryAnalyzer()

    def route_query(self, question: str) -> QueryRoute:
        """Classify a question into a routing decision."""
        if not question.strip():
            return QueryRoute(strategy=self.default_route, reason="Empty question")
        semantic_spec = self.semantic_analyzer.analyze(question)
        if semantic_spec.requires_planning or getattr(semantic_spec.coverage_scope, "value", "local") != "local":
            return QueryRoute(
                strategy=_task_route_to_legacy_strategy(semantic_spec.route),
                reason=f"semantic analyzer preflight: {semantic_spec.route_reason}",
                task_route=semantic_spec.route,
            )

        prompt = ROUTING_PROMPT.format(question=question)

        try:
            response = self._call_llm(prompt)
            route = self._parse_response(response)
            logger.info(
                "Routed query '%s...' to %s (Reason: %s)",
                question[:30],
                route.strategy,
                route.reason,
            )
            return route
        except Exception as exc:
            spec = self.semantic_analyzer.analyze(question)
            logger.warning(
                "Query routing failed, falling back to local semantic analyzer %s. Error: %s",
                spec.route,
                exc,
            )
            return QueryRoute(
                strategy=_task_route_to_legacy_strategy(spec.route),
                reason=f"semantic analyzer fallback after routing failed: {exc}",
                task_route=spec.route,
            )

    def _call_llm(self, prompt: str) -> str:
        for method_name in ("generate", "complete", "invoke"):
            method = getattr(self.llm_client, method_name, None)
            if callable(method):
                return str(method(prompt))
        if callable(self.llm_client):
            return str(self.llm_client(prompt))
        raise TypeError("LLM client must be callable or expose generate/complete/invoke.")

    def _parse_response(self, text: str) -> QueryRoute:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            parsed = json.loads(text)
            raw_strategy = str(parsed.get("strategy", self.default_route)).upper()
            task_route = _coerce_task_route(raw_strategy) or _legacy_strategy_to_task_route(raw_strategy)
            strategy = _task_route_to_legacy_strategy(task_route) if task_route else raw_strategy
            if strategy not in (RoutingDecision.VECTOR_ONLY, RoutingDecision.LOCAL_SEARCH, RoutingDecision.GLOBAL_SEARCH):
                strategy = self.default_route
            return QueryRoute(
                strategy=strategy,
                reason=str(parsed.get("reason", "Parsed successfully")),
                task_route=task_route,
            )
        except json.JSONDecodeError:
            # Fallback heuristic
            upper_text = text.upper()
            for route in QueryRouteName:
                if route.value in upper_text:
                    return QueryRoute(
                        strategy=_task_route_to_legacy_strategy(route),
                        reason="Heuristic task route match",
                        task_route=route,
                    )
            if "GLOBAL_SEARCH" in upper_text:
                return QueryRoute(strategy=RoutingDecision.GLOBAL_SEARCH, reason="Heuristic match")
            elif "VECTOR_ONLY" in upper_text:
                return QueryRoute(strategy=RoutingDecision.VECTOR_ONLY, reason="Heuristic match")
            return QueryRoute(strategy=self.default_route, reason="Fallback match")


def _coerce_task_route(value: str) -> QueryRouteName | None:
    try:
        return QueryRouteName(value)
    except ValueError:
        return None


def _task_route_to_legacy_strategy(route: QueryRouteName | None) -> str:
    if route == QueryRouteName.LOCAL_RAG:
        return RoutingDecision.VECTOR_ONLY
    if route in {QueryRouteName.GLOBAL_SUMMARY, QueryRouteName.COMPARE_SYNTHESIS, QueryRouteName.COMPREHENSIVE_ANALYSIS}:
        return RoutingDecision.GLOBAL_SEARCH
    if route in {QueryRouteName.GRAPH_PATH, QueryRouteName.MULTI_HOP}:
        return RoutingDecision.LOCAL_SEARCH
    return RoutingDecision.LOCAL_SEARCH


def _legacy_strategy_to_task_route(strategy: str) -> QueryRouteName | None:
    if strategy == RoutingDecision.VECTOR_ONLY:
        return QueryRouteName.LOCAL_RAG
    if strategy == RoutingDecision.LOCAL_SEARCH:
        return QueryRouteName.GRAPH_PATH
    if strategy == RoutingDecision.GLOBAL_SEARCH:
        return QueryRouteName.GLOBAL_SUMMARY
    return None
