"""Community summary generation for GraphRAG.

Uses an LLM to generate natural-language summaries of detected communities,
enabling the global search capability that distinguishes GraphRAG from plain RAG.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_ENTITIES_IN_PROMPT = 50
DEFAULT_MAX_EDGES_IN_PROMPT = 80


@dataclass(frozen=True, slots=True)
class CommunitySummary:
    """A generated summary for a community."""

    community_id: str
    level: int
    title: str
    summary: str
    entity_count: int
    edge_count: int
    entity_names: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CommunitySummaryResult:
    """Result of summarizing all communities at a given level."""

    level: int
    communities_processed: int
    communities_skipped: int
    summaries: list[CommunitySummary]
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "communities_processed": self.communities_processed,
            "communities_skipped": self.communities_skipped,
            "total_summaries": len(self.summaries),
            "errors": self.errors,
        }


def build_community_prompt(
    community_id: str,
    entities: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    max_entities: int = DEFAULT_MAX_ENTITIES_IN_PROMPT,
    max_edges: int = DEFAULT_MAX_EDGES_IN_PROMPT,
) -> str:
    """Build a prompt for LLM community summarization.

    Args:
        community_id: The community identifier.
        entities: List of entity dicts with 'name' and 'type'.
        edges: List of edge dicts with 'subject', 'predicate', 'object'.
        max_entities: Maximum entities to include in the prompt.
        max_edges: Maximum edges to include in the prompt.

    Returns:
        A formatted prompt string.
    """
    entity_lines = []
    for entity in entities[:max_entities]:
        entity_type = entity.get("type", "Unknown")
        entity_lines.append(f"- {entity['name']} (type: {entity_type})")
    if len(entities) > max_entities:
        entity_lines.append(f"- ... and {len(entities) - max_entities} more entities")

    edge_lines = []
    for edge in edges[:max_edges]:
        subject = edge.get("subject", "?")
        predicate = edge.get("predicate", "RELATED_TO")
        obj = edge.get("object", "?")
        edge_lines.append(f"- {subject} --{predicate}--> {obj}")
    if len(edges) > max_edges:
        edge_lines.append(f"- ... and {len(edges) - max_edges} more relationships")

    entities_text = "\n".join(entity_lines) if entity_lines else "- (no entities)"
    edges_text = "\n".join(edge_lines) if edge_lines else "- (no relationships)"

    return f"""You are an expert knowledge graph analyst. Analyze the following community of entities and their relationships from a knowledge graph.

Community ID: {community_id}
Entity Count: {len(entities)}
Relationship Count: {len(edges)}

## Entities in this community:
{entities_text}

## Relationships in this community:
{edges_text}

## Task:
Generate a comprehensive summary of this community. Your response MUST be valid JSON with the following structure:
{{
  "title": "A concise title (5-10 words) describing the main theme of this community",
  "summary": "A detailed 2-4 paragraph summary explaining: (1) What this community is about, (2) The key entities and their roles, (3) The important relationships and patterns, (4) The significance of this knowledge cluster."
}}

Respond with ONLY the JSON object, no additional text."""


def _call_llm(llm_client: Any, prompt: str) -> str:
    """Call the LLM client in a compatible way."""
    for method_name in ("generate", "complete", "invoke"):
        method = getattr(llm_client, method_name, None)
        if callable(method):
            return str(method(prompt))
    if callable(llm_client):
        return str(llm_client(prompt))
    raise TypeError("LLM client must be callable or expose generate/complete/invoke.")


def _parse_summary_response(raw: str) -> dict[str, str]:
    """Parse the LLM response into title and summary."""
    # Try to extract JSON from potentially wrapped response
    text = raw.strip()
    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (code block markers)
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        parsed = json.loads(text)
        return {
            "title": str(parsed.get("title", "")).strip(),
            "summary": str(parsed.get("summary", "")).strip(),
        }
    except json.JSONDecodeError:
        # Fallback: use the raw text as summary
        return {
            "title": "Community Summary",
            "summary": text[:2000],
        }


def summarize_communities(
    graph_store: Any,
    llm_client: Any,
    *,
    level: int = 0,
    min_community_size: int = 2,
    max_entities_in_prompt: int = DEFAULT_MAX_ENTITIES_IN_PROMPT,
    max_edges_in_prompt: int = DEFAULT_MAX_EDGES_IN_PROMPT,
) -> CommunitySummaryResult:
    """Generate summaries for all communities at a given level.

    Args:
        graph_store: A GraphStore instance with community assignments.
        llm_client: An LLM client (must expose generate/complete/invoke or be callable).
        level: The community level to summarize.
        min_community_size: Skip communities smaller than this threshold.
        max_entities_in_prompt: Max entities to include in the LLM prompt.
        max_edges_in_prompt: Max edges to include in the LLM prompt.

    Returns:
        CommunitySummaryResult with all generated summaries.
    """
    communities = graph_store.get_communities(level=level)
    summaries: list[CommunitySummary] = []
    errors: list[dict[str, Any]] = []
    skipped = 0

    for community in communities:
        community_id = str(community["community_id"])
        member_count = int(community["member_count"])

        if member_count < min_community_size:
            skipped += 1
            logger.debug(
                "Skipping community %s (size=%d < min=%d)",
                community_id,
                member_count,
                min_community_size,
            )
            continue

        entities = graph_store.get_community_entities(community_id, level=level)
        edges = graph_store.get_community_edges(community_id, level=level)

        prompt = build_community_prompt(
            community_id,
            entities,
            edges,
            max_entities=max_entities_in_prompt,
            max_edges=max_edges_in_prompt,
        )

        try:
            raw_response = _call_llm(llm_client, prompt)
            parsed = _parse_summary_response(raw_response)

            summary = CommunitySummary(
                community_id=community_id,
                level=level,
                title=parsed["title"],
                summary=parsed["summary"],
                entity_count=len(entities),
                edge_count=len(edges),
                entity_names=[e["name"] for e in entities],
            )
            summaries.append(summary)
            logger.info(
                "Summarized community %s: '%s' (%d entities, %d edges)",
                community_id,
                parsed["title"][:50],
                len(entities),
                len(edges),
            )
        except Exception as exc:
            logger.error("Failed to summarize community %s: %s", community_id, exc)
            errors.append({"community_id": community_id, "error": str(exc)})

    # Store summaries in GraphStore
    if summaries:
        graph_store.store_community_summaries(
            [
                {
                    "community_id": s.community_id,
                    "title": s.title,
                    "summary": s.summary,
                    "entity_count": s.entity_count,
                    "edge_count": s.edge_count,
                }
                for s in summaries
            ],
            level=level,
            reset_level=True,
        )

    result = CommunitySummaryResult(
        level=level,
        communities_processed=len(summaries),
        communities_skipped=skipped,
        summaries=summaries,
        errors=errors,
    )
    logger.info(
        "Community summarization complete: %d summarized, %d skipped, %d errors",
        len(summaries),
        skipped,
        len(errors),
    )
    return result


def summarize_from_file(
    sqlite_path: str,
    llm_client: Any,
    *,
    level: int = 0,
    min_community_size: int = 2,
) -> CommunitySummaryResult:
    """Convenience: summarize communities in an existing SQLite graph DB."""
    from storage_layer.graph_store import GraphStore

    store = GraphStore(sqlite_path)
    store.initialize(reset=False)
    return summarize_communities(
        store, llm_client, level=level, min_community_size=min_community_size
    )
