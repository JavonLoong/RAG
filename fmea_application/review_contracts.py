"""Immutable application contracts for the review-only FMEA interface."""

# Review constructors intentionally expose ValueError for invalid contract data.
# The project Ruff profile recommends TypeError for some of these branches.
# ruff: noqa: TRY004

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from hashlib import sha256
from typing import Literal, TypeVar, cast
from uuid import UUID

from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.states import (
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
    RunStatus,
)
from core_domain.fmea.value_objects import EvidencePack, VersionSet
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile

from .review_errors import REVIEW_ERROR_CODES

EDITABLE_REVIEW_FIELDS = frozenset(
    {
        "failure_mode",
        "causes",
        "mechanisms",
        "effects",
        "symptoms",
        "controls",
        "barriers",
        "actions",
    }
)

_MAX_ID_LENGTH = 256
_MAX_EVIDENCE_ID_LENGTH = 128
_MAX_REASON_LENGTH = 500
_MAX_QUESTION_LENGTH = 1000
_MAX_DESCRIPTION_LENGTH = 500
_MAX_VALUE_LENGTH = 4000
_MAX_VALUE_ITEM_LENGTH = 1000
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_PLAIN_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_UNRESOLVED_CLAIM_STATUSES = frozenset(
    {
        ClaimStatus.UNKNOWN,
        ClaimStatus.INSUFFICIENT_EVIDENCE,
        ClaimStatus.CONFLICT,
    }
)

_T = TypeVar("_T")


