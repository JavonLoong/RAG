"""Global search (map-reduce) over community summaries.

This is the third critical missing GraphRAG feature: the ability to answer
high-level, open-ended questions by reasoning over community summaries
rather than individual document chunks.

Implements the map-reduce pattern from the Microsoft GraphRAG paper:
- Map: Each relevant community summary generates a partial answer.
- Reduce: Partial answers are combined into a final comprehensive response.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAP_PROMPT = """You are a helpful assistant analyzing a knowledge graph community to answer a question.

## Community Summary:
Title: {title}
{summary}

## Question:
{question}

## Instructions:
Based on the community summary above, provide any relevant information that helps answer the question.
If this community is not relevant to the question, respond with exactly: "NOT_RELEVANT"
Otherwise, provide a concise but complete partial answer, citing specific entities and relationships from the community.

Partial Answer:"""

DEFAULT_REDUCE_PROMPT = """You are a helpful assistant synthesizing information from multiple knowledge graph communities.

## Question:
{question}

## Partial Answers from Community Analysis:
{partial_answers}

## Instructions:
Synthesize all partial answers above into a single, comprehensive, well-structured final answer.
- Combine overlapping information, removing redundancy.
- Preserve important details and specific entity names.
- Organize the answer logically.
- If partial answers contradict each other, note the discrepancy.
- Use markdown formatting for readability.

Final Answer:"""


@dataclass(slots=True)
class GlobalSearchResult:
    """Result of a global search over community summaries."""

    question: str
    answer: str
    communities_searched: int
    communities_relevant: int
    partial_answers: list[dict[str, Any]]
    context_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "communities_searched": self.communities_searched,
            "communities_relevant": self.communities_relevant,
            "partial_answers": self.partial_answers,
            "context_only": self.context_only,
        }


def _call_llm(llm_client: Any, prompt: str) -> str:
    """Call the LLM client in a compatible way."""
    for method_name in ("generate", "complete", "invoke"):
        method = getattr(llm_client, method_name, None)
        if callable(method):
            return str(method(prompt))
    if callable(llm_client):
        return str(llm_client(prompt))
    raise TypeError("LLM client must be callable or expose generate/complete/invoke.")


class GlobalSearchOrchestrator:
    """Orchestrates global search using map-reduce over community summaries.

    This is the key differentiator of GraphRAG over standard RAG:
    it can answer high-level questions like "What are the main themes in this knowledge base?"
    by reasoning over community-level summaries rather than individual chunks.
    """

    def __init__(
        self,
        *,
        graph_store: Any,
        llm_client: Any,
        map_prompt: str | None = None,
        reduce_prompt: str | None = None,
        max_communities: int = 20,
    ) -> None:
        """Initialize the global search orchestrator.

        Args:
            graph_store: A GraphStore instance with community summaries.
            llm_client: An LLM client for map and reduce steps.
            map_prompt: Custom prompt template for the map step.
            reduce_prompt: Custom prompt template for the reduce step.
            max_communities: Maximum number of communities to include in search.
        """
        self.graph_store = graph_store
        self.llm_client = llm_client
        self.map_prompt = map_prompt or DEFAULT_MAP_PROMPT
        self.reduce_prompt = reduce_prompt or DEFAULT_REDUCE_PROMPT
        self.max_communities = max_communities

    def search(
        self,
        question: str,
        *,
        level: int = 0,
        context_only: bool = False,
        stream_callback: Any | None = None,
    ) -> GlobalSearchResult:
        """Execute a global search over community summaries.

        Args:
            question: The user's question.
            level: Community hierarchy level to search.
            context_only: If True, return partial answers without final synthesis.
            stream_callback: Optional callback func(current: int, total: int, pa: dict) for streaming progress.

        Returns:
            GlobalSearchResult with the final answer and metadata.
        """
        question = (question or "").strip()
        if not question:
            raise ValueError("Question must not be empty.")

        # Get all community summaries at this level
        summaries = self.graph_store.get_community_summaries(level=level)
        if not summaries:
            logger.warning("No community summaries found at level %d", level)
            return GlobalSearchResult(
                question=question,
                answer="No community summaries are available. Please run community detection and summarization first.",
                communities_searched=0,
                communities_relevant=0,
                partial_answers=[],
            )

        # Limit to max_communities (sorted by entity_count, largest first)
        summaries = summaries[: self.max_communities]
        total_communities = len(summaries)

        # MAP phase: generate partial answers from each community
        partial_answers: list[dict[str, Any]] = []
        relevant_count = 0

        for i, summary in enumerate(summaries, start=1):
            map_prompt = self.map_prompt.format(
                title=summary.get("title", ""),
                summary=summary.get("summary", ""),
                question=question,
            )
            try:
                response = _call_llm(self.llm_client, map_prompt)
                response = response.strip()

                if response == "NOT_RELEVANT" or not response:
                    if stream_callback:
                        stream_callback(i, total_communities, None)
                    continue

                relevant_count += 1
                pa_dict = {
                    "community_id": summary["community_id"],
                    "title": summary.get("title", ""),
                    "entity_count": summary.get("entity_count", 0),
                    "answer": response,
                }
                partial_answers.append(pa_dict)
                if stream_callback:
                    stream_callback(i, total_communities, pa_dict)
            except Exception as exc:
                logger.error(
                    "Map step failed for community %s: %s",
                    summary["community_id"],
                    exc,
                )
                if stream_callback:
                    stream_callback(i, total_communities, None)

        if context_only:
            return GlobalSearchResult(
                question=question,
                answer="",
                communities_searched=len(summaries),
                communities_relevant=relevant_count,
                partial_answers=partial_answers,
                context_only=True,
            )

        # REDUCE phase: synthesize partial answers
        if not partial_answers:
            return GlobalSearchResult(
                question=question,
                answer="Based on the available community summaries, no relevant information was found for this question.",
                communities_searched=len(summaries),
                communities_relevant=0,
                partial_answers=[],
            )

        # Build partial answers text
        partial_text_parts = []
        for index, pa in enumerate(partial_answers, start=1):
            partial_text_parts.append(
                f"### Community: {pa['title']} ({pa['entity_count']} entities)\n{pa['answer']}"
            )
        partial_answers_text = "\n\n".join(partial_text_parts)

        reduce_prompt = self.reduce_prompt.format(
            question=question,
            partial_answers=partial_answers_text,
        )

        try:
            final_answer = _call_llm(self.llm_client, reduce_prompt)
        except Exception as exc:
            logger.error("Reduce step failed: %s", exc)
            final_answer = (
                "Error during answer synthesis. Partial answers:\n\n"
                + partial_answers_text
            )

        return GlobalSearchResult(
            question=question,
            answer=final_answer.strip(),
            communities_searched=len(summaries),
            communities_relevant=relevant_count,
            partial_answers=partial_answers,
        )
