"""Structured-generation adapter for analysis-scope drafts."""

# ruff: noqa: TRY003

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from core_domain.fmea.value_objects import EvidencePack
from core_domain.structured_generation import StructuredGenerationError
from fmea_application.assistance_contracts import AssistanceKind, AssistanceRequest, AssistanceSuggestion
from fmea_application.assistance_service import stable_id, utc_now
from fmea_application.review_errors import ReviewError

from .risk_generator import _candidate, _compose_service, _invalid, _safe_generation_error

_TEMPLATE_ID = "fmea-analysis-scope"
_TEMPLATE_VERSION = "1.0.0"
_ROOT_KEYS = {"scope", "system_boundary", "exclusions", "operating_modes", "assumptions", "limitations"}


class AnalysisAssistanceGenerator:
    def __init__(
        self,
        service: Any,
        *,
        evidence_loader: Callable[[str, str], EvidencePack | None],
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self._service = service
        self._evidence_loader = evidence_loader
        self._clock = clock

    def generate(self, request: AssistanceRequest[object]) -> AssistanceSuggestion[object]:
        if not isinstance(request, AssistanceRequest) or request.kind is not AssistanceKind.ANALYSIS_SCOPE_DRAFT:
            raise _invalid("analysis scope model request is invalid")
        if len(request.evidence_pack_ids) != 1:
            raise _invalid("analysis scope generation supports exactly one EvidencePack")
        pack = self._evidence_loader(request.evidence_pack_ids[0], request.workspace_id)
        if pack is None or pack.pack_id != request.evidence_pack_ids[0] or pack.workspace_id != request.workspace_id:
            raise _invalid("analysis scope EvidencePack is invalid")
        try:
            task = json.dumps(
                {
                    "analysis": dict(request.payload) if isinstance(request.payload, Mapping) else request.payload,
                    "allowed_fields": sorted(_ROOT_KEYS),
                    "rule": "Draft scope only. Never create an analysis or return risk, workflow, publication, or confirmation state.",
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            model_pack = replace(pack, refs=())
            result = self._service.run(
                run_id=request.request_id,
                task=task,
                template_id=_TEMPLATE_ID,
                version=_TEMPLATE_VERSION,
                evidence_pack=model_pack,
            )
        except StructuredGenerationError as exc:
            raise _safe_generation_error(exc) from exc
        except (TypeError, ValueError) as exc:
            raise _invalid("analysis scope model request is invalid") from exc
        candidate, trace = _candidate(result, template_id=_TEMPLATE_ID, evidence_pack_id=pack.pack_id)
        if not isinstance(candidate.payload, Mapping) or set(candidate.payload) != _ROOT_KEYS:
            raise _invalid("analysis scope candidate contains unknown or missing fields")
        return AssistanceSuggestion(
            suggestion_id=stable_id("scope-suggestion", request.request_id, candidate.candidate_id),
            kind=AssistanceKind.ANALYSIS_SCOPE_DRAFT,
            workspace_id=request.workspace_id,
            target_type=request.target_type,
            target_id=request.target_id,
            target_record_version=request.target_record_version,
            evidence_pack_ids=request.evidence_pack_ids,
            payload=dict(candidate.payload),
            evidence_ids=(),
            model_hash=trace.response_hash,
            prompt_hash=trace.prompt_hash,
            run_id=request.request_id,
            trace_id=stable_id("scope-trace", request.request_id),
            domain_pack_id=request.domain_pack_id,
            domain_pack_version=request.domain_pack_version,
            template_id=request.template_id,
            template_version=request.template_version,
            rule_pack_id=request.rule_pack_id,
            rule_pack_version=request.rule_pack_version,
            created_at=self._clock(),
        )


class EnvironmentAnalysisAssistanceGenerator:
    def __init__(
        self,
        *,
        evidence_loader: Callable[[str, str], EvidencePack | None],
        registry_root: Path | None = None,
        template_path: Path | None = None,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self._evidence_loader = evidence_loader
        self._registry_root = registry_root
        self._template_path = template_path or Path(__file__).resolve().parents[1] / "templates" / "examples" / "fmea-analysis-scope.yaml"
        self._clock = clock

    def generate(self, request: AssistanceRequest[object]) -> AssistanceSuggestion[object]:
        try:
            service = _compose_service(_TEMPLATE_ID, _TEMPLATE_VERSION, self._template_path, self._registry_root)
            return AnalysisAssistanceGenerator(
                service,
                evidence_loader=self._evidence_loader,
                clock=self._clock,
            ).generate(request)
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError(
                "FMEA_MODEL_SUGGESTION_UNAVAILABLE",
                "the analysis scope model is temporarily unavailable",
                retryable=True,
            ) from exc


__all__ = ["AnalysisAssistanceGenerator", "EnvironmentAnalysisAssistanceGenerator"]
