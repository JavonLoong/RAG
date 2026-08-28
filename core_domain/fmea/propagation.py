from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from .errors import FmeaDomainError
from .states import ClaimStatus, EvidenceSupportStatus, PropagationStatus, PublicationStatus, ReviewStatus
from .value_objects import EvidencePack


class PropagationRelation(str, Enum):
    PROPAGATION = "propagation"
    COMMON_CAUSE = "common_cause"
    DEPENDENCY = "dependency"
    FEEDBACK = "feedback"


RISK_PRIORITIES = frozenset({"normal", "medium", "high", "critical"})
AUTO_ACCEPT_RISK_PRIORITIES = frozenset({"normal", "medium"})


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FmeaDomainError(f"{field_name} must not be empty")  # noqa: TRY003
    return value.strip()


def _strings(value: Iterable[object], field_name: str) -> tuple[str, ...]:
    if isinstance(value, str | bytes):
        raise FmeaDomainError(f"{field_name} must be a sequence")  # noqa: TRY003
    try:
        result = tuple(value)
    except TypeError as exc:
        raise FmeaDomainError(f"{field_name} must be a sequence") from exc  # noqa: TRY003
    if any(not isinstance(item, str) or not item.strip() for item in result):
        raise FmeaDomainError(f"{field_name} must contain non-empty strings")  # noqa: TRY003
    normalized = tuple(item.strip() for item in result)
    if len(normalized) != len(set(normalized)):
        raise FmeaDomainError(f"{field_name} must not contain duplicates")  # noqa: TRY003
    return normalized


def _positive_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise FmeaDomainError(f"{field_name} must be a positive integer")  # noqa: TRY003
    return value


def _non_negative_timing(value: object, field_name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
        raise FmeaDomainError(f"timing value {field_name} must be non-negative")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class TopologyNode:
    node_id: str
    node_type: str
    operating_modes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _text(self.node_id, "node_id"))
        object.__setattr__(self, "node_type", _text(self.node_type, "node_type"))
        object.__setattr__(self, "operating_modes", _strings(self.operating_modes, "node operating_modes"))


@dataclass(frozen=True, slots=True)
class TopologyInterface:
    interface_id: str
    source_node_id: str
    target_node_id: str
    interface_variable: str
    unit: str
    direction: str
    operating_modes: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "interface_id",
            "source_node_id",
            "target_node_id",
            "interface_variable",
            "unit",
            "direction",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        object.__setattr__(self, "operating_modes", _strings(self.operating_modes, "interface operating_modes"))

    @property
    def variable(self) -> str:
        """Compatibility spelling for topology adapters."""

        return self.interface_variable


@dataclass(frozen=True, slots=True)
class TopologySnapshot:
    topology_snapshot_id: str
    workspace_id: str
    analysis_id: str | None
    topology_hash: str
    nodes: tuple[TopologyNode, ...]
    interfaces: tuple[TopologyInterface, ...]
    record_version: int = 1
    created_at: str = ""

    def __post_init__(self) -> None:
        for field_name in ("topology_snapshot_id", "workspace_id", "topology_hash"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        if self.analysis_id is not None:
            object.__setattr__(self, "analysis_id", _text(self.analysis_id, "analysis_id"))
        nodes = tuple(self.nodes)
        interfaces = tuple(self.interfaces)
        if any(not isinstance(item, TopologyNode) for item in nodes):
            raise FmeaDomainError("topology nodes must contain TopologyNode objects")  # noqa: TRY003
        if any(not isinstance(item, TopologyInterface) for item in interfaces):
            raise FmeaDomainError("topology interfaces must contain TopologyInterface objects")  # noqa: TRY003
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "interfaces", interfaces)
        object.__setattr__(self, "record_version", _positive_integer(self.record_version, "record_version"))
        if self.created_at:
            object.__setattr__(self, "created_at", _text(self.created_at, "created_at"))