def _text(value: object, field_name: str, *, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")  # noqa: TRY003
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")  # noqa: TRY003
    if len(normalized) > limit:
        raise ValueError(f"{field_name} must be at most {limit} characters")  # noqa: TRY003
    if any(ord(character) < 32 and character not in {"\n", "\r", "\t"} for character in normalized):
        raise ValueError(f"{field_name} contains a control character")  # noqa: TRY003
    return normalized


def _label(value: object, field_name: str) -> str:
    return _text(value, field_name, limit=_MAX_ID_LENGTH)


def _tuple(value: object, field_name: str) -> tuple[object, ...]:
    if isinstance(value, str | bytes) or value is None:
        raise ValueError(f"{field_name} must be a tuple or list")  # noqa: TRY003
    try:
        return tuple(cast(Iterable[object], value))
    except TypeError as exc:
        raise ValueError(f"{field_name} must be a tuple or list") from exc  # noqa: TRY003


def _strings(
    value: object,
    field_name: str,
    *,
    limit: int = _MAX_ID_LENGTH,
    max_items: int | None = None,
    unique: bool = False,
) -> tuple[str, ...]:
    normalized = tuple(_text(item, field_name, limit=limit) for item in _tuple(value, field_name))
    if max_items is not None and len(normalized) > max_items:
        raise ValueError(f"{field_name} must contain at most {max_items} items")  # noqa: TRY003
    if unique and len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")  # noqa: TRY003
    return normalized


def _enum(value: object, expected: type[_T], field_name: str) -> _T:
    if not isinstance(value, expected):
        raise ValueError(f"{field_name} must be a {expected.__name__}")  # noqa: TRY003
    return value


def _positive(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be positive")  # noqa: TRY003
    return value


def _hash(value: object, field_name: str) -> str:
    normalized = _text(value, field_name, limit=71)
    if not _HASH_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex>")  # noqa: TRY003
    return normalized


def _pack_hash(value: object, field_name: str) -> str:
    normalized = _text(value, field_name, limit=71)
    if not (_HASH_PATTERN.fullmatch(normalized) or _PLAIN_HASH_PATTERN.fullmatch(normalized)):
        raise ValueError(f"{field_name} must be a SHA-256 hash")  # noqa: TRY003
    return normalized


def _timestamp(value: object, field_name: str) -> str:
    normalized = _text(value, field_name, limit=64)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 UTC timestamp") from exc  # noqa: TRY003
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be a timezone-aware UTC timestamp")  # noqa: TRY003
    return normalized


def _optional_timestamp(value: object, field_name: str) -> str | None:
    return None if value is None else _timestamp(value, field_name)


def _uuid(value: object, field_name: str) -> str:
    normalized = _text(value, field_name, limit=36)
    try:
        parsed = UUID(normalized)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a canonical lowercase UUID") from exc  # noqa: TRY003
    if str(parsed) != normalized:
        raise ValueError(f"{field_name} must be a canonical lowercase UUID")  # noqa: TRY003
    return normalized


def _editable_field(value: object, field_name: str = "target_field") -> str:
    normalized = _label(value, field_name)
    if normalized not in EDITABLE_REVIEW_FIELDS:
        raise ValueError(f"{field_name} is not an editable review field")  # noqa: TRY003
    return normalized


def _evidence_ids(value: object, field_name: str = "evidence_ids", *, minimum: int = 0) -> tuple[str, ...]:
    normalized = _strings(
        value,
        field_name,
        limit=_MAX_EVIDENCE_ID_LENGTH,
        max_items=32,
        unique=True,
    )
    if len(normalized) < minimum:
        raise ValueError(f"{field_name} must contain at least {minimum} items")  # noqa: TRY003
    return normalized


def _string_value(value: object, field_name: str) -> str | tuple[str, ...]:
    if isinstance(value, str):
        return _text(value, field_name, limit=_MAX_VALUE_LENGTH)
    normalized = _strings(
        value,
        field_name,
        limit=_MAX_VALUE_ITEM_LENGTH,
        max_items=64,
        unique=True,
    )
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")  # noqa: TRY003
    return normalized


def _tuple_of(value: object, expected: type[_T], field_name: str) -> tuple[_T, ...]:
    normalized = _tuple(value, field_name)
    result: list[_T] = []
    for item in normalized:
        if not isinstance(item, expected):
            raise ValueError(f"{field_name} contains an invalid item")  # noqa: TRY003
        result.append(item)
    return tuple(result)


def _tuple_of_unique(value: object, expected: type[_T], field_name: str) -> tuple[_T, ...]:
    normalized = _tuple_of(value, expected, field_name)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")  # noqa: TRY003
    return normalized


def _field_claim_statuses(value: object) -> tuple[tuple[str, ClaimStatus], ...]:
    raw = _tuple(value, "field_claim_statuses")
    result: list[tuple[str, ClaimStatus]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, tuple | list) or len(item) != 2:
            raise ValueError("field_claim_statuses must contain field/status pairs")  # noqa: TRY003
        field_name = _editable_field(item[0])
        status = _enum(item[1], ClaimStatus, "field_claim_statuses status")
        if field_name in seen:
            raise ValueError(f"duplicate field_claim_statuses field: {field_name}")  # noqa: TRY003
        seen.add(field_name)
        result.append((field_name, status))
    return tuple(result)


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, frozenset):
        return sorted(str(_json_value(item)) for item in value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _canonical_hash(value: object, *, prefixed: bool = True) -> str:
    digest = sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}" if prefixed else digest


def _validate_contract_tuple(value: object, expected: type[_T], field_name: str) -> tuple[_T, ...]:
    return _tuple_of(value, expected, field_name)


class ReviewAction(str, Enum):
    ACCEPT = "accept"
    MODIFY_AND_ACCEPT = "modify_and_accept"
    REJECT = "reject"
    REQUEST_EVIDENCE = "request_evidence"
    DEFER = "defer"


class ReviewJudgement(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"
    NOT_APPLICABLE = "not_applicable"


class ReviewReasonCode(str, Enum):
    ACCEPT_AS_IS = "ACCEPT_AS_IS"
    FIELD_CORRECTION = "FIELD_CORRECTION"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
    CONFLICT_UNRESOLVED = "CONFLICT_UNRESOLVED"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    DEFERRED_FOR_EXPERT = "DEFERRED_FOR_EXPERT"
    HUMAN_OVERRIDE = "HUMAN_OVERRIDE"
    OTHER = "OTHER"


class ReviewPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class ActorContext:
    actor_id: str
    actor_type: ActorType
    roles: frozenset[str]
    workspace_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor_id", _label(self.actor_id, "actor_id"))
        object.__setattr__(self, "actor_type", _enum(self.actor_type, ActorType, "actor_type"))
        roles = frozenset(_strings(self.roles, "roles", max_items=64, unique=True))
        object.__setattr__(self, "roles", roles)
        object.__setattr__(self, "workspace_id", _label(self.workspace_id, "workspace_id"))


@dataclass(frozen=True, slots=True)
class FieldReviewEdit:
    target_field: str
    operation: Literal["replace"]
    value: str | tuple[str, ...]
    claim_status: ClaimStatus
    support_status: EvidenceSupportStatus
    evidence_ids: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_field", _editable_field(self.target_field))
        if self.operation != "replace":
            raise ValueError("operation must be replace")  # noqa: TRY003
        object.__setattr__(self, "value", _string_value(self.value, "value"))
        object.__setattr__(self, "claim_status", _enum(self.claim_status, ClaimStatus, "claim_status"))
        object.__setattr__(self, "support_status", _enum(self.support_status, EvidenceSupportStatus, "support_status"))
        evidence_ids = _evidence_ids(self.evidence_ids)
        object.__setattr__(self, "evidence_ids", evidence_ids)
        object.__setattr__(self, "reason", _text(self.reason, "reason", limit=_MAX_REASON_LENGTH))
        if self.claim_status is ClaimStatus.KNOWN:
            if not evidence_ids:
                raise ValueError("known claim requires evidence")  # noqa: TRY003
            if self.support_status in {
                EvidenceSupportStatus.CONTRADICTED,
                EvidenceSupportStatus.NOT_SUPPORTED,
            }:
                raise ValueError("known claim cannot use contradicted or not_supported evidence")  # noqa: TRY003
        if self.target_field == "failure_mode" and not isinstance(self.value, str):
            raise ValueError("failure_mode value must be a string")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class ReviewSourceSnapshot:
    row_id: str
    source_record_version: int
    candidate_id: str
    item_label: str
    function_label: str
    template_id: str
    template_version: str
    profile_id: str
    profile_version: str
    generation_run_id: str
    requested_evidence_profile: EvidenceSelectionProfile
    resolved_evidence_profile: EvidenceSelectionProfile
    evidence_types: tuple[CitationType, ...]
    trace_id: str
    retrieval_warnings: tuple[str, ...]
    retrieval_incomplete: bool
    field_claim_statuses: tuple[tuple[str, ClaimStatus], ...]
    source_hash: str

    def __post_init__(self) -> None:
        for field_name in (
            "row_id",
            "candidate_id",
            "template_id",
            "template_version",
            "profile_id",
            "profile_version",
            "generation_run_id",
            "trace_id",
        ):
            object.__setattr__(self, field_name, _label(getattr(self, field_name), field_name))
        object.__setattr__(self, "item_label", _label(self.item_label, "item_label"))
        object.__setattr__(self, "function_label", _label(self.function_label, "function_label"))
        object.__setattr__(self, "source_record_version", _positive(self.source_record_version, "source_record_version"))
        object.__setattr__(
            self,
            "requested_evidence_profile",
            _enum(self.requested_evidence_profile, EvidenceSelectionProfile, "requested_evidence_profile"),
        )
        object.__setattr__(
            self,
            "resolved_evidence_profile",
            _enum(self.resolved_evidence_profile, EvidenceSelectionProfile, "resolved_evidence_profile"),
        )
        evidence_types = _tuple_of_unique(self.evidence_types, CitationType, "evidence_types")
        object.__setattr__(self, "evidence_types", evidence_types)
        object.__setattr__(self, "retrieval_warnings", _strings(self.retrieval_warnings, "retrieval_warnings", limit=4000))
        if not isinstance(self.retrieval_incomplete, bool):
            raise ValueError("retrieval_incomplete must be a boolean")  # noqa: TRY003
        object.__setattr__(self, "field_claim_statuses", _field_claim_statuses(self.field_claim_statuses))
        object.__setattr__(self, "source_hash", _hash(self.source_hash, "source_hash"))

    @classmethod
    def build(
        cls,
        *,
        row_id: str,
        source_record_version: int,
        candidate_id: str,
        item_label: str,
        function_label: str,
        template_id: str,
        template_version: str,
        profile_id: str,
        profile_version: str,
        generation_run_id: str,
        requested_evidence_profile: EvidenceSelectionProfile,
        resolved_evidence_profile: EvidenceSelectionProfile,
        evidence_types: tuple[CitationType, ...],
        trace_id: str,
        retrieval_warnings: tuple[str, ...],
        retrieval_incomplete: bool,
        field_claim_statuses: tuple[tuple[str, ClaimStatus], ...],
    ) -> ReviewSourceSnapshot:
        candidate = cls(
            row_id=row_id,
            source_record_version=source_record_version,
            candidate_id=candidate_id,
            item_label=item_label,
            function_label=function_label,
            template_id=template_id,
            template_version=template_version,
            profile_id=profile_id,
            profile_version=profile_version,
            generation_run_id=generation_run_id,
            requested_evidence_profile=requested_evidence_profile,
            resolved_evidence_profile=resolved_evidence_profile,
            evidence_types=evidence_types,
            trace_id=trace_id,
            retrieval_warnings=retrieval_warnings,
            retrieval_incomplete=retrieval_incomplete,
            field_claim_statuses=field_claim_statuses,
            source_hash="sha256:" + "0" * 64,
        )
        payload = {
            field.name: getattr(candidate, field.name)
            for field in fields(candidate)
            if field.name != "source_hash"
        }
        return replace(candidate, source_hash=_canonical_hash(payload))


@dataclass(frozen=True, slots=True)
class FieldFinding:
    target_field: str
    judgement: ReviewJudgement
    recommended_claim_status: ClaimStatus
    evidence_ids: tuple[str, ...]
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_field", _editable_field(self.target_field))
        object.__setattr__(self, "judgement", _enum(self.judgement, ReviewJudgement, "judgement"))
        object.__setattr__(
            self,
            "recommended_claim_status",
            _enum(self.recommended_claim_status, ClaimStatus, "recommended_claim_status"),
        )
        object.__setattr__(self, "evidence_ids", _evidence_ids(self.evidence_ids))
        object.__setattr__(self, "rationale", _text(self.rationale, "rationale", limit=_MAX_REASON_LENGTH))


@dataclass(frozen=True, slots=True)
class EvidenceRequestItem:
    target_field: str
    question: str
    preferred_source_types: tuple[str, ...]
    priority: ReviewPriority

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_field", _editable_field(self.target_field))
        object.__setattr__(self, "question", _text(self.question, "question", limit=_MAX_QUESTION_LENGTH))
        object.__setattr__(
            self,
            "preferred_source_types",
            _strings(self.preferred_source_types, "preferred_source_types", limit=64, max_items=16, unique=True),
        )
        object.__setattr__(self, "priority", _enum(self.priority, ReviewPriority, "priority"))


@dataclass(frozen=True, slots=True)
class MissingEvidenceItem:
    target_field: str
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_field", _editable_field(self.target_field))
        object.__setattr__(self, "description", _text(self.description, "description", limit=_MAX_DESCRIPTION_LENGTH))


@dataclass(frozen=True, slots=True)
class ConflictItem:
    target_field: str
    evidence_ids: tuple[str, ...]
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_field", _editable_field(self.target_field))
        object.__setattr__(self, "evidence_ids", _evidence_ids(self.evidence_ids, minimum=2))
        object.__setattr__(self, "description", _text(self.description, "description", limit=_MAX_DESCRIPTION_LENGTH))


@dataclass(frozen=True, slots=True)
class UnresolvedAcknowledgement:
    target_field: str
    claim_status: ClaimStatus
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_field", _editable_field(self.target_field))
        status = _enum(self.claim_status, ClaimStatus, "claim_status")
        if status not in _UNRESOLVED_CLAIM_STATUSES:
            raise ValueError("unresolved acknowledgement claim_status must be unknown, insufficient_evidence, or conflict")  # noqa: TRY003
        object.__setattr__(self, "claim_status", status)
        object.__setattr__(self, "reason", _text(self.reason, "reason", limit=_MAX_REASON_LENGTH))


@dataclass(frozen=True, slots=True)
class ReviewModelManifest:
    provider: str
    model: str
    template_id: str
    template_version: str
    prompt_hash: str

    def __post_init__(self) -> None:
        for field_name in ("provider", "model", "template_id", "template_version"):
            object.__setattr__(self, field_name, _label(getattr(self, field_name), field_name))
        object.__setattr__(self, "prompt_hash", _hash(self.prompt_hash, "prompt_hash"))


@dataclass(frozen=True, slots=True)
class ReviewSuggestionDraft:
    recommended_action: ReviewAction
    field_findings: tuple[FieldFinding, ...]
    proposed_edits: tuple[FieldReviewEdit, ...]
    evidence_requests: tuple[EvidenceRequestItem, ...]
    missing_evidence: tuple[MissingEvidenceItem, ...]
    conflicts: tuple[ConflictItem, ...]
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "recommended_action", _enum(self.recommended_action, ReviewAction, "recommended_action"))
        object.__setattr__(self, "field_findings", _validate_contract_tuple(self.field_findings, FieldFinding, "field_findings"))
        object.__setattr__(self, "proposed_edits", _validate_contract_tuple(self.proposed_edits, FieldReviewEdit, "proposed_edits"))
        object.__setattr__(
            self,
            "evidence_requests",
            _validate_contract_tuple(self.evidence_requests, EvidenceRequestItem, "evidence_requests"),
        )
        object.__setattr__(
            self,
            "missing_evidence",
            _validate_contract_tuple(self.missing_evidence, MissingEvidenceItem, "missing_evidence"),
        )
        object.__setattr__(self, "conflicts", _validate_contract_tuple(self.conflicts, ConflictItem, "conflicts"))
        object.__setattr__(self, "rationale", _text(self.rationale, "rationale", limit=_MAX_REASON_LENGTH))
        if len(self.field_findings) > 64:
            raise ValueError("field_findings must contain at most 64 items")  # noqa: TRY003
        if len(self.proposed_edits) > 8:
            raise ValueError("proposed_edits must contain at most 8 items")  # noqa: TRY003
        if len(self.evidence_requests) > 16:
            raise ValueError("evidence_requests must contain at most 16 items")  # noqa: TRY003
        if len(self.missing_evidence) > 16:
            raise ValueError("missing_evidence must contain at most 16 items")  # noqa: TRY003
        if len(self.conflicts) > 16:
            raise ValueError("conflicts must contain at most 16 items")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class ReviewSuggestion:
    suggestion_id: str
    run_id: str
    row_id: str
    source_record_version: int
    recommended_action: ReviewAction
    field_findings: tuple[FieldFinding, ...]
    proposed_edits: tuple[FieldReviewEdit, ...]
    evidence_requests: tuple[EvidenceRequestItem, ...]
    missing_evidence: tuple[MissingEvidenceItem, ...]
    conflicts: tuple[ConflictItem, ...]
    rationale: str
    model_manifest: ReviewModelManifest
    actor_type: ActorType
    applied: bool
    stale: bool
    created_at: str

    def __post_init__(self) -> None:
        for field_name in ("suggestion_id", "run_id", "row_id"):
            object.__setattr__(self, field_name, _label(getattr(self, field_name), field_name))
        object.__setattr__(self, "source_record_version", _positive(self.source_record_version, "source_record_version"))
        draft = ReviewSuggestionDraft(
            recommended_action=self.recommended_action,
            field_findings=self.field_findings,
            proposed_edits=self.proposed_edits,
            evidence_requests=self.evidence_requests,
            missing_evidence=self.missing_evidence,
            conflicts=self.conflicts,
            rationale=self.rationale,
        )
        for field_name in (
            "recommended_action",
            "field_findings",
            "proposed_edits",
            "evidence_requests",
            "missing_evidence",
            "conflicts",
            "rationale",
        ):
            object.__setattr__(self, field_name, getattr(draft, field_name))
        if not isinstance(self.model_manifest, ReviewModelManifest):
            raise ValueError("model_manifest must be a ReviewModelManifest")  # noqa: TRY003
        object.__setattr__(self, "actor_type", _enum(self.actor_type, ActorType, "actor_type"))
        if self.actor_type is not ActorType.MODEL:
            raise ValueError("review suggestion actor_type must be MODEL")  # noqa: TRY003
        if self.applied is not False:
            raise ValueError("review suggestion applied must be False")  # noqa: TRY003
        if not isinstance(self.stale, bool):
            raise ValueError("stale must be a boolean")  # noqa: TRY003
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))


