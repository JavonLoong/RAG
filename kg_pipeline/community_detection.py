"""Community detection for GraphRAG knowledge graphs.

Implements Louvain community detection using networkx, loading graph data
from the SQLite-backed GraphStore and writing community assignments back.

This is a core GraphRAG capability identified as a critical gap in the project evaluation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CommunityAssignment:
    """A node's assignment to a community at a given hierarchical level."""

    node_name: str
    community_id: str
    level: int = 0


@dataclass(slots=True)
class CommunityDetectionResult:
    """Result of running community detection on a knowledge graph."""

    total_nodes: int
    total_edges: int
    num_communities: int
    level: int
    assignments: list[CommunityAssignment]
    community_sizes: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "num_communities": self.num_communities,
            "level": self.level,
            "community_sizes": self.community_sizes,
            "assignment_count": len(self.assignments),
        }


def _import_networkx() -> Any:
    try:
        import networkx as nx
    except ModuleNotFoundError as exc:
        raise ImportError(
            "networkx is required for community detection. Install with: pip install networkx"
        ) from exc
    return nx


def _import_community() -> Any:
    """Import python-louvain (community) for Louvain community detection."""
    try:
        import community as community_louvain
    except ModuleNotFoundError as exc:
        raise ImportError(
            "python-louvain is required for Louvain community detection. "
            "Install with: pip install python-louvain"
        ) from exc
    return community_louvain


def build_networkx_graph(graph_store: Any) -> Any:
    """Load all edges from GraphStore into a networkx Graph.

    Args:
        graph_store: A storage_layer.graph_store.GraphStore instance.

    Returns:
        A networkx.Graph with node/edge attributes.
    """
    nx = _import_networkx()
    G = nx.Graph()

    # Add all nodes
    for node in graph_store.get_all_nodes():
        G.add_node(node["name"], type=node.get("type", "Unknown"))

    # Add all edges
    for subject, obj, attrs in graph_store.get_all_edges_as_tuples():
        if G.has_edge(subject, obj):
            # Merge predicates for multigraph support on simple graph
            existing = G[subject][obj].get("predicates", [])
            existing.append(attrs.get("predicate", "RELATED_TO"))
            G[subject][obj]["predicates"] = existing
            G[subject][obj]["weight"] = len(existing)
        else:
            G.add_edge(
                subject,
                obj,
                predicate=attrs.get("predicate", "RELATED_TO"),
                predicates=[attrs.get("predicate", "RELATED_TO")],
                confidence=attrs.get("confidence"),
                weight=1,
            )

    return G


def run_louvain_detection(
    graph_store: Any,
    *,
    resolution: float = 1.0,
    level: int = 0,
    random_state: int = 42,
) -> CommunityDetectionResult:
    """Run Louvain community detection on the knowledge graph.

    Args:
        graph_store: A GraphStore instance with loaded graph data.
        resolution: Resolution parameter for Louvain (higher = more communities).
        level: Hierarchical level to assign to results.
        random_state: Random seed for reproducibility.

    Returns:
        CommunityDetectionResult with all assignments.
    """
    community_louvain = _import_community()

    G = build_networkx_graph(graph_store)
    total_nodes = G.number_of_nodes()
    total_edges = G.number_of_edges()

    if total_nodes == 0:
        logger.warning("Graph is empty, no communities to detect.")
        return CommunityDetectionResult(
            total_nodes=0,
            total_edges=0,
            num_communities=0,
            level=level,
            assignments=[],
        )

    # Run Louvain community detection
    partition = community_louvain.best_partition(
        G, resolution=resolution, random_state=random_state
    )

    # Build assignments
    assignments: list[CommunityAssignment] = []
    community_sizes: dict[str, int] = {}
    for node_name, comm_id in partition.items():
        community_id = f"C{comm_id}"
        assignments.append(
            CommunityAssignment(
                node_name=node_name,
                community_id=community_id,
                level=level,
            )
        )
        community_sizes[community_id] = community_sizes.get(community_id, 0) + 1

    # Store assignments in GraphStore
    graph_store.store_communities(
        [{"community_id": a.community_id, "node_name": a.node_name} for a in assignments],
        level=level,
        reset_level=True,
    )

    result = CommunityDetectionResult(
        total_nodes=total_nodes,
        total_edges=total_edges,
        num_communities=len(community_sizes),
        level=level,
        assignments=assignments,
        community_sizes=community_sizes,
    )

    logger.info(
        "Community detection complete: %d nodes, %d edges, %d communities",
        total_nodes,
        total_edges,
        len(community_sizes),
    )
    return result


def run_hierarchical_detection(
    graph_store: Any,
    *,
    resolutions: list[float] | None = None,
    random_state: int = 42,
) -> list[CommunityDetectionResult]:
    """Run multi-level community detection with different resolutions.

    Args:
        graph_store: A GraphStore instance.
        resolutions: List of resolution values for each level. Default: [0.5, 1.0, 2.0]
        random_state: Random seed for reproducibility.

    Returns:
        List of CommunityDetectionResult, one per level.
    """
    if resolutions is None:
        resolutions = [0.5, 1.0, 2.0]

    results = []
    for level, resolution in enumerate(resolutions):
        result = run_louvain_detection(
            graph_store,
            resolution=resolution,
            level=level,
            random_state=random_state,
        )
        results.append(result)
        logger.info(
            "Level %d (resolution=%.2f): %d communities",
            level,
            resolution,
            result.num_communities,
        )

    return results


def detect_communities_from_file(
    sqlite_path: str | Path,
    *,
    resolution: float = 1.0,
    level: int = 0,
) -> CommunityDetectionResult:
    """Convenience function: run community detection on an existing SQLite graph DB.

    Args:
        sqlite_path: Path to the SQLite graph database.
        resolution: Louvain resolution parameter.
        level: Hierarchical level.

    Returns:
        CommunityDetectionResult.
    """
    from storage_layer.graph_store import GraphStore

    store = GraphStore(sqlite_path)
    store.initialize(reset=False)
    return run_louvain_detection(store, resolution=resolution, level=level)
