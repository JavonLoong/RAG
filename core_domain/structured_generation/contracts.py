"""Provider-neutral contracts for bounded structured generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal, cast

from core_domain.structured_output import (
    StructuredCandidateBatch,
    StructuredOutputError,
    ValidationIssue,
    parse_pointer,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_MODEL_IDS = frozenset({"deepseek-v4-flash", "deepseek-v4-pro"})


class GenerationStage(str, Enum):
    GENERATE = "generate"
    CRITIC = "critic"
    REPAIR = "repair"


class GenerationRunStatus(str, Enum):
    SUCCEEDED = "succeeded"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class CriticVerdict(str, Enum):
    ACCEPT = "accept"
    REPAIR = "repair"
    NEEDS_REVIEW = "needs_review"


class SemanticSupport(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONTRADICTED = "contradicted"
    NOT_SUPPORTED = "not_supported"


class StructuredGenerationError(ValueError):
    """Stable safe error crossing structured-generation boundaries."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        stage: GenerationStage | None = None,
        retryable: bool = False,
        attempts: int = 0,
    ) -> None:
        if _CODE.fullmatch(code) is None or not isinstance(message, str) or not message:
            raise ValueError
        if stage is not None and not isinstance(stage, GenerationStage):
            raise ValueError
        if not isinstance(retryable, bool) or not _is_int(attempts) or attempts < 0:
            raise ValueError
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.retryable = retryable
        self.attempts = attempts


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _text(value: object, field_name: str, *, maximum: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise StructuredGenerationError(
            "GENERATION_CONTRACT_INVALID",
            f"Structured-generation {field_name} is invalid.",
        )
    return value


def _sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise StructuredGenerationError(
            "GENERATION_CONTRACT_INVALID",
            f"Structured-generation {field_name} is invalid.",
        )
    return value


def _strings(values: object, field_name: str) -> tuple[str, ...]:
    if isinstance(values, str) or not isinstance(values, list | tuple):
        raise StructuredGenerationError(
            "GENERATION_CONTRACT_INVALID",
            f"Structured-generation {field_name} is invalid.",
        )
    normalized = tuple(values)
    if any(not isinstance(item, str) or not item for item in normalized) or len(normalized) != len(
        set(normalized)
    ):
        raise StructuredGenerationError(
            "GENERATION_CONTRACT_INVALID",
            f"Structured-generation {field_name} is invalid.",
        )
    return cast("tuple[str, ...]", normalized)


def _tuple(values: object, expected: type, field_name: str) -> tuple[object, ...]:
    if isinstance(values, str) or not isinstance(values, list | tuple):
        raise StructuredGenerationError(
            "GENERATION_CONTRACT_INVALID",
            f"Structured-generation {field_name} is invalid.",
        )
    normalized = tuple(values)
    if any(not isinstance(item, expected) for item in normalized):
        raise StructuredGenerationError(
            "GENERATION_CONTRACT_INVALID",
            f"Structured-generation {field_name} is invalid.",
        )
    return normalized


def _tokens(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if not _is_int(value) or cast("int", value) < 0:
        raise StructuredGenerationError(
            "GENERATION_CONTRACT_INVALID",
            f"Structured-generation {field_name} is invalid.",
        )
    return cast("int", value)


@dataclass(frozen=True, slots=True)
class GenerationIssue:
    code: str
    message: str
    stage: GenerationStage | None = None
    retryable: bool = False
    pointer: str = ""

    def __post_init__(self) -> None:
        if _CODE.fullmatch(self.code) is None:
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Structured-generation issue code is invalid."
            )
        _text(self.message, "issue message", maximum=1000)
        if self.stage is not None and not isinstance(self.stage, GenerationStage):
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Structured-generation issue stage is invalid."
            )
        if not isinstance(self.retryable, bool) or not isinstance(self.pointer, str) or len(self.pointer) > 2000:
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Structured-generation issue audit fields are invalid."
            )


@dataclass(frozen=True, slots=True)
class StructuredModelRequest:
    stage: GenerationStage
    model_id: str
    system_prompt: str
    user_prompt: str
    max_output_tokens: int
    thinking_enabled: bool
    reasoning_effort: Literal["low", "high", "max"] | None

    def __post_init__(self) -> None:
        if not isinstance(self.stage, GenerationStage) or self.model_id not in _MODEL_IDS:
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Structured model request identity is invalid."
            )
        _text(self.system_prompt, "system prompt", maximum=48000)
        _text(self.user_prompt, "user prompt", maximum=48000)
        if not _is_int(self.max_output_tokens) or not 1 <= self.max_output_tokens <= 8000:
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Structured model output budget is invalid."
            )
        if not isinstance(self.thinking_enabled, bool):
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Structured model thinking mode is invalid."
            )
        if self.stage is GenerationStage.GENERATE:
            valid_thinking = not self.thinking_enabled and self.reasoning_effort is None
        else:
            valid_thinking = self.thinking_enabled and self.reasoning_effort in {"low", "high", "max"}
        if not valid_thinking:
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Structured model thinking configuration is invalid."
            )


@dataclass(frozen=True, slots=True)
class StructuredModelResponse:
    content: str
    model_id: str
    finish_reason: str
    input_tokens: int | None
    output_tokens: int | None
    response_hash: str
    http_attempts: int

    def __post_init__(self) -> None:
        _text(self.content, "model content", maximum=128000)
        if self.model_id not in _MODEL_IDS:
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Structured model response identity is invalid."
            )
        _text(self.finish_reason, "finish reason", maximum=128)
        _tokens(self.input_tokens, "input tokens")
        _tokens(self.output_tokens, "output tokens")
        _sha256(self.response_hash, "response hash")
        if not _is_int(self.http_attempts) or not 1 <= self.http_attempts <= 6:
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Structured model attempt count is invalid."
            )