@dataclass(frozen=True, slots=True)
class PropagationRulePack:
    rule_pack_id: str
    version: str
    applicable_analysis_types: tuple[str, ...]
    relation_types: tuple[str, ...]
    interface_variables: tuple[str, ...]
    units: tuple[str, ...]
    directions: tuple[str, ...]
    max_automatic_depth: int = 2
    mandatory_review_conditions: tuple[str, ...] = (
        "long_path",
        "cyclic",
        "high_risk",
        "external",
        "evidence_gap",
    )
    barrier_semantics: str = "explicit_barriers"
    risk_escalation: str = "high_and_critical_require_review"
    prohibit_silent_fallback: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_pack_id", _text(self.rule_pack_id, "rule_pack_id"))
        object.__setattr__(self, "version", _text(self.version, "rule_pack_version"))
        for field_name in (
            "applicable_analysis_types",
            "relation_types",
            "interface_variables",
            "units",
            "directions",
            "mandatory_review_conditions",
        ):
            object.__setattr__(self, field_name, _strings(getattr(self, field_name), field_name))
        object.__setattr__(
            self,
            "max_automatic_depth",
            _positive_integer(self.max_automatic_depth, "max_automatic_depth"),
        )
        object.__setattr__(self, "barrier_semantics", _text(self.barrier_semantics, "barrier_semantics"))
        object.__setattr__(self, "risk_escalation", _text(self.risk_escalation, "risk_escalation"))
        if not isinstance(self.prohibit_silent_fallback, bool):
            raise FmeaDomainError("prohibit_silent_fallback must be a boolean")  # noqa: TRY003

        supported = {item.value for item in PropagationRelation}
        if not set(self.relation_types).issubset(supported):
            raise FmeaDomainError("rule pack relation_types contains an unsupported relation")  # noqa: TRY003

    @property
    def allowed_relation_types(self) -> tuple[str, ...]:
        return self.relation_types

    @property
    def allowed_interface_variables(self) -> tuple[str, ...]:
        return self.interface_variables

    @property
    def allowed_units(self) -> tuple[str, ...]:
        return self.units

    @property
    def automatic_search_depth(self) -> int:
        return self.max_automatic_depth


@dataclass(frozen=True, slots=True)
class PropagationEdge:
    edge_id: str
    analysis_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    interface_variable: str
    unit: str
    direction: str
    threshold: str | None
    operating_modes: tuple[str, ...]
    delay_ms: int | None
    response_time_ms: int | None
    fault_tolerance_time_ms: int | None
    barrier_ids: tuple[str, ...]
    evidence_pack_id: str
    evidence_ids: tuple[str, ...]
    evidence_support: EvidenceSupportStatus
    claim_status: ClaimStatus
    review_status: ReviewStatus
    publication_status: PublicationStatus
    path_length: int
    is_cyclic: bool
    is_unprocessed: bool
    is_external: bool
    is_terminal: bool
    risk_priority: str | None
    record_version: int = 1

    @property
    def inferred(self) -> bool:
        return self.path_length > 2

    @property
    def auto_accept_allowed(self) -> bool:
        return (
            self.path_length in {1, 2}
            and not self.is_cyclic
            and not self.is_unprocessed
            and not self.is_external
            and bool(self.evidence_ids)
            and self.evidence_support
            in {
                EvidenceSupportStatus.SUPPORTED,
                EvidenceSupportStatus.PARTIALLY_SUPPORTED,
            }
            and self.claim_status is ClaimStatus.KNOWN
            and self.risk_priority in AUTO_ACCEPT_RISK_PRIORITIES
        )


def validate_propagation_edge(edge: PropagationEdge, pack: EvidencePack | None) -> None:
    from .policies import validate_propagation_edge as validate_edge

    validate_edge(edge, pack)