@dataclass(frozen=True, slots=True)
class ReviewSuggestionRun:
    run_id: str
    row_id: str
    source_record_version: int
    status: RunStatus
    suggestion_id: str | None
    error_code: str | None
    retryable: bool
    request_id: str
    trace_id: str
    created_at: str
    started_at: str | None
    finished_at: str | None

    def __post_init__(self) -> None:
        for field_name in ("run_id", "row_id", "request_id", "trace_id"):
            object.__setattr__(self, field_name, _label(getattr(self, field_name), field_name))
        object.__setattr__(self, "source_record_version", _positive(self.source_record_version, "source_record_version"))
        object.__setattr__(self, "status", _enum(self.status, RunStatus, "status"))
        if self.suggestion_id is not None:
            object.__setattr__(self, "suggestion_id", _label(self.suggestion_id, "suggestion_id"))
        if self.error_code is not None:
            error_code = _label(self.error_code, "error_code")
            if error_code not in REVIEW_ERROR_CODES:
                raise ValueError("error_code is not a stable review error code")  # noqa: TRY003
            object.__setattr__(self, "error_code", error_code)
        if not isinstance(self.retryable, bool):
            raise ValueError("retryable must be a boolean")  # noqa: TRY003
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        object.__setattr__(self, "started_at", _optional_timestamp(self.started_at, "started_at"))
        object.__setattr__(self, "finished_at", _optional_timestamp(self.finished_at, "finished_at"))


