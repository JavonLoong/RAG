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

logger = logging.getLogger(__name__)


class RoutingDecision:
    VECTOR_ONLY = "VECTOR_ONLY"
    LOCAL_SEARCH = "LOCAL_SEARCH"
    GLOBAL_SEARCH = "GLOBAL_SEARCH"


@dataclass(slots=True)
class QueryRoute:
    strategy: str
    reason: str


ROUTING_PROMPT = """You are a smart query router for a knowledge base.
You must analyze the user's question and decide the best retrieval strategy.

Available strategies:
1. VECTOR_ONLY: Use for simple, factual questions asking about specific details, definitions, or single facts (e.g., "What is the operating temperature of X?", "Who is the author of Y?").
2. LOCAL_SEARCH: Use for questions involving relationships between specific entities, multi-hop reasoning, or questions asking "How does X relate to Y?" or "What are the causes of Z?".
3. GLOBAL_SEARCH: Use for high-level, thematic, or summarizing questions about the entire dataset (e.g., "What are the main themes?", "Summarize the entire document", "What are the most common issues overall?").

Question:
{question}

Instructions:
Select the most appropriate strategy. Respond with ONLY a valid JSON object matching exactly this structure:
{{"strategy": "VECTOR_ONLY" | "LOCAL_SEARCH" | "GLOBAL_SEARCH", "reason": "brief explanation"}}
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

    def route_query(self, question: str) -> QueryRoute:
        """Classify a question into a routing decision."""
        if not question.strip():
            return QueryRoute(strategy=self.default_route, reason="Empty question")

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
            logger.warning(
                "Query routing failed, falling back to %s. Error: %s",
                self.default_route,
                exc,
            )
            return QueryRoute(strategy=self.default_route, reason=f"Routing failed: {exc}")

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
            strategy = str(parsed.get("strategy", self.default_route)).upper()
            if strategy not in (
                RoutingDecision.VECTOR_ONLY,
                RoutingDecision.LOCAL_SEARCH,
                RoutingDecision.GLOBAL_SEARCH,
            ):
                strategy = self.default_route
            return QueryRoute(
                strategy=strategy,
                reason=str(parsed.get("reason", "Parsed successfully")),
            )
        except json.JSONDecodeError:
            # Fallback heuristic
            if "GLOBAL_SEARCH" in text.upper():
                return QueryRoute(
                    strategy=RoutingDecision.GLOBAL_SEARCH, reason="Heuristic match"
                )
            elif "VECTOR_ONLY" in text.upper():
                return QueryRoute(
                    strategy=RoutingDecision.VECTOR_ONLY, reason="Heuristic match"
                )
            return QueryRoute(strategy=self.default_route, reason="Fallback match")