@dataclass(frozen=True, slots=True)
class PropagationPath:
    path_id: str
    analysis_id: str
    source_entity_id: str
    target_entity_id: str
    edges: tuple[PropagationEdge, ...]
    path_length: int
    is_cyclic: bool
    requires_human_review: bool

    def __post_init__(self) -> None:
        for field_name in ("path_id", "analysis_id", "source_entity_id", "target_entity_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        edges = tuple(self.edges)
        if not edges or any(not isinstance(item, PropagationEdge) for item in edges):
            raise FmeaDomainError("path edges must contain at least one PropagationEdge")  # noqa: TRY003
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "path_length", _positive_integer(self.path_length, "path_length"))
        if not isinstance(self.is_cyclic, bool):
            raise FmeaDomainError("is_cyclic must be a boolean")  # noqa: TRY003
        if not isinstance(self.requires_human_review, bool):
            raise FmeaDomainError("requires_human_review must be a boolean")  # noqa: TRY003
        requires_review = (
            self.path_length > 2
            or self.is_cyclic
            or any(
                edge.is_cyclic or edge.is_unprocessed or edge.is_external or not edge.auto_accept_allowed
                for edge in edges
            )
        )
        object.__setattr__(self, "requires_human_review", self.requires_human_review or requires_review)


@dataclass(frozen=True, slots=True)
class PropagationGraphRevision:
    graph_revision_id: str
    workspace_id: str
    analysis_id: str
    analysis_record_version: int
    topology_snapshot_id: str
    topology_hash: str
    evidence_pack_ids: tuple[str, ...]
    domain_pack_id: str
    domain_pack_version: str
    rule_pack_id: str
    rule_pack_version: str
    status: PropagationStatus
    assistance_suggestion_ids: tuple[str, ...]
    nodes: tuple[TopologyNode, ...]
    edges: tuple[PropagationEdge, ...]
    paths: tuple[PropagationPath, ...]
    unresolved_issue_codes: tuple[str, ...]
    parent_graph_revision_id: str | None
    record_version: int
    created_at: str

    def __post_init__(self) -> None:
        for field_name in (
            "graph_revision_id",
            "workspace_id",
            "analysis_id",
            "topology_snapshot_id",
            "topology_hash",
            "domain_pack_id",
            "domain_pack_version",
            "rule_pack_id",
            "rule_pack_version",
            "created_at",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        object.__setattr__(
            self, "analysis_record_version", _positive_integer(self.analysis_record_version, "analysis_record_version")
        )
        object.__setattr__(self, "record_version", _positive_integer(self.record_version, "record_version"))
        if not isinstance(self.status, PropagationStatus):
            raise FmeaDomainError("status must be a PropagationStatus")  # noqa: TRY003
        for field_name in ("evidence_pack_ids", "assistance_suggestion_ids", "unresolved_issue_codes"):
            object.__setattr__(self, field_name, _strings(getattr(self, field_name), field_name))
        nodes = tuple(self.nodes)
        edges = tuple(self.edges)
        paths = tuple(self.paths)
        if any(not isinstance(item, TopologyNode) for item in nodes):
            raise FmeaDomainError("graph nodes must contain TopologyNode objects")  # noqa: TRY003
        if any(not isinstance(item, PropagationEdge) for item in edges):
            raise FmeaDomainError("graph edges must contain PropagationEdge objects")  # noqa: TRY003
        if any(not isinstance(item, PropagationPath) for item in paths):
            raise FmeaDomainError("graph paths must contain PropagationPath objects")  # noqa: TRY003
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "paths", paths)
        if self.parent_graph_revision_id is not None:
            object.__setattr__(
                self, "parent_graph_revision_id", _text(self.parent_graph_revision_id, "parent_graph_revision_id")
            )


def _require_unique(items: Iterable[str], field_name: str) -> None:
    values = tuple(items)
    if len(values) != len(set(values)):
        raise FmeaDomainError(f"{field_name} must contain unique IDs")  # noqa: TRY003