@dataclass(frozen=True, slots=True)
class StartReviewSuggestionCommand:
    row_id: str
    expected_record_version: int
    idempotency_key: str
    review_policy: Literal["default"]
    focus_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_id", _label(self.row_id, "row_id"))
        object.__setattr__(self, "expected_record_version", _positive(self.expected_record_version, "expected_record_version"))
        object.__setattr__(self, "idempotency_key", _uuid(self.idempotency_key, "idempotency_key"))
        if self.review_policy != "default":
            raise ValueError("review_policy must be default")  # noqa: TRY003
        focus_fields = tuple(_editable_field(item, "focus_fields") for item in _tuple(self.focus_fields, "focus_fields"))
        if len(focus_fields) != len(set(focus_fields)):
            raise ValueError("focus_fields must not contain duplicates")  # noqa: TRY003
        if len(focus_fields) > len(EDITABLE_REVIEW_FIELDS):
            raise ValueError("focus_fields contains too many fields")  # noqa: TRY003
        object.__setattr__(self, "focus_fields", focus_fields)


@dataclass(frozen=True, slots=True)
class ReviewDecisionCommand:
    row_id: str
    expected_record_version: int
    idempotency_key: str
    action: ReviewAction
    suggestion_id: str | None
    reason_code: ReviewReasonCode
    reason: str
    edits: tuple[FieldReviewEdit, ...]
    evidence_requests: tuple[EvidenceRequestItem, ...]
    unresolved_acknowledgements: tuple[UnresolvedAcknowledgement, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_id", _label(self.row_id, "row_id"))
        object.__setattr__(self, "expected_record_version", _positive(self.expected_record_version, "expected_record_version"))
        object.__setattr__(self, "idempotency_key", _uuid(self.idempotency_key, "idempotency_key"))
        object.__setattr__(self, "action", _enum(self.action, ReviewAction, "action"))
        if self.suggestion_id is not None:
            object.__setattr__(self, "suggestion_id", _label(self.suggestion_id, "suggestion_id"))
        object.__setattr__(self, "reason_code", _enum(self.reason_code, ReviewReasonCode, "reason_code"))
        object.__setattr__(self, "reason", _text(self.reason, "reason", limit=_MAX_REASON_LENGTH))
        edits = _validate_contract_tuple(self.edits, FieldReviewEdit, "edits")
        requests = _validate_contract_tuple(self.evidence_requests, EvidenceRequestItem, "evidence_requests")
        acknowledgements = _validate_contract_tuple(
            self.unresolved_acknowledgements,
            UnresolvedAcknowledgement,
            "unresolved_acknowledgements",
        )
        object.__setattr__(self, "edits", edits)
        object.__setattr__(self, "evidence_requests", requests)
        object.__setattr__(self, "unresolved_acknowledgements", acknowledgements)
        if self.action is ReviewAction.MODIFY_AND_ACCEPT and not edits:
            raise ValueError("modify_and_accept requires at least one edit")  # noqa: TRY003
        if self.action is not ReviewAction.MODIFY_AND_ACCEPT and edits:
            raise ValueError("only modify_and_accept may contain edits")  # noqa: TRY003
        if self.action is ReviewAction.REQUEST_EVIDENCE and not requests:
            raise ValueError("request_evidence requires at least one evidence request")  # noqa: TRY003
        if self.action is not ReviewAction.REQUEST_EVIDENCE and requests:
            raise ValueError("only request_evidence may contain evidence requests")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class ReviewDecisionRecord:
    decision_id: str
    row_id: str
    previous_record_version: int
    record_version: int
    actor_id: str
    action: ReviewAction
    suggestion_id: str | None
    reason_code: ReviewReasonCode
    reason: str
    edits: tuple[FieldReviewEdit, ...]
    evidence_requests: tuple[EvidenceRequestItem, ...]
    unresolved_acknowledgements: tuple[UnresolvedAcknowledgement, ...]
    created_at: str

    def __post_init__(self) -> None:
        for field_name in ("decision_id", "row_id", "actor_id"):
            object.__setattr__(self, field_name, _label(getattr(self, field_name), field_name))
        object.__setattr__(self, "previous_record_version", _positive(self.previous_record_version, "previous_record_version"))
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        if self.record_version <= self.previous_record_version:
            raise ValueError("record_version must be greater than previous_record_version")  # noqa: TRY003
        object.__setattr__(self, "action", _enum(self.action, ReviewAction, "action"))
        if self.suggestion_id is not None:
            object.__setattr__(self, "suggestion_id", _label(self.suggestion_id, "suggestion_id"))
        object.__setattr__(self, "reason_code", _enum(self.reason_code, ReviewReasonCode, "reason_code"))
        object.__setattr__(self, "reason", _text(self.reason, "reason", limit=_MAX_REASON_LENGTH))
        object.__setattr__(self, "edits", _validate_contract_tuple(self.edits, FieldReviewEdit, "edits"))
        object.__setattr__(
            self,
            "evidence_requests",
            _validate_contract_tuple(self.evidence_requests, EvidenceRequestItem, "evidence_requests"),
        )
        object.__setattr__(
            self,
            "unresolved_acknowledgements",
            _validate_contract_tuple(
                self.unresolved_acknowledgements,
                UnresolvedAcknowledgement,
                "unresolved_acknowledgements",
            ),
        )
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))


