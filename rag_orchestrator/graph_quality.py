from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class GraphQualityThresholds:
    min_evidence_coverage: float = 1.0
    min_edge_confidence: float = 0.7
    max_isolated_node_rate: float = 0.0
    min_community_assignment_coverage: float = 1.0
    min_community_summary_coverage: float = 1.0
    min_summary_evidence_coverage: float = 1.0
    min_summary_sentence_evidence_coverage: float = 1.0
    min_summary_sentence_source_coverage: float = 1.0


@dataclass(slots=True)
class GraphQualityReport:
    metrics: dict[str, float | int | None]
    gate_failures: list[dict[str, Any]]
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def gate_status(self) -> str:
        return "pass" if not self.gate_failures else "fail"

    def to_dict(self) -> dict[str, Any]:
        return {
            "quality_gate": {
                "status": self.gate_status,
                "failures": self.gate_failures,
            },
            "metrics": self.metrics,
            "details": self.details,
        }


def evaluate_graph_quality(
    graph_store_or_export: Any,
    *,
    thresholds: GraphQualityThresholds | None = None,
) -> GraphQualityReport:
    thresholds = thresholds or GraphQualityThresholds()
    graph = _export_graph(graph_store_or_export)

    nodes = list(graph.get("nodes") or [])
    edges = list(graph.get("edges") or [])
    evidence_rows = list(graph.get("evidence") or [])
    communities = list(graph.get("communities") or [])
    summaries = list(graph.get("community_summaries") or [])

    node_count = len(nodes)
    edge_count = len(edges)
    evidence_triple_ids = {
        str(row.get("triple_id"))
        for row in evidence_rows
        if str(row.get("triple_id") or "").strip() and str(row.get("text") or "").strip()
    }
    missing_evidence_edges = [
        str(edge.get("triple_id"))
        for edge in edges
        if str(edge.get("triple_id") or "").strip() not in evidence_triple_ids
    ]

    low_confidence_edges = [
        str(edge.get("triple_id"))
        for edge in edges
        if _confidence(edge.get("confidence")) is None or (_confidence(edge.get("confidence")) or 0.0) < thresholds.min_edge_confidence
    ]

    endpoint_node_ids = {
        node_id
        for edge in edges
        for node_id in (_coerce_int(edge.get("subject_node_id")), _coerce_int(edge.get("object_node_id")))
        if node_id is not None
    }

    node_rows_by_id = {
        node_id: node
        for node in nodes
        for node_id in (_coerce_int(node.get("id")),)
        if node_id is not None
    }

    assigned_node_ids: set[int] = set()
    node_community_keys: dict[int, set[str]] = {}
    community_ids: set[str] = set()
    for row in communities:
        community_key = _community_key(row)
        if community_key:
            community_ids.add(community_key)
        node_id = _coerce_int(row.get("node_id"))
        if node_id is None:
            continue
        assigned_node_ids.add(node_id)
        if community_key:
            node_community_keys.setdefault(node_id, set()).add(community_key)

    summarized_community_ids = {_community_key(row) for row in summaries if _community_key(row)}
    summary_with_evidence = [summary for summary in summaries if _summary_has_evidence(summary)]
    summary_with_evidence_ids = {_community_key(summary) for summary in summary_with_evidence if _community_key(summary)}

    isolated_nodes: list[str] = []
    ignored_isolated_nodes: list[str] = []
    ignored_isolated_noise_nodes: list[str] = []
    ignored_isolated_summary_covered_nodes: list[str] = []
    ignored_isolated_node_ids: set[int] = set()
    for node_id, node in node_rows_by_id.items():
        if node_id in endpoint_node_ids:
            continue
        node_name = _node_display_name(node)
        is_noise_node = _is_noise_isolated_node(node)
        has_evidenced_summary = bool(node_community_keys.get(node_id, set()) & summary_with_evidence_ids)
        if is_noise_node or has_evidenced_summary:
            ignored_isolated_node_ids.add(node_id)
            ignored_isolated_nodes.append(node_name)
            if is_noise_node:
                ignored_isolated_noise_nodes.append(node_name)
            if has_evidenced_summary:
                ignored_isolated_summary_covered_nodes.append(node_name)
            continue
        isolated_nodes.append(node_name)

    quality_node_ids = set(node_rows_by_id) - ignored_isolated_node_ids
    quality_node_count = len(quality_node_ids)
    assigned_quality_node_ids = assigned_node_ids & quality_node_ids

    sentence_stats = [_summary_sentence_evidence_stats(summary) for summary in summaries]
    summary_sentence_count = sum(total for total, _bound in sentence_stats)
    summary_bound_sentence_count = sum(bound for _total, bound in sentence_stats)
    summaries_with_unbound_sentences = [
        str(summary.get("community_id"))
        for summary, (total, bound) in zip(summaries, sentence_stats, strict=False)
        if total > bound
    ]
    sentence_source_stats = [_summary_sentence_source_stats(summary) for summary in summaries]
    summary_sourced_sentence_count = sum(sourced for _total, sourced in sentence_source_stats)
    summaries_with_missing_sentence_sources = [
        str(summary.get("community_id"))
        for summary, (total, sourced) in zip(summaries, sentence_source_stats, strict=False)
        if total > sourced
    ]

    metrics: dict[str, float | int | None] = {
        "node_count": node_count,
        "quality_node_count": quality_node_count,
        "edge_count": edge_count,
        "evidence_count": len(evidence_rows),
        "evidence_coverage": _rate(edge_count - len(missing_evidence_edges), edge_count),
        "missing_evidence_edge_count": len(missing_evidence_edges),
        "low_confidence_edge_count": len(low_confidence_edges),
        "low_confidence_edge_rate": _rate(len(low_confidence_edges), edge_count),
        "ignored_isolated_node_count": len(ignored_isolated_nodes),
        "ignored_isolated_noise_node_count": len(ignored_isolated_noise_nodes),
        "ignored_isolated_summary_covered_node_count": len(ignored_isolated_summary_covered_nodes),
        "isolated_node_count": len(isolated_nodes),
        "isolated_node_rate": _rate(len(isolated_nodes), quality_node_count),
        "community_count": len(community_ids),
        "community_assignment_coverage": _rate(len(assigned_quality_node_ids), quality_node_count),
        "community_summary_count": len(summarized_community_ids),
        "community_summary_coverage": _rate(len(community_ids & summarized_community_ids), len(community_ids)),
        "summary_evidence_coverage": _rate(len(summary_with_evidence), len(summaries)),
        "summary_sentence_count": summary_sentence_count,
        "summary_bound_sentence_count": summary_bound_sentence_count,
        "summary_sentence_evidence_coverage": _rate(summary_bound_sentence_count, summary_sentence_count),
        "summary_sourced_sentence_count": summary_sourced_sentence_count,
        "summary_sentence_source_coverage": _rate(summary_sourced_sentence_count, summary_sentence_count),
    }
    details = {
        "missing_evidence_edges": missing_evidence_edges,
        "low_confidence_edges": low_confidence_edges,
        "isolated_nodes": isolated_nodes,
        "ignored_isolated_nodes": ignored_isolated_nodes,
        "ignored_isolated_noise_nodes": ignored_isolated_noise_nodes,
        "ignored_isolated_summary_covered_nodes": ignored_isolated_summary_covered_nodes,
        "communities_without_summaries": sorted(community_ids - summarized_community_ids),
        "summaries_without_evidence": [
            str(summary.get("community_id"))
            for summary in summaries
            if not _summary_has_evidence(summary)
        ],
        "summaries_with_unbound_sentences": summaries_with_unbound_sentences,
        "summaries_with_missing_sentence_sources": summaries_with_missing_sentence_sources,
    }
    return GraphQualityReport(
        metrics=metrics,
        gate_failures=_check_gate(metrics, thresholds),
        details=details,
    )


