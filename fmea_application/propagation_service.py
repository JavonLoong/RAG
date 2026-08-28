"""Bounded, proposal-only FMEA propagation analysis."""

# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from core_domain.fmea.domain_pack import DomainPackManifest
from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.propagation import (
    LOCKED_AUTOMATIC_DEPTH,
    PropagationEdge,
    PropagationEvidenceResolution,
    PropagationGraphRevision,
    PropagationPath,
    PropagationRulePack,
    TopologyInterface,
    TopologySnapshot,
    validate_graph_revision,
    validate_propagation_rule_pack,
    validate_topology_snapshot,
)
from core_domain.fmea.scoring import RiskAssessmentRecord
from core_domain.fmea.states import (
    ClaimStatus,
    EvidenceSupportStatus,
    PropagationStatus,
    PublicationStatus,
    ReviewStatus,
    RiskStatus,
    RunStatus,
)
from core_domain.fmea.value_objects import EvidencePack

from .assistance_contracts import AssistanceKind, AssistanceSuggestion
from .assistance_service import make_audit, stable_id, utc_now
from .ports import AssistanceRepository, RiskRepository
from .review_contracts import ActorContext, IdempotencyScope, idempotency_key_hash
from .risk_contracts import PreparedAssistanceSuggestion, assistance_suggestion_payload_hash

_MAX_MODEL_EVIDENCE_REFS = 20
PROPAGATION_TEMPLATE_ID = "fmea-propagation-hypothesis"
PROPAGATION_TEMPLATE_VERSION = "1.0.0"


