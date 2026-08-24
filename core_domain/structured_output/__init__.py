"""Public contracts for generic structured output."""

from .canonical import (
    canonical_hash,
    canonical_json,
    expand_pattern,
    parse_pointer,
    pattern_matches,
    resolve_pointer,
)
from .contracts import (
    CandidateClaim,
    CandidateValidationReport,
    ClaimState,
    CompiledTemplate,
    EvidenceBinding,
    JsonScalar,
    JsonValue,
    StructuredCandidate,
    StructuredCandidateBatch,
    StructuredOutputError,
    TemplateMetadata,
    TemplateValidationReport,
    ValidationIssue,
)
from .policies import TemplateLimits, measure_schema, validate_json_value

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
    "TemplateLimits",
    "TemplateMetadata",
    "TemplateValidationReport",
    "ValidationIssue",
    "canonical_hash",
    "canonical_json",
    "expand_pattern",
    "measure_schema",
    "parse_pointer",
    "pattern_matches",
    "resolve_pointer",
    "validate_json_value",
]
