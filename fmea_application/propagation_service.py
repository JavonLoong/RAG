"""Bounded, proposal-only FMEA propagation analysis."""

# ruff: noqa: TRY003, TRY004

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
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
    ActorType,
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
from .review_contracts import (
    ActorContext,
    AuditEvent,
    IdempotencyScope,
    encode_review_json,
    idempotency_key_hash,
)
from .review_errors import ReviewError
from .risk_contracts import (
    OutboxEvent,
    PreparedAssistanceSuggestion,
    assistance_suggestion_payload_hash,
    outbox_payload_hash,
)

_MAX_MODEL_EVIDENCE_REFS = 20
PROPAGATION_TEMPLATE_ID = "fmea-propagation-hypothesis"
PROPAGATION_TEMPLATE_VERSION = "1.0.0"


class PropagationError(ValueError):
    """Safe, transport-neutral error for a propagation proposal boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PropagationDecisionAction(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class PropagationEdgeDecision:
    edge_id: str
    action: PropagationDecisionAction
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.edge_id, str) or not self.edge_id.strip():
            raise ValueError("edge_id must not be empty")
        object.__setattr__(self, "edge_id", self.edge_id.strip())
        if not isinstance(self.action, PropagationDecisionAction):
            try:
                object.__setattr__(self, "action", PropagationDecisionAction(self.action))
            except (TypeError, ValueError) as exc:
                raise ValueError("propagation edge decision action is invalid") from exc
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("decision reason must not be empty")
        object.__setattr__(self, "reason", self.reason.strip())


@dataclass(frozen=True, slots=True)
class ConfirmPropagationCommand:
    graph_revision_id: str
    expected_graph_record_version: int
    edge_decisions: tuple[PropagationEdgeDecision, ...]
    acknowledgements: tuple[str, ...]
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.graph_revision_id, str) or not self.graph_revision_id.strip():
            raise ValueError("graph_revision_id must not be empty")
        object.__setattr__(self, "graph_revision_id", self.graph_revision_id.strip())
        if (
            isinstance(self.expected_graph_record_version, bool)
            or not isinstance(self.expected_graph_record_version, int)
            or self.expected_graph_record_version < 1
        ):
            raise ValueError("expected_graph_record_version must be positive")
        decisions = tuple(self.edge_decisions)
        if any(not isinstance(item, PropagationEdgeDecision) for item in decisions):
            raise ValueError("edge_decisions must contain PropagationEdgeDecision objects")
        if len({item.edge_id for item in decisions}) != len(decisions):
            raise ValueError("edge_decisions must contain one decision per edge")
        object.__setattr__(self, "edge_decisions", decisions)
        acknowledgements = tuple(item.strip() if isinstance(item, str) else item for item in self.acknowledgements)
        if any(not isinstance(item, str) or not item.strip() for item in acknowledgements):
            raise ValueError("acknowledgements must contain non-empty issue codes")
        if len(set(acknowledgements)) != len(acknowledgements):
            raise ValueError("acknowledgements must not contain duplicates")
        object.__setattr__(self, "acknowledgements", tuple(sorted(acknowledgements)))
        idempotency_key_hash(self.idempotency_key)

    @property
    def acknowledged_issue_codes(self) -> tuple[str, ...]:
        return self.acknowledgements


@dataclass(frozen=True, slots=True)
class InvalidatePropagationCommand:
    graph_revision_id: str
    expected_graph_record_version: int
    changed_evidence_hash: str
    reason: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.graph_revision_id, str) or not self.graph_revision_id.strip():
            raise ValueError("graph_revision_id must not be empty")
        object.__setattr__(self, "graph_revision_id", self.graph_revision_id.strip())
        if (
            isinstance(self.expected_graph_record_version, bool)
            or not isinstance(self.expected_graph_record_version, int)
            or self.expected_graph_record_version < 1
        ):
            raise ValueError("expected_graph_record_version must be positive")
        if not isinstance(self.changed_evidence_hash, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", self.changed_evidence_hash.strip()
        ):
            raise ValueError("changed_evidence_hash must use sha256:<64 lowercase hex>")
        object.__setattr__(self, "changed_evidence_hash", self.changed_evidence_hash.strip())
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("invalidation reason must not be empty")
        object.__setattr__(self, "reason", self.reason.strip())
        idempotency_key_hash(self.idempotency_key)


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
    request_scope: IdempotencyScope
    request_hash: str
    command: StartPropagationCommand

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_row_ids", tuple(self.source_row_ids))
        if not isinstance(self.request_scope, IdempotencyScope):
            raise ValueError("request_scope must be an IdempotencyScope")
        if not isinstance(self.request_hash, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", self.request_hash):
            raise ValueError("request_hash must use sha256:<64 lowercase hex>")
        if not isinstance(self.command, StartPropagationCommand):
            raise ValueError("command must be a StartPropagationCommand")


@dataclass(frozen=True, slots=True)
class PropagationReviewResult:
    graph: PropagationGraphRevision
    decision_id: str
    audit_event_id: str
    outbox_event_id: str
    replayed: bool = False
    persisted: bool = True


@dataclass(frozen=True, slots=True)
class PreparedPropagationReview:
    scope: IdempotencyScope
    payload_hash: str
    command: ConfirmPropagationCommand
    previous_graph: PropagationGraphRevision
    graph: PropagationGraphRevision
    edge_decisions: tuple[PropagationEdgeDecision, ...]
    decision_id: str
    audit: AuditEvent
    outbox: OutboxEvent
    topology: TopologySnapshot
    rule_pack: PropagationRulePack
    evidence_packs: tuple[EvidencePack, ...]
    source_row_ids: tuple[str, ...]

    def __post_init__(self) -> None:  # noqa: C901
        if not isinstance(self.scope, IdempotencyScope):
            raise ValueError("scope must be an IdempotencyScope")
        if not isinstance(self.command, ConfirmPropagationCommand):
            raise ValueError("command must be a ConfirmPropagationCommand")
        if not isinstance(self.previous_graph, PropagationGraphRevision):
            raise ValueError("previous_graph must be a PropagationGraphRevision")
        if not isinstance(self.graph, PropagationGraphRevision):
            raise ValueError("graph must be a PropagationGraphRevision")
        if not isinstance(self.audit, AuditEvent):
            raise ValueError("audit must be an AuditEvent")
        if not isinstance(self.outbox, OutboxEvent):
            raise ValueError("outbox must be an OutboxEvent")
        object.__setattr__(self, "edge_decisions", tuple(self.edge_decisions))
        object.__setattr__(self, "evidence_packs", tuple(self.evidence_packs))
        object.__setattr__(self, "source_row_ids", tuple(self.source_row_ids))
        if not self.source_row_ids:
            raise ValueError("source_row_ids must not be empty")
        expected = propagation_review_payload_hash(self.scope, self.command, edge_decisions=self.edge_decisions)
        if self.payload_hash != expected:
            raise ValueError("propagation review payload hash does not match canonical payload")
        if (
            self.scope.workspace_id != self.previous_graph.workspace_id
            or self.graph.workspace_id != self.scope.workspace_id
            or self.scope.command != "fmea.propagation.review"
            or self.scope.resource_path != f"/fmea/propagation-graphs/{self.previous_graph.graph_revision_id}/reviews"
            or self.command.graph_revision_id != self.previous_graph.graph_revision_id
            or self.command.expected_graph_record_version != self.previous_graph.record_version
            or idempotency_key_hash(self.command.idempotency_key) != self.scope.key_hash
            or self.decision_id != stable_id("propagation-review", self.scope.scope_key)
            or self.graph.graph_revision_id != stable_id("propagation-confirmed-graph", self.scope.scope_key)
            or self.graph.status is not PropagationStatus.CONFIRMED
            or self.graph.record_version != self.previous_graph.record_version + 1
            or self.audit.workspace_id != self.scope.workspace_id
            or self.audit.actor_id != self.scope.actor_id
            or self.audit.actor_type is not ActorType.HUMAN
            or "propagation_reviewer" not in self.audit.actor_roles
        ):
            raise ValueError("propagation review workspace binding is invalid")
        if self.graph.parent_graph_revision_id != self.previous_graph.graph_revision_id:
            raise ValueError("confirmed graph must link to its parent revision")
        if (
            self.outbox.workspace_id != self.scope.workspace_id
            or self.outbox.aggregate_id != self.graph.graph_revision_id
            or self.outbox.scope_key != self.scope.scope_key
            or self.outbox.event_type != "propagation.confirmed"
        ):
            raise ValueError("propagation review outbox binding is invalid")

    @property
    def outbox_event(self) -> OutboxEvent:
        return self.outbox


@dataclass(frozen=True, slots=True)
class PreparedPropagationInvalidation:
    scope: IdempotencyScope
    payload_hash: str
    command: InvalidatePropagationCommand
    previous_graph: PropagationGraphRevision
    graph: PropagationGraphRevision
    decision_id: str
    audit: AuditEvent
    outbox: OutboxEvent
    topology: TopologySnapshot
    rule_pack: PropagationRulePack
    evidence_packs: tuple[EvidencePack, ...]
    source_row_ids: tuple[str, ...]

    def __post_init__(self) -> None:  # noqa: C901
        if not isinstance(self.scope, IdempotencyScope):
            raise ValueError("scope must be an IdempotencyScope")
        if not isinstance(self.command, InvalidatePropagationCommand):
            raise ValueError("command must be an InvalidatePropagationCommand")
        if not isinstance(self.previous_graph, PropagationGraphRevision):
            raise ValueError("previous_graph must be a PropagationGraphRevision")
        if not isinstance(self.graph, PropagationGraphRevision):
            raise ValueError("graph must be a PropagationGraphRevision")
        if not isinstance(self.audit, AuditEvent):
            raise ValueError("audit must be an AuditEvent")
        if not isinstance(self.outbox, OutboxEvent):
            raise ValueError("outbox must be an OutboxEvent")
        object.__setattr__(self, "evidence_packs", tuple(self.evidence_packs))
        object.__setattr__(self, "source_row_ids", tuple(self.source_row_ids))
        if not self.source_row_ids:
            raise ValueError("source_row_ids must not be empty")
        expected = propagation_invalidation_payload_hash(self.scope, self.command)
        if self.payload_hash != expected:
            raise ValueError("propagation invalidation payload hash does not match canonical payload")
        if (
            self.scope.workspace_id != self.previous_graph.workspace_id
            or self.graph.workspace_id != self.scope.workspace_id
            or self.scope.command != "fmea.propagation.invalidate"
            or self.scope.resource_path
            != f"/fmea/propagation-graphs/{self.previous_graph.graph_revision_id}/invalidations"
            or self.command.graph_revision_id != self.previous_graph.graph_revision_id
            or self.command.expected_graph_record_version != self.previous_graph.record_version
            or idempotency_key_hash(self.command.idempotency_key) != self.scope.key_hash
            or self.decision_id != stable_id("propagation-invalidation", self.scope.scope_key)
            or self.graph.graph_revision_id != stable_id("propagation-invalidated-graph", self.scope.scope_key)
            or self.graph.status is not PropagationStatus.INVALIDATED
            or self.graph.record_version != self.previous_graph.record_version + 1
            or self.audit.workspace_id != self.scope.workspace_id
            or self.audit.actor_id != self.scope.actor_id
            or self.audit.actor_type is ActorType.MODEL
        ):
            raise ValueError("propagation invalidation workspace binding is invalid")
        if self.graph.parent_graph_revision_id != self.previous_graph.graph_revision_id:
            raise ValueError("invalidated graph must link to its parent revision")
        if (
            self.outbox.workspace_id != self.scope.workspace_id
            or self.outbox.aggregate_id != self.graph.graph_revision_id
            or self.outbox.scope_key != self.scope.scope_key
            or self.outbox.event_type != "propagation.invalidated"
        ):
            raise ValueError("propagation invalidation outbox binding is invalid")


class PropagationRepository(Protocol):
    """Workspace-scoped reads; entities without workspace fields rely on this port boundary."""

    def get_analysis(self, analysis_id: str, workspace_id: str) -> FmeaAnalysis | None: ...

    def get_row(self, row_id: str, workspace_id: str) -> FmeaRow | None: ...

    def get_evidence_pack(self, pack_id: str, workspace_id: str) -> EvidencePack | None: ...

    def save_run_and_proposal(self, prepared: PreparedPropagationProposal) -> PropagationRun: ...

    def replay_propagation_start(self, scope: IdempotencyScope, payload_hash: str) -> PropagationRun | None: ...

    def get_run(self, run_id: str, workspace_id: str) -> PropagationRun | None: ...

    def get_graph(self, analysis_id: str, workspace_id: str) -> PropagationGraphRevision | None: ...

    def get_current_graph(self, analysis_id: str, workspace_id: str) -> PropagationGraphRevision | None: ...

    def get_topology_snapshot(self, topology_snapshot_id: str, workspace_id: str) -> TopologySnapshot | None: ...

    def get_graph_source_row_ids(self, graph_revision_id: str, workspace_id: str) -> tuple[str, ...]: ...

    def replay_graph_review(self, scope: IdempotencyScope, payload_hash: str) -> PropagationReviewResult | None: ...

    def replay_invalidation(self, scope: IdempotencyScope, payload_hash: str) -> PropagationGraphRevision | None: ...

    def commit_graph_review(self, prepared: PreparedPropagationReview) -> PropagationReviewResult: ...

    def invalidate(self, prepared: PreparedPropagationInvalidation) -> PropagationGraphRevision: ...


def _propagation_scope_payload(scope: IdempotencyScope) -> dict[str, str]:
    return {
        "workspace_id": scope.workspace_id,
        "actor_id": scope.actor_id,
        "command": scope.command,
        "resource_path": scope.resource_path,
    }


def _propagation_payload_hash(payload: object) -> str:
    return "sha256:" + sha256(encode_review_json(payload).encode("utf-8")).hexdigest()


def propagation_start_payload(scope: IdempotencyScope, command: StartPropagationCommand) -> Mapping[str, object]:
    return {
        "operation": "propagation.start",
        "scope": _propagation_scope_payload(scope),
        "command": {
            "analysis_id": command.analysis_id,
            "expected_analysis_record_version": command.expected_analysis_record_version,
            "source_row_ids": command.source_row_ids,
            "evidence_pack_id": command.evidence_pack_id,
            "topology_id": command.topology_id,
            "topology_version": command.topology_version,
            "domain_pack_id": command.domain_pack_id,
            "domain_pack_version": command.domain_pack_version,
            "rule_pack_id": command.rule_pack_id,
            "rule_pack_version": command.rule_pack_version,
            "max_depth": command.max_depth,
            "max_edges": command.max_edges,
            "require_confirmed_risk": command.require_confirmed_risk,
        },
    }


def propagation_start_payload_hash(scope: IdempotencyScope, command: StartPropagationCommand) -> str:
    return _propagation_payload_hash(propagation_start_payload(scope, command))


def _revision_for_payload(graph: PropagationGraphRevision) -> Mapping[str, object]:
    """Exclude server-assigned time from retry identity while retaining it in storage."""

    value = json.loads(encode_review_json(graph))
    if not isinstance(value, dict):
        raise ValueError("propagation graph canonical projection is invalid")
    value.pop("created_at", None)
    return value


def propagation_review_payload(
    scope: IdempotencyScope,
    command: ConfirmPropagationCommand,
    previous_graph: PropagationGraphRevision | None = None,
    graph: PropagationGraphRevision | None = None,
    edge_decisions: tuple[PropagationEdgeDecision, ...] = (),
) -> Mapping[str, object]:
    # Replay identity is request-only. Persisted graph/edge/audit/outbox rows
    # independently bind the resulting immutable child revision.
    return {
        "operation": "propagation.review",
        "scope": _propagation_scope_payload(scope),
        "command": {
            "graph_revision_id": command.graph_revision_id,
            "expected_graph_record_version": command.expected_graph_record_version,
            "acknowledgements": command.acknowledgements,
        },
        "edge_decisions": edge_decisions,
    }


def propagation_review_payload_hash(
    scope: IdempotencyScope,
    command: ConfirmPropagationCommand,
    previous_graph: PropagationGraphRevision | None = None,
    graph: PropagationGraphRevision | None = None,
    edge_decisions: tuple[PropagationEdgeDecision, ...] = (),
) -> str:
    return _propagation_payload_hash(propagation_review_payload(scope, command, previous_graph, graph, edge_decisions))


def propagation_invalidation_payload(
    scope: IdempotencyScope,
    command: InvalidatePropagationCommand,
    previous_graph: PropagationGraphRevision | None = None,
    graph: PropagationGraphRevision | None = None,
) -> Mapping[str, object]:
    return {
        "operation": "propagation.invalidation",
        "scope": _propagation_scope_payload(scope),
        "command": {
            "graph_revision_id": command.graph_revision_id,
            "expected_graph_record_version": command.expected_graph_record_version,
            "changed_evidence_hash": command.changed_evidence_hash,
            "reason": command.reason,
        },
    }


def propagation_invalidation_payload_hash(
    scope: IdempotencyScope,
    command: InvalidatePropagationCommand,
    previous_graph: PropagationGraphRevision | None = None,
    graph: PropagationGraphRevision | None = None,
) -> str:
    return _propagation_payload_hash(propagation_invalidation_payload(scope, command, previous_graph, graph))


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
        request_scope = IdempotencyScope(
            workspace_id=actor.workspace_id,
            actor_id=actor.actor_id,
            command="fmea.propagation.start",
            resource_path=f"/fmea/analyses/{command.analysis_id}/propagation",
            key_hash=idempotency_key_hash(command.idempotency_key),
        )
        request_hash = propagation_start_payload_hash(request_scope, command)
        run_id = stable_id("propagation-run", request_scope.scope_key)
        replay = getattr(self._repository, "replay_propagation_start", None)
        if callable(replay):
            replayed = replay(request_scope, request_hash)
            if replayed is not None:
                return replayed
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
            suggestion_scope = IdempotencyScope(
                workspace_id=actor.workspace_id,
                actor_id=actor.actor_id,
                command="fmea.propagation.suggestion",
                resource_path=f"/fmea/propagation-runs/{run_id}/suggestion",
                key_hash=idempotency_key_hash(command.idempotency_key),
            )
            payload_hash = assistance_suggestion_payload_hash(suggestion_scope, suggestion)
            audit = make_audit(
                actor=actor,
                scope=suggestion_scope,
                payload_hash=payload_hash,
                command=suggestion_scope.command,
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
                event_id=stable_id("propagation-assistance-audit", suggestion_scope.scope_key),
                request_id=run_id,
                trace_id=suggestion.trace_id,
                run_id=run_id,
            )
            prepared_assistance = PreparedAssistanceSuggestion(
                scope=suggestion_scope,
                payload_hash=payload_hash,
                suggestion=suggestion,
                audit=audit,
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
                request_scope=request_scope,
                request_hash=request_hash,
                command=command,
            )
            return self._repository.save_run_and_proposal(prepared)
        except ReviewError:
            raise
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

    @staticmethod
    def _review_issue_codes(edge: PropagationEdge) -> tuple[str, ...]:
        issues: list[str] = []
        if edge.path_length > LOCKED_AUTOMATIC_DEPTH:
            issues.append("long_path")
        if edge.is_cyclic:
            issues.append("cyclic")
        if edge.risk_priority in {"high", "critical"}:
            issues.append("high_risk")
        if edge.is_external:
            issues.append("external")
        if edge.is_unprocessed:
            issues.append("unprocessed")
        if edge.claim_status is ClaimStatus.CONFLICT:
            issues.append("conflicting")
        if not edge.evidence_ids or edge.evidence_support in {
            EvidenceSupportStatus.CONTRADICTED,
            EvidenceSupportStatus.NOT_SUPPORTED,
        }:
            issues.append("evidence_gap")
        return tuple(issues)

    def _graph_dependencies(
        self, graph: PropagationGraphRevision, actor: ActorContext
    ) -> tuple[TopologySnapshot, PropagationRulePack, tuple[EvidencePack, ...], tuple[str, ...]]:
        get_topology = getattr(self._repository, "get_topology_snapshot", None)
        topology = get_topology(graph.topology_snapshot_id, actor.workspace_id) if callable(get_topology) else None
        if not isinstance(topology, TopologySnapshot) or topology.workspace_id != actor.workspace_id:
            raise PropagationError("FMEA_PROPAGATION_TOPOLOGY_INVALID", "persisted topology snapshot is unavailable")

        rule_pack = self._propagation_rule_registry.get(graph.rule_pack_id, graph.rule_pack_version)
        if not isinstance(rule_pack, PropagationRulePack):
            raise PropagationError("FMEA_PROPAGATION_REGISTRY_INVALID", "persisted propagation rule pack is invalid")

        evidence_packs: list[EvidencePack] = []
        for pack_id in graph.evidence_pack_ids:
            pack = self._repository.get_evidence_pack(pack_id, actor.workspace_id)
            if not isinstance(pack, EvidencePack) or pack.workspace_id != actor.workspace_id:
                raise PropagationError(
                    "FMEA_PROPAGATION_EVIDENCE_INVALID", "persisted graph EvidencePack is unavailable"
                )
            evidence_packs.append(pack)

        get_source_rows = getattr(self._repository, "get_graph_source_row_ids", None)
        source_row_ids = (
            tuple(get_source_rows(graph.graph_revision_id, actor.workspace_id))
            if callable(get_source_rows)
            else (graph.analysis_id,)
        )
        if not source_row_ids:
            raise PropagationError("FMEA_PROPAGATION_PERSISTENCE_INVALID", "graph source row binding is unavailable")
        return topology, rule_pack, tuple(evidence_packs), source_row_ids

    def _graph_by_revision(self, graph_revision_id: str, actor: ActorContext) -> PropagationGraphRevision:
        getter = getattr(self._repository, "get_graph_revision", None)
        graph = (
            getter(graph_revision_id, actor.workspace_id)
            if callable(getter)
            else self._repository.get_graph(graph_revision_id, actor.workspace_id)
        )
        if not isinstance(graph, PropagationGraphRevision):
            raise PropagationError("FMEA_PROPAGATION_GRAPH_NOT_FOUND", "propagation graph revision was not found")
        return graph

    @staticmethod
    def _require_propagation_reviewer(actor: ActorContext) -> None:
        if actor.actor_type is not ActorType.HUMAN:
            raise PropagationError(
                "FMEA_PROPAGATION_REVIEW_FORBIDDEN",
                "propagation confirmation requires a human actor",
            )
        if "propagation_reviewer" not in actor.roles:
            raise PropagationError(
                "FMEA_PROPAGATION_REVIEW_FORBIDDEN",
                "the propagation_reviewer role is required",
            )

    def _review_audit_and_outbox(
        self,
        *,
        actor: ActorContext,
        scope: IdempotencyScope,
        payload_hash: str,
        decision_id: str,
        graph: PropagationGraphRevision,
        source_row_ids: tuple[str, ...],
        evidence_ids: tuple[str, ...],
        reason: str,
        event_type: str,
        request_id: str,
        trace_id: str,
        occurred_at: str,
        edge_decisions: tuple[PropagationEdgeDecision, ...] = (),
    ) -> tuple[AuditEvent, OutboxEvent]:
        audit = make_audit(
            actor=actor,
            scope=scope,
            payload_hash=payload_hash,
            command=scope.command,
            reason=reason,
            row_id=source_row_ids[0],
            analysis_id=graph.analysis_id,
            suggestion_id=graph.assistance_suggestion_ids[0] if graph.assistance_suggestion_ids else None,
            decision_id=decision_id,
            expected_record_version=graph.record_version - 1,
            applied_record_version=graph.record_version,
            evidence_ids=evidence_ids,
            template_id=PROPAGATION_TEMPLATE_ID,
            template_version=PROPAGATION_TEMPLATE_VERSION,
            scoring_version=graph.rule_pack_version,
            occurred_at=occurred_at,
            event_id=stable_id("propagation-audit", scope.scope_key),
            request_id=request_id,
            trace_id=trace_id,
            run_id=None,
        )
        payload = {
            "graph": json.loads(encode_review_json(graph)),
            "audit_event_id": audit.event_id,
            "decision_id": decision_id,
            "edge_decisions": json.loads(encode_review_json(edge_decisions)),
        }
        outbox = OutboxEvent(
            event_id=stable_id("propagation-outbox", scope.scope_key),
            workspace_id=actor.workspace_id,
            aggregate_type="propagation_graph",
            aggregate_id=graph.graph_revision_id,
            event_type=event_type,
            payload=payload,
            payload_hash=outbox_payload_hash(payload),
            created_at=occurred_at,
            scope_key=scope.scope_key,
        )
        return audit, outbox

    def _confirm_graph(self, command: ConfirmPropagationCommand, actor: ActorContext) -> PropagationReviewResult:
        self._require_propagation_reviewer(actor)
        scope = IdempotencyScope(
            workspace_id=actor.workspace_id,
            actor_id=actor.actor_id,
            command="fmea.propagation.review",
            resource_path=f"/fmea/propagation-graphs/{command.graph_revision_id}/reviews",
            key_hash=idempotency_key_hash(command.idempotency_key),
        )
        edge_decisions = tuple(sorted(command.edge_decisions, key=lambda item: item.edge_id))
        payload_hash = propagation_review_payload_hash(scope, command, edge_decisions=edge_decisions)
        replay = getattr(self._repository, "replay_graph_review", None)
        if callable(replay):
            replayed = replay(scope, payload_hash)
            if replayed is not None:
                return replayed
        parent = self._graph_by_revision(command.graph_revision_id, actor)
        if parent.status not in {PropagationStatus.PROPOSED, PropagationStatus.REVIEWED}:
            raise PropagationError("FMEA_PROPAGATION_REVIEW_TERMINAL", "propagation graph is not confirmable")
        if parent.record_version != command.expected_graph_record_version:
            raise PropagationError("FMEA_PROPAGATION_VERSION_CONFLICT", "propagation graph revision is stale")
        decision_by_edge = {item.edge_id: item for item in command.edge_decisions}
        edge_ids = {edge.edge_id for edge in parent.edges}
        if set(decision_by_edge) != edge_ids:
            raise PropagationError(
                "FMEA_PROPAGATION_REVIEW_INCOMPLETE",
                "one decision is required for every graph edge",
            )
        retained_issues = {
            issue
            for edge in parent.edges
            if decision_by_edge[edge.edge_id].action is PropagationDecisionAction.ACCEPT
            for issue in self._review_issue_codes(edge)
        }
        if not retained_issues.issubset(set(command.acknowledgements)):
            missing = sorted(retained_issues - set(command.acknowledgements))
            raise PropagationError(
                "FMEA_PROPAGATION_ACKNOWLEDGEMENT_REQUIRED",
                "explicit acknowledgements are required for retained graph issues: " + ", ".join(missing),
            )
        allowed_acknowledgements = {
            "long_path",
            "cyclic",
            "high_risk",
            "external",
            "unprocessed",
            "conflicting",
            "evidence_gap",
        }
        if not set(command.acknowledgements).issubset(allowed_acknowledgements):
            raise PropagationError(
                "FMEA_PROPAGATION_ACKNOWLEDGEMENT_INVALID",
                "acknowledgements contain an unknown propagation issue code",
            )
        if set(command.acknowledgements) != retained_issues:
            raise PropagationError(
                "FMEA_PROPAGATION_ACKNOWLEDGEMENT_INVALID",
                "acknowledgements must refer only to retained graph issues",
            )

        accepted_edges = tuple(
            replace(edge, review_status=ReviewStatus.ACCEPTED)
            for edge in parent.edges
            if decision_by_edge[edge.edge_id].action is PropagationDecisionAction.ACCEPT
        )
        decision_id = stable_id("propagation-review", scope.scope_key)
        child = replace(
            parent,
            graph_revision_id=stable_id("propagation-confirmed-graph", scope.scope_key),
            status=PropagationStatus.CONFIRMED,
            edges=accepted_edges,
            paths=self._paths(accepted_edges, parent.analysis_id),
            unresolved_issue_codes=tuple(sorted(command.acknowledgements)),
            parent_graph_revision_id=parent.graph_revision_id,
            record_version=parent.record_version + 1,
            created_at=self._clock(),
        )
        topology, rule_pack, evidence_packs, source_row_ids = self._graph_dependencies(parent, actor)
        try:
            validate_graph_revision(parent, topology, rule_pack, PropagationEvidenceResolution(evidence_packs))
            # The generic domain validator intentionally rejects CONFIRMED.
            # Validate the exact same child as a proposed revision, then apply
            # the separate persistence-backed human authority below.
            validate_graph_revision(
                replace(child, status=PropagationStatus.REVIEWED),
                topology,
                rule_pack,
                PropagationEvidenceResolution(evidence_packs),
            )
        except FmeaDomainError as exc:
            raise PropagationError("FMEA_PROPAGATION_GRAPH_INVALID", "propagation graph failed validation") from exc
        evidence_ids = tuple(sorted({item for edge in accepted_edges for item in edge.evidence_ids}))
        audit, outbox = self._review_audit_and_outbox(
            actor=actor,
            scope=scope,
            payload_hash=payload_hash,
            decision_id=decision_id,
            graph=child,
            source_row_ids=source_row_ids,
            evidence_ids=evidence_ids,
            reason="human propagation graph confirmation",
            event_type="propagation.confirmed",
            request_id=decision_id,
            trace_id=decision_id,
            occurred_at=child.created_at,
            edge_decisions=edge_decisions,
        )
        return self._repository.commit_graph_review(
            PreparedPropagationReview(
                scope=scope,
                payload_hash=payload_hash,
                command=command,
                previous_graph=parent,
                graph=child,
                edge_decisions=edge_decisions,
                decision_id=decision_id,
                audit=audit,
                outbox=outbox,
                topology=topology,
                rule_pack=rule_pack,
                evidence_packs=evidence_packs,
                source_row_ids=source_row_ids,
            )
        )

    def _invalidate(self, command: InvalidatePropagationCommand, actor: ActorContext) -> PropagationGraphRevision:
        if actor.actor_type is ActorType.MODEL:
            raise PropagationError("FMEA_PROPAGATION_REVIEW_FORBIDDEN", "a model actor cannot invalidate propagation")
        scope = IdempotencyScope(
            workspace_id=actor.workspace_id,
            actor_id=actor.actor_id,
            command="fmea.propagation.invalidate",
            resource_path=f"/fmea/propagation-graphs/{command.graph_revision_id}/invalidations",
            key_hash=idempotency_key_hash(command.idempotency_key),
        )
        payload_hash = propagation_invalidation_payload_hash(scope, command)
        replay = getattr(self._repository, "replay_invalidation", None)
        if callable(replay):
            replayed = replay(scope, payload_hash)
            if replayed is not None:
                return replayed
        parent = self._graph_by_revision(command.graph_revision_id, actor)
        if parent.record_version != command.expected_graph_record_version:
            raise PropagationError("FMEA_PROPAGATION_VERSION_CONFLICT", "propagation graph revision is stale")
        if parent.status is PropagationStatus.INVALIDATED:
            return parent
        decision_id = stable_id("propagation-invalidation", scope.scope_key)
        child = replace(
            parent,
            graph_revision_id=stable_id("propagation-invalidated-graph", scope.scope_key),
            status=PropagationStatus.INVALIDATED,
            unresolved_issue_codes=tuple(sorted(set(parent.unresolved_issue_codes) | {"stale_evidence"})),
            parent_graph_revision_id=parent.graph_revision_id,
            record_version=parent.record_version + 1,
            created_at=self._clock(),
        )
        topology, rule_pack, evidence_packs, source_row_ids = self._graph_dependencies(parent, actor)
        evidence_ids = tuple(
            sorted({item for pack in evidence_packs for item in (ref.evidence_id for ref in pack.refs)})
        )
        audit, outbox = self._review_audit_and_outbox(
            actor=actor,
            scope=scope,
            payload_hash=payload_hash,
            decision_id=decision_id,
            graph=child,
            source_row_ids=source_row_ids,
            evidence_ids=evidence_ids,
            reason=command.reason,
            event_type="propagation.invalidated",
            request_id=decision_id,
            trace_id=decision_id,
            occurred_at=child.created_at,
        )
        return self._repository.invalidate(
            PreparedPropagationInvalidation(
                scope=scope,
                payload_hash=payload_hash,
                command=command,
                previous_graph=parent,
                graph=child,
                decision_id=decision_id,
                audit=audit,
                outbox=outbox,
                topology=topology,
                rule_pack=rule_pack,
                evidence_packs=evidence_packs,
                source_row_ids=source_row_ids,
            )
        )

    def _invalidate_if_stale(
        self, analysis_id: str, changed_evidence_hash: str, actor: ActorContext, idempotency_key: str | None = None
    ) -> PropagationGraphRevision | None:
        if actor.actor_type is ActorType.MODEL:
            raise PropagationError("FMEA_PROPAGATION_REVIEW_FORBIDDEN", "a model actor cannot invalidate propagation")
        getter = getattr(self._repository, "get_current_graph", None)
        parent = (
            getter(analysis_id, actor.workspace_id)
            if callable(getter)
            else self._repository.get_graph(analysis_id, actor.workspace_id)
        )
        if parent is None or parent.status is PropagationStatus.INVALIDATED:
            return parent
        evidence_hashes: set[str] = set()
        for pack_id in parent.evidence_pack_ids:
            pack = self._repository.get_evidence_pack(pack_id, actor.workspace_id)
            if isinstance(pack, EvidencePack):
                evidence_hashes.add(pack.pack_hash)
        if changed_evidence_hash in evidence_hashes:
            return parent
        raw_key = idempotency_key or stable_id(
            "propagation-invalidation-key", actor.workspace_id, parent.graph_revision_id, changed_evidence_hash
        ).removeprefix("propagation-invalidation-key-")
        command = InvalidatePropagationCommand(
            graph_revision_id=parent.graph_revision_id,
            expected_graph_record_version=parent.record_version,
            changed_evidence_hash=changed_evidence_hash,
            reason="bound evidence hash changed",
            idempotency_key=raw_key,
        )
        return self._invalidate(command, actor)

    def get_run(self, run_id: str, actor: ActorContext) -> PropagationRun:
        run = self._repository.get_run(run_id, actor.workspace_id)
        if run is None:
            raise PropagationError("FMEA_PROPAGATION_RUN_NOT_FOUND", "propagation run was not found")
        return run

    def get_graph(self, analysis_id: str, actor: ActorContext) -> PropagationGraphRevision | None:
        return self._repository.get_current_graph(analysis_id, actor.workspace_id)


class PropagationReviewService(PropagationAnalysisService):
    """Persistence-backed human authority kept separate from proposal generation."""

    def confirm_graph(self, command: ConfirmPropagationCommand, actor: ActorContext) -> PropagationReviewResult:
        return self._confirm_graph(command, actor)

    def invalidate(self, command: InvalidatePropagationCommand, actor: ActorContext) -> PropagationGraphRevision:
        return self._invalidate(command, actor)

    def invalidate_if_stale(
        self, analysis_id: str, changed_evidence_hash: str, actor: ActorContext, idempotency_key: str | None = None
    ) -> PropagationGraphRevision | None:
        return self._invalidate_if_stale(analysis_id, changed_evidence_hash, actor, idempotency_key)


__all__ = [
    "PROPAGATION_TEMPLATE_ID",
    "PROPAGATION_TEMPLATE_VERSION",
    "ConfirmPropagationCommand",
    "InvalidatePropagationCommand",
    "PreparedPropagationInvalidation",
    "PreparedPropagationProposal",
    "PreparedPropagationReview",
    "PropagationAnalysisService",
    "PropagationCandidateInterface",
    "PropagationDecisionAction",
    "PropagationEdgeDecision",
    "PropagationEdgeProposal",
    "PropagationError",
    "PropagationModelRequest",
    "PropagationRepository",
    "PropagationReviewResult",
    "PropagationReviewService",
    "PropagationRun",
    "PropagationSuggestionGenerator",
    "StartPropagationCommand",
    "propagation_invalidation_payload",
    "propagation_invalidation_payload_hash",
    "propagation_review_payload",
    "propagation_review_payload_hash",
]
