"""Stable contracts for generic evidence-bound structured output."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal, TypeAlias

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIREMENTS = frozenset({"required", "optional", "forbidden"})


class StructuredOutputError(ValueError):
    """A stable, public-safe structured-output domain error."""

    def __init__(self, code: str, message: str, pointer: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.pointer = pointer


class ClaimState(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICT = "conflict"
    NOT_APPLICABLE = "not_applicable"


def _as_unique_tuple(values: object, *, field_name: str) -> tuple[str, ...]:
    result = tuple(values)  # type: ignore[arg-type]
    if not all(isinstance(item, str) and item for item in result):
        raise StructuredOutputError("STRUCTURED_OUTPUT_CONTRACT_INVALID", f"{field_name} must contain strings")
    if len(result) != len(set(result)):
        raise StructuredOutputError("STRUCTURED_OUTPUT_CONTRACT_INVALID", f"duplicate {field_name}")
    return result


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise StructuredOutputError("STRUCTURED_OUTPUT_CONTRACT_INVALID", f"{field_name} must not be empty")


def _require_sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise StructuredOutputError("STRUCTURED_OUTPUT_CONTRACT_INVALID", f"{field_name} must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class TemplateMetadata:
    template_id: str
    version: str
    title: str
    description: str
    domain_tags: tuple[str, ...]
    schema_dialect: str

    def __post_init__(self) -> None:
        for field_name in ("template_id", "version", "title", "schema_dialect"):
            _require_text(getattr(self, field_name), field_name)
        if not isinstance(self.description, str):
            raise StructuredOutputError("STRUCTURED_OUTPUT_CONTRACT_INVALID", "description must be a string")
        object.__setattr__(self, "domain_tags", _as_unique_tuple(self.domain_tags, field_name="domain_tags"))


@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    target: str
    requirement: Literal["required", "optional", "forbidden"]
    min_refs: int = 0
    max_refs: int | None = None
    allowed_source_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.target, "target")
        if self.requirement not in _REQUIREMENTS:
            raise StructuredOutputError("TEMPLATE_BINDING_INVALID", "requirement is invalid")
        if not isinstance(self.min_refs, int) or isinstance(self.min_refs, bool) or self.min_refs < 0:
            raise StructuredOutputError("TEMPLATE_BINDING_INVALID", "min_refs must be a non-negative integer")
        if self.max_refs is not None and (
            not isinstance(self.max_refs, int)
            or isinstance(self.max_refs, bool)
            or self.max_refs < self.min_refs
        ):
            raise StructuredOutputError("TEMPLATE_BINDING_INVALID", "max_refs must be at least min_refs")
        if self.requirement == "required" and self.min_refs < 1:
            raise StructuredOutputError("TEMPLATE_BINDING_INVALID", "required binding must require evidence")
        if self.requirement == "forbidden" and not (self.min_refs == 0 and self.max_refs == 0):
            raise StructuredOutputError("TEMPLATE_BINDING_INVALID", "forbidden binding must set max_refs to zero")
        object.__setattr__(
            self,
            "allowed_source_types",
            _as_unique_tuple(self.allowed_source_types, field_name="allowed_source_types"),
        )


@dataclass(frozen=True, slots=True)
class CompiledTemplate:
    metadata: TemplateMetadata
    output_schema: dict[str, JsonValue]
    evidence_bindings: tuple[EvidenceBinding, ...]
    template_hash: str
    canonical_json: str

    def __post_init__(self) -> None:
        if not isinstance(self.output_schema, dict):
            raise StructuredOutputError("STRUCTURED_OUTPUT_CONTRACT_INVALID", "output_schema must be an object")
        object.__setattr__(self, "evidence_bindings", tuple(self.evidence_bindings))
        targets = tuple(binding.target for binding in self.evidence_bindings)
        if len(targets) != len(set(targets)):
            raise StructuredOutputError("TEMPLATE_BINDING_INVALID", "duplicate binding target")
        _require_sha256(self.template_hash, "template_hash")
        if not isinstance(self.canonical_json, str) or not self.canonical_json:
            raise StructuredOutputError("STRUCTURED_OUTPUT_CONTRACT_INVALID", "canonical_json must not be empty")


@dataclass(frozen=True, slots=True)
class CandidateClaim:
    target: str
    state: ClaimState
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.target, "target")
        if not isinstance(self.state, ClaimState):
            raise StructuredOutputError("CANDIDATE_CLAIM_STATE_INVALID", "claim state is invalid")
        object.__setattr__(self, "evidence_ids", _as_unique_tuple(self.evidence_ids, field_name="evidence_ids"))
        if self.state in {ClaimState.UNKNOWN, ClaimState.NOT_APPLICABLE} and self.evidence_ids:
            raise StructuredOutputError("CANDIDATE_CLAIM_STATE_INVALID", "claim state forbids evidence")
        if self.state is ClaimState.CONFLICT and len(self.evidence_ids) < 2:
            raise StructuredOutputError("CANDIDATE_CLAIM_STATE_INVALID", "conflict requires two evidence IDs")


@dataclass(frozen=True, slots=True)
class StructuredCandidate:
    candidate_id: str
    payload: JsonValue
    claims: tuple[CandidateClaim, ...]

    def __post_init__(self) -> None:
        _require_text(self.candidate_id, "candidate_id")
        object.__setattr__(self, "claims", tuple(self.claims))
        targets = tuple(claim.target for claim in self.claims)
        if len(targets) != len(set(targets)):
            raise StructuredOutputError("STRUCTURED_OUTPUT_CONTRACT_INVALID", "duplicate claim target")


@dataclass(frozen=True, slots=True)
class StructuredCandidateBatch:
    template_id: str
    template_version: str
    template_hash: str
    evidence_pack_id: str
    candidates: tuple[StructuredCandidate, ...]

    def __post_init__(self) -> None:
        for field_name in ("template_id", "template_version", "evidence_pack_id"):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.template_hash, "template_hash")
        object.__setattr__(self, "candidates", tuple(self.candidates))
        candidate_ids = tuple(candidate.candidate_id for candidate in self.candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise StructuredOutputError("STRUCTURED_OUTPUT_CONTRACT_INVALID", "duplicate candidate_id")


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    pointer: str
    candidate_id: str | None = None
    target: str | None = None
    binding: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.code, "code")
        _require_text(self.message, "message")
        if not isinstance(self.pointer, str):
            raise StructuredOutputError("STRUCTURED_OUTPUT_CONTRACT_INVALID", "pointer must be a string")


@dataclass(frozen=True, slots=True)
class TemplateValidationReport:
    valid: bool
    issues: tuple[ValidationIssue, ...]
    compiled_template: CompiledTemplate | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "issues", tuple(self.issues))
        if self.valid != (not self.issues):
            raise StructuredOutputError("STRUCTURED_OUTPUT_CONTRACT_INVALID", "valid must match issue presence")
        if self.valid and self.compiled_template is None:
            raise StructuredOutputError("STRUCTURED_OUTPUT_CONTRACT_INVALID", "valid report requires a template")


@dataclass(frozen=True, slots=True)
class CandidateValidationReport:
    valid: bool
    issues: tuple[ValidationIssue, ...]
    batch: StructuredCandidateBatch

    def __post_init__(self) -> None:
        object.__setattr__(self, "issues", tuple(self.issues))
        if self.valid != (not self.issues):
            raise StructuredOutputError("STRUCTURED_OUTPUT_CONTRACT_INVALID", "valid must match issue presence")


__all__ = [
    "CandidateClaim",
    "CandidateValidationReport",
    "ClaimState",
    "CompiledTemplate",
    "EvidenceBinding",
    "JsonScalar",
    "JsonValue",
    "StructuredCandidate",
    "StructuredCandidateBatch",
    "StructuredOutputError",
    "TemplateMetadata",
    "TemplateValidationReport",
    "ValidationIssue",
]
