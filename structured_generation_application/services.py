"""Use-case facade for registry-backed structured generation and FMEA adaptation."""

from __future__ import annotations

from core_domain.fmea.entities import FmeaAnalysis
from core_domain.fmea.value_objects import EvidencePack
from core_domain.structured_generation import (
    GenerationIssue,
    GenerationRunResult,
    StructuredGenerationError,
)
from fmea_application import (
    FmeaAdaptationResult,
    FmeaTemplateProfile,
    StructuredCandidateFmeaAdapter,
)
from structured_output_application import TemplateRegistry

from .contracts import GenerationRunRequest
from .pipeline import StructuredGenerationPipeline


class StructuredGenerationService:
    """Resolve immutable templates, run the model pipeline, and adapt suggestions."""

    def __init__(
        self,
        *,
        registry: TemplateRegistry,
        pipeline: StructuredGenerationPipeline,
        fmea_adapter: StructuredCandidateFmeaAdapter | None = None,
    ) -> None:
        self._registry = registry
        self._pipeline = pipeline
        self._fmea_adapter = fmea_adapter

    def _request(
        self,
        *,
        run_id: str,
        task: str,
        template_id: str,
        version: str,
        evidence_pack: EvidencePack,
    ) -> GenerationRunRequest:
        template = self._registry.get(template_id, version)
        return GenerationRunRequest(
            run_id=run_id,
            task=task,
            template=template,
            evidence_pack=evidence_pack,
        )

    def run(
        self,
        *,
        run_id: str,
        task: str,
        template_id: str,
        version: str,
        evidence_pack: EvidencePack,
    ) -> GenerationRunResult:
        request = self._request(
            run_id=run_id,
            task=task,
            template_id=template_id,
            version=version,
            evidence_pack=evidence_pack,
        )
        return self._pipeline.run(request)

    def run_fmea(
        self,
        *,
        run_id: str,
        task: str,
        template_id: str,
        version: str,
        evidence_pack: EvidencePack,
        analysis: FmeaAnalysis,
        profile: FmeaTemplateProfile,
    ) -> tuple[GenerationRunResult, FmeaAdaptationResult]:
        if self._fmea_adapter is None:
            raise StructuredGenerationError(
                "FMEA_ADAPTER_UNAVAILABLE",
                "Structured-generation FMEA adaptation is not configured.",
            )
        request = self._request(
            run_id=run_id,
            task=task,
            template_id=template_id,
            version=version,
            evidence_pack=evidence_pack,
        )
        result = self._pipeline.run(request)
        if result.batch is None:
            return result, FmeaAdaptationResult(
                rows=(),
                issues=(
                    GenerationIssue(
                        code="FMEA_GENERATION_FAILED",
                        message="No candidate batch is available for FMEA adaptation.",
                    ),
                ),
                needs_review=True,
            )
        adaptation = self._fmea_adapter.adapt(
            analysis=analysis,
            evidence_pack=evidence_pack,
            template=request.template,
            batch=result.batch,
            critic_report=result.critic_report,
            profile=profile,
            repair_count=result.repair_count,
            deterministic_issues=result.deterministic_issues,
        )
        return result, adaptation


__all__ = ["StructuredGenerationService"]
