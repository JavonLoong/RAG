"""Provider-neutral immutable envelopes for model assistance."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import Enum
from hashlib import sha256
from math import isfinite
from types import MappingProxyType
from typing import Generic, TypeVar
from uuid import UUID

from core_domain.fmea.states import ActorType

_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_T = TypeVar("_T")
_MAX_DEPTH = 8
_MAX_CONTAINER_ITEMS = 64
_MAX_TOTAL_NODES = 2048
_MAX_STRING_LENGTH = 4096
_MAX_ID_LENGTH = 256
_MAX_FIELD_LENGTH = 256
_MAX_CANONICAL_BYTES = 65536
_FORBIDDEN_KEY_MARKERS = frozenset(
    {
        "password",
        "passwd",
        "authorization",
        "apikey",
        "secret",
        "accesstoken",
        "rawprompt",
        "privatepath",
        "providererror",
    }
)


class AssistanceKind(str, Enum):
    ANALYSIS_SCOPE_DRAFT = "analysis_scope_draft"
    TEMPLATE_FIELD_MAPPING = "template_field_mapping"
    FMEA_CANDIDATE_GENERATION = "fmea_candidate_generation"
    SCORE_RECOMMENDATION = "score_recommendation"
    PROPAGATION_HYPOTHESIS = "propagation_hypothesis"
    EVIDENCE_GAP_EXPLANATION = "evidence_gap_explanation"
    REVIEW_SUMMARY = "review_summary"
    APPROVAL_READINESS_CHECKLIST = "approval_readiness_checklist"
    MIGRATION_PATCH_PROPOSAL = "migration_patch_proposal"
    EXPORT_NARRATIVE_DRAFT = "export_narrative_draft"


class AssistanceDecisionAction(str, Enum):
    ADOPT = "adopt"
    PARTIAL_ADOPT = "partial_adopt"
    EDIT_AND_ADOPT = "edit_and_adopt"
    REJECT = "reject"
    DEFER = "defer"
    REQUEST_EVIDENCE = "request_evidence"


def _text(value: object, field_name: str, *, max_length: int = _MAX_STRING_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")  # noqa: TRY003
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")  # noqa: TRY003
    return normalized


def _positive(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be positive")  # noqa: TRY003
    return value


def _ids(value: object, field_name: str, *, require_non_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise ValueError(f"{field_name} must be a tuple or list")  # noqa: TRY003, TRY004
    normalized = tuple(_text(item, field_name, max_length=_MAX_ID_LENGTH) for item in value)
    if require_non_empty and not normalized:
        raise ValueError(f"{field_name} must contain at least one ID")  # noqa: TRY003
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")  # noqa: TRY003
    return normalized


def _hash(value: object, field_name: str) -> str:
    normalized = _text(value, field_name)
    if _SHA256.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must be lowercase SHA-256")  # noqa: TRY003
    return normalized


def _normalized_sensitive_key(value: str) -> str:
    camel_case_separated = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])",
        "_",
        value,
    )
    normalized = re.sub(r"[^a-z0-9]+", "_", camel_case_separated.casefold())
    return re.sub(r"_+", "_", normalized).strip("_")


def _is_forbidden_sensitive_key(value: str) -> bool:
    normalized = _normalized_sensitive_key(value)
    compact = normalized.replace("_", "")
    return any(marker in compact for marker in _FORBIDDEN_KEY_MARKERS)


def _json_key(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("JSON object key must be a string")  # noqa: TRY003, TRY004
    if len(value) > _MAX_STRING_LENGTH:
        raise ValueError(f"JSON object keys must be at most {_MAX_STRING_LENGTH} characters")  # noqa: TRY003
    if _is_forbidden_sensitive_key(value):
        raise ValueError("JSON object contains a forbidden private key")  # noqa: TRY003
    return value


class _NodeBudget:
    __slots__ = ("count",)

    def __init__(self) -> None:
        self.count = 0

    def consume(self) -> None:
        self.count += 1
        if self.count > _MAX_TOTAL_NODES:
            raise ValueError(f"JSON value exceeds {_MAX_TOTAL_NODES} total nodes")  # noqa: TRY003


def _freeze_mapping(
    value: Mapping[object, object],
    *,
    depth: int,
    budget: _NodeBudget,
    active_containers: frozenset[int],
) -> object:
    container_id = id(value)
    if container_id in active_containers:
        raise ValueError("JSON value must not contain cycles")  # noqa: TRY003
    items = list(value.items())
    if len(items) > _MAX_CONTAINER_ITEMS:
        raise ValueError(f"JSON containers must contain at most {_MAX_CONTAINER_ITEMS} items")  # noqa: TRY003
    checked_items = [(_json_key(key), item) for key, item in items]
    frozen = {
        key: _freeze_json(
            item,
            depth=depth + 1,
            budget=budget,
            active_containers=active_containers | {container_id},
        )
        for key, item in sorted(checked_items, key=lambda pair: pair[0])
    }
    return MappingProxyType(frozen)


def _freeze_sequence(
    value: tuple[object, ...] | list[object],
    *,
    depth: int,
    budget: _NodeBudget,
    active_containers: frozenset[int],
) -> tuple[object, ...]:
    container_id = id(value)
    if container_id in active_containers:
        raise ValueError("JSON value must not contain cycles")  # noqa: TRY003
    if len(value) > _MAX_CONTAINER_ITEMS:
        raise ValueError(f"JSON containers must contain at most {_MAX_CONTAINER_ITEMS} items")  # noqa: TRY003
    return tuple(
        _freeze_json(
            item,
            depth=depth + 1,
            budget=budget,
            active_containers=active_containers | {container_id},
        )
        for item in value
    )


def _freeze_json(
    value: object,
    *,
    depth: int = 0,
    budget: _NodeBudget | None = None,
    active_containers: frozenset[int] = frozenset(),
) -> object:
    if depth > _MAX_DEPTH:
        raise ValueError(f"JSON value exceeds maximum depth {_MAX_DEPTH}")  # noqa: TRY003
    budget = _NodeBudget() if budget is None else budget
    budget.consume()
    if isinstance(value, Enum):
        raise ValueError("JSON value must use JSON scalar types")  # noqa: TRY003, TRY004
    if value is None or isinstance(value, bool | int | str):
        if isinstance(value, str) and len(value) > _MAX_STRING_LENGTH:
            raise ValueError(f"JSON strings must be at most {_MAX_STRING_LENGTH} characters")  # noqa: TRY003
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("JSON numbers must be finite")  # noqa: TRY003
        return value
    if isinstance(value, Mapping):
        return _freeze_mapping(value, depth=depth, budget=budget, active_containers=active_containers)
    if isinstance(value, tuple | list):
        return _freeze_sequence(value, depth=depth, budget=budget, active_containers=active_containers)
    raise ValueError("JSON value must use JSON scalar, mapping, list, or tuple types")  # noqa: TRY003


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {_json_key(key): _json_value(item) for key, item in sorted(value.items(), key=lambda pair: pair[0])}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("JSON numbers must be finite")  # noqa: TRY003
        return value
    raise ValueError("value is not JSON-safe")  # noqa: TRY003


def _canonical_json_bytes(value: object, label: str) -> bytes:
    try:
        encoded = json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be canonical JSON") from exc  # noqa: TRY003
    if len(encoded) > _MAX_CANONICAL_BYTES:
        raise ValueError(f"{label} canonical JSON exceeds {_MAX_CANONICAL_BYTES} bytes")  # noqa: TRY003
    return encoded


def _freeze_payload(value: object, label: str) -> object:
    frozen = _freeze_json(value)
    _canonical_json_bytes(frozen, f"canonical {label}")
    return frozen


def _optional_identity_pair(
    identifier: object,
    version: object,
    identifier_name: str,
    version_name: str,
) -> tuple[str | None, str | None]:
    if (identifier is None) != (version is None):
        raise ValueError(f"{identifier_name} and {version_name} require both ID and version")  # noqa: TRY003
    if identifier is None:
        return None, None
    return (
        _text(identifier, identifier_name, max_length=_MAX_ID_LENGTH),
        _text(version, version_name, max_length=_MAX_ID_LENGTH),
    )


def _uuid(value: object, field_name: str) -> str:
    normalized = _text(value, field_name, max_length=36)
    try:
        parsed = UUID(normalized)
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a canonical lowercase UUID") from exc  # noqa: TRY003
    if str(parsed) != normalized:
        raise ValueError(f"{field_name} must be a canonical lowercase UUID")  # noqa: TRY003
    return normalized


def _normalize_edits(value: object) -> tuple[tuple[str, object], ...]:
    if not isinstance(value, tuple | list):
        raise ValueError("edits must be a tuple or list")  # noqa: TRY003, TRY004
    if len(value) > 32:
        raise ValueError("edits must contain at most 32 items")  # noqa: TRY003
    budget = _NodeBudget()
    budget.consume()
    normalized: list[tuple[str, object]] = []
    seen_fields: set[str] = set()
    for edit in value:
        budget.consume()
        if not isinstance(edit, tuple | list) or len(edit) != 2:
            raise ValueError("edits must contain field/value pairs")  # noqa: TRY003
        field = _text(edit[0], "edit field", max_length=_MAX_FIELD_LENGTH)
        if _is_forbidden_sensitive_key(field):
            raise ValueError("edit field is a forbidden private key")  # noqa: TRY003
        if field in seen_fields:
            raise ValueError("edit fields must be unique")  # noqa: TRY003
        seen_fields.add(field)
        normalized.append((field, _freeze_json(edit[1], budget=budget)))
    result = tuple(normalized)
    _canonical_json_bytes(result, "canonical edits")
    return result


def _normalize_resource_identity(value: object) -> tuple[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, tuple | list):
        raise ValueError("resulting_resource_identity must be a tuple or list")  # noqa: TRY003, TRY004
    if len(value) != 2:
        raise ValueError("resulting_resource_identity must contain type and ID")  # noqa: TRY003
    return (
        _text(value[0], "resulting resource type", max_length=_MAX_ID_LENGTH),
        _text(value[1], "resulting resource ID", max_length=_MAX_ID_LENGTH),
    )


def _canonical_hash(value: object) -> str:
    return "sha256:" + sha256(_canonical_json_bytes(value, "canonical suggestion")).hexdigest()


@dataclass(frozen=True, slots=True)
class AssistanceRequest(Generic[_T]):
    request_id: str
    kind: AssistanceKind
    workspace_id: str
    target_type: str
    target_id: str
    target_record_version: int
    evidence_pack_ids: tuple[str, ...]
    payload: _T | None = None
    domain_pack_id: str | None = None
    domain_pack_version: str | None = None
    template_id: str | None = None
    template_version: str | None = None
    rule_pack_id: str | None = None
    rule_pack_version: str | None = None
    record_version: int = 1
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("request_id", "workspace_id", "target_type", "target_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name, max_length=_MAX_ID_LENGTH))
        if not isinstance(self.kind, AssistanceKind):
            raise ValueError("kind must be an AssistanceKind")  # noqa: TRY003, TRY004
        object.__setattr__(self, "target_record_version", _positive(self.target_record_version, "target_record_version"))
        object.__setattr__(
            self,
            "evidence_pack_ids",
            _ids(self.evidence_pack_ids, "evidence_pack_ids", require_non_empty=True),
        )
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        for identifier_name, version_name in (
            ("domain_pack_id", "domain_pack_version"),
            ("template_id", "template_version"),
            ("rule_pack_id", "rule_pack_version"),
        ):
            identifier, version = _optional_identity_pair(
                getattr(self, identifier_name),
                getattr(self, version_name),
                identifier_name,
                version_name,
            )
            object.__setattr__(self, identifier_name, identifier)
            object.__setattr__(self, version_name, version)
        object.__setattr__(self, "payload", _freeze_payload(self.payload, "payload"))
        if self.idempotency_key is not None:
            object.__setattr__(self, "idempotency_key", _uuid(self.idempotency_key, "idempotency_key"))


@dataclass(frozen=True, slots=True)
class AssistanceSuggestion(Generic[_T]):
    suggestion_id: str
    kind: AssistanceKind
    workspace_id: str
    target_type: str
    target_id: str
    target_record_version: int
    evidence_pack_ids: tuple[str, ...]
    payload: _T
    evidence_ids: tuple[str, ...] = ()
    conflict_ids: tuple[str, ...] = ()
    uncertainty: str | None = None
    model_hash: str = ""
    prompt_hash: str = ""
    run_id: str = ""
    trace_id: str = ""
    domain_pack_id: str | None = None
    domain_pack_version: str | None = None
    template_id: str | None = None
    template_version: str | None = None
    rule_pack_id: str | None = None
    rule_pack_version: str | None = None
    record_version: int = 1
    created_at: str = ""
    applied: bool = False
    suggestion_hash: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("suggestion_id", "workspace_id", "target_type", "target_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name, max_length=_MAX_ID_LENGTH))
        if not isinstance(self.kind, AssistanceKind):
            raise ValueError("kind must be an AssistanceKind")  # noqa: TRY003, TRY004
        object.__setattr__(self, "target_record_version", _positive(self.target_record_version, "target_record_version"))
        object.__setattr__(
            self,
            "evidence_pack_ids",
            _ids(self.evidence_pack_ids, "evidence_pack_ids", require_non_empty=True),
        )
        object.__setattr__(self, "evidence_ids", _ids(self.evidence_ids, "evidence_ids"))
        object.__setattr__(self, "conflict_ids", _ids(self.conflict_ids, "conflict_ids"))
        object.__setattr__(self, "model_hash", _hash(self.model_hash, "model_hash"))
        object.__setattr__(self, "prompt_hash", _hash(self.prompt_hash, "prompt_hash"))
        object.__setattr__(self, "run_id", _text(self.run_id, "run_id", max_length=_MAX_ID_LENGTH))
        object.__setattr__(self, "trace_id", _text(self.trace_id, "trace_id", max_length=_MAX_ID_LENGTH))
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        if self.uncertainty is not None:
            object.__setattr__(self, "uncertainty", _text(self.uncertainty, "uncertainty"))
        if self.applied:
            raise ValueError("AssistanceSuggestion.applied must remain false")  # noqa: TRY003
        for identifier_name, version_name in (
            ("domain_pack_id", "domain_pack_version"),
            ("template_id", "template_version"),
            ("rule_pack_id", "rule_pack_version"),
        ):
            identifier, version = _optional_identity_pair(
                getattr(self, identifier_name),
                getattr(self, version_name),
                identifier_name,
                version_name,
            )
            object.__setattr__(self, identifier_name, identifier)
            object.__setattr__(self, version_name, version)
        object.__setattr__(self, "created_at", _text(self.created_at, "created_at"))
        object.__setattr__(self, "payload", _freeze_payload(self.payload, "payload"))
        expected_hash = _canonical_hash(
            {
                field.name: getattr(self, field.name)
                for field in fields(self)
                if field.name not in {"suggestion_hash", "applied"}
            }
        )
        if self.suggestion_hash is not None and self.suggestion_hash != expected_hash:
            raise ValueError("suggestion_hash does not match canonical suggestion")  # noqa: TRY003
        object.__setattr__(self, "suggestion_hash", expected_hash)

    @property
    def suggestion_version(self) -> int:
        return self.record_version


@dataclass(frozen=True, slots=True)
class AssistanceHandlerCheckpoint:
    decision_id: str
    reservation_hash: str
    resulting_resource_identity: tuple[str, str] | None
    applied_record_version: int | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", _text(self.decision_id, "decision_id", max_length=_MAX_ID_LENGTH))
        reservation_hash = _text(self.reservation_hash, "reservation_hash")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", reservation_hash):
            raise ValueError("reservation_hash must be a canonical hash")  # noqa: TRY003
        object.__setattr__(self, "reservation_hash", reservation_hash)
        identity = _normalize_resource_identity(self.resulting_resource_identity)
        object.__setattr__(self, "resulting_resource_identity", identity)
        if self.applied_record_version is not None:
            object.__setattr__(
                self,
                "applied_record_version",
                _positive(self.applied_record_version, "applied_record_version"),
            )
        if (identity is None) != (self.applied_record_version is None):
            raise ValueError("checkpoint resource identity and applied version require both values")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class AssistanceDecision:
    decision_id: str
    suggestion_id: str
    suggestion_hash: str
    suggestion_record_version: int
    target_record_version: int
    action: AssistanceDecisionAction
    actor_id: str
    actor_type: ActorType
    edits: tuple[tuple[str, object], ...]
    reason: str
    idempotency_key: str
    resulting_resource_identity: tuple[str, str] | None
    created_at: str = ""

    def __post_init__(self) -> None:
        for field_name in ("decision_id", "suggestion_id", "actor_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name, max_length=_MAX_ID_LENGTH))
        object.__setattr__(self, "suggestion_hash", _text(self.suggestion_hash, "suggestion_hash"))
        object.__setattr__(self, "actor_id", _text(self.actor_id, "actor_id", max_length=_MAX_ID_LENGTH))
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        object.__setattr__(self, "idempotency_key", _uuid(self.idempotency_key, "idempotency_key"))
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.suggestion_hash):
            raise ValueError("suggestion_hash must be a canonical hash")  # noqa: TRY003
        if not isinstance(self.action, AssistanceDecisionAction):
            raise ValueError("action must be an AssistanceDecisionAction")  # noqa: TRY003, TRY004
        if self.actor_type is not ActorType.HUMAN:
            raise ValueError("assistance decision requires a human actor")  # noqa: TRY003
        object.__setattr__(self, "suggestion_record_version", _positive(self.suggestion_record_version, "suggestion_record_version"))
        object.__setattr__(self, "target_record_version", _positive(self.target_record_version, "target_record_version"))
        edits = _normalize_edits(self.edits)
        if self.action in {
            AssistanceDecisionAction.ADOPT,
            AssistanceDecisionAction.REJECT,
            AssistanceDecisionAction.DEFER,
            AssistanceDecisionAction.REQUEST_EVIDENCE,
        } and edits:
            raise ValueError("this action must not contain edits")  # noqa: TRY003
        if self.action in {AssistanceDecisionAction.PARTIAL_ADOPT, AssistanceDecisionAction.EDIT_AND_ADOPT} and not edits:
            raise ValueError("this action must contain edits")  # noqa: TRY003
        object.__setattr__(self, "edits", edits)
        identity = _normalize_resource_identity(self.resulting_resource_identity)
        adopt_action = self.action in {
            AssistanceDecisionAction.ADOPT,
            AssistanceDecisionAction.PARTIAL_ADOPT,
            AssistanceDecisionAction.EDIT_AND_ADOPT,
        }
        if adopt_action and identity is None:
            raise ValueError("adopt actions require resulting_resource_identity")  # noqa: TRY003
        if not adopt_action and identity is not None:
            raise ValueError("non-adopt actions require resulting_resource_identity to be None")  # noqa: TRY003
        object.__setattr__(self, "resulting_resource_identity", identity)
        object.__setattr__(self, "created_at", _text(self.created_at, "created_at"))


__all__ = [
    "AssistanceDecision",
    "AssistanceDecisionAction",
    "AssistanceHandlerCheckpoint",
    "AssistanceKind",
    "AssistanceRequest",
    "AssistanceSuggestion",
]
