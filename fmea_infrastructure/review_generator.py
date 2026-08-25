"""Lazy environment-backed FMEA suggestion generation."""

# Stable public ReviewError branches deliberately preserve private exception chaining.
# ruff: noqa: TRY300, TRY301

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, cast

from core_domain.structured_generation import GenerationRunStatus, GenerationStage, StructuredGenerationError
from core_domain.structured_output import StructuredOutputError
from fmea_application.review_contracts import ReviewModelManifest, ReviewModelRequest, ReviewSuggestionDraft
from fmea_application.review_errors import ReviewError
from fmea_application.review_template_adapter import ReviewTemplateAdapter

_TEMPLATE_ID = "fmea-row-review"
_TEMPLATE_VERSION = "1.0.0"
_UNAVAILABLE_MODEL_CODES = frozenset(
    {
        "MODEL_AUTHENTICATION_FAILED",
        "MODEL_CONFIGURATION_INVALID",
        "MODEL_RATE_LIMITED",
        "MODEL_REQUEST_REJECTED",
        "MODEL_UPSTREAM_UNAVAILABLE",
        "MODEL_TIMEOUT",
        "MODEL_TOTAL_TIMEOUT",
    }
)


class EnvironmentReviewSuggestionGenerator:
    """Build the approved server-owned generation stack only for an executed run."""

    def __init__(self, *, registry_root: Path | None = None, template_path: Path | None = None) -> None:
        self._registry_root = registry_root
        self._template_path = template_path

    def _paths(self) -> tuple[Path, Path]:
        source = self._template_path or Path(__file__).resolve().parents[1] / "templates" / "examples" / "fmea-row-review.yaml"
        root = self._registry_root or Path(tempfile.gettempdir()) / "fmea-review-template-registry"
        return root, source

    def _compose(self) -> tuple[Any, Any]:
        from structured_generation_application import StructuredGenerationPipeline, StructuredGenerationService
        from structured_generation_infrastructure import (
            StrictCandidateBatchCodec,
            StrictCriticReportCodec,
            build_deepseek_gateway_from_env,
        )
        from structured_output_application import StructuredCandidateValidator, TemplateCompiler
        from structured_output_infrastructure import (
            Draft202012SchemaAdapter,
            FileTemplateRegistry,
            load_template_source,
        )

        registry_root, source_path = self._paths()
        schema_adapter = Draft202012SchemaAdapter()
        compiler = TemplateCompiler(schema_validator=schema_adapter, source_loader=load_template_source)
        registry = FileTemplateRegistry(registry_root)
        compiled = compiler.compile_path(source_path)
        source_bytes = source_path.read_bytes()
        try:
            stored = registry.get(_TEMPLATE_ID, _TEMPLATE_VERSION)
        except StructuredOutputError as exc:
            if exc.code != "TEMPLATE_NOT_FOUND":
                raise ReviewError(
                    "FMEA_MODEL_SUGGESTION_INVALID",
                    "the review template registry is invalid",
                ) from exc
            try:
                template = registry.register(compiled, source_bytes, source_path.suffix.lower())
            except StructuredOutputError as register_error:
                try:
                    raced = registry.get(_TEMPLATE_ID, _TEMPLATE_VERSION)
                except Exception as reread_error:
                    raise ReviewError(
                        "FMEA_MODEL_SUGGESTION_INVALID",
                        "the review template registry is invalid",
                    ) from reread_error
                if raced.template_hash != compiled.template_hash:
                    raise ReviewError(
                        "FMEA_MODEL_SUGGESTION_INVALID",
                        "the review template registry is stale",
                    ) from register_error
                template = raced
        else:
            if stored.template_hash != compiled.template_hash:
                raise ReviewError(
                    "FMEA_MODEL_SUGGESTION_INVALID",
                    "the review template registry is stale",
                )
            template = stored
        pipeline = StructuredGenerationPipeline(
            gateway=build_deepseek_gateway_from_env(),
            batch_codec=StrictCandidateBatchCodec(),
            critic_codec=StrictCriticReportCodec(),
            candidate_validator=StructuredCandidateValidator(schema_adapter),
        )
        return StructuredGenerationService(registry=registry, pipeline=pipeline), template

    @staticmethod
    def _safe_error(error: BaseException) -> ReviewError:
        if isinstance(error, ReviewError):
            return error
        if isinstance(error, StructuredGenerationError):
            code = (
                "FMEA_MODEL_SUGGESTION_UNAVAILABLE"
                if error.code in _UNAVAILABLE_MODEL_CODES
                else "FMEA_MODEL_SUGGESTION_INVALID"
            )
            message = (
                "the review model is temporarily unavailable"
                if code == "FMEA_MODEL_SUGGESTION_UNAVAILABLE"
                else "the review model returned an invalid suggestion"
            )
            return ReviewError(code, message, retryable=code == "FMEA_MODEL_SUGGESTION_UNAVAILABLE")
        return ReviewError("FMEA_MODEL_SUGGESTION_UNAVAILABLE", "the review model is temporarily unavailable", retryable=True)

    @staticmethod
    def _failed_result_error(result: Any) -> ReviewError:
        if any(getattr(issue, "code", None) in _UNAVAILABLE_MODEL_CODES for issue in result.generation_issues):
            return ReviewError(
                "FMEA_MODEL_SUGGESTION_UNAVAILABLE",
                "the review model is temporarily unavailable",
                retryable=True,
            )
        return ReviewError("FMEA_MODEL_SUGGESTION_INVALID", "the review model returned an invalid suggestion")

    @staticmethod
    def _final_pro_trace(result: Any) -> str:
        expected_stage = GenerationStage.REPAIR if result.repair_count == 1 else GenerationStage.CRITIC
        if result.repair_count not in {0, 1}:
            raise ReviewError("FMEA_MODEL_SUGGESTION_INVALID", "the review model returned an invalid suggestion")
        traces = tuple(
            trace
            for trace in result.traces
            if trace.stage is expected_stage
            and trace.model_id == "deepseek-v4-pro"
            and trace.response_hash is not None
            and trace.error_code is None
        )
        if len(traces) != 1:
            raise ReviewError("FMEA_MODEL_SUGGESTION_INVALID", "the review model returned an invalid suggestion")
        prompt_hash = cast(str, traces[0].prompt_hash)
        if len(prompt_hash) != 64 or any(character not in "0123456789abcdef" for character in prompt_hash):
            raise ReviewError("FMEA_MODEL_SUGGESTION_INVALID", "the review model returned an invalid suggestion")
        return "sha256:" + prompt_hash

    def generate(self, request: ReviewModelRequest) -> tuple[ReviewSuggestionDraft, ReviewModelManifest]:
        if not isinstance(request, ReviewModelRequest):
            raise ReviewError("FMEA_MODEL_SUGGESTION_INVALID", "the review model request is invalid")
        try:
            service, template = self._compose()
            adapter = ReviewTemplateAdapter()
            result = service.run(
                run_id=request.run_id,
                task=adapter.render_task(request),
                template_id=_TEMPLATE_ID,
                version=_TEMPLATE_VERSION,
                evidence_pack=request.evidence_pack,
            )
            if result.status is GenerationRunStatus.FAILED:
                raise self._failed_result_error(result)
            if result.status is not GenerationRunStatus.SUCCEEDED:
                raise ReviewError("FMEA_MODEL_SUGGESTION_INVALID", "the review model returned an invalid suggestion")
            draft = adapter.decode_draft(result, request.context)
            manifest = ReviewModelManifest(
                provider="deepseek",
                model="deepseek-v4-pro",
                template_id=template.metadata.template_id,
                template_version=template.metadata.version,
                prompt_hash=self._final_pro_trace(result),
            )
            return draft, manifest
        except ReviewError:
            raise
        except (OSError, KeyError, TypeError, ValueError, StructuredGenerationError) as exc:
            raise self._safe_error(exc) from exc
        except Exception as exc:
            raise self._safe_error(exc) from exc


__all__ = ["EnvironmentReviewSuggestionGenerator"]