def validate_topology_snapshot(topology: TopologySnapshot) -> None:
    if not isinstance(topology, TopologySnapshot):
        raise FmeaDomainError("topology snapshot is invalid")  # noqa: TRY003
    node_ids = tuple(node.node_id for node in topology.nodes)
    interface_ids = tuple(item.interface_id for item in topology.interfaces)
    _require_unique(node_ids, "topology node IDs")
    _require_unique(interface_ids, "topology interface IDs")
    node_set = set(node_ids)
    for item in topology.interfaces:
        if item.source_node_id not in node_set or item.target_node_id not in node_set:
            raise FmeaDomainError("topology interface endpoint is outside topology")  # noqa: TRY003


def validate_propagation_rule_pack(rule_pack: PropagationRulePack) -> None:
    if not isinstance(rule_pack, PropagationRulePack):
        raise FmeaDomainError("propagation rule pack is invalid")  # noqa: TRY003
    if not rule_pack.relation_types:
        raise FmeaDomainError("rule pack relation_types must not be empty")  # noqa: TRY003
    if not rule_pack.interface_variables:
        raise FmeaDomainError("rule pack interface_variables must not be empty")  # noqa: TRY003
    if not rule_pack.units:
        raise FmeaDomainError("rule pack units must not be empty")  # noqa: TRY003
    if not rule_pack.directions:
        raise FmeaDomainError("rule pack directions must not be empty")  # noqa: TRY003
    if rule_pack.prohibit_silent_fallback is not True:
        raise FmeaDomainError("rule pack must prohibit silent fallback")  # noqa: TRY003


def _validate_edge_timing(edge: PropagationEdge) -> None:
    for field_name in ("delay_ms", "response_time_ms", "fault_tolerance_time_ms"):
        _non_negative_timing(getattr(edge, field_name), field_name)


def _validate_edge_against_topology(
    edge: PropagationEdge,
    topology: TopologySnapshot,
    rule_pack: PropagationRulePack,
) -> None:
    validate_propagation_edge(edge, None)
    _validate_edge_timing(edge)
    topology_node_ids = {node.node_id for node in topology.nodes}
    if edge.source_entity_id not in topology_node_ids or edge.target_entity_id not in topology_node_ids:
        raise FmeaDomainError("edge endpoint is outside topology")  # noqa: TRY003
    if edge.relation_type not in rule_pack.relation_types:
        raise FmeaDomainError("edge relation_type is not supported by rule pack")  # noqa: TRY003
    if edge.interface_variable not in rule_pack.interface_variables:
        raise FmeaDomainError("edge interface_variable is not supported by rule pack")  # noqa: TRY003
    if edge.unit not in rule_pack.units:
        raise FmeaDomainError("edge unit is not supported by rule pack")  # noqa: TRY003
    if edge.direction not in rule_pack.directions:
        raise FmeaDomainError("edge direction is not supported by rule pack")  # noqa: TRY003
    _validate_interface_compatibility(edge, topology)


def _validate_interface_compatibility(edge: PropagationEdge, topology: TopologySnapshot) -> None:
    nodes_by_id = {node.node_id: node for node in topology.nodes}
    for endpoint_id in (edge.source_entity_id, edge.target_entity_id):
        node = nodes_by_id[endpoint_id]
        if node.operating_modes and not set(edge.operating_modes).intersection(node.operating_modes):
            raise FmeaDomainError("edge operating mode has no endpoint node intersection")  # noqa: TRY003
    matching_endpoints = tuple(
        item
        for item in topology.interfaces
        if item.source_node_id == edge.source_entity_id and item.target_node_id == edge.target_entity_id
    )
    if not matching_endpoints:
        raise FmeaDomainError("edge interface_variable has no topology interface")  # noqa: TRY003
    matching_variable = tuple(item for item in matching_endpoints if item.interface_variable == edge.interface_variable)
    if not matching_variable:
        raise FmeaDomainError("edge interface_variable does not match topology")  # noqa: TRY003
    matching_unit = tuple(item for item in matching_variable if item.unit == edge.unit)
    if not matching_unit:
        raise FmeaDomainError("edge unit does not match topology interface")  # noqa: TRY003
    matching_direction = tuple(item for item in matching_unit if item.direction == edge.direction)
    if not matching_direction:
        raise FmeaDomainError("edge direction does not match topology interface")  # noqa: TRY003
    if not set(edge.operating_modes).intersection(*(set(item.operating_modes) for item in matching_direction)):
        raise FmeaDomainError("edge operating mode has no topology intersection")  # noqa: TRY003