@dataclass(frozen=True, slots=True)
class CriticFinding:
    candidate_id: str
    target: str
    support: SemanticSupport
    code: str
    evidence_ids: tuple[str, ...]
    explanation: str

    def __post_init__(self) -> None:
        _text(self.candidate_id, "critic candidate ID", maximum=256)
        try:
            parse_pointer(self.target)
        except StructuredOutputError as exc:
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Critic target is invalid."
            ) from exc
        if not isinstance(self.support, SemanticSupport) or _CODE.fullmatch(self.code) is None:
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Critic finding classification is invalid."
            )
        object.__setattr__(self, "evidence_ids", _strings(self.evidence_ids, "critic evidence IDs"))
        _text(self.explanation, "critic explanation", maximum=500)


@dataclass(frozen=True, slots=True)
class CriticReport:
    verdict: CriticVerdict
    findings: tuple[CriticFinding, ...]
    summary: str

    def __post_init__(self) -> None:
        if not isinstance(self.verdict, CriticVerdict):
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Critic verdict is invalid."
            )
        normalized = cast(
            "tuple[CriticFinding, ...]",
            _tuple(self.findings, CriticFinding, "critic findings"),
        )
        identities = tuple((finding.candidate_id, finding.target) for finding in normalized)
        if len(identities) != len(set(identities)):
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Critic findings contain a duplicate."
            )
        object.__setattr__(self, "findings", normalized)
        _text(self.summary, "critic summary", maximum=1000)


@dataclass(frozen=True, slots=True)
class ModelCallTrace:
    stage: GenerationStage
    model_id: str
    prompt_hash: str
    response_hash: str | None
    http_attempts: int
    input_tokens: int | None
    output_tokens: int | None
    finish_reason: str | None
    error_code: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.stage, GenerationStage) or self.model_id not in _MODEL_IDS:
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Model trace identity is invalid."
            )
        _sha256(self.prompt_hash, "prompt hash")
        if not _is_int(self.http_attempts) or not 1 <= self.http_attempts <= 6:
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Model trace attempt count is invalid."
            )
        _tokens(self.input_tokens, "input tokens")
        _tokens(self.output_tokens, "output tokens")
        if self.response_hash is None:
            if self.finish_reason is not None or self.error_code is None or _CODE.fullmatch(self.error_code) is None:
                raise StructuredGenerationError(
                    "GENERATION_CONTRACT_INVALID", "Failed model trace is invalid."
                )
        else:
            _sha256(self.response_hash, "response hash")
            if self.error_code is not None:
                raise StructuredGenerationError(
                    "GENERATION_CONTRACT_INVALID", "Successful model trace cannot contain an error."
                )
            _text(self.finish_reason, "finish reason", maximum=128)


@dataclass(frozen=True, slots=True)
class GenerationRunResult:
    run_id: str
    status: GenerationRunStatus
    batch: StructuredCandidateBatch | None
    critic_report: CriticReport | None
    deterministic_issues: tuple[ValidationIssue, ...]
    generation_issues: tuple[GenerationIssue, ...]
    traces: tuple[ModelCallTrace, ...]
    repair_count: int

    def __post_init__(self) -> None:
        _text(self.run_id, "run ID", maximum=256)
        if not isinstance(self.status, GenerationRunStatus):
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Generation result status is invalid."
            )
        object.__setattr__(
            self,
            "deterministic_issues",
            cast("tuple[ValidationIssue, ...]", _tuple(self.deterministic_issues, ValidationIssue, "issues")),
        )
        object.__setattr__(
            self,
            "generation_issues",
            cast("tuple[GenerationIssue, ...]", _tuple(self.generation_issues, GenerationIssue, "issues")),
        )
        object.__setattr__(
            self,
            "traces",
            cast("tuple[ModelCallTrace, ...]", _tuple(self.traces, ModelCallTrace, "traces")),
        )
        if not _is_int(self.repair_count) or not 0 <= self.repair_count <= 1:
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Generation result repair count is invalid."
            )
        if self.batch is not None and not isinstance(self.batch, StructuredCandidateBatch):
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Generation result batch is invalid."
            )
        if self.critic_report is not None and not isinstance(self.critic_report, CriticReport):
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Generation result critic report is invalid."
            )
        if self.status in {GenerationRunStatus.SUCCEEDED, GenerationRunStatus.NEEDS_REVIEW} and self.batch is None:
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "Successful generation result requires a batch."
            )
        if self.status is GenerationRunStatus.FAILED and self.batch is not None:
            raise StructuredGenerationError(
                "GENERATION_CONTRACT_INVALID", "A failed generation result cannot expose a batch."
            )
        if self.status is GenerationRunStatus.SUCCEEDED:
            if self.critic_report is None or self.critic_report.verdict is not CriticVerdict.ACCEPT:
                raise StructuredGenerationError(
                    "GENERATION_CONTRACT_INVALID", "Successful generation result requires an accepting critic."
                )
            if self.repair_count or self.deterministic_issues or self.generation_issues:
                raise StructuredGenerationError(
                    "GENERATION_CONTRACT_INVALID", "Successful generation result cannot contain unresolved issues."
                )


__all__ = [
    "CriticFinding",
    "CriticReport",
    "CriticVerdict",
    "GenerationIssue",
    "GenerationRunResult",
    "GenerationRunStatus",
    "GenerationStage",
    "ModelCallTrace",
    "SemanticSupport",
    "StructuredGenerationError",
    "StructuredModelRequest",
    "StructuredModelResponse",
]