def _export_graph(graph_store_or_export: Any) -> dict[str, Any]:
    if isinstance(graph_store_or_export, dict):
        return graph_store_or_export
    export_graph = getattr(graph_store_or_export, "export_graph", None)
    if callable(export_graph):
        return export_graph()
    raise TypeError("Expected a GraphStore-like object with export_graph() or an exported graph dict.")


def _check_gate(metrics: dict[str, float | int | None], thresholds: GraphQualityThresholds) -> list[dict[str, Any]]:
    checks = [
        ("evidence_coverage", ">=", thresholds.min_evidence_coverage),
        ("low_confidence_edge_rate", "<=", 0.0),
        ("isolated_node_rate", "<=", thresholds.max_isolated_node_rate),
        ("community_assignment_coverage", ">=", thresholds.min_community_assignment_coverage),
        ("community_summary_coverage", ">=", thresholds.min_community_summary_coverage),
        ("summary_evidence_coverage", ">=", thresholds.min_summary_evidence_coverage),
        (
            "summary_sentence_evidence_coverage",
            ">=",
            thresholds.min_summary_sentence_evidence_coverage,
        ),
        (
            "summary_sentence_source_coverage",
            ">=",
            thresholds.min_summary_sentence_source_coverage,
        ),
    ]
    failures: list[dict[str, Any]] = []
    for metric, operator, threshold in checks:
        actual = metrics.get(metric)
        if actual is None:
            continue
        actual_float = float(actual)
        failed = actual_float < threshold if operator == ">=" else actual_float > threshold
        if failed:
            failures.append(
                {
                    "metric": metric,
                    "operator": operator,
                    "threshold": threshold,
                    "actual": round(actual_float, 6),
                }
            )
    return failures


