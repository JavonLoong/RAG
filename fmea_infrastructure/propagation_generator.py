"""Structured-generation adapter for bounded propagation hypotheses."""

# ruff: noqa: TRY003

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from core_domain.fmea.states import ClaimStatus, EvidenceSupportStatus
from core_domain.structured_generation import GenerationRunStatus, GenerationStage, StructuredGenerationError
from core_domain.structured_output import CompiledTemplate, JsonValue, TemplateLimits
from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
from fmea_application.assistance_service import stable_id, utc_now
from fmea_application.propagation_service import (
    PROPAGATION_EDGE_PROPOSAL_KEYS,
    PropagationError,
    PropagationModelRequest,
)

_TEMPLATE_ID = "fmea-propagation-hypothesis"
_TEMPLATE_VERSION = "1.0.0"
_EDGE_KEYS = PROPAGATION_EDGE_PROPOSAL_KEYS


class PropagationGenerationError(PropagationError):
    """Safe error raised when a model proposal crosses the candidate boundary."""


def _invalid(message: str, code: str = "FMEA_PROPAGATION_SUGGESTION_INVALID") -> PropagationGenerationError:
    return PropagationGenerationError(code, message)


def _template_source() -> dict[str, JsonValue]:
    edge_properties = {
        "source_entity_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "target_entity_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "relation_type": {"type": "string", "minLength": 1, "maxLength": 64},
        "interface_variable": {"type": "string", "minLength": 1, "maxLength": 128},
        "unit": {"type": "string", "minLength": 1, "maxLength": 64},
        "direction": {"type": "string", "minLength": 1, "maxLength": 128},
        "threshold": {"type": ["string", "null"], "maxLength": 256},
        "operating_modes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "maxLength": 128},
        },
        "delay_ms": {"type": ["integer", "null"], "minimum": 0},
        "response_time_ms": {"type": ["integer", "null"], "minimum": 0},
        "fault_tolerance_time_ms": {"type": ["integer", "null"], "minimum": 0},
        "barrier_ids": {
            "type": "array",
            "maxItems": 64,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "maxLength": 256},
        },
        "evidence_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "maxLength": 128},
        },
        "evidence_support": {
            "type": "string",
            "enum": [item.value for item in EvidenceSupportStatus],
        },
        "claim_status": {"type": "string", "enum": [item.value for item in ClaimStatus]},
        "path_length": {"type": "integer", "minimum": 1, "maximum": 2},
        "is_cyclic": {"type": "boolean"},
        "is_unprocessed": {"type": "boolean"},
        "is_external": {"type": "boolean"},
        "is_terminal": {"type": "boolean"},
        "risk_priority": {"type": ["string", "null"], "maxLength": 64},
    }
    return cast(
        dict[str, JsonValue],
        {
            "template": {
                "id": _TEMPLATE_ID,
                "version": _TEMPLATE_VERSION,
                "title": "Bounded FMEA propagation hypothesis",
                "description": "Propose topology-bounded propagation edges only; deterministic code and human review own acceptance.",
                "domain_tags": ["fmea", "propagation", "proposal"],
                "schema_dialect": "https://json-schema.org/draft/2020-12/schema",
            },
            "output_schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["edges"],
                "properties": {
                    "edges": {
                        "type": "array",
                        "maxItems": 40,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": sorted(_EDGE_KEYS),
                            "properties": edge_properties,
                        },
                    }
                },
            },
            "evidence_bindings": [],
        },
    )


class _SingleTemplateRegistry:
    def __init__(self, template: CompiledTemplate) -> None:
        self._template = template

    def register(self, template: CompiledTemplate, _source_bytes: bytes, _source_suffix: str) -> CompiledTemplate:
        if template != self._template:
            raise ValueError("the propagation template registry is immutable")
        return self._template

    def get(self, template_id: str, version: str) -> CompiledTemplate:
        if template_id != _TEMPLATE_ID or version != _TEMPLATE_VERSION:
            raise KeyError((template_id, version))
        return self._template


