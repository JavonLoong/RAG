"""Graph retriever with indexed entity matching.

Replaces the full-table-scan approach (max_scan_rows=5000) with a proper
indexed entity name matching strategy using SQLite's built-in FTS5 or
efficient LIKE queries with precomputed indexes.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .core import BaseRetriever, DocumentChunk, RetrievalResult

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


class SQLiteGraphRetriever(BaseRetriever):
    """Retriever that searches the SQLite knowledge graph by entity name matching.

    Instead of scanning all edges, this retriever:
    1. Tokenizes the query into entity name candidates
    2. Uses indexed lookups to find matching seed nodes
    3. Traverses the graph using a Personalized PageRank (PPR) approximation
       (multi-hop BFS with a damping factor) to find deep relational evidence
    4. Scores by match quality, edge confidence, and graph distance (hops)
    """

    name = "graph"

    def __init__(
        self,
        graph_store: Any,
        *,
        name: str | None = None,
        include_community_summaries: bool = True,
    ) -> None:
        self.graph_store = graph_store
        self.name = name or self.name
        self.include_community_summaries = include_community_summaries
        self.max_hops = 2
        self.damping_factor = 0.85

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        if top_k <= 0 or not query.strip():
            return []

        # Extract entity candidates from the query
        entity_candidates = self._extract_entity_candidates(query)
        if not entity_candidates:
            return []

        # Personalized PageRank (PPR) Approximation via BFS
        results: list[RetrievalResult] = []
        seen_triples: set[str] = set()
        visited_nodes: set[str] = set()

        # Seed frontier: (node_name, current_score, current_hop)
        frontier = [(candidate, match_score, 0) for candidate, match_score in entity_candidates]

        while frontier:
            current_node, current_score, hop = frontier.pop(0)
            
            if hop >= self.max_hops:
                continue
                
            if current_node in visited_nodes:
                continue
            visited_nodes.add(current_node)

            neighbors = self.graph_store.neighbors(current_node, limit=top_k * 2)
            
            for neighbor in neighbors:
                triple_id = str(neighbor.get("triple_id", ""))
                
                subject = str(neighbor.get("subject", ""))
                obj = str(neighbor.get("object", ""))
                confidence = float(neighbor.get("confidence") or 0.5)

                # PPR score decay based on hops and edge confidence
                edge_score = current_score * confidence * (self.damping_factor ** hop)

                if triple_id not in seen_triples:
                    seen_triples.add(triple_id)
                    predicate = str(neighbor.get("predicate", ""))
                    
                    text = f"{subject} --{predicate}--> {obj}"
                    metadata = {
                        "subject": subject,
                        "predicate": predicate,
                        "object": obj,
                        "confidence": confidence,
                        "source_file": neighbor.get("source_file"),
                        "source_page": neighbor.get("source_page"),
                        "triple_id": triple_id,
                        "direction": neighbor.get("direction"),
                        "hop": hop,
                    }

                    chunk = DocumentChunk(
                        text=text,
                        source=neighbor.get("source_file"),
                        chunk_id=triple_id,
                        metadata=metadata,
                    )
                    
                    results.append(
                        RetrievalResult(chunk=chunk, score=edge_score, retriever_name=self.name)
                    )

                # Add next hop nodes to frontier
                next_node = obj if subject == current_node else subject
                if next_node and next_node not in visited_nodes:
                    frontier.append((next_node, edge_score, hop + 1))

        # Add community summary results if available
        if self.include_community_summaries:
            try:
                community_results = self._search_communities(query, top_k)
                results.extend(community_results)
            except Exception:
                pass  # Gracefully skip if communities not available

        # Sort by score and return top_k
        results.sort(key=lambda r: -r.score)
        return results[:top_k]

    def _extract_entity_candidates(self, query: str) -> list[tuple[str, float]]:
        """Extract potential entity names from query using multiple strategies."""
        candidates: list[tuple[str, float]] = []

        # Strategy 1: Try full query as entity name (exact match)
        all_nodes = self._get_matching_nodes(query)
        for node_name in all_nodes:
            candidates.append((node_name, 1.0))

        # Strategy 2: Try n-grams from query
        tokens = _TOKEN_RE.findall(query)
        # Try bigrams
        for i in range(len(tokens) - 1):
            bigram = tokens[i] + tokens[i + 1]
            for node_name in self._get_matching_nodes(bigram):
                if node_name not in [c[0] for c in candidates]:
                    candidates.append((node_name, 0.8))

        # Strategy 3: Try individual tokens (but weight them lower)
        for token in tokens:
            if len(token) < 2:
                continue
            for node_name in self._get_matching_nodes(token):
                if node_name not in [c[0] for c in candidates]:
                    candidates.append((node_name, 0.5))

        return candidates[:20]  # Limit candidates

    def _get_matching_nodes(self, pattern: str) -> list[str]:
        """Find nodes matching a pattern using the public search_nodes API."""
        try:
            rows = self.graph_store.search_nodes(pattern, limit=10)
            return [row["name"] for row in rows]
        except Exception:
            return []

    def _search_communities(self, query: str, top_k: int) -> list[RetrievalResult]:
        """Search community summaries for relevant context."""
        results: list[RetrievalResult] = []
        try:
            summaries = self.graph_store.search_community_summaries(query, limit=top_k)
            for summary in summaries:
                chunk = DocumentChunk(
                    text=str(summary.get("summary", "")),
                    source=f"community:{summary.get('community_id', '')}",
                    chunk_id=f"community-{summary.get('community_id', '')}",
                    metadata={
                        "source_type": "community_summary",
                        "community_id": summary.get("community_id"),
                        "title": summary.get("title"),
                        "entity_count": summary.get("entity_count"),
                    },
                )
                # Weight community results slightly lower than direct entity matches
                score = 0.6 * (summary.get("entity_count", 1) / 100)
                results.append(
                    RetrievalResult(chunk=chunk, score=min(score, 0.8), retriever_name=self.name)
                )
        except Exception:
            pass
        return results