def validate_path(
    path: PropagationPath,
    evidence_pack: EvidencePack | None,
    rule_pack: PropagationRulePack,
) -> None:
    if not isinstance(path, PropagationPath):
        raise FmeaDomainError("propagation path is invalid")  # noqa: TRY003
    validate_propagation_rule_pack(rule_pack)
    _validate_path_shape(path)
    _validate_path_edges(path, evidence_pack)
    _validate_path_cycle_flags(path)


def _validate_path_shape(path: PropagationPath) -> None:
    if path.path_length != len(path.edges):
        raise FmeaDomainError("path_length must equal the number of edges")  # noqa: TRY003
    if any(edge.analysis_id != path.analysis_id for edge in path.edges):
        raise FmeaDomainError("path edge analysis_id does not match path")  # noqa: TRY003
    if (
        path.edges[0].source_entity_id != path.source_entity_id
        or path.edges[-1].target_entity_id != path.target_entity_id
    ):
        raise FmeaDomainError("path endpoints do not match edge endpoints")  # noqa: TRY003
    for previous, current in zip(path.edges, path.edges[1:], strict=False):
        if previous.target_entity_id != current.source_entity_id:
            raise FmeaDomainError("path continuity is broken")  # noqa: TRY003


def _validate_path_edges(path: PropagationPath, evidence_pack: EvidencePack | None) -> None:
    pack_ids = None if evidence_pack is None else {ref.evidence_id for ref in evidence_pack.refs}
    for edge in path.edges:
        validate_propagation_edge(edge, evidence_pack)
        _validate_edge_timing(edge)
        if not edge.evidence_ids:
            raise FmeaDomainError("edge evidence is required for every path edge")  # noqa: TRY003
        if pack_ids is not None and not set(edge.evidence_ids).issubset(pack_ids):
            missing = next(item for item in edge.evidence_ids if item not in pack_ids)
            raise FmeaDomainError(f"edge evidence ID {missing} is absent from EvidencePack")  # noqa: TRY003
        if edge.path_length > path.path_length:
            raise FmeaDomainError("edge path_length exceeds path_length")  # noqa: TRY003


def _validate_path_cycle_flags(path: PropagationPath) -> None:
    visited: set[str] = set()
    repeated = False
    for edge in path.edges:
        if edge.source_entity_id in visited:
            repeated = True
        visited.add(edge.source_entity_id)
    if path.edges[-1].target_entity_id in visited:
        repeated = True
    flagged = any(edge.is_cyclic for edge in path.edges)
    if repeated and not path.is_cyclic:
        raise FmeaDomainError("cycle flag is missing from path")  # noqa: TRY003
    if path.is_cyclic and not (repeated or flagged):
        raise FmeaDomainError("cycle flag is not supported by path edges")  # noqa: TRY003
    if flagged and not path.is_cyclic:
        raise FmeaDomainError("cycle flag is inconsistent with path edges")  # noqa: TRY003


