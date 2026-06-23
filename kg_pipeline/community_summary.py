"""Community summary generation for GraphRAG.

Uses an LLM to generate natural-language summaries of detected communities,
enabling the global search capability that distinguishes GraphRAG from plain RAG.
"""
from __future__ import annotations

import json
import logging
import re
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
    metadata: dict[str, Any] = field(default_factory=dict)


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
        triple_id = str(edge.get("triple_id") or "").strip()
        subject = edge.get("subject", "?")
        predicate = edge.get("predicate", "RELATED_TO")
        obj = edge.get("object", "?")
        prefix = f"[{triple_id}] " if triple_id else ""
        edge_lines.append(f"- {prefix}{subject} --{predicate}--> {obj}")
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


def split_summary_sentences(summary: str) -> list[str]:
    """Return sentence-like claims that should carry source evidence."""
    text = str(summary or "").strip()
    if not text:
        return []

    punctuated = [
        match.group(0).strip()
        for match in re.finditer(r"[^.!?。！？\n]+[.!?。！？]", text)
        if match.group(0).strip()
    ]
    if punctuated:
        return punctuated

    return [line.strip("- \t") for line in text.splitlines() if line.strip("- \t")]


def build_summary_sentence_evidence(summary: str, edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bind each summary sentence to source triples from the community.

    The matcher prefers triples whose endpoint or predicate text appears in the
    sentence, then falls back to the full community edge set so no generated
    sentence is left without an auditable source trail.
    """
    sentences = split_summary_sentences(summary)
    triple_ids = [_edge_triple_id(edge) for edge in edges]
    triple_ids = [triple_id for triple_id in triple_ids if triple_id]
    if not sentences or not triple_ids:
        return []

    bindings: list[dict[str, Any]] = []
    for index, sentence in enumerate(sentences):
        matched = _match_sentence_edges(sentence, edges)
        evidence_triple_ids = matched or triple_ids
        source_evidence = [
            source
            for edge in edges
            if _edge_triple_id(edge) in evidence_triple_ids
            for source in [_edge_source_evidence(edge)]
            if source
        ]
        bindings.append(
            {
                "sentence_index": index,
                "sentence": sentence,
                "evidence_triple_ids": evidence_triple_ids,
                "source_evidence": source_evidence,
            }
        )
    return bindings


def _edge_triple_id(edge: dict[str, Any]) -> str:
    return str(edge.get("triple_id") or "").strip()


def _match_sentence_edges(sentence: str, edges: list[dict[str, Any]]) -> list[str]:
    sentence_lower = sentence.lower()
    scored: list[tuple[int, str]] = []
    for edge in edges:
        triple_id = _edge_triple_id(edge)
        if not triple_id:
            continue
        terms = (
            str(edge.get("subject") or ""),
            str(edge.get("object") or ""),
            str(edge.get("predicate") or "").replace("_", " "),
        )
        score = sum(1 for term in terms if term.strip() and term.lower() in sentence_lower)
        if score > 0:
            scored.append((score, triple_id))
    if not scored:
        return []
    best_score = max(score for score, _triple_id in scored)
    return [triple_id for score, triple_id in scored if score == best_score]


def _edge_source_evidence(edge: dict[str, Any]) -> dict[str, str]:
    evidence_text = str(edge.get("evidence") or edge.get("text") or "").strip()
    triple_id = _edge_triple_id(edge)
    if not evidence_text or not triple_id:
        return {}

    source = {
        "triple_id": triple_id,
        "text": evidence_text,
    }
    for key in ("source_file", "source_page", "source_chunk_id"):
        value = str(edge.get(key) or "").strip()
        if value:
            source[key] = value
    return source


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
                metadata={
                    "evidence_triple_ids": [
                        _edge_triple_id(edge)
                        for edge in edges
                        if _edge_triple_id(edge)
                    ],
                    "sentence_evidence": build_summary_sentence_evidence(parsed["summary"], edges),
                },
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
                    "metadata": s.metadata,
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
