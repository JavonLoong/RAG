"""Provider-neutral immutable envelopes for model assistance."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from hashlib import sha256
from typing import Generic, TypeVar

from core_domain.fmea.states import ActorType

_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_T = TypeVar("_T")


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


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")  # noqa: TRY003
    return value.strip()


def _positive(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be positive")  # noqa: TRY003
    return value


def _ids(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or value is None:
        raise ValueError(f"{field_name} must be a sequence")  # noqa: TRY003
    try:
        result = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(f"{field_name} must be a sequence") from exc
    normalized = tuple(_text(item, field_name) for item in result)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")  # noqa: TRY003
    return normalized


def _hash(value: object, field_name: str) -> str:
    normalized = _text(value, field_name)
    if _SHA256.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must be lowercase SHA-256")  # noqa: TRY003
    return normalized


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _canonical_hash(value: object) -> str:
    payload = json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


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

    def __post_init__(self) -> None:
        for field_name in ("request_id", "workspace_id", "target_type", "target_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        if not isinstance(self.kind, AssistanceKind):
            raise ValueError("kind must be an AssistanceKind")  # noqa: TRY003
        object.__setattr__(self, "target_record_version", _positive(self.target_record_version, "target_record_version"))
        object.__setattr__(self, "evidence_pack_ids", _ids(self.evidence_pack_ids, "evidence_pack_ids"))
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        for field_name in (
            "domain_pack_id",
            "domain_pack_version",
            "template_id",
            "template_version",
            "rule_pack_id",
            "rule_pack_version",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _text(value, field_name))


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
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        if not isinstance(self.kind, AssistanceKind):
            raise ValueError("kind must be an AssistanceKind")  # noqa: TRY003
        object.__setattr__(self, "target_record_version", _positive(self.target_record_version, "target_record_version"))
        object.__setattr__(self, "evidence_pack_ids", _ids(self.evidence_pack_ids, "evidence_pack_ids"))
        object.__setattr__(self, "evidence_ids", _ids(self.evidence_ids, "evidence_ids"))
        object.__setattr__(self, "conflict_ids", _ids(self.conflict_ids, "conflict_ids"))
        object.__setattr__(self, "model_hash", _hash(self.model_hash, "model_hash"))
        object.__setattr__(self, "prompt_hash", _hash(self.prompt_hash, "prompt_hash"))
        object.__setattr__(self, "run_id", _text(self.run_id, "run_id"))
        object.__setattr__(self, "trace_id", _text(self.trace_id, "trace_id"))
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        if self.uncertainty is not None:
            object.__setattr__(self, "uncertainty", _text(self.uncertainty, "uncertainty"))
        if self.applied:
            raise ValueError("AssistanceSuggestion.applied must remain false")  # noqa: TRY003
        for field_name in (
            "domain_pack_id",
            "domain_pack_version",
            "template_id",
            "template_version",
            "rule_pack_id",
            "rule_pack_version",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _text(value, field_name))
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
        for field_name in ("decision_id", "suggestion_id", "suggestion_hash", "actor_id", "reason", "idempotency_key"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.suggestion_hash):
            raise ValueError("suggestion_hash must be a canonical hash")  # noqa: TRY003
        if not isinstance(self.action, AssistanceDecisionAction):
            raise ValueError("action must be an AssistanceDecisionAction")  # noqa: TRY003
        if self.actor_type is not ActorType.HUMAN:
            raise ValueError("assistance decision requires a human actor")  # noqa: TRY003
        object.__setattr__(self, "suggestion_record_version", _positive(self.suggestion_record_version, "suggestion_record_version"))
        object.__setattr__(self, "target_record_version", _positive(self.target_record_version, "target_record_version"))
        raw_edits = tuple(self.edits)
        for edit in raw_edits:
            if not isinstance(edit, tuple | list) or len(edit) != 2:
                raise ValueError("edits must contain field/value pairs")  # noqa: TRY003
            _text(edit[0], "edit field")
        object.__setattr__(self, "edits", tuple((str(field), value) for field, value in raw_edits))
        if self.resulting_resource_identity is not None:
            identity = tuple(self.resulting_resource_identity)
            if len(identity) != 2:
                raise ValueError("resulting_resource_identity must contain type and ID")  # noqa: TRY003
            object.__setattr__(
                self,
                "resulting_resource_identity",
                (_text(identity[0], "resulting resource type"), _text(identity[1], "resulting resource ID")),
            )


__all__ = [
    "AssistanceDecision",
    "AssistanceDecisionAction",
    "AssistanceKind",
    "AssistanceRequest",
    "AssistanceSuggestion",
]
