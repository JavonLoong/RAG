"""Structured-generation adapter for bounded FMEA risk proposals."""

# ruff: noqa: TRY003

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from core_domain.structured_generation import GenerationRunStatus, GenerationStage, StructuredGenerationError
from core_domain.structured_output import StructuredOutputError
from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
from fmea_application.assistance_service import stable_id, utc_now
from fmea_application.review_errors import ReviewError
from fmea_application.risk_contracts import RiskModelRequest

_TEMPLATE_ID = "fmea-risk-proposal"
_TEMPLATE_VERSION = "1.0.0"
_ROOT_KEYS = {"dimensions", "reason", "uncertainty"}
_UNAVAILABLE_CODES = {
    "MODEL_AUTHENTICATION_FAILED",
    "MODEL_CONFIGURATION_INVALID",
    "MODEL_RATE_LIMITED",
    "MODEL_REQUEST_REJECTED",
    "MODEL_UPSTREAM_UNAVAILABLE",
    "MODEL_TIMEOUT",
    "MODEL_TOTAL_TIMEOUT",
}


def _invalid(message: str) -> ReviewError:
    return ReviewError("FMEA_MODEL_SUGGESTION_INVALID", message)


def _safe_generation_error(error: StructuredGenerationError) -> ReviewError:
    if error.code in _UNAVAILABLE_CODES:
        return ReviewError(
            "FMEA_MODEL_SUGGESTION_UNAVAILABLE",
            "the FMEA assistance model is temporarily unavailable",
            retryable=True,
        )
    return _invalid("the FMEA assistance model returned an invalid suggestion")


def _compose_service(template_id: str, version: str, source_path: Path, registry_root: Path | None = None) -> Any:
    from structured_generation_application import StructuredGenerationPipeline, StructuredGenerationService
    from structured_generation_infrastructure import (
        StrictCandidateBatchCodec,
        StrictCriticReportCodec,
        build_deepseek_gateway_from_env,
    )
    from structured_output_application import StructuredCandidateValidator, TemplateCompiler
    from structured_output_infrastructure import Draft202012SchemaAdapter, FileTemplateRegistry, load_template_source

    root = registry_root or Path(tempfile.gettempdir()) / "fmea-assistance-template-registry"
    schema = Draft202012SchemaAdapter()
    compiled = TemplateCompiler(schema_validator=schema, source_loader=load_template_source).compile_path(source_path)
    if compiled.metadata.template_id != template_id or compiled.metadata.version != version:
        raise _invalid("built-in FMEA assistance template identity is invalid")
    registry = FileTemplateRegistry(root)
    source = source_path.read_bytes()
    try:
        stored = registry.get(template_id, version)
    except StructuredOutputError as exc:
        if exc.code != "TEMPLATE_NOT_FOUND":
            raise _invalid("FMEA assistance template registry is invalid") from exc
        registry.register(compiled, source, source_path.suffix.lower())
    else:
        if stored.template_hash != compiled.template_hash:
            raise _invalid("FMEA assistance template registry is stale")
    pipeline = StructuredGenerationPipeline(
        gateway=build_deepseek_gateway_from_env(),
        batch_codec=StrictCandidateBatchCodec(),
        critic_codec=StrictCriticReportCodec(),
        candidate_validator=StructuredCandidateValidator(schema),
    )
    return StructuredGenerationService(registry=registry, pipeline=pipeline)


def _candidate(result: Any, *, template_id: str, evidence_pack_id: str) -> tuple[Any, Any]:
    if result.status is not GenerationRunStatus.SUCCEEDED or result.batch is None:
        raise _invalid("the risk model did not return one accepted candidate")
    if result.repair_count not in {0, 1}:
        raise _invalid("the risk model exceeded the bounded repair budget")
    batch = result.batch
    if (
        batch.template_id != template_id
        or batch.template_version != _TEMPLATE_VERSION
        or batch.evidence_pack_id != evidence_pack_id
        or len(batch.candidates) != 1
    ):
        raise _invalid("the risk model candidate identity is invalid")
    expected_stage = GenerationStage.REPAIR if result.repair_count == 1 else GenerationStage.CRITIC
    traces = tuple(
        trace
        for trace in result.traces
        if trace.stage is expected_stage
        and trace.model_id == "deepseek-v4-pro"
        and trace.response_hash is not None
        and trace.error_code is None
    )
    if len(traces) != 1:
        raise _invalid("the risk model final critic trace is invalid")
    return batch.candidates[0], traces[0]