@dataclass(frozen=True, slots=True)
class ReviewCandidateBundle:
    analysis: FmeaAnalysis
    evidence_pack: EvidencePack
    rows: tuple[FmeaRow, ...]
    source_snapshots: tuple[ReviewSourceSnapshot, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.analysis, FmeaAnalysis):
            raise ValueError("analysis must be an FmeaAnalysis")  # noqa: TRY003
        if not isinstance(self.evidence_pack, EvidencePack):
            raise ValueError("evidence_pack must be an EvidencePack")  # noqa: TRY003
        object.__setattr__(self, "rows", _validate_contract_tuple(self.rows, FmeaRow, "rows"))
        object.__setattr__(
            self,
            "source_snapshots",
            _validate_contract_tuple(self.source_snapshots, ReviewSourceSnapshot, "source_snapshots"),
        )


@dataclass(frozen=True, slots=True)
class FieldReviewState:
    target_field: str
    value: str | tuple[str, ...]
    claim_status: ClaimStatus
    support_status: EvidenceSupportStatus
    evidence_ids: tuple[str, ...]
    last_decision_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_field", _editable_field(self.target_field))
        object.__setattr__(self, "value", _string_value(self.value, "value"))
        object.__setattr__(self, "claim_status", _enum(self.claim_status, ClaimStatus, "claim_status"))
        object.__setattr__(self, "support_status", _enum(self.support_status, EvidenceSupportStatus, "support_status"))
        object.__setattr__(self, "evidence_ids", _evidence_ids(self.evidence_ids))
        if self.last_decision_id is not None:
            object.__setattr__(self, "last_decision_id", _label(self.last_decision_id, "last_decision_id"))


