"""Typed FMEA wrappers for JSON-safe template-patch assistance."""

# Immutable value-object validation deliberately uses direct safe messages.
# ruff: noqa: TRY003

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from core_domain.fmea.states import ActorType
from core_domain.fmea.template_migration import TemplatePatchCandidate, TemplatePatchStatus

from .assistance_contracts import AssistanceKind, AssistanceSuggestion

_SOURCE_KEY = re.compile(r"[^a-z0-9]+")
_VALID_SOURCE_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")


def normalize_source_mapping_key(value: str) -> str:
    """Return a stable ASCII identity without dropping non-ASCII headers."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("source mapping header must not be empty")
    canonical = unicodedata.normalize("NFKC", value).casefold().strip()
    if _VALID_SOURCE_KEY.fullmatch(canonical) is not None:
        return canonical
    ascii_slug = _SOURCE_KEY.sub("_", canonical).strip("_")
    digest = sha256(canonical.encode("utf-8")).hexdigest()[:24]
    prefix = ascii_slug[:103].rstrip("_") or "source"
    return f"{prefix}_{digest}"


def candidate_payload(candidate: TemplatePatchCandidate) -> Mapping[str, object]:
    return {
        "patch_id": candidate.patch_id,
        "draft_id": candidate.draft_id,
        "input_template_version": candidate.input_template_version,
        "target_template_id": candidate.target_template_id,
        "target_template_version": candidate.target_template_version,
        "target_template_hash": candidate.target_template_hash,
        "domain_pack_id": candidate.domain_pack_id,
        "domain_pack_version": candidate.domain_pack_version,
        "domain_pack_hash": candidate.domain_pack_hash,
        "evidence_pack_id": candidate.evidence_pack_id,
        "evidence_pack_hash": candidate.evidence_pack_hash,
        "run_id": candidate.run_id,
        "trace_id": candidate.trace_id,
        "model_version": candidate.model_version,
        "prompt_version": candidate.prompt_version,
        "diff": [dict(item) for item in candidate.diff],
        "evidence_ids": list(candidate.evidence_ids),
        "status": TemplatePatchStatus(candidate.status).value,
        "created_at": candidate.created_at,
        "applied": candidate.applied,
    }


def candidate_from_payload(payload: object) -> TemplatePatchCandidate:
    if not isinstance(payload, Mapping):
        raise TypeError("template patch payload must be a mapping")
    required = frozenset({
        "patch_id",
        "draft_id",
        "input_template_version",
        "target_template_id",
        "target_template_version",
        "target_template_hash",
        "domain_pack_id",
        "domain_pack_version",
        "domain_pack_hash",
        "evidence_pack_id",
        "evidence_pack_hash",
        "run_id",
        "trace_id",
        "model_version",
        "prompt_version",
        "diff",
        "evidence_ids",
        "status",
        "created_at",
        "applied",
    })
    if set(payload) != required:
        raise ValueError("template patch payload has unknown or missing fields")
    return TemplatePatchCandidate(**{key: payload[key] for key in required})


@dataclass(frozen=True, slots=True)
class TemplatePatchSuggestion:
    """Typed candidate plus its canonical generic assistance envelope."""

    candidate: TemplatePatchCandidate
    envelope: AssistanceSuggestion[object]

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, TemplatePatchCandidate):
            raise TypeError("candidate must be a TemplatePatchCandidate")
        if not isinstance(self.envelope, AssistanceSuggestion):
            raise TypeError("envelope must be an AssistanceSuggestion")
        if self.envelope.kind is not AssistanceKind.TEMPLATE_FIELD_MAPPING:
            raise ValueError("template patch envelope kind is invalid")
        if self.envelope.applied or self.candidate.applied:
            raise ValueError("template patch suggestions must remain unapplied")
        if candidate_from_payload(self.envelope.payload) != self.candidate:
            raise ValueError("template patch envelope payload does not match candidate")

    @property
    def suggestion_id(self) -> str:
        return self.envelope.suggestion_id

    @property
    def applied(self) -> bool:
        return self.envelope.applied

    @property
    def payload(self) -> TemplatePatchCandidate:
        return self.candidate


@dataclass(frozen=True, slots=True)
class TemplatePatchDecision:
    decision_id: str
    suggestion_id: str
    patch_id: str
    workspace_id: str
    actor_id: str
    actor_type: ActorType
    action: Literal["accepted", "rejected"]
    reason: str
    base_template_id: str
    base_template_version: str
    base_template_hash: str
    candidate: TemplatePatchCandidate
    new_template_version: str | None
    created_at: str

    def __post_init__(self) -> None:
        for field_name in (
            "decision_id",
            "suggestion_id",
            "patch_id",
            "workspace_id",
            "actor_id",
            "reason",
            "base_template_id",
            "base_template_version",
            "base_template_hash",
            "created_at",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip() or len(value) > 4096:
                raise ValueError(f"{field_name} is invalid")
        if self.actor_type is not ActorType.HUMAN:
            raise ValueError("template patch decisions require a human actor")
        if not isinstance(self.candidate, TemplatePatchCandidate):
            raise TypeError("template patch decision candidate is invalid")
        if (
            self.candidate.patch_id != self.patch_id
            or self.candidate.target_template_id != self.base_template_id
            or self.candidate.target_template_version != self.base_template_version
            or self.candidate.target_template_hash != self.base_template_hash
        ):
            raise ValueError("template patch decision candidate provenance is invalid")
        if self.action not in {"accepted", "rejected"}:
            raise ValueError("template patch decision action is invalid")
        if (self.action == "accepted") != (self.new_template_version is not None):
            raise ValueError("accepted decisions require exactly one new template version")


__all__ = [
    "TemplatePatchDecision",
    "TemplatePatchSuggestion",
    "candidate_from_payload",
    "candidate_payload",
    "normalize_source_mapping_key",
]