class PropagationError(ValueError):
    """Safe, transport-neutral error for a propagation proposal boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class StartPropagationCommand:
    analysis_id: str
    expected_analysis_record_version: int
    source_row_ids: tuple[str, ...]
    evidence_pack_id: str
    topology_id: str
    topology_version: str
    domain_pack_id: str
    domain_pack_version: str
    rule_pack_id: str
    rule_pack_version: str
    idempotency_key: str
    max_depth: int = LOCKED_AUTOMATIC_DEPTH
    max_edges: int = 40
    require_confirmed_risk: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "analysis_id",
            "evidence_pack_id",
            "topology_id",
            "topology_version",
            "domain_pack_id",
            "domain_pack_version",
            "rule_pack_id",
            "rule_pack_version",
            "idempotency_key",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if not isinstance(self.expected_analysis_record_version, int):
            raise TypeError("expected_analysis_record_version must be an integer")
        if isinstance(self.expected_analysis_record_version, bool) or self.expected_analysis_record_version < 1:
            raise ValueError("expected_analysis_record_version must be positive")
        object.__setattr__(self, "source_row_ids", tuple(self.source_row_ids))
        if not self.source_row_ids or any(
            not isinstance(item, str) or not item.strip() for item in self.source_row_ids
        ):
            raise ValueError("source_row_ids must contain non-empty IDs")
        if len(set(self.source_row_ids)) != len(self.source_row_ids):
            raise ValueError("source_row_ids must be unique")
        if not isinstance(self.max_depth, int) or isinstance(self.max_depth, bool):
            raise TypeError("max_depth must be an integer")
        if not isinstance(self.max_edges, int) or isinstance(self.max_edges, bool):
            raise TypeError("max_edges must be an integer")
        if not isinstance(self.require_confirmed_risk, bool):
            raise TypeError("require_confirmed_risk must be a boolean")


@dataclass(frozen=True, slots=True)
class PropagationCandidateInterface:
    """One server-enumerated topology interface available to the model."""

    interface_id: str
    source_node_id: str
    target_node_id: str
    interface_variable: str
    unit: str
    direction: str
    operating_modes: tuple[str, ...]
    path_length: int


@dataclass(frozen=True, slots=True)
class PropagationModelRequest:
    run_id: str
    analysis: FmeaAnalysis
    source_rows: tuple[FmeaRow, ...]
    evidence_pack: EvidencePack
    topology: TopologySnapshot
    domain_pack: DomainPackManifest
    rule_pack: PropagationRulePack
    candidate_interfaces: tuple[PropagationCandidateInterface, ...]
    candidate_endpoint_ids: tuple[str, ...]
    candidate_evidence_ids: tuple[str, ...]
    allowed_relation_types: tuple[str, ...]
    max_depth: int
    max_edges: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_rows", tuple(self.source_rows))
        object.__setattr__(self, "candidate_interfaces", tuple(self.candidate_interfaces))
        object.__setattr__(self, "candidate_endpoint_ids", tuple(sorted(set(self.candidate_endpoint_ids))))
        object.__setattr__(self, "candidate_evidence_ids", tuple(sorted(set(self.candidate_evidence_ids))))
        object.__setattr__(self, "allowed_relation_types", tuple(sorted(set(self.allowed_relation_types))))
        if self.max_depth != LOCKED_AUTOMATIC_DEPTH:
            raise PropagationError(
                "FMEA_PROPAGATION_DEPTH_INVALID",
                "propagation automatic depth is locked to exactly two hops",
            )
        if not 1 <= self.max_edges <= 40:
            raise PropagationError(
                "FMEA_PROPAGATION_BUDGET_INVALID",
                "propagation edge budget must be between one and forty",
            )


PropagationEdgeProposal = Mapping[str, object]

PROPAGATION_EDGE_PROPOSAL_KEYS = frozenset({
    "interface_id",
    "source_entity_id",
    "target_entity_id",
    "relation_type",
    "interface_variable",
    "unit",
    "direction",
    "threshold",
    "operating_modes",
    "delay_ms",
    "response_time_ms",
    "fault_tolerance_time_ms",
    "barrier_ids",
    "evidence_ids",
    "evidence_support",
    "claim_status",
    "path_length",
    "is_cyclic",
    "is_unprocessed",
    "is_external",
    "is_terminal",
    "risk_priority",
})


class PropagationSuggestionGenerator(Protocol):
    def generate(
        self, request: PropagationModelRequest
    ) -> AssistanceSuggestion[tuple[PropagationEdgeProposal, ...]]: ...


@dataclass(frozen=True, slots=True)
class PropagationRun:
    run_id: str
    workspace_id: str
    analysis_id: str
    status: RunStatus
    graph: PropagationGraphRevision | None
    error_code: str | None
    error_message: str | None
    assistance_suggestion_ids: tuple[str, ...]
    created_at: str
    updated_at: str
    record_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "assistance_suggestion_ids", tuple(self.assistance_suggestion_ids))


@dataclass(frozen=True, slots=True)
class PreparedPropagationProposal:
    run: PropagationRun
    graph: PropagationGraphRevision
    suggestion: AssistanceSuggestion[object]
    assistance: PreparedAssistanceSuggestion
    topology: TopologySnapshot
    rule_pack: PropagationRulePack
    evidence_pack: EvidencePack
    source_row_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_row_ids", tuple(self.source_row_ids))


class PropagationRepository(Protocol):
    """Workspace-scoped reads; entities without workspace fields rely on this port boundary."""

    def get_analysis(self, analysis_id: str, workspace_id: str) -> FmeaAnalysis | None: ...

    def get_row(self, row_id: str, workspace_id: str) -> FmeaRow | None: ...

    def get_evidence_pack(self, pack_id: str, workspace_id: str) -> EvidencePack | None: ...

    def save_run_and_proposal(self, prepared: PreparedPropagationProposal) -> PropagationRun: ...

    def get_run(self, run_id: str, workspace_id: str) -> PropagationRun | None: ...

    def get_graph(self, analysis_id: str, workspace_id: str) -> PropagationGraphRevision | None: ...


def _failed_run(run_id: str, workspace_id: str, analysis_id: str, code: str, message: str, now: str) -> PropagationRun:
    return PropagationRun(
        run_id=run_id,
        workspace_id=workspace_id,
        analysis_id=analysis_id,
        status=RunStatus.FAILED,
        graph=None,
        error_code=code,
        error_message=message,
        assistance_suggestion_ids=(),
        created_at=now,
        updated_at=now,
    )


def _sorted_interface_key(interface: TopologyInterface) -> tuple[object, ...]:
    return (
        interface.interface_id,
        interface.source_node_id,
        interface.target_node_id,
        interface.interface_variable,
        interface.unit,
        interface.direction,
        interface.operating_modes,
    )


def find_propagation_candidate(
    candidate_interfaces: Sequence[PropagationCandidateInterface],
    proposal: Mapping[str, object],
) -> PropagationCandidateInterface | None:
    """Return the exact server-enumerated interface represented by a proposal."""

    interface_id = proposal.get("interface_id")
    path_length = proposal.get("path_length")
    source = proposal.get("source_entity_id")
    target = proposal.get("target_entity_id")
    variable = proposal.get("interface_variable")
    unit = proposal.get("unit")
    direction = proposal.get("direction")
    if (
        not all(isinstance(value, str) for value in (interface_id, source, target, variable, unit, direction))
        or not isinstance(path_length, int)
        or isinstance(path_length, bool)
    ):
        return None
    return next(
        (
            candidate
            for candidate in candidate_interfaces
            if candidate.interface_id == interface_id
            and candidate.path_length == path_length
            and candidate.source_node_id == source
            and candidate.target_node_id == target
            and candidate.interface_variable == variable
            and candidate.unit == unit
            and candidate.direction == direction
        ),
        None,
    )


class PropagationAnalysisService:
    """Enumerate a bounded topology closure, then persist model proposals only."""

    def __init__(
        self,
        repository: PropagationRepository,
        *,
        assistance_repository: AssistanceRepository,
        topology_port: Any,
        domain_pack_registry: Any,
        propagation_rule_registry: Any,
        generator: PropagationSuggestionGenerator,
        risk_repository: RiskRepository | None = None,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self._repository = repository
        self._assistance_repository = assistance_repository
        self._topology_port = topology_port
        self._domain_pack_registry = domain_pack_registry
        self._propagation_rule_registry = propagation_rule_registry
        self._generator = generator
        self._risk_repository = risk_repository
        self._clock = clock

    def _load_inputs(  # noqa: C901
        self, command: StartPropagationCommand, actor: ActorContext
    ) -> tuple[
        FmeaAnalysis, tuple[FmeaRow, ...], EvidencePack, DomainPackManifest, PropagationRulePack, TopologySnapshot
    ]:
        analysis = self._repository.get_analysis(command.analysis_id, actor.workspace_id)
        if not isinstance(analysis, FmeaAnalysis):
            raise PropagationError("FMEA_ANALYSIS_NOT_FOUND", "FMEA analysis was not found")
        if analysis.record_version != command.expected_analysis_record_version:
            raise PropagationError("FMEA_ANALYSIS_VERSION_CONFLICT", "FMEA analysis version is stale")

        rows: list[FmeaRow] = []
        for row_id in command.source_row_ids:
            row = self._repository.get_row(row_id, actor.workspace_id)
            if not isinstance(row, FmeaRow) or row.analysis_id != analysis.analysis_id:
                raise PropagationError("FMEA_ROW_NOT_FOUND", "an accepted FMEA source row was not found")
            if row.review_status is not ReviewStatus.ACCEPTED:
                raise PropagationError(
                    "FMEA_PROPAGATION_SOURCE_INVALID", "propagation sources must be accepted FMEA rows"
                )
            rows.append(row)

        evidence_pack = self._repository.get_evidence_pack(command.evidence_pack_id, actor.workspace_id)
        if not isinstance(evidence_pack, EvidencePack) or evidence_pack.workspace_id != actor.workspace_id:
            raise PropagationError("FMEA_EVIDENCE_INVALID", "the EvidencePack is unavailable for this workspace")
        if any(row.evidence_pack_id != evidence_pack.pack_id for row in rows):
            raise PropagationError("FMEA_EVIDENCE_INVALID", "source rows and EvidencePack are not bound")
        if command.require_confirmed_risk:
            if self._risk_repository is None:
                raise PropagationError("FMEA_PROPAGATION_RISK_INVALID", "a confirmed risk assessment is required")
            for row in rows:
                record = self._risk_repository.get_current_assessment(row.row_id, actor.workspace_id)
                if not isinstance(record, RiskAssessmentRecord) or (
                    record.workspace_id != actor.workspace_id
                    or record.row_id != row.row_id
                    or record.source_record_version != row.record_version
                    or record.evidence_pack_id != evidence_pack.pack_id
                    or record.status is not RiskStatus.CONFIRMED
                ):
                    raise PropagationError(
                        "FMEA_PROPAGATION_RISK_INVALID", "a confirmed risk assessment bound to the row is required"
                    )

        domain_pack = self._domain_pack_registry.get(command.domain_pack_id, command.domain_pack_version)
        rule_pack = self._propagation_rule_registry.get(command.rule_pack_id, command.rule_pack_version)
        if not isinstance(domain_pack, DomainPackManifest) or not isinstance(rule_pack, PropagationRulePack):
            raise PropagationError("FMEA_PROPAGATION_REGISTRY_INVALID", "propagation registry identity is invalid")
        if (
            analysis.analysis_type not in domain_pack.analysis_types
            or analysis.analysis_type not in rule_pack.applicable_analysis_types
        ):
            raise PropagationError(
                "FMEA_PROPAGATION_REGISTRY_INVALID", "propagation packs do not apply to this analysis"
            )
        if (PROPAGATION_TEMPLATE_ID, PROPAGATION_TEMPLATE_VERSION) not in domain_pack.template_identities:
            raise PropagationError(
                "FMEA_PROPAGATION_REGISTRY_INVALID", "domain pack does not authorize the propagation template"
            )
        if (rule_pack.rule_pack_id, rule_pack.version) not in domain_pack.propagation_rule_identities:
            raise PropagationError(
                "FMEA_PROPAGATION_REGISTRY_INVALID", "domain pack does not bind the propagation rule pack"
            )
        try:
            validate_propagation_rule_pack(rule_pack)
        except FmeaDomainError as exc:
            raise PropagationError("FMEA_PROPAGATION_REGISTRY_INVALID", "propagation rule pack is invalid") from exc

        topology = self._topology_port.load_snapshot(command.topology_id, command.topology_version)
        if not isinstance(topology, TopologySnapshot) or topology.workspace_id != actor.workspace_id:
            raise PropagationError("FMEA_PROPAGATION_TOPOLOGY_INVALID", "topology snapshot is invalid")
        if topology.analysis_id is not None and topology.analysis_id != analysis.analysis_id:
            raise PropagationError(
                "FMEA_PROPAGATION_TOPOLOGY_INVALID", "topology snapshot is not bound to the analysis"
            )
        try:
            validate_topology_snapshot(topology)
        except FmeaDomainError as exc:
            raise PropagationError("FMEA_PROPAGATION_TOPOLOGY_INVALID", "topology snapshot is invalid") from exc
        return analysis, tuple(rows), evidence_pack, domain_pack, rule_pack, topology

    def _enumerate(
        self,
        topology: TopologySnapshot,
        rows: tuple[FmeaRow, ...],
        rule_pack: PropagationRulePack,
        *,
        max_depth: int,
        max_edges: int,
    ) -> tuple[tuple[PropagationCandidateInterface, ...], tuple[str, ...]]:
        frontier = tuple(sorted({row.item_id for row in rows}))
        discovered: list[PropagationCandidateInterface] = []
        seen: set[tuple[str, str, int]] = set()
        for depth in range(1, max_depth + 1):
            next_frontier: set[str] = set()
            for source_id in frontier:
                raw_neighbors = self._topology_port.neighbors(topology, source_id)
                for interface in sorted(raw_neighbors, key=_sorted_interface_key):
                    if not isinstance(interface, TopologyInterface) or interface.source_node_id != source_id:
                        continue
                    if (
                        interface.interface_variable not in rule_pack.interface_variables
                        or interface.unit not in rule_pack.units
                        or interface.direction not in rule_pack.directions
                    ):
                        continue
                    identity = (interface.interface_id, interface.target_node_id, depth)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    discovered.append(
                        PropagationCandidateInterface(
                            interface_id=interface.interface_id,
                            source_node_id=interface.source_node_id,
                            target_node_id=interface.target_node_id,
                            interface_variable=interface.interface_variable,
                            unit=interface.unit,
                            direction=interface.direction,
                            operating_modes=interface.operating_modes,
                            path_length=depth,
                        )
                    )
                    next_frontier.add(interface.target_node_id)
                    if len(discovered) > max_edges:
                        raise PropagationError(
                            "FMEA_PROPAGATION_BUDGET_INVALID",
                            "deterministic propagation candidates exceed the edge budget",
                        )
            frontier = tuple(sorted(next_frontier))
            if not frontier:
                break
        candidates = tuple(
            sorted(
                discovered,
                key=lambda item: (
                    item.path_length,
                    item.interface_id,
                    item.source_node_id,
                    item.target_node_id,
                ),
            )
        )
        endpoints = tuple(sorted({row.item_id for row in rows} | {item.target_node_id for item in candidates}))
        return candidates, endpoints

    @staticmethod
    def _validate_suggestion(
        suggestion: AssistanceSuggestion[object],
        request: PropagationModelRequest,
    ) -> None:
        if not isinstance(suggestion, AssistanceSuggestion):
            raise PropagationError("FMEA_PROPAGATION_SUGGESTION_INVALID", "generator did not return a suggestion")
        if (
            suggestion.kind is not AssistanceKind.PROPAGATION_HYPOTHESIS
            or suggestion.workspace_id != request.evidence_pack.workspace_id
            or suggestion.target_type != "fmea_analysis"
            or suggestion.target_id != request.analysis.analysis_id
            or suggestion.target_record_version != request.analysis.record_version
            or suggestion.evidence_pack_ids != (request.evidence_pack.pack_id,)
            or suggestion.domain_pack_id != request.domain_pack.pack_id
            or suggestion.domain_pack_version != request.domain_pack.version
            or suggestion.rule_pack_id != request.rule_pack.rule_pack_id
            or suggestion.rule_pack_version != request.rule_pack.version
            or suggestion.template_id != PROPAGATION_TEMPLATE_ID
            or suggestion.template_version != PROPAGATION_TEMPLATE_VERSION
        ):
            raise PropagationError(
                "FMEA_PROPAGATION_SUGGESTION_INVALID", "suggestion identity is not bound to the request"
            )
        if not set(suggestion.evidence_ids).issubset(set(request.candidate_evidence_ids)):
            raise PropagationError(
                "FMEA_PROPAGATION_EVIDENCE_INVALID", "suggestion evidence is outside the EvidencePack"
            )

    @staticmethod
    def _edge_from_proposal(  # noqa: C901
        proposal: Mapping[str, object],
        request: PropagationModelRequest,
    ) -> PropagationEdge:
        if set(proposal) != PROPAGATION_EDGE_PROPOSAL_KEYS:
            raise PropagationError(
                "FMEA_PROPAGATION_SUGGESTION_INVALID", "model edge contains unknown or missing fields"
            )
        source = proposal.get("source_entity_id")
        target = proposal.get("target_entity_id")
        variable = proposal.get("interface_variable")
        unit = proposal.get("unit")
        direction = proposal.get("direction")
        path_length = proposal.get("path_length")
        interface_id = proposal.get("interface_id")
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or source not in request.candidate_endpoint_ids
            or target not in request.candidate_endpoint_ids
        ):
            raise PropagationError(
                "FMEA_PROPAGATION_ENDPOINT_INVALID", "model endpoint is outside enumerated candidates"
            )
        if not all(isinstance(value, str) for value in (interface_id, variable, unit, direction)):
            raise PropagationError("FMEA_PROPAGATION_SUGGESTION_INVALID", "model interface metadata is invalid")
        if (
            not isinstance(path_length, int)
            or isinstance(path_length, bool)
            or not 1 <= path_length <= request.max_depth
        ):
            raise PropagationError("FMEA_PROPAGATION_DEPTH_INVALID", "model path length exceeds the bounded depth")
        if find_propagation_candidate(request.candidate_interfaces, proposal) is None:
            raise PropagationError(
                "FMEA_PROPAGATION_ENDPOINT_INVALID", "model edge is not an enumerated topology interface"
            )
        relation_type = proposal.get("relation_type")
        if not isinstance(relation_type, str) or relation_type not in request.allowed_relation_types:
            raise PropagationError("FMEA_PROPAGATION_RELATION_INVALID", "model relation is outside the rule pack")
        evidence_ids = proposal.get("evidence_ids")
        if (
            isinstance(evidence_ids, str | bytes)
            or not isinstance(evidence_ids, Sequence)
            or not evidence_ids
            or not all(isinstance(item, str) for item in evidence_ids)
        ):
            raise PropagationError("FMEA_PROPAGATION_EVIDENCE_INVALID", "model evidence IDs are invalid")
        evidence_ids_tuple = tuple(evidence_ids)
        if len(set(evidence_ids_tuple)) != len(evidence_ids_tuple) or not set(evidence_ids_tuple).issubset(
            set(request.candidate_evidence_ids)
        ):
            raise PropagationError("FMEA_PROPAGATION_EVIDENCE_INVALID", "model evidence is outside the EvidencePack")

        def strings(name: str) -> tuple[str, ...]:
            value = proposal.get(name)
            if (
                isinstance(value, str | bytes)
                or not isinstance(value, Sequence)
                or not all(isinstance(item, str) and item.strip() for item in value)
            ):
                raise PropagationError("FMEA_PROPAGATION_SUGGESTION_INVALID", f"model {name} is invalid")
            result = tuple(value)
            if len(set(result)) != len(result):
                raise PropagationError("FMEA_PROPAGATION_SUGGESTION_INVALID", f"model {name} contains duplicates")
            return result

        def timing(name: str) -> int | None:
            value = proposal.get(name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise PropagationError("FMEA_PROPAGATION_SUGGESTION_INVALID", f"model {name} is invalid")
            return value

        support = proposal.get("evidence_support")
        claim = proposal.get("claim_status")
        if support not in {item.value for item in EvidenceSupportStatus}:
            raise PropagationError("FMEA_PROPAGATION_EVIDENCE_INVALID", "model evidence support is invalid")
        if claim not in {item.value for item in ClaimStatus}:
            raise PropagationError("FMEA_PROPAGATION_SUGGESTION_INVALID", "model claim status is invalid")
        for flag in ("is_cyclic", "is_unprocessed", "is_external", "is_terminal"):
            if type(proposal.get(flag)) is not bool:
                raise PropagationError("FMEA_PROPAGATION_SUGGESTION_INVALID", f"model {flag} is invalid")
        threshold = proposal.get("threshold")
        if threshold is not None and not isinstance(threshold, str):
            raise PropagationError("FMEA_PROPAGATION_SUGGESTION_INVALID", "model threshold is invalid")
        priority = proposal.get("risk_priority")
        if priority is not None and not isinstance(priority, str):
            raise PropagationError("FMEA_PROPAGATION_SUGGESTION_INVALID", "model risk priority is invalid")
        flags = {
            name: cast(bool, proposal[name]) for name in ("is_cyclic", "is_unprocessed", "is_external", "is_terminal")
        }
        return PropagationEdge(
            edge_id=stable_id(
                "propagation-edge",
                request.run_id,
                interface_id,
                path_length,
                source,
                target,
                variable,
                unit,
                direction,
                relation_type,
                evidence_ids_tuple,
            ),
            analysis_id=request.analysis.analysis_id,
            source_entity_id=source,
            target_entity_id=target,
            relation_type=relation_type,
            interface_variable=cast(str, variable),
            unit=cast(str, unit),
            direction=cast(str, direction),
            threshold=threshold,
            operating_modes=strings("operating_modes"),
            delay_ms=timing("delay_ms"),
            response_time_ms=timing("response_time_ms"),
            fault_tolerance_time_ms=timing("fault_tolerance_time_ms"),
            barrier_ids=strings("barrier_ids"),
            evidence_pack_id=request.evidence_pack.pack_id,
            evidence_ids=evidence_ids_tuple,
            evidence_support=EvidenceSupportStatus(support),
            claim_status=ClaimStatus(claim),
            review_status=ReviewStatus.SUGGESTED,
            publication_status=PublicationStatus.UNPUBLISHED,
            path_length=path_length,
            is_cyclic=flags["is_cyclic"],
            is_unprocessed=flags["is_unprocessed"],
            is_external=flags["is_external"],
            is_terminal=flags["is_terminal"],
            risk_priority=priority,
        )

    @staticmethod
    def _paths(edges: tuple[PropagationEdge, ...], analysis_id: str) -> tuple[PropagationPath, ...]:
        paths: list[PropagationPath] = []
        for edge in edges:
            if edge.path_length == 1:
                paths.append(
                    PropagationPath(
                        path_id=stable_id("propagation-path", edge.edge_id),
                        analysis_id=analysis_id,
                        source_entity_id=edge.source_entity_id,
                        target_entity_id=edge.target_entity_id,
                        edges=(edge,),
                        path_length=1,
                        is_cyclic=edge.is_cyclic,
                        requires_human_review=not edge.auto_accept_allowed,
                    )
                )
        for edge in edges:
            if edge.path_length != 2:
                continue
            predecessors = tuple(
                candidate
                for candidate in edges
                if candidate.target_entity_id == edge.source_entity_id and candidate.edge_id != edge.edge_id
            )
            if not predecessors:
                continue
            previous = sorted(predecessors, key=lambda item: item.edge_id)[0]
            paths.append(
                PropagationPath(
                    path_id=stable_id("propagation-path", previous.edge_id, edge.edge_id),
                    analysis_id=analysis_id,
                    source_entity_id=previous.source_entity_id,
                    target_entity_id=edge.target_entity_id,
                    edges=(previous, edge),
                    path_length=2,
                    is_cyclic=previous.is_cyclic or edge.is_cyclic,
                    requires_human_review=True,
                )
            )
        return tuple(sorted(paths, key=lambda path: path.path_id))

    def start_analysis(self, command: StartPropagationCommand, actor: ActorContext) -> PropagationRun:  # noqa: C901
        run_id = stable_id("propagation-run", command.analysis_id, command.idempotency_key)
        now = self._clock()
        if command.max_depth != LOCKED_AUTOMATIC_DEPTH:
            return _failed_run(
                run_id,
                actor.workspace_id,
                command.analysis_id,
                "FMEA_PROPAGATION_DEPTH_INVALID",
                "propagation automatic depth is locked to exactly two hops",
                now,
            )
        if not 1 <= command.max_edges <= 40:
            return _failed_run(
                run_id,
                actor.workspace_id,
                command.analysis_id,
                "FMEA_PROPAGATION_BUDGET_INVALID",
                "propagation edge budget is invalid",
                now,
            )
        try:
            analysis, rows, evidence_pack, domain_pack, rule_pack, topology = self._load_inputs(command, actor)
            candidates, endpoints = self._enumerate(
                topology, rows, rule_pack, max_depth=command.max_depth, max_edges=command.max_edges
            )
            request = PropagationModelRequest(
                run_id=run_id,
                analysis=analysis,
                source_rows=rows,
                evidence_pack=evidence_pack,
                topology=topology,
                domain_pack=domain_pack,
                rule_pack=rule_pack,
                candidate_interfaces=candidates,
                candidate_endpoint_ids=endpoints,
                candidate_evidence_ids=tuple(
                    ref.evidence_id
                    for ref in sorted(evidence_pack.refs, key=lambda ref: ref.evidence_id)[:_MAX_MODEL_EVIDENCE_REFS]
                ),
                allowed_relation_types=rule_pack.relation_types,
                max_depth=command.max_depth,
                max_edges=command.max_edges,
            )
            suggestion = cast(AssistanceSuggestion[object], self._generator.generate(request))
            self._validate_suggestion(suggestion, request)
            payload = suggestion.payload
            raw_proposals: object
            if isinstance(payload, Mapping):
                if set(payload) != {"edges"}:
                    raise PropagationError(  # noqa: TRY301
                        "FMEA_PROPAGATION_BUDGET_INVALID",
                        "model payload contains unsupported budget or authority fields",
                    )
                raw_proposals = payload["edges"]
            else:
                raw_proposals = payload
            if isinstance(raw_proposals, str | bytes) or not isinstance(raw_proposals, Sequence):
                raise PropagationError("FMEA_PROPAGATION_SUGGESTION_INVALID", "model edge proposals are invalid")  # noqa: TRY301
            proposals = cast(Sequence[object], raw_proposals)
            if len(proposals) > command.max_edges:
                raise PropagationError("FMEA_PROPAGATION_BUDGET_INVALID", "model edge proposals exceed the edge budget")  # noqa: TRY301
            edges = tuple(
                sorted(
                    (self._edge_from_proposal(item, request) for item in proposals if isinstance(item, Mapping)),
                    key=lambda edge: (
                        edge.path_length,
                        edge.source_entity_id,
                        edge.target_entity_id,
                        edge.interface_variable,
                        edge.unit,
                        edge.direction,
                        edge.relation_type,
                        edge.edge_id,
                    ),
                )
            )
            if len(edges) != len(proposals):
                raise PropagationError("FMEA_PROPAGATION_SUGGESTION_INVALID", "model edge proposals must be objects")  # noqa: TRY301
            for edge in edges:
                from core_domain.fmea.propagation import validate_propagation_edge

                try:
                    validate_propagation_edge(edge, evidence_pack)
                except FmeaDomainError as exc:
                    raise PropagationError(
                        "FMEA_PROPAGATION_EDGE_INVALID", "model edge failed domain validation"
                    ) from exc
            paths = self._paths(edges, analysis.analysis_id)
            graph = PropagationGraphRevision(
                graph_revision_id=stable_id("propagation-graph", run_id),
                workspace_id=actor.workspace_id,
                analysis_id=analysis.analysis_id,
                analysis_record_version=analysis.record_version,
                topology_snapshot_id=topology.topology_snapshot_id,
                topology_hash=topology.topology_hash,
                evidence_pack_ids=(evidence_pack.pack_id,),
                domain_pack_id=domain_pack.pack_id,
                domain_pack_version=domain_pack.version,
                rule_pack_id=rule_pack.rule_pack_id,
                rule_pack_version=rule_pack.version,
                status=PropagationStatus.PROPOSED,
                assistance_suggestion_ids=(suggestion.suggestion_id,),
                nodes=tuple(
                    sorted(
                        (node for node in topology.nodes if node.node_id in endpoints), key=lambda node: node.node_id
                    )
                ),
                edges=edges,
                paths=paths,
                unresolved_issue_codes=(),
                parent_graph_revision_id=None,
                record_version=1,
                created_at=now,
            )
            try:
                validate_graph_revision(graph, topology, rule_pack, PropagationEvidenceResolution((evidence_pack,)))
            except FmeaDomainError as exc:
                raise PropagationError(
                    "FMEA_PROPAGATION_GRAPH_INVALID", "propagation graph failed domain validation"
                ) from exc
            scope = IdempotencyScope(
                workspace_id=actor.workspace_id,
                actor_id=actor.actor_id,
                command="fmea.propagation.start",
                resource_path=f"/fmea/analyses/{analysis.analysis_id}/propagation",
                key_hash=idempotency_key_hash(command.idempotency_key),
            )
            payload_hash = assistance_suggestion_payload_hash(scope, suggestion)
            audit = make_audit(
                actor=actor,
                scope=scope,
                payload_hash=payload_hash,
                command=scope.command,
                reason="bounded propagation hypothesis generated",
                row_id=analysis.analysis_id,
                analysis_id=analysis.analysis_id,
                suggestion_id=suggestion.suggestion_id,
                decision_id=None,
                expected_record_version=analysis.record_version,
                applied_record_version=None,
                evidence_ids=suggestion.evidence_ids,
                template_id=suggestion.template_id or "fmea-propagation-hypothesis",
                template_version=suggestion.template_version or "1.0.0",
                scoring_version=rule_pack.version,
                occurred_at=now,
                event_id=stable_id("propagation-audit", run_id),
                request_id=run_id,
                trace_id=suggestion.trace_id,
                run_id=run_id,
            )
            prepared_assistance = PreparedAssistanceSuggestion(
                scope=scope,
                payload_hash=payload_hash,
                suggestion=suggestion,
                audit=audit,
            )
            persisted_suggestion = self._assistance_repository.save_suggestion(prepared_assistance)
            if persisted_suggestion.suggestion_id != suggestion.suggestion_id:
                raise PropagationError(  # noqa: TRY301
                    "FMEA_PROPAGATION_PERSISTENCE_INVALID", "assistance repository changed suggestion identity"
                )
            run = PropagationRun(
                run_id=run_id,
                workspace_id=actor.workspace_id,
                analysis_id=analysis.analysis_id,
                status=RunStatus.SUCCEEDED,
                graph=graph,
                error_code=None,
                error_message=None,
                assistance_suggestion_ids=(suggestion.suggestion_id,),
                created_at=now,
                updated_at=now,
            )
            prepared = PreparedPropagationProposal(
                run=run,
                graph=graph,
                suggestion=suggestion,
                assistance=prepared_assistance,
                topology=topology,
                rule_pack=rule_pack,
                evidence_pack=evidence_pack,
                source_row_ids=command.source_row_ids,
            )
            return self._repository.save_run_and_proposal(prepared)
        except PropagationError as exc:
            return _failed_run(run_id, actor.workspace_id, command.analysis_id, exc.code, str(exc), now)
        except (FmeaDomainError, KeyError, TypeError, ValueError) as exc:
            return _failed_run(
                run_id,
                actor.workspace_id,
                command.analysis_id,
                getattr(exc, "code", "FMEA_PROPAGATION_FAILED"),
                "propagation analysis failed closed",
                now,
            )

    def get_run(self, run_id: str, actor: ActorContext) -> PropagationRun:
        run = self._repository.get_run(run_id, actor.workspace_id)
        if run is None:
            raise PropagationError("FMEA_PROPAGATION_RUN_NOT_FOUND", "propagation run was not found")
        return run

    def get_graph(self, analysis_id: str, actor: ActorContext) -> PropagationGraphRevision | None:
        return self._repository.get_graph(analysis_id, actor.workspace_id)


__all__ = [
    "PROPAGATION_TEMPLATE_ID",
    "PROPAGATION_TEMPLATE_VERSION",
    "PreparedPropagationProposal",
    "PropagationAnalysisService",
    "PropagationCandidateInterface",
    "PropagationEdgeProposal",
    "PropagationError",
    "PropagationModelRequest",
    "PropagationRepository",
    "PropagationRun",
    "PropagationSuggestionGenerator",
    "StartPropagationCommand",
]