@dataclass(frozen=True, slots=True)
class ReviewEvidenceRef:
    evidence_id: str
    source_type: str
    source_trust: str
    is_primary: bool
    locator: str
    quote: str

    def __post_init__(self) -> None:
        for field_name in ("evidence_id", "source_type", "source_trust", "locator"):
            object.__setattr__(self, field_name, _label(getattr(self, field_name), field_name))
        if not isinstance(self.is_primary, bool):
            raise ValueError("is_primary must be a boolean")  # noqa: TRY003
        object.__setattr__(self, "quote", _text(self.quote, "quote", limit=_MAX_VALUE_LENGTH))


@dataclass(frozen=True, slots=True)
class ReviewEvidenceProjection:
    pack_id: str
    pack_hash: str
    expires_at: str | None
    refs: tuple[ReviewEvidenceRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "pack_id", _label(self.pack_id, "pack_id"))
        object.__setattr__(self, "pack_hash", _pack_hash(self.pack_hash, "pack_hash"))
        object.__setattr__(self, "expires_at", _optional_timestamp(self.expires_at, "expires_at"))
        refs = _validate_contract_tuple(self.refs, ReviewEvidenceRef, "refs")
        ids = tuple(ref.evidence_id for ref in refs)
        if len(ids) != len(set(ids)):
            raise ValueError("refs must not contain duplicate evidence IDs")  # noqa: TRY003
        object.__setattr__(self, "refs", refs)


@dataclass(frozen=True, slots=True)
class RetrievalProvenance:
    requested_profile: EvidenceSelectionProfile
    resolved_profile: EvidenceSelectionProfile
    evidence_types: tuple[CitationType, ...]
    trace_id: str
    warnings: tuple[str, ...]
    incomplete: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requested_profile",
            _enum(self.requested_profile, EvidenceSelectionProfile, "requested_profile"),
        )
        resolved = _enum(self.resolved_profile, EvidenceSelectionProfile, "resolved_profile")
        if resolved is EvidenceSelectionProfile.AUTO:
            raise ValueError("resolved_profile cannot be AUTO")  # noqa: TRY003
        object.__setattr__(self, "resolved_profile", resolved)
        evidence_types = _tuple_of_unique(self.evidence_types, CitationType, "evidence_types")
        object.__setattr__(self, "evidence_types", evidence_types)
        object.__setattr__(self, "trace_id", _label(self.trace_id, "trace_id"))
        warnings = _strings(self.warnings, "warnings", limit=4000)
        if not isinstance(self.incomplete, bool):
            raise ValueError("incomplete must be a boolean")  # noqa: TRY003
        if (
            resolved is EvidenceSelectionProfile.CUSTOM
            and not evidence_types
            and (not self.incomplete or not warnings)
        ):
            raise ValueError("custom resolved_profile requires unique evidence_types")  # noqa: TRY003
        object.__setattr__(self, "warnings", warnings)


@dataclass(frozen=True, slots=True)
class ReviewContext:
    row: FmeaRow
    item_label: str
    function_label: str
    reviewability: bool
    field_reviews: tuple[FieldReviewState, ...]
    evidence: ReviewEvidenceProjection
    retrieval: RetrievalProvenance
    latest_suggestion: ReviewSuggestion | None
    decision_history: tuple[ReviewDecisionRecord, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.row, FmeaRow):
            raise ValueError("row must be an FmeaRow")  # noqa: TRY003
        object.__setattr__(self, "item_label", _label(self.item_label, "item_label"))
        object.__setattr__(self, "function_label", _label(self.function_label, "function_label"))
        if not isinstance(self.reviewability, bool):
            raise ValueError("reviewability must be a boolean")  # noqa: TRY003
        object.__setattr__(self, "field_reviews", _validate_contract_tuple(self.field_reviews, FieldReviewState, "field_reviews"))
        if not isinstance(self.evidence, ReviewEvidenceProjection):
            raise ValueError("evidence must be a ReviewEvidenceProjection")  # noqa: TRY003
        if not isinstance(self.retrieval, RetrievalProvenance):
            raise ValueError("retrieval must be a RetrievalProvenance")  # noqa: TRY003
        if self.latest_suggestion is not None and not isinstance(self.latest_suggestion, ReviewSuggestion):
            raise ValueError("latest_suggestion must be a ReviewSuggestion or None")  # noqa: TRY003
        object.__setattr__(
            self,
            "decision_history",
            _validate_contract_tuple(self.decision_history, ReviewDecisionRecord, "decision_history"),
        )
        object.__setattr__(self, "warnings", _strings(self.warnings, "warnings", limit=4000))