def _compose_service(gateway: Any) -> Any:
    from structured_generation_application import StructuredGenerationPipeline, StructuredGenerationService
    from structured_generation_infrastructure import StrictCandidateBatchCodec, StrictCriticReportCodec
    from structured_output_application import StructuredCandidateValidator, TemplateCompiler
    from structured_output_infrastructure import Draft202012SchemaAdapter

    source = _template_source()

    def source_loader(path: str | Path, limits: TemplateLimits | None = None) -> dict[str, JsonValue]:
        del path, limits
        return source

    compiler = TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=source_loader,
    )
    compiled = compiler.compile(source)
    pipeline = StructuredGenerationPipeline(
        gateway=gateway,
        batch_codec=StrictCandidateBatchCodec(),
        critic_codec=StrictCriticReportCodec(),
        candidate_validator=StructuredCandidateValidator(Draft202012SchemaAdapter()),
    )
    return StructuredGenerationService(registry=_SingleTemplateRegistry(compiled), pipeline=pipeline)


def _final_trace(result: Any) -> Any:
    expected_stage = GenerationStage.REPAIR if result.repair_count == 1 else GenerationStage.CRITIC
    traces = tuple(
        trace
        for trace in result.traces
        if trace.stage is expected_stage
        and trace.model_id == "deepseek-v4-pro"
        and trace.response_hash is not None
        and getattr(trace, "error_code", None) is None
    )
    if len(traces) != 1:
        raise _invalid("the propagation model final critic trace is invalid")
    return traces[0]


def _candidate(result: Any, evidence_pack_id: str) -> tuple[Any, Any]:
    accepted = result.status is GenerationRunStatus.SUCCEEDED or (
        result.status is GenerationRunStatus.NEEDS_REVIEW and result.repair_count == 1
    )
    if not accepted or result.batch is None:
        raise _invalid("the propagation model did not return one accepted candidate")
    if result.repair_count not in {0, 1} or len(result.batch.candidates) != 1:
        raise _invalid("the propagation model exceeded its bounded candidate or repair budget")
    batch = result.batch
    if (
        batch.template_id != _TEMPLATE_ID
        or batch.template_version != _TEMPLATE_VERSION
        or batch.evidence_pack_id != evidence_pack_id
    ):
        raise _invalid("the propagation model candidate identity is invalid")
    return batch.candidates[0], _final_trace(result)


def _safe_text(value: object, maximum: int = 500) -> str:
    text = value if isinstance(value, str) else str(value)
    return text[:maximum]