def validate_graph_revision(
    graph_revision: PropagationGraphRevision,
    topology: TopologySnapshot,
    rule_pack: PropagationRulePack,
) -> None:
    if not isinstance(graph_revision, PropagationGraphRevision):
        raise FmeaDomainError("propagation graph revision is invalid")  # noqa: TRY003
    validate_topology_snapshot(topology)
    validate_propagation_rule_pack(rule_pack)
    _validate_graph_bindings(graph_revision, topology, rule_pack)
    _validate_graph_collections(graph_revision)
    topology_node_ids = {node.node_id for node in topology.nodes}
    for node in graph_revision.nodes:
        if node.node_id not in topology_node_ids:
            raise FmeaDomainError("graph node is outside topology")  # noqa: TRY003
    graph_edge_ids = {edge.edge_id for edge in graph_revision.edges}
    for edge in graph_revision.edges:
        _validate_graph_edge(edge, graph_revision, topology, rule_pack)
    for path in graph_revision.paths:
        _validate_graph_path(path, graph_revision, graph_edge_ids, rule_pack)


def _validate_graph_bindings(
    graph_revision: PropagationGraphRevision,
    topology: TopologySnapshot,
    rule_pack: PropagationRulePack,
) -> None:
    if graph_revision.workspace_id != topology.workspace_id:
        raise FmeaDomainError("graph workspace_id does not match topology")  # noqa: TRY003
    if topology.analysis_id is not None and graph_revision.analysis_id != topology.analysis_id:
        raise FmeaDomainError("graph analysis_id does not match topology")  # noqa: TRY003
    if graph_revision.topology_snapshot_id != topology.topology_snapshot_id:
        raise FmeaDomainError("graph topology_snapshot_id does not match topology")  # noqa: TRY003
    if graph_revision.topology_hash != topology.topology_hash:
        raise FmeaDomainError("graph topology_hash does not match topology")  # noqa: TRY003
    if graph_revision.rule_pack_id != rule_pack.rule_pack_id or graph_revision.rule_pack_version != rule_pack.version:
        raise FmeaDomainError("graph rule pack identity does not match rule pack")  # noqa: TRY003


def _validate_graph_collections(graph_revision: PropagationGraphRevision) -> None:
    _require_unique((node.node_id for node in graph_revision.nodes), "graph node IDs")
    _require_unique((edge.edge_id for edge in graph_revision.edges), "graph edge IDs")
    _require_unique((path.path_id for path in graph_revision.paths), "graph path IDs")
    _require_unique(graph_revision.evidence_pack_ids, "graph evidence_pack_ids")
    _require_unique(graph_revision.assistance_suggestion_ids, "assistance_suggestion_ids")
    _require_unique(graph_revision.unresolved_issue_codes, "unresolved_issue_codes")


def _validate_graph_edge(
    edge: PropagationEdge,
    graph_revision: PropagationGraphRevision,
    topology: TopologySnapshot,
    rule_pack: PropagationRulePack,
) -> None:
    if edge.analysis_id != graph_revision.analysis_id:
        raise FmeaDomainError("edge analysis_id does not match graph")  # noqa: TRY003
    if edge.evidence_pack_id not in graph_revision.evidence_pack_ids:
        raise FmeaDomainError("edge evidence_pack_id is not bound to graph")  # noqa: TRY003
    _validate_edge_against_topology(edge, topology, rule_pack)
    if not edge.evidence_ids:
        raise FmeaDomainError("edge evidence is required for every graph edge")  # noqa: TRY003
    if graph_revision.status is PropagationStatus.CONFIRMED and edge.review_status is not ReviewStatus.ACCEPTED:
        raise FmeaDomainError("confirmed graph requires human review of every edge")  # noqa: TRY003


def _validate_graph_path(
    path: PropagationPath,
    graph_revision: PropagationGraphRevision,
    graph_edge_ids: set[str],
    rule_pack: PropagationRulePack,
) -> None:
    if path.analysis_id != graph_revision.analysis_id:
        raise FmeaDomainError("path analysis_id does not match graph")  # noqa: TRY003
    if any(edge.edge_id not in graph_edge_ids for edge in path.edges):
        raise FmeaDomainError("path references a graph edge outside the graph revision")  # noqa: TRY003
    validate_path(path, None, rule_pack)