def _mapping(value: object, message: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _invalid(message)
    return value


class RiskSuggestionGenerator:
    """Decode a generic structured-generation result into a proposal-only envelope."""

    def __init__(self, service: Any, *, clock: Callable[[], str] = utc_now) -> None:
        self._service = service
        self._clock = clock

    @staticmethod
    def _task(request: RiskModelRequest) -> str:
        anchors = {
            name: [{"score": score, "description": description} for score, description in values]
            for name, values in request.rule_pack.dimension_anchors
        }
        payload = {
            "row": {
                "row_id": request.context.row.row_id,
                "record_version": request.context.row.record_version,
                "item": request.context.item_label,
                "function": request.context.function_label,
                "failure_mode": request.context.row.failure_mode,
                "causes": list(request.context.row.causes),
                "effects": list(request.context.row.effects),
                "controls": list(request.context.row.controls),
            },
            "scoring": {
                "required_dimensions": list(request.rule_pack.required_dimensions),
                "score_min": request.rule_pack.score_min,
                "score_max": request.rule_pack.score_max,
                "anchors": anchors,
                "missing_score_policy": request.rule_pack.missing_score_policy,
                "conflict_score_policy": request.rule_pack.conflict_score_policy,
            },
            "evidence": [
                {
                    "evidence_id": ref.evidence_id,
                    "source_type": ref.source_type,
                    "source_trust": ref.source_trust,
                    "is_primary": ref.is_primary,
                    "locator": ref.locator,
                    "quote": ref.quote,
                }
                for ref in request.context.evidence.refs
            ],
            "rule": "Return score proposals only. Never return status, RPN, priority, confirmation, or derived risk.",
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def generate(self, request: RiskModelRequest) -> AssistanceSuggestion[object]:  # noqa: C901
        if not isinstance(request, RiskModelRequest):
            raise _invalid("risk model request is invalid")
        try:
            result = self._service.run(
                run_id=request.run_id,
                task=self._task(request),
                template_id=_TEMPLATE_ID,
                version=_TEMPLATE_VERSION,
                evidence_pack=request.evidence_pack,
            )
            candidate, trace = _candidate(result, template_id=_TEMPLATE_ID, evidence_pack_id=request.evidence_pack.pack_id)
            payload = _mapping(candidate.payload, "risk candidate payload must be an object")
            if set(payload) != _ROOT_KEYS:
                raise _invalid("risk candidate contains unknown or missing authority fields")
            raw_dimensions = payload["dimensions"]
            if isinstance(raw_dimensions, str | bytes) or not isinstance(raw_dimensions, Sequence):
                raise _invalid("risk candidate dimensions must be an array")
            dimensions: list[dict[str, object]] = []
            evidence_ids: list[str] = []
            known_ids = {ref.evidence_id for ref in request.evidence_pack.refs}
            for raw in raw_dimensions:
                item = _mapping(raw, "risk dimension must be an object")
                if set(item) != {"name", "value", "evidence_ids", "reason", "uncertainty"}:
                    raise _invalid("risk dimension contains unknown or missing fields")
                ids = item["evidence_ids"]
                if isinstance(ids, str | bytes) or not isinstance(ids, Sequence) or not all(isinstance(i, str) for i in ids):
                    raise _invalid("risk dimension evidence IDs are invalid")
                normalized_ids = list(ids)
                if not set(normalized_ids).issubset(known_ids):
                    raise _invalid("risk dimension evidence is outside the EvidencePack")
                for evidence_id in normalized_ids:
                    if evidence_id not in evidence_ids:
                        evidence_ids.append(evidence_id)
                dimensions.append(dict(item))
            normalized = {"dimensions": dimensions, "reason": payload["reason"], "uncertainty": payload["uncertainty"]}
            return AssistanceSuggestion(
                suggestion_id=stable_id("risk-suggestion", request.run_id, candidate.candidate_id),
                kind=AssistanceKind.SCORE_RECOMMENDATION,
                workspace_id=request.evidence_pack.workspace_id,
                target_type="fmea_row",
                target_id=request.context.row.row_id,
                target_record_version=request.context.row.record_version,
                evidence_pack_ids=(request.evidence_pack.pack_id,),
                payload=normalized,
                evidence_ids=tuple(evidence_ids),
                uncertainty=payload["uncertainty"],
                model_hash=trace.response_hash,
                prompt_hash=trace.prompt_hash,
                run_id=request.run_id,
                trace_id=stable_id("risk-trace", request.run_id),
                domain_pack_id=request.domain_pack.pack_id,
                domain_pack_version=request.domain_pack.version,
                template_id=request.template_id,
                template_version=request.template_version,
                rule_pack_id=request.rule_pack.rule_pack_id,
                rule_pack_version=request.rule_pack.version,
                created_at=self._clock(),
            )
        except ReviewError:
            raise
        except StructuredGenerationError as exc:
            raise _safe_generation_error(exc) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise _invalid("the risk model returned an invalid suggestion") from exc


class EnvironmentRiskSuggestionGenerator:
    """Lazily compose the approved Flash -> Pro critic -> one-repair stack."""

    def __init__(self, *, registry_root: Path | None = None, template_path: Path | None = None) -> None:
        self._registry_root = registry_root
        self._template_path = template_path or Path(__file__).resolve().parents[1] / "templates" / "examples" / "fmea-risk-proposal.yaml"

    def generate(self, request: RiskModelRequest) -> AssistanceSuggestion[object]:
        try:
            service = _compose_service(_TEMPLATE_ID, _TEMPLATE_VERSION, self._template_path, self._registry_root)
            return RiskSuggestionGenerator(service).generate(request)
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError(
                "FMEA_MODEL_SUGGESTION_UNAVAILABLE",
                "the risk model is temporarily unavailable",
                retryable=True,
            ) from exc


__all__ = ["EnvironmentRiskSuggestionGenerator", "RiskSuggestionGenerator"]
