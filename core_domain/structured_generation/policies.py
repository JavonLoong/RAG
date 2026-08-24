"""Fixed server-side resource policies for structured generation."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import StructuredGenerationError

_CAPS: dict[str, int | float] = {
    "max_candidates": 20,
    "max_evidence_refs": 20,
    "max_quote_chars_per_ref": 2000,
    "max_evidence_chars": 24000,
    "max_prompt_chars": 48000,
    "max_response_chars": 128000,
    "max_output_tokens": 8000,
    "max_logical_calls": 3,
    "max_http_attempts": 6,
    "max_repairs": 1,
    "request_timeout_seconds": 30.0,
    "total_timeout_seconds": 90.0,
}
_INTEGER_FIELDS = frozenset(
    {
        "max_candidates",
        "max_evidence_refs",
        "max_quote_chars_per_ref",
        "max_evidence_chars",
        "max_prompt_chars",
        "max_response_chars",
        "max_output_tokens",
        "max_logical_calls",
        "max_http_attempts",
        "max_repairs",
    }
)


@dataclass(frozen=True, slots=True)
class GenerationBudget:
    max_candidates: int = 20
    max_evidence_refs: int = 20
    max_quote_chars_per_ref: int = 2000
    max_evidence_chars: int = 24000
    max_prompt_chars: int = 48000
    max_response_chars: int = 128000
    max_output_tokens: int = 8000
    max_logical_calls: int = 3
    max_http_attempts: int = 6
    max_repairs: int = 1
    request_timeout_seconds: float = 30.0
    total_timeout_seconds: float = 90.0

    def __post_init__(self) -> None:
        for field_name, cap in _CAPS.items():
            value = getattr(self, field_name)
            wrong_type = (
                isinstance(value, bool)
                or (field_name in _INTEGER_FIELDS and not isinstance(value, int))
                or (field_name not in _INTEGER_FIELDS and not isinstance(value, int | float))
            )
            if wrong_type or value <= 0 or value > cap:
                if field_name == "max_repairs" and value == 0:
                    continue
                raise StructuredGenerationError(
                    "MODEL_REQUEST_LIMIT_EXCEEDED",
                    "Structured-generation configured limit is invalid.",
                )
        if self.total_timeout_seconds < self.request_timeout_seconds:
            raise StructuredGenerationError(
                "MODEL_REQUEST_LIMIT_EXCEEDED",
                "Structured-generation configured limit is invalid.",
            )


__all__ = ["GenerationBudget"]
