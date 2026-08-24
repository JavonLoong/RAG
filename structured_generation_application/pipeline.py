"""Explicit bounded generate, critic and single-repair orchestration."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from core_domain.structured_generation import (
    CriticReport,
    CriticVerdict,
    GenerationIssue,
    GenerationRunResult,
    GenerationRunStatus,
    GenerationStage,
    ModelCallTrace,
    StructuredGenerationError,
    StructuredModelRequest,
    StructuredModelResponse,
)
from core_domain.structured_output import (
    CandidateValidationReport,
    StructuredCandidateBatch,
    ValidationIssue,
)
from structured_output_application import StructuredCandidateValidator

from .contracts import GenerationRunRequest
from .critic_validation import validate_critic_report
from .ports import CandidateBatchCodec, CriticReportCodec, StructuredModelGateway
from .prompts import PromptBundle, build_critic_prompt, build_generation_prompt, build_repair_prompt


@dataclass(slots=True)
class _RunState:
    started_at: float
    logical_calls: int = 0
    http_attempts: int = 0
    traces: list[ModelCallTrace] = field(default_factory=list)
    generation_issues: list[GenerationIssue] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Generated:
    response: StructuredModelResponse
    batch: StructuredCandidateBatch
    validation: CandidateValidationReport


_GATEWAY_BUDGET_ERROR = "gateway exceeded the supplied attempt budget"


class StructuredGenerationPipeline:
    def __init__(
        self,
        *,
        gateway: StructuredModelGateway,
        batch_codec: CandidateBatchCodec,
        critic_codec: CriticReportCodec,
        candidate_validator: StructuredCandidateValidator,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._gateway = gateway
        self._batch_codec = batch_codec
        self._critic_codec = critic_codec
        self._candidate_validator = candidate_validator
        self._monotonic = monotonic

    @staticmethod
    def _generation_issue(error: StructuredGenerationError, stage: GenerationStage) -> GenerationIssue:
        return GenerationIssue(
            code=error.code,
            message=str(error),
            stage=error.stage or stage,
            retryable=error.retryable,
        )

    @staticmethod
    def _validation_issue(issue: ValidationIssue, stage: GenerationStage) -> GenerationIssue:
        return GenerationIssue(
            code=issue.code,
            message=issue.message,
            stage=stage,
            pointer=issue.pointer,
        )

    @staticmethod
    def _model_request(
        request: GenerationRunRequest,
        stage: GenerationStage,
        bundle: PromptBundle,
    ) -> StructuredModelRequest:
        if stage is GenerationStage.GENERATE:
            model_id = request.generator_model
            thinking_enabled = False
            reasoning_effort: Literal["high"] | None = None
        elif stage is GenerationStage.CRITIC:
            model_id = request.critic_model
            thinking_enabled = True
            reasoning_effort = "high"
        else:
            model_id = request.repair_model
            thinking_enabled = True
            reasoning_effort = "high"
        return StructuredModelRequest(
            stage=stage,
            model_id=model_id,
            system_prompt=bundle.system_prompt,
            user_prompt=bundle.user_prompt,
            max_output_tokens=request.budget.max_output_tokens,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
        )

    @staticmethod
    def _failed_trace(
        stage: GenerationStage,
        model_id: str,
        bundle: PromptBundle,
        error: StructuredGenerationError,
    ) -> ModelCallTrace:
        return ModelCallTrace(
            stage=stage,
            model_id=model_id,
            prompt_hash=bundle.prompt_hash,
            response_hash=None,
            http_attempts=error.attempts,
            input_tokens=None,
            output_tokens=None,
            finish_reason=None,
            error_code=error.code,
        )

    @staticmethod
    def _successful_trace(
        stage: GenerationStage,
        bundle: PromptBundle,
        response: StructuredModelResponse,
    ) -> ModelCallTrace:
        return ModelCallTrace(
            stage=stage,
            model_id=response.model_id,
            prompt_hash=bundle.prompt_hash,
            response_hash=response.response_hash,
            http_attempts=response.http_attempts,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            finish_reason=response.finish_reason,
            error_code=None,
        )

    def _call_window(
        self,
        request: GenerationRunRequest,
        state: _RunState,
        stage: GenerationStage,
    ) -> tuple[int, float] | None:
        remaining_calls = request.budget.max_logical_calls - state.logical_calls
        remaining_attempts = request.budget.max_http_attempts - state.http_attempts
        remaining_time = request.budget.total_timeout_seconds - (self._monotonic() - state.started_at)
        if remaining_calls <= 0:
            boundary_error = StructuredGenerationError(
                "MODEL_CALL_LIMIT_EXCEEDED",
                "The structured-generation logical-call limit is exhausted.",
                stage=stage,
            )
        elif remaining_attempts <= 0:
            boundary_error = StructuredGenerationError(
                "MODEL_ATTEMPT_LIMIT_EXCEEDED",
                "The structured-generation HTTP-attempt limit is exhausted.",
                stage=stage,
            )
        elif remaining_time <= 0:
            boundary_error = StructuredGenerationError(
                "MODEL_TOTAL_TIMEOUT",
                "The structured-generation run deadline is exhausted.",
                stage=stage,
            )
        else:
            return remaining_attempts, min(request.budget.request_timeout_seconds, remaining_time)
        state.generation_issues.append(self._generation_issue(boundary_error, stage))
        return None

    def _response_boundary_error(
        self,
        request: GenerationRunRequest,
        state: _RunState,
        stage: GenerationStage,
        expected_model: str,
        response: StructuredModelResponse,
    ) -> StructuredGenerationError | None:
        if response.model_id != expected_model:
            return StructuredGenerationError(
                "MODEL_ID_MISMATCH",
                "The structured-generation provider returned an unexpected model.",
                stage=stage,
                attempts=response.http_attempts,
            )
        if len(response.content) > request.budget.max_response_chars:
            return StructuredGenerationError(
                "MODEL_OUTPUT_LIMIT_EXCEEDED",
                "The structured-generation model output exceeds the configured limit.",
                stage=stage,
                attempts=response.http_attempts,
            )
        if self._monotonic() - state.started_at > request.budget.total_timeout_seconds:
            return StructuredGenerationError(
                "MODEL_TOTAL_TIMEOUT",
                "The structured-generation run deadline is exhausted.",
                stage=stage,
                attempts=response.http_attempts,
            )
        return None

    def _call(
        self,
        request: GenerationRunRequest,
        state: _RunState,
        stage: GenerationStage,
        bundle: PromptBundle,
    ) -> StructuredModelResponse | None:
        window = self._call_window(request, state, stage)
        if window is None:
            return None
        remaining_attempts, timeout_seconds = window

        model_request = self._model_request(request, stage, bundle)
        state.logical_calls += 1
        try:
            response = self._gateway.complete(
                model_request,
                max_attempts=remaining_attempts,
                timeout_seconds=timeout_seconds,
            )
        except StructuredGenerationError as caught:
            if caught.attempts > remaining_attempts:
                raise RuntimeError(_GATEWAY_BUDGET_ERROR) from caught
            state.http_attempts += caught.attempts
            if caught.attempts:
                state.traces.append(self._failed_trace(stage, model_request.model_id, bundle, caught))
            state.generation_issues.append(self._generation_issue(caught, stage))
            return None

        if response.http_attempts > remaining_attempts:
            raise RuntimeError(_GATEWAY_BUDGET_ERROR)
        state.http_attempts += response.http_attempts
        boundary_error = self._response_boundary_error(
            request,
            state,
            stage,
            model_request.model_id,
            response,
        )
        if boundary_error is not None:
            state.traces.append(self._failed_trace(stage, model_request.model_id, bundle, boundary_error))
            state.generation_issues.append(self._generation_issue(boundary_error, stage))
            return None
        state.traces.append(self._successful_trace(stage, bundle, response))
        return response

    @staticmethod
    def _result(
        request: GenerationRunRequest,
        state: _RunState,
        status: GenerationRunStatus,
        *,
        batch: StructuredCandidateBatch | None,
        critic_report: CriticReport | None = None,
        deterministic_issues: tuple[ValidationIssue, ...] = (),
        repair_count: int = 0,
    ) -> GenerationRunResult:
        return GenerationRunResult(
            run_id=request.run_id,
            status=status,
            batch=batch,
            critic_report=critic_report,
            deterministic_issues=deterministic_issues,
            generation_issues=tuple(state.generation_issues),
            traces=tuple(state.traces),
            repair_count=repair_count,
        )

    def _repair(
        self,
        request: GenerationRunRequest,
        state: _RunState,
        *,
        original_output: str,
        deterministic_issues: tuple[ValidationIssue, ...],
        critic_report: CriticReport | None,
    ) -> GenerationRunResult:
        for issue in deterministic_issues:
            state.generation_issues.append(self._validation_issue(issue, GenerationStage.GENERATE))
        try:
            bundle = build_repair_prompt(
                request,
                original_output=original_output,
                deterministic_issues=deterministic_issues,
                generation_issues=tuple(state.generation_issues),
                critic_report=critic_report,
            )
        except StructuredGenerationError as error:
            state.generation_issues.append(self._generation_issue(error, GenerationStage.REPAIR))
            return self._result(
                request,
                state,
                GenerationRunStatus.FAILED,
                batch=None,
                deterministic_issues=deterministic_issues,
                repair_count=1,
            )
        response = self._call(request, state, GenerationStage.REPAIR, bundle)
        if response is None:
            return self._result(
                request,
                state,
                GenerationRunStatus.FAILED,
                batch=None,
                deterministic_issues=deterministic_issues,
                repair_count=1,
            )
        try:
            batch = self._batch_codec.decode_batch(response.content)
        except StructuredGenerationError as error:
            state.generation_issues.append(self._generation_issue(error, GenerationStage.REPAIR))
            return self._result(
                request,
                state,
                GenerationRunStatus.FAILED,
                batch=None,
                repair_count=1,
            )
        validation = self._candidate_validator.validate(batch, request.template, request.evidence_pack)
        if not validation.valid:
            return self._result(
                request,
                state,
                GenerationRunStatus.FAILED,
                batch=None,
                deterministic_issues=validation.issues,
                repair_count=1,
            )
        return self._result(
            request,
            state,
            GenerationRunStatus.NEEDS_REVIEW,
            batch=batch,
            repair_count=1,
        )

    def _generate(
        self,
        request: GenerationRunRequest,
        state: _RunState,
    ) -> _Generated | GenerationRunResult:
        try:
            generation_bundle = build_generation_prompt(request)
        except StructuredGenerationError as caught:
            state.generation_issues.append(self._generation_issue(caught, GenerationStage.GENERATE))
            return self._result(request, state, GenerationRunStatus.FAILED, batch=None)
        generation_response = self._call(
            request,
            state,
            GenerationStage.GENERATE,
            generation_bundle,
        )
        if generation_response is None:
            return self._result(request, state, GenerationRunStatus.FAILED, batch=None)
        try:
            batch = self._batch_codec.decode_batch(generation_response.content)
        except StructuredGenerationError as caught:
            state.generation_issues.append(self._generation_issue(caught, GenerationStage.GENERATE))
            return self._repair(
                request,
                state,
                original_output=generation_response.content,
                deterministic_issues=(),
                critic_report=None,
            )

        return _Generated(
            response=generation_response,
            batch=batch,
            validation=self._candidate_validator.validate(batch, request.template, request.evidence_pack),
        )

    def _review_or_repair(
        self,
        request: GenerationRunRequest,
        state: _RunState,
        generated: _Generated,
        *,
        critic_report: CriticReport | None,
    ) -> GenerationRunResult:
        if generated.validation.valid:
            return self._result(
                request,
                state,
                GenerationRunStatus.NEEDS_REVIEW,
                batch=generated.batch,
                critic_report=critic_report,
                deterministic_issues=generated.validation.issues,
            )
        return self._repair(
            request,
            state,
            original_output=generated.response.content,
            deterministic_issues=generated.validation.issues,
            critic_report=critic_report,
        )

    def _critic(
        self,
        request: GenerationRunRequest,
        state: _RunState,
        generated: _Generated,
    ) -> GenerationRunResult:
        try:
            critic_bundle = build_critic_prompt(
                request,
                generated.batch,
                deterministic_issues=generated.validation.issues,
            )
        except StructuredGenerationError as caught:
            state.generation_issues.append(self._generation_issue(caught, GenerationStage.CRITIC))
            return self._review_or_repair(request, state, generated, critic_report=None)
        critic_response = self._call(request, state, GenerationStage.CRITIC, critic_bundle)
        if critic_response is None:
            return self._review_or_repair(request, state, generated, critic_report=None)
        try:
            critic_report = self._critic_codec.decode_critic(critic_response.content)
        except StructuredGenerationError as caught:
            state.generation_issues.append(self._generation_issue(caught, GenerationStage.CRITIC))
            return self._review_or_repair(request, state, generated, critic_report=None)

        critic_issues = validate_critic_report(critic_report, generated.batch, request.evidence_pack)
        state.generation_issues.extend(critic_issues)
        if critic_issues:
            return self._review_or_repair(request, state, generated, critic_report=critic_report)
        if generated.validation.issues or critic_report.verdict is CriticVerdict.REPAIR:
            return self._repair(
                request,
                state,
                original_output=generated.response.content,
                deterministic_issues=generated.validation.issues,
                critic_report=critic_report,
            )
        if critic_report.verdict is CriticVerdict.ACCEPT:
            return self._result(
                request,
                state,
                GenerationRunStatus.SUCCEEDED,
                batch=generated.batch,
                critic_report=critic_report,
            )
        return self._result(
            request,
            state,
            GenerationRunStatus.NEEDS_REVIEW,
            batch=generated.batch,
            critic_report=critic_report,
        )

    def run(self, request: GenerationRunRequest) -> GenerationRunResult:
        state = _RunState(started_at=self._monotonic())
        generated = self._generate(request, state)
        if isinstance(generated, GenerationRunResult):
            return generated
        return self._critic(request, state, generated)


__all__ = ["StructuredGenerationPipeline"]
