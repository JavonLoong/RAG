"""Evidence-bound deterministic community summaries for the governed active graph."""
# ruff: noqa: RUF001

from __future__ import annotations

from typing import Any

from storage_layer.graph_store import GraphStore


def build_governed_community_summaries(
    graph_store: GraphStore,
    *,
    graph_version_id: str,
    level: int = 0,
) -> dict[str, Any]:
    exported = graph_store.export_graph()
    edges = list(exported.get("edges") or [])
    nodes = list(exported.get("nodes") or [])
    adjacency: dict[str, set[str]] = {str(item.get("name") or ""): set() for item in nodes}
    for edge in edges:
        subject = str(edge.get("subject") or "")
        object_name = str(edge.get("object") or edge.get("object_name") or "")
        if not subject or not object_name:
            continue
        adjacency.setdefault(subject, set()).add(object_name)
        adjacency.setdefault(object_name, set()).add(subject)
    components: list[list[str]] = []
    unseen = set(adjacency)
    while unseen:
        root = min(unseen)
        unseen.remove(root)
        stack = [root]
        component: list[str] = []
        while stack:
            node = stack.pop()
            component.append(node)
            for neighbor in sorted(adjacency.get(node, ())):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    components.sort(key=lambda item: (-len(item), item[0] if item else ""))
    assignments: list[dict[str, str]] = []
    summaries: list[dict[str, Any]] = []
    for index, members in enumerate(components, start=1):
        community_id = f"C{index:04d}"
        member_set = set(members)
        assignments.extend({"community_id": community_id, "node_name": member} for member in members)
        community_edges = [
            edge
            for edge in edges
            if str(edge.get("subject") or "") in member_set
            and str(edge.get("object") or edge.get("object_name") or "") in member_set
        ]
        triples = [
            f"{edge.get('subject')} --{edge.get('predicate')}--> {edge.get('object') or edge.get('object_name')}"
            for edge in community_edges[:30]
        ]
        summary = "\n".join(
            [
                f"社区 {community_id} 包含 {len(members)} 个实体和 {len(community_edges)} 条内部关系。",
                f"实体：{', '.join(members[:20])}",
                "证据关系：",
                *(triples or ["无内部关系。"]),
            ]
        )
        summaries.append(
            {
                "community_id": community_id,
                "title": f"治理图社区 {community_id}",
                "summary": summary,
                "entity_count": len(members),
                "edge_count": len(community_edges),
                "metadata": {
                    "graph_version_id": graph_version_id,
                    "provider": "deterministic-evidence-summary",
                    "generated_text_only_from_graph_edges": True,
                    "evidence_triple_ids": [
                        str(edge.get("triple_id") or "")
                        for edge in community_edges
                        if edge.get("triple_id")
                    ],
                },
            }
        )
    graph_store.store_communities(assignments, level=level, reset_level=True)
    graph_store.store_community_summaries(summaries, level=level, reset_level=True)
    return {
        "graph_version_id": graph_version_id,
        "level": level,
        "community_count": len(summaries),
        "assignment_count": len(assignments),
        "edge_count": len(edges),
        "summaries": summaries,
    }