@dataclass(frozen=True, slots=True)
class IdempotencyScope:
    workspace_id: str
    actor_id: str
    command: str
    resource_path: str
    key_hash: str

    def __post_init__(self) -> None:
        for field_name in ("workspace_id", "actor_id", "command", "resource_path"):
            object.__setattr__(self, field_name, _label(getattr(self, field_name), field_name))
        object.__setattr__(self, "key_hash", _hash(self.key_hash, "key_hash"))

    @property
    def scope_key(self) -> str:
        return _canonical_hash(
            {
                "workspace_id": self.workspace_id,
                "actor_id": self.actor_id,
                "command": self.command,
                "resource_path": self.resource_path,
                "key_hash": self.key_hash,
            },
            prefixed=False,
        )


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    occurred_at_server: str
    workspace_id: str
    actor_id: str
    actor_type: ActorType
    actor_roles: tuple[str, ...]
    command: str
    action: ReviewAction | None
    reason_code: ReviewReasonCode | None
    reason: str
    analysis_id: str
    row_id: str
    suggestion_id: str | None
    decision_id: str | None
    expected_record_version: int | None
    applied_record_version: int | None
    before_hash: str | None
    after_hash: str | None
    changed_fields: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    evidence_request_targets: tuple[str, ...]
    idempotency_key_hash: str
    canonical_payload_hash: str
    versions: VersionSet
    template_id: str
    template_version: str
    profile_id: str
    profile_version: str
    model_manifest: ReviewModelManifest | None
    request_id: str
    trace_id: str
    retrieval_trace_id: str

    def __post_init__(self) -> None:  # noqa: C901
        for field_name in (
            "event_id",
            "workspace_id",
            "actor_id",
            "command",
            "analysis_id",
            "row_id",
            "template_id",
            "template_version",
            "profile_id",
            "profile_version",
            "request_id",
            "trace_id",
            "retrieval_trace_id",
        ):
            object.__setattr__(self, field_name, _label(getattr(self, field_name), field_name))
        object.__setattr__(self, "occurred_at_server", _timestamp(self.occurred_at_server, "occurred_at_server"))
        object.__setattr__(self, "actor_type", _enum(self.actor_type, ActorType, "actor_type"))
        object.__setattr__(self, "actor_roles", _strings(self.actor_roles, "actor_roles", max_items=64, unique=True))
        if self.action is not None:
            object.__setattr__(self, "action", _enum(self.action, ReviewAction, "action"))
        if self.reason_code is not None:
            object.__setattr__(self, "reason_code", _enum(self.reason_code, ReviewReasonCode, "reason_code"))
        object.__setattr__(self, "reason", _text(self.reason, "reason", limit=_MAX_REASON_LENGTH))
        for field_name in ("suggestion_id", "decision_id"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _label(value, field_name))
        for field_name in ("expected_record_version", "applied_record_version"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _positive(value, field_name))
        for field_name in ("before_hash", "after_hash"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _pack_hash(value, field_name))
        changed_fields = tuple(_editable_field(item, "changed_fields") for item in _tuple(self.changed_fields, "changed_fields"))
        if len(changed_fields) != len(set(changed_fields)):
            raise ValueError("changed_fields must not contain duplicates")  # noqa: TRY003
        object.__setattr__(self, "changed_fields", changed_fields)
        object.__setattr__(self, "evidence_ids", _evidence_ids(self.evidence_ids))
        request_targets = tuple(
            _editable_field(item, "evidence_request_targets")
            for item in _tuple(self.evidence_request_targets, "evidence_request_targets")
        )
        if len(request_targets) != len(set(request_targets)):
            raise ValueError("evidence_request_targets must not contain duplicates")  # noqa: TRY003
        object.__setattr__(self, "evidence_request_targets", request_targets)
        object.__setattr__(self, "idempotency_key_hash", _hash(self.idempotency_key_hash, "idempotency_key_hash"))
        object.__setattr__(self, "canonical_payload_hash", _hash(self.canonical_payload_hash, "canonical_payload_hash"))
        if not isinstance(self.versions, VersionSet):
            raise ValueError("versions must be a VersionSet")  # noqa: TRY003
        if self.model_manifest is not None and not isinstance(self.model_manifest, ReviewModelManifest):
            raise ValueError("model_manifest must be a ReviewModelManifest or None")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class PreparedSuggestionRun:
    scope: IdempotencyScope
    payload_hash: str
    command: StartReviewSuggestionCommand
    actor: ActorContext
    run: ReviewSuggestionRun
    audit: AuditEvent
    response_status: Literal[202]

    def __post_init__(self) -> None:
        for field_name, expected in (
            ("scope", IdempotencyScope),
            ("command", StartReviewSuggestionCommand),
            ("actor", ActorContext),
            ("run", ReviewSuggestionRun),
            ("audit", AuditEvent),
        ):
            if not isinstance(getattr(self, field_name), expected):
                raise ValueError(f"{field_name} has an invalid contract type")  # noqa: TRY003
        object.__setattr__(self, "payload_hash", _hash(self.payload_hash, "payload_hash"))
        if self.response_status != 202:
            raise ValueError("response_status must be 202")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class SuggestionRunReservation:
    run: ReviewSuggestionRun
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.run, ReviewSuggestionRun):
            raise ValueError("run must be a ReviewSuggestionRun")  # noqa: TRY003
        if not isinstance(self.replayed, bool):
            raise ValueError("replayed must be a boolean")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class PreparedReviewDecision:
    scope: IdempotencyScope
    payload_hash: str
    expected_record_version: int
    previous_row: FmeaRow
    next_row: FmeaRow
    decision: ReviewDecisionRecord
    audit: AuditEvent
    response_status: int

    def __post_init__(self) -> None:
        if not isinstance(self.scope, IdempotencyScope):
            raise ValueError("scope must be an IdempotencyScope")  # noqa: TRY003
        object.__setattr__(self, "payload_hash", _hash(self.payload_hash, "payload_hash"))
        object.__setattr__(self, "expected_record_version", _positive(self.expected_record_version, "expected_record_version"))
        for field_name, expected in (
            ("previous_row", FmeaRow),
            ("next_row", FmeaRow),
            ("decision", ReviewDecisionRecord),
            ("audit", AuditEvent),
        ):
            if not isinstance(getattr(self, field_name), expected):
                raise ValueError(f"{field_name} has an invalid contract type")  # noqa: TRY003
        if isinstance(self.response_status, bool) or not isinstance(self.response_status, int) or not 100 <= self.response_status <= 599:
            raise ValueError("response_status must be an HTTP status code")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class ReviewDecisionResult:
    decision_id: str
    row: FmeaRow
    previous_record_version: int
    record_version: int
    review_status: ReviewStatus
    publication_status: PublicationStatus
    audit_event_id: str
    suggestion_id: str | None
    evidence_requests: tuple[EvidenceRequestItem, ...]
    persisted: bool
    request_id: str
    trace_id: str

    def __post_init__(self) -> None:
        for field_name in ("decision_id", "audit_event_id", "request_id", "trace_id"):
            object.__setattr__(self, field_name, _label(getattr(self, field_name), field_name))
        if not isinstance(self.row, FmeaRow):
            raise ValueError("row must be an FmeaRow")  # noqa: TRY003
        object.__setattr__(self, "previous_record_version", _positive(self.previous_record_version, "previous_record_version"))
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        if self.record_version <= self.previous_record_version:
            raise ValueError("record_version must be greater than previous_record_version")  # noqa: TRY003
        object.__setattr__(self, "review_status", _enum(self.review_status, ReviewStatus, "review_status"))
        object.__setattr__(self, "publication_status", _enum(self.publication_status, PublicationStatus, "publication_status"))
        if self.suggestion_id is not None:
            object.__setattr__(self, "suggestion_id", _label(self.suggestion_id, "suggestion_id"))
        object.__setattr__(
            self,
            "evidence_requests",
            _validate_contract_tuple(self.evidence_requests, EvidenceRequestItem, "evidence_requests"),
        )
        if not isinstance(self.persisted, bool):
            raise ValueError("persisted must be a boolean")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class ReviewModelRequest:
    run_id: str
    context: ReviewContext
    evidence_pack: EvidencePack
    review_policy: Literal["default"]
    focus_fields: tuple[str, ...]
    template_id: Literal["fmea-row-review"]
    template_version: Literal["1.0.0"]

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _label(self.run_id, "run_id"))
        if not isinstance(self.context, ReviewContext):
            raise ValueError("context must be a ReviewContext")  # noqa: TRY003
        if not isinstance(self.evidence_pack, EvidencePack):
            raise ValueError("evidence_pack must be an EvidencePack")  # noqa: TRY003
        if self.review_policy != "default":
            raise ValueError("review_policy must be default")  # noqa: TRY003
        focus_fields = tuple(_editable_field(item, "focus_fields") for item in _tuple(self.focus_fields, "focus_fields"))
        if len(focus_fields) != len(set(focus_fields)):
            raise ValueError("focus_fields must not contain duplicates")  # noqa: TRY003
        object.__setattr__(self, "focus_fields", focus_fields)
        if self.template_id != "fmea-row-review":
            raise ValueError("template_id must be fmea-row-review")  # noqa: TRY003
        if self.template_version != "1.0.0":
            raise ValueError("template_version must be 1.0.0")  # noqa: TRY003