def _rate(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _confidence(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _node_display_name(node: dict[str, Any]) -> str:
    return str(node.get("name") or node.get("label") or node.get("id") or "").strip()


_NOISE_NODE_NAMES = {
    "none",
    "null",
    "undefined",
    "nan",
    "qlogo",
    "setting",
    "settings",
    "sayhello",
}
_NOISE_FILE_EXTENSION_NAMES = {
    "csv",
    "doc",
    "docx",
    "gif",
    "jpeg",
    "jpg",
    "json",
    "md",
    "mp3",
    "mp4",
    "pdf",
    "png",
    "ppt",
    "pptx",
    "txt",
    "wav",
    "xls",
    "xlsx",
    "zip",
}
_NOISE_NODE_TYPES = {
    "asset",
    "attachment",
    "emoji",
    "file_extension",
    "image",
    "metadata",
    "metadata_noise",
    "noise",
    "ocr_noise",
    "system",
}
_DIMENSION_RE = re.compile(r"^\d{2,5}x\d{2,5}$", re.IGNORECASE)


def _is_noise_isolated_node(node: dict[str, Any]) -> bool:
    name = _node_display_name(node).strip().lower()
    node_type = str(node.get("type") or "").strip().lower()
    if not name:
        return True
    if name in _NOISE_NODE_NAMES or name in _NOISE_FILE_EXTENSION_NAMES:
        return True
    if _DIMENSION_RE.match(name):
        return True
    return node_type in _NOISE_NODE_TYPES


def _community_key(row: dict[str, Any]) -> str:
    community_id = str(row.get("community_id") or "").strip()
    if not community_id:
        return ""
    return f"{row.get('level', 0)}:{community_id}"


def _summary_has_evidence(summary: dict[str, Any]) -> bool:
    metadata = summary.get("metadata")
    if not isinstance(metadata, dict):
        return False
    return _metadata_has_evidence(metadata)


def _metadata_has_evidence(metadata: dict[str, Any]) -> bool:
    for key in (
        "evidence_triple_ids",
        "source_triple_ids",
        "source_edge_ids",
        "citation_ids",
        "citations",
        "evidence",
    ):
        value = metadata.get(key)
        if isinstance(value, list | tuple | set) and any(str(item).strip() for item in value):
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def _summary_sentence_evidence_stats(summary: dict[str, Any]) -> tuple[int, int]:
    sentences = _summary_sentences(str(summary.get("summary") or ""))
    total = len(sentences)
    if total == 0:
        return 0, 0

    metadata = summary.get("metadata")
    if total == 1 and isinstance(metadata, dict) and _metadata_has_evidence(metadata):
        return total, 1

    bindings = _summary_sentence_bindings(metadata)
    bound_indexes: set[int] = set()
    sequential_index = 0
    for binding in bindings:
        if not _binding_has_evidence(binding):
            sequential_index += 1
            continue
        if isinstance(binding, dict) and binding.get("sentence_index") is not None:
            try:
                index = int(binding["sentence_index"])
            except (TypeError, ValueError):
                index = sequential_index
        else:
            index = sequential_index
        if 0 <= index < total:
            bound_indexes.add(index)
        sequential_index += 1
    return total, len(bound_indexes)


def _summary_sentence_source_stats(summary: dict[str, Any]) -> tuple[int, int]:
    sentences = _summary_sentences(str(summary.get("summary") or ""))
    total = len(sentences)
    if total == 0:
        return 0, 0

    bindings = _summary_sentence_bindings(summary.get("metadata"))
    sourced_indexes: set[int] = set()
    sequential_index = 0
    for binding in bindings:
        if not _binding_has_source_evidence(binding):
            sequential_index += 1
            continue
        if isinstance(binding, dict) and binding.get("sentence_index") is not None:
            try:
                index = int(binding["sentence_index"])
            except (TypeError, ValueError):
                index = sequential_index
        else:
            index = sequential_index
        if 0 <= index < total:
            sourced_indexes.add(index)
        sequential_index += 1
    return total, len(sourced_indexes)


def _summary_sentences(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    punctuated = [
        match.group(0).strip()
        for match in re.finditer(r"[^.!?。！？\n]+[.!?。！？]", stripped)
        if match.group(0).strip()
    ]
    if punctuated:
        return punctuated
    return [line.strip("- \t") for line in stripped.splitlines() if line.strip("- \t")]


def _summary_sentence_bindings(metadata: Any) -> list[Any]:
    if not isinstance(metadata, dict):
        return []
    for key in ("sentence_evidence", "sentence_evidence_bindings", "sentence_citations"):
        value = metadata.get(key)
        if isinstance(value, list):
            return value
    return []


def _binding_has_evidence(binding: Any) -> bool:
    if isinstance(binding, dict):
        return _metadata_has_evidence(binding)
    if isinstance(binding, list | tuple | set):
        return any(str(item).strip() for item in binding)
    return isinstance(binding, str) and bool(binding.strip())


def _binding_has_source_evidence(binding: Any) -> bool:
    if isinstance(binding, dict):
        for key in ("source_evidence", "source_spans", "evidence_sources", "sources"):
            value = binding.get(key)
            if isinstance(value, list) and any(_source_entry_has_span(item) for item in value):
                return True
        return _source_entry_has_span(binding)
    if isinstance(binding, list | tuple | set):
        return any(_source_entry_has_span(item) for item in binding)
    return False


def _source_entry_has_span(entry: Any) -> bool:
    if isinstance(entry, dict):
        return bool(str(entry.get("text") or entry.get("evidence") or entry.get("quote") or "").strip())
    return isinstance(entry, str) and bool(entry.strip())