class PropagationSuggestionGenerator:
    """Decode the generic Flash -> Pro -> one-repair result into an immutable suggestion."""

    def __init__(self, service_or_gateway: Any, *, clock: Callable[[], str] = utc_now) -> None:
        self._service = (
            service_or_gateway if hasattr(service_or_gateway, "run") else _compose_service(service_or_gateway)
        )
        self._clock = clock

    @staticmethod
    def _task(request: PropagationModelRequest) -> str:
        payload = {
            "source_failures": [
                {
                    "row_id": row.row_id,
                    "record_version": row.record_version,
                    "item_id": row.item_id,
                    "failure_mode": _safe_text(row.failure_mode),
                    "causes": [_safe_text(value, 300) for value in row.causes[:8]],
                    "effects": [_safe_text(value, 300) for value in row.effects[:8]],
                    "barriers": [_safe_text(value, 300) for value in row.barriers[:8]],
                }
                for row in request.source_rows
            ],
            "candidate_interfaces": [
                {
                    "interface_id": candidate.interface_id,
                    "source_entity_id": candidate.source_node_id,
                    "target_entity_id": candidate.target_node_id,
                    "interface_variable": candidate.interface_variable,
                    "unit": candidate.unit,
                    "direction": candidate.direction,
                    "operating_modes": list(candidate.operating_modes),
                    "path_length": candidate.path_length,
                }
                for candidate in request.candidate_interfaces
            ],
            "candidate_endpoint_ids": list(request.candidate_endpoint_ids),
            "candidate_evidence_ids": list(request.candidate_evidence_ids),
            "allowed_relation_types": list(request.allowed_relation_types),
            "rule_identity": {
                "rule_pack_id": request.rule_pack.rule_pack_id,
                "rule_pack_version": request.rule_pack.version,
            },
            "max_depth": request.max_depth,
            "max_edges": request.max_edges,
            "authority": "Return hypotheses only from the enumerated candidates. Never confirm, publish, or invent IDs.",
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @staticmethod
    def _strings(value: object, field_name: str) -> tuple[str, ...]:
        if (
            isinstance(value, str | bytes)
            or not isinstance(value, Sequence)
            or not all(isinstance(item, str) and item.strip() for item in value)
        ):
            raise _invalid(f"model {field_name} is invalid")
        result = tuple(value)
        if len(set(result)) != len(result):
            raise _invalid(f"model {field_name} contains duplicates")
        return result

    @staticmethod
    def _validate_edge(raw: object, request: PropagationModelRequest) -> dict[str, object]:  # noqa: C901
        if not isinstance(raw, Mapping) or set(raw) != _EDGE_KEYS:
            extra_keys = set(raw) - _EDGE_KEYS if isinstance(raw, Mapping) else set()
            code = (
                "FMEA_PROPAGATION_BUDGET_INVALID"
                if extra_keys & {"max_depth", "max_edges", "budget"}
                else "FMEA_PROPAGATION_SUGGESTION_INVALID"
            )
            raise _invalid("model edge contains unknown or missing fields", code)
        edge = dict(raw)
        source = edge["source_entity_id"]
        target = edge["target_entity_id"]
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or source not in request.candidate_endpoint_ids
            or target not in request.candidate_endpoint_ids
        ):
            raise _invalid("model endpoint is outside enumerated candidates", "FMEA_PROPAGATION_ENDPOINT_INVALID")
        if not any(
            candidate.source_node_id == source
            and candidate.target_node_id == target
            and candidate.interface_variable == edge["interface_variable"]
            and candidate.unit == edge["unit"]
            and candidate.direction == edge["direction"]
            for candidate in request.candidate_interfaces
        ):
            raise _invalid("model edge is not an enumerated topology interface", "FMEA_PROPAGATION_ENDPOINT_INVALID")
        relation = edge["relation_type"]
        if not isinstance(relation, str) or relation not in request.allowed_relation_types:
            raise _invalid("model relation is outside the rule pack", "FMEA_PROPAGATION_RELATION_INVALID")
        path_length = edge["path_length"]
        if (
            not isinstance(path_length, int)
            or isinstance(path_length, bool)
            or not 1 <= path_length <= request.max_depth
        ):
            raise _invalid("model path length exceeds the bounded depth", "FMEA_PROPAGATION_DEPTH_INVALID")
        evidence_ids = edge["evidence_ids"]
        if isinstance(evidence_ids, str | bytes) or not isinstance(evidence_ids, Sequence) or not evidence_ids:
            raise _invalid("model evidence IDs are invalid", "FMEA_PROPAGATION_EVIDENCE_INVALID")
        evidence_tuple = tuple(evidence_ids)
        if (
            not all(isinstance(item, str) for item in evidence_tuple)
            or len(set(evidence_tuple)) != len(evidence_tuple)
            or not set(evidence_tuple).issubset(set(request.candidate_evidence_ids))
        ):
            raise _invalid("model evidence is outside the EvidencePack", "FMEA_PROPAGATION_EVIDENCE_INVALID")
        PropagationSuggestionGenerator._strings(edge["operating_modes"], "operating_modes")
        PropagationSuggestionGenerator._strings(edge["barrier_ids"], "barrier_ids")
        for name in ("delay_ms", "response_time_ms", "fault_tolerance_time_ms"):
            value = edge[name]
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise _invalid(f"model {name} is invalid")
        if edge["evidence_support"] not in {item.value for item in EvidenceSupportStatus}:
            raise _invalid("model evidence support is invalid", "FMEA_PROPAGATION_EVIDENCE_INVALID")
        if edge["claim_status"] not in {item.value for item in ClaimStatus}:
            raise _invalid("model claim status is invalid")
        for name in ("is_cyclic", "is_unprocessed", "is_external", "is_terminal"):
            if type(edge[name]) is not bool:
                raise _invalid(f"model {name} is invalid")
        if edge["threshold"] is not None and not isinstance(edge["threshold"], str):
            raise _invalid("model threshold is invalid")
        if edge["risk_priority"] is not None and not isinstance(edge["risk_priority"], str):
            raise _invalid("model risk priority is invalid")
        return edge

    def generate(self, request: PropagationModelRequest) -> AssistanceSuggestion[tuple[Mapping[str, object], ...]]:
        if not isinstance(request, PropagationModelRequest):
            raise _invalid("propagation model request is invalid")
        try:
            result = self._service.run(
                run_id=request.run_id,
                task=self._task(request),
                template_id=_TEMPLATE_ID,
                version=_TEMPLATE_VERSION,
                evidence_pack=request.evidence_pack,
            )
            candidate, trace = _candidate(result, request.evidence_pack.pack_id)
            if not isinstance(candidate.payload, Mapping) or set(candidate.payload) != {"edges"}:
                extra_keys = set(candidate.payload) - {"edges"} if isinstance(candidate.payload, Mapping) else set()
                code = (
                    "FMEA_PROPAGATION_BUDGET_INVALID"
                    if extra_keys & {"max_depth", "max_edges", "budget"}
                    else "FMEA_PROPAGATION_SUGGESTION_INVALID"
                )
                raise _invalid("propagation candidate payload must contain only edges", code)
            raw_edges = candidate.payload["edges"]
            if (
                isinstance(raw_edges, str | bytes)
                or not isinstance(raw_edges, Sequence)
                or len(raw_edges) > request.max_edges
            ):
                raise _invalid("model edge proposals exceed the edge budget", "FMEA_PROPAGATION_BUDGET_INVALID")
            edges = tuple(self._validate_edge(raw, request) for raw in raw_edges)
            evidence_ids_list: list[str] = []
            for edge in edges:
                for evidence_id in cast(Sequence[str], edge["evidence_ids"]):
                    if evidence_id not in evidence_ids_list:
                        evidence_ids_list.append(evidence_id)
            return AssistanceSuggestion(
                suggestion_id=stable_id("propagation-suggestion", request.run_id, candidate.candidate_id),
                kind=AssistanceKind.PROPAGATION_HYPOTHESIS,
                workspace_id=request.evidence_pack.workspace_id,
                target_type="fmea_analysis",
                target_id=request.analysis.analysis_id,
                target_record_version=request.analysis.record_version,
                evidence_pack_ids=(request.evidence_pack.pack_id,),
                payload=edges,
                evidence_ids=tuple(evidence_ids_list),
                model_hash=trace.response_hash,
                prompt_hash=trace.prompt_hash,
                run_id=request.run_id,
                trace_id=getattr(result, "trace_id", stable_id("propagation-trace", request.run_id)),
                domain_pack_id=request.domain_pack.pack_id,
                domain_pack_version=request.domain_pack.version,
                template_id=_TEMPLATE_ID,
                template_version=_TEMPLATE_VERSION,
                rule_pack_id=request.rule_pack.rule_pack_id,
                rule_pack_version=request.rule_pack.version,
                created_at=self._clock(),
            )
        except PropagationError:
            raise
        except StructuredGenerationError as exc:
            raise _invalid("the propagation model is unavailable") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise _invalid("the propagation model returned an invalid suggestion") from exc


class EnvironmentPropagationSuggestionGenerator:
    """Lazy environment-backed adapter; tests should inject a fake service or gateway."""

    def __init__(self, *, clock: Callable[[], str] = utc_now) -> None:
        self._clock = clock

    def generate(self, request: PropagationModelRequest) -> AssistanceSuggestion[tuple[Mapping[str, object], ...]]:
        try:
            from structured_generation_infrastructure import build_deepseek_gateway_from_env

            return PropagationSuggestionGenerator(build_deepseek_gateway_from_env(), clock=self._clock).generate(
                request
            )
        except PropagationError:
            raise
        except Exception as exc:
            raise _invalid("the propagation model is temporarily unavailable") from exc


__all__ = [
    "EnvironmentPropagationSuggestionGenerator",
    "PropagationGenerationError",
    "PropagationSuggestionGenerator",
]