def idempotency_key_hash(raw_key: str) -> str:
    """Validate and hash the raw canonical lowercase UUID idempotency key."""

    normalized = _uuid(raw_key, "idempotency_key")
    return "sha256:" + sha256(normalized.encode("utf-8")).hexdigest()


def canonical_payload_hash(command: StartReviewSuggestionCommand | ReviewDecisionCommand) -> str:
    """Hash semantic command fields while excluding the raw idempotency key."""

    payload = {
        field.name: getattr(command, field.name)
        for field in fields(command)
        if field.name != "idempotency_key"
    }
    return _canonical_hash(payload)


__all__ = [
    "EDITABLE_REVIEW_FIELDS",
    "ActorContext",
    "AuditEvent",
    "ConflictItem",
    "EvidenceRequestItem",
    "FieldFinding",
    "FieldReviewEdit",
    "FieldReviewState",
    "IdempotencyScope",
    "MissingEvidenceItem",
    "PreparedReviewDecision",
    "PreparedSuggestionRun",
    "RetrievalProvenance",
    "ReviewAction",
    "ReviewCandidateBundle",
    "ReviewContext",
    "ReviewDecisionCommand",
    "ReviewDecisionRecord",
    "ReviewDecisionResult",
    "ReviewEvidenceProjection",
    "ReviewEvidenceRef",
    "ReviewJudgement",
    "ReviewModelManifest",
    "ReviewModelRequest",
    "ReviewPriority",
    "ReviewReasonCode",
    "ReviewSourceSnapshot",
    "ReviewSuggestion",
    "ReviewSuggestionDraft",
    "ReviewSuggestionRun",
    "StartReviewSuggestionCommand",
    "SuggestionRunReservation",
    "UnresolvedAcknowledgement",
    "canonical_payload_hash",
    "idempotency_key_hash",
]
