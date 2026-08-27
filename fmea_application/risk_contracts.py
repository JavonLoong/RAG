"""Immutable persistence handoffs for the model-assisted FMEA risk workflow.

This module deliberately contains no repository or transport code.  The domain
objects remain the source of truth; the prepared contracts only bind those
objects to the transaction metadata required by a persistence adapter.
"""

# These application contracts intentionally raise ValueError for invalid input,
# matching the existing immutable assistance/review contracts.
# ruff: noqa: TRY003, TRY004

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from types import MappingProxyType

from core_domain.fmea.scoring import RiskAssessmentRecord, RiskProposal
from core_domain.fmea.states import ActorType, RiskStatus

from .assistance_contracts import AssistanceDecision, AssistanceSuggestion
from .review_contracts import AuditEvent, IdempotencyScope

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_TEXT_LENGTH = 256
_MAX_REASON_LENGTH = 4096
_MAX_PAYLOAD_DEPTH = 8
_MAX_PAYLOAD_ITEMS = 128


def _text(value: object, field_name: str, *, limit: int = _MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    normalized = value.strip()
    if len(normalized) > limit:
        raise ValueError(f"{field_name} must be at most {limit} characters")
    return normalized


def _positive(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


def _hash(value: object, field_name: str) -> str:
    normalized = _text(value, field_name, limit=71)
    if _HASH_PATTERN.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must be a canonical SHA-256 hash")
    return normalized


def _freeze_json(value: object, *, depth: int = 0, active: frozenset[int] = frozenset()) -> object:  # noqa: C901
    if depth > _MAX_PAYLOAD_DEPTH:
        raise ValueError(f"payload exceeds maximum depth {_MAX_PAYLOAD_DEPTH}")
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("payload numbers must be finite")
        return value
    if isinstance(value, Mapping):
        container_id = id(value)
        if container_id in active:
            raise ValueError("payload must not contain cycles")
        if len(value) > _MAX_PAYLOAD_ITEMS:
            raise ValueError(f"payload mappings must contain at most {_MAX_PAYLOAD_ITEMS} items")
        items: list[tuple[str, object]] = []
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("payload object keys must be non-empty strings")
            items.append((key, _freeze_json(item, depth=depth + 1, active=active | {container_id})))
        return MappingProxyType(dict(sorted(items)))
    if isinstance(value, tuple | list):
        container_id = id(value)
        if container_id in active:
            raise ValueError("payload must not contain cycles")
        if len(value) > _MAX_PAYLOAD_ITEMS:
            raise ValueError(f"payload arrays must contain at most {_MAX_PAYLOAD_ITEMS} items")
        return tuple(_freeze_json(item, depth=depth + 1, active=active | {container_id}) for item in value)
    raise ValueError("payload must contain only JSON values")


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    return value


def canonical_json(value: object) -> str:
    """Return compact deterministic JSON for persistence payloads."""

    frozen = _freeze_json(value)
    return json.dumps(_json_value(frozen), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def outbox_payload_hash(payload: object) -> str:
    return "sha256:" + sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _payload(value: object) -> Mapping[str, object]:
    frozen = _freeze_json(value)
    if not isinstance(frozen, Mapping):
        raise ValueError("payload must be a JSON object")
    canonical_json(frozen)
    return frozen


def _validate_scope(scope: object, payload_hash: object, workspace_id: str, actor_id: str) -> str:
    if not isinstance(scope, IdempotencyScope):
        raise ValueError("scope must be an IdempotencyScope")
    normalized_hash = _hash(payload_hash, "payload_hash")
    if scope.workspace_id != workspace_id:
        raise ValueError("scope workspace does not match resource workspace")
    if scope.actor_id != actor_id:
        raise ValueError("scope actor does not match resource actor")
    return normalized_hash


def _validate_audit(
    audit: object,
    *,
    workspace_id: str,
    row_id: str | None = None,
    actor_id: str | None = None,
    actor_type: ActorType | None = None,
    suggestion_id: str | None = None,
    decision_id: str | None = None,
) -> AuditEvent:
    if not isinstance(audit, AuditEvent):
        raise ValueError("audit must be an AuditEvent")
    if audit.workspace_id != workspace_id:
        raise ValueError("audit workspace does not match resource workspace")
    if row_id is not None and audit.row_id != row_id:
        raise ValueError("audit row identity does not match resource")
    if actor_id is not None and audit.actor_id != actor_id:
        raise ValueError("audit actor does not match resource actor")
    if actor_type is not None and audit.actor_type is not actor_type:
        raise ValueError(f"audit requires {actor_type.value} actor")
    if suggestion_id is not None and audit.suggestion_id != suggestion_id:
        raise ValueError("audit suggestion identity does not match resource")
    if decision_id is not None and audit.decision_id != decision_id:
        raise ValueError("audit decision identity does not match resource")
    if audit.action is not None:
        raise ValueError("risk persistence audit action must be None")
    return audit


def _validate_assessment_identity(
    proposal: RiskProposal,
    assessment: RiskAssessmentRecord,
    *,
    expected_status: RiskStatus,
) -> None:
    if not isinstance(proposal, RiskProposal):
        raise ValueError("proposal must be a RiskProposal")
    if not isinstance(assessment, RiskAssessmentRecord):
        raise ValueError("assessment must be a RiskAssessmentRecord")
    if assessment.status is not expected_status:
        raise ValueError(f"assessment status must be {expected_status.value}")
    for field_name in (
        "workspace_id",
        "row_id",
        "source_record_version",
        "evidence_pack_id",
        "domain_pack_id",
        "domain_pack_version",
        "rule_pack_id",
        "rule_pack_version",
    ):
        if getattr(assessment, field_name) != getattr(proposal, field_name):
            raise ValueError(f"assessment {field_name} does not match proposal")
    if assessment.proposal_id != proposal.proposal_id:
        raise ValueError("assessment proposal identity does not match proposal")
    if assessment.assistance_suggestion_id != proposal.assistance_suggestion_id:
        raise ValueError("assessment suggestion identity does not match proposal")
    if assessment.dimensions != proposal.dimensions:
        raise ValueError("assessment dimensions do not match proposal")


@dataclass(frozen=True, slots=True)
class PreparedAssistanceSuggestion:
    scope: IdempotencyScope
    payload_hash: str
    suggestion: AssistanceSuggestion[object]
    audit: AuditEvent

    def __post_init__(self) -> None:
        if not isinstance(self.scope, IdempotencyScope):
            raise ValueError("scope must be an IdempotencyScope")
        if not isinstance(self.audit, AuditEvent):
            raise ValueError("audit must be an AuditEvent")
        if not isinstance(self.suggestion, AssistanceSuggestion):
            raise ValueError("suggestion must be an AssistanceSuggestion")
        object.__setattr__(
            self,
            "payload_hash",
            _validate_scope(self.scope, self.payload_hash, self.suggestion.workspace_id, self.audit.actor_id),
        )
        if self.audit.suggestion_id != self.suggestion.suggestion_id:
            raise ValueError("audit suggestion identity does not match suggestion")
        _validate_audit(
            self.audit,
            workspace_id=self.suggestion.workspace_id,
            actor_id=self.scope.actor_id,
            suggestion_id=self.suggestion.suggestion_id,
        )
        if self.audit.decision_id is not None:
            raise ValueError("suggestion audit must not contain a decision identity")


@dataclass(frozen=True, slots=True)
class PreparedAssistanceDecision:
    scope: IdempotencyScope
    payload_hash: str
    suggestion: AssistanceSuggestion[object]
    decision: AssistanceDecision
    audit: AuditEvent

    def __post_init__(self) -> None:
        if not isinstance(self.scope, IdempotencyScope):
            raise ValueError("scope must be an IdempotencyScope")
        if not isinstance(self.audit, AuditEvent):
            raise ValueError("audit must be an AuditEvent")
        if not isinstance(self.suggestion, AssistanceSuggestion):
            raise ValueError("suggestion must be an AssistanceSuggestion")
        if not isinstance(self.decision, AssistanceDecision):
            raise ValueError("decision must be an AssistanceDecision")
        if self.decision.suggestion_id != self.suggestion.suggestion_id:
            raise ValueError("decision suggestion identity does not match suggestion")
        if self.decision.suggestion_hash != self.suggestion.suggestion_hash:
            raise ValueError("decision suggestion hash does not match suggestion")
        if self.decision.suggestion_record_version != self.suggestion.record_version:
            raise ValueError("decision suggestion version does not match suggestion")
        if self.decision.target_record_version != self.suggestion.target_record_version:
            raise ValueError("decision target version does not match suggestion")
        object.__setattr__(
            self,
            "payload_hash",
            _validate_scope(self.scope, self.payload_hash, self.suggestion.workspace_id, self.decision.actor_id),
        )
        _validate_audit(
            self.audit,
            workspace_id=self.suggestion.workspace_id,
            actor_id=self.decision.actor_id,
            actor_type=ActorType.HUMAN,
            suggestion_id=self.suggestion.suggestion_id,
            decision_id=self.decision.decision_id,
        )


@dataclass(frozen=True, slots=True)
class PreparedRiskProposal:
    scope: IdempotencyScope
    payload_hash: str
    proposal: RiskProposal
    assessment: RiskAssessmentRecord
    audit: AuditEvent

    def __post_init__(self) -> None:
        if not isinstance(self.scope, IdempotencyScope):
            raise ValueError("scope must be an IdempotencyScope")
        if not isinstance(self.audit, AuditEvent):
            raise ValueError("audit must be an AuditEvent")
        _validate_assessment_identity(self.proposal, self.assessment, expected_status=RiskStatus.PROPOSED)
        if self.assessment.derived is not None:
            raise ValueError("proposed assessment must not contain derived risk")
        if self.assessment.confirmer_actor_id is not None or self.assessment.invalidated_reason is not None:
            raise ValueError("proposed assessment contains terminal state")
        object.__setattr__(
            self,
            "payload_hash",
            _validate_scope(self.scope, self.payload_hash, self.proposal.workspace_id, self.audit.actor_id),
        )
        _validate_audit(
            self.audit,
            workspace_id=self.proposal.workspace_id,
            row_id=self.proposal.row_id,
            actor_id=self.scope.actor_id,
            suggestion_id=self.proposal.assistance_suggestion_id,
        )


@dataclass(frozen=True, slots=True)
class PreparedRiskConfirmation:
    scope: IdempotencyScope
    payload_hash: str
    proposal: RiskProposal
    previous_assessment: RiskAssessmentRecord
    assessment: RiskAssessmentRecord
    expected_assessment_version: int
    decision_id: str
    audit: AuditEvent

    def __post_init__(self) -> None:
        expected = _positive(self.expected_assessment_version, "expected_assessment_version")
        object.__setattr__(self, "expected_assessment_version", expected)
        decision_id = _text(self.decision_id, "decision_id")
        object.__setattr__(self, "decision_id", decision_id)
        if not isinstance(self.scope, IdempotencyScope):
            raise ValueError("scope must be an IdempotencyScope")
        if not isinstance(self.audit, AuditEvent):
            raise ValueError("audit must be an AuditEvent")
        if not isinstance(self.previous_assessment, RiskAssessmentRecord):
            raise ValueError("previous_assessment must be a RiskAssessmentRecord")
        _validate_assessment_identity(self.proposal, self.previous_assessment, expected_status=self.previous_assessment.status)
        if self.previous_assessment.status not in (RiskStatus.PROPOSED, RiskStatus.REVIEWED):
            raise ValueError("confirmation previous assessment status is not confirmable")
        if self.previous_assessment.record_version != expected:
            raise ValueError("expected assessment version does not match previous assessment")
        _validate_assessment_identity(self.proposal, self.assessment, expected_status=RiskStatus.CONFIRMED)
        if self.assessment.assessment_id != self.previous_assessment.assessment_id:
            raise ValueError("confirmation must retain assessment identity")
        if self.assessment.record_version != expected + 1:
            raise ValueError("confirmed assessment version must increment by one")
        if self.audit.actor_type is not ActorType.HUMAN:
            raise ValueError("confirmation requires a human actor")
        if self.assessment.confirmer_actor_id != self.audit.actor_id:
            raise ValueError("confirmed assessment confirmer does not match audit actor")
        object.__setattr__(
            self,
            "payload_hash",
            _validate_scope(self.scope, self.payload_hash, self.proposal.workspace_id, self.audit.actor_id),
        )
        _validate_audit(
            self.audit,
            workspace_id=self.proposal.workspace_id,
            row_id=self.proposal.row_id,
            actor_id=self.scope.actor_id,
            actor_type=ActorType.HUMAN,
            suggestion_id=self.proposal.assistance_suggestion_id,
            decision_id=self.decision_id,
        )


@dataclass(frozen=True, slots=True)
class PreparedRiskRejection:
    scope: IdempotencyScope
    payload_hash: str
    proposal: RiskProposal
    previous_assessment: RiskAssessmentRecord
    assessment: RiskAssessmentRecord
    expected_assessment_version: int
    decision_id: str
    audit: AuditEvent

    def __post_init__(self) -> None:
        expected = _positive(self.expected_assessment_version, "expected_assessment_version")
        object.__setattr__(self, "expected_assessment_version", expected)
        object.__setattr__(self, "decision_id", _text(self.decision_id, "decision_id"))
        if not isinstance(self.scope, IdempotencyScope):
            raise ValueError("scope must be an IdempotencyScope")
        if not isinstance(self.audit, AuditEvent):
            raise ValueError("audit must be an AuditEvent")
        if not isinstance(self.previous_assessment, RiskAssessmentRecord):
            raise ValueError("previous_assessment must be a RiskAssessmentRecord")
        if self.previous_assessment.status not in (RiskStatus.PROPOSED, RiskStatus.REVIEWED):
            raise ValueError("rejection previous assessment status is not rejectable")
        _validate_assessment_identity(self.proposal, self.previous_assessment, expected_status=self.previous_assessment.status)
        _validate_assessment_identity(self.proposal, self.assessment, expected_status=RiskStatus.REVIEWED)
        if self.previous_assessment.record_version != expected:
            raise ValueError("expected assessment version does not match previous assessment")
        if self.assessment.assessment_id != self.previous_assessment.assessment_id:
            raise ValueError("rejection must retain assessment identity")
        if self.assessment.record_version != expected + 1:
            raise ValueError("reviewed assessment version must increment by one")
        if self.assessment.derived is not None or self.assessment.confirmer_actor_id is not None:
            raise ValueError("rejected assessment must remain unconfirmed")
        object.__setattr__(
            self,
            "payload_hash",
            _validate_scope(self.scope, self.payload_hash, self.proposal.workspace_id, self.audit.actor_id),
        )
        _validate_audit(
            self.audit,
            workspace_id=self.proposal.workspace_id,
            row_id=self.proposal.row_id,
            actor_id=self.scope.actor_id,
            actor_type=ActorType.HUMAN,
            suggestion_id=self.proposal.assistance_suggestion_id,
            decision_id=self.decision_id,
        )


@dataclass(frozen=True, slots=True)
class PreparedRiskInvalidation:
    scope: IdempotencyScope
    payload_hash: str
    previous_assessment: RiskAssessmentRecord
    assessment: RiskAssessmentRecord
    expected_assessment_version: int
    decision_id: str
    audit: AuditEvent

    def __post_init__(self) -> None:  # noqa: C901
        expected = _positive(self.expected_assessment_version, "expected_assessment_version")
        object.__setattr__(self, "expected_assessment_version", expected)
        object.__setattr__(self, "decision_id", _text(self.decision_id, "decision_id"))
        if not isinstance(self.scope, IdempotencyScope):
            raise ValueError("scope must be an IdempotencyScope")
        if not isinstance(self.audit, AuditEvent):
            raise ValueError("audit must be an AuditEvent")
        if not isinstance(self.previous_assessment, RiskAssessmentRecord):
            raise ValueError("previous_assessment must be a RiskAssessmentRecord")
        if not isinstance(self.assessment, RiskAssessmentRecord):
            raise ValueError("assessment must be a RiskAssessmentRecord")
        if self.assessment.status is not RiskStatus.INVALIDATED:
            raise ValueError("invalidated assessment status is required")
        if self.previous_assessment.status is RiskStatus.INVALIDATED:
            raise ValueError("invalidated assessment cannot be invalidated again")
        if self.previous_assessment.workspace_id != self.assessment.workspace_id:
            raise ValueError("invalidation workspace does not match")
        if self.previous_assessment.row_id != self.assessment.row_id:
            raise ValueError("invalidation row identity does not match")
        if self.previous_assessment.proposal_id != self.assessment.proposal_id:
            raise ValueError("invalidation proposal identity does not match")
        if self.previous_assessment.status is RiskStatus.CONFIRMED:
            if self.assessment.assessment_id == self.previous_assessment.assessment_id:
                raise ValueError("confirmed assessment must remain historical")
            if self.previous_assessment.record_version != expected:
                raise ValueError("expected assessment version does not match previous assessment")
            if self.assessment.record_version != expected + 1:
                raise ValueError("invalidated successor version must increment by one")
        else:
            if self.assessment.assessment_id != self.previous_assessment.assessment_id:
                raise ValueError("non-confirmed invalidation must retain assessment identity")
            if self.previous_assessment.record_version != expected:
                raise ValueError("expected assessment version does not match previous assessment")
            if self.assessment.record_version != expected + 1:
                raise ValueError("invalidated assessment version must increment by one")
        object.__setattr__(
            self,
            "payload_hash",
            _validate_scope(self.scope, self.payload_hash, self.assessment.workspace_id, self.audit.actor_id),
        )
        _validate_audit(
            self.audit,
            workspace_id=self.assessment.workspace_id,
            row_id=self.assessment.row_id,
            actor_id=self.scope.actor_id,
            decision_id=self.decision_id,
        )
        if self.audit.actor_type is ActorType.MODEL:
            raise ValueError("invalidation cannot be performed by a model actor")


@dataclass(frozen=True, slots=True)
class RiskConfirmationResult:
    assessment: RiskAssessmentRecord
    decision_id: str
    audit_event_id: str
    outbox_event_id: str
    replayed: bool = False
    persisted: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.assessment, RiskAssessmentRecord):
            raise ValueError("assessment must be a RiskAssessmentRecord")
        if self.assessment.status is not RiskStatus.CONFIRMED:
            raise ValueError("confirmation result requires a confirmed assessment")
        for field_name in ("decision_id", "audit_event_id", "outbox_event_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        if not isinstance(self.replayed, bool) or not isinstance(self.persisted, bool):
            raise ValueError("replayed and persisted must be booleans")


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    event_id: str
    workspace_id: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: Mapping[str, object]
    payload_hash: str
    created_at: str
    scope_key: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("event_id", "workspace_id", "aggregate_type", "aggregate_id", "event_type", "created_at"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        frozen_payload = _payload(self.payload)
        object.__setattr__(self, "payload", frozen_payload)
        normalized_hash = _hash(self.payload_hash, "payload_hash")
        if normalized_hash != outbox_payload_hash(frozen_payload):
            raise ValueError("outbox payload hash does not match payload")
        object.__setattr__(self, "payload_hash", normalized_hash)
        if self.scope_key is not None:
            object.__setattr__(self, "scope_key", _text(self.scope_key, "scope_key", limit=128))


__all__ = [
    "OutboxEvent",
    "PreparedAssistanceDecision",
    "PreparedAssistanceSuggestion",
    "PreparedRiskConfirmation",
    "PreparedRiskInvalidation",
    "PreparedRiskProposal",
    "PreparedRiskRejection",
    "RiskConfirmationResult",
    "canonical_json",
    "outbox_payload_hash",
]
