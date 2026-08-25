"""Use-case facade for registry-backed structured generation and FMEA adaptation."""

from __future__ import annotations

from typing import cast

from core_domain.fmea.entities import FmeaAnalysis
from core_domain.fmea.value_objects import EvidencePack
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile
from core_domain.structured_generation import (
    GenerationBudget,
    GenerationIssue,
    GenerationRunResult,
    StructuredGenerationError,
)
from fmea_application import (
    FmeaAdaptationResult,
    FmeaTemplateProfile,
    StructuredCandidateFmeaAdapter,
)
from fmea_application.review_contracts import RetrievalProvenance
from structured_output_application import TemplateRegistry

from .contracts import GenerationRunRequest
from .pipeline import StructuredGenerationPipeline

_LEGACY_SOURCE_TYPES = {
    "rag_text": CitationType.TEXT,
    "primary_document": CitationType.TEXT,
    "graphrag_relation": CitationType.GRAPH,
    "graphrag_community": CitationType.COMMUNITY,
}


def _fmea_provenance(
    *,
    run_id: str,
    evidence_pack: EvidencePack,
    requested_evidence_profile: EvidenceSelectionProfile | None,
    resolved_evidence_profile: EvidenceSelectionProfile | None,
    evidence_types: tuple[CitationType, ...] | None,
    trace_id: str | None,
    retrieval_warnings: tuple[str, ...] | None,
    retrieval_incomplete: bool | None,
) -> tuple[
    EvidenceSelectionProfile,
    EvidenceSelectionProfile,
    tuple[CitationType, ...],
    str,
    tuple[str, ...],
    bool,
]:
    supplied = (
        requested_evidence_profile,
        resolved_evidence_profile,
        evidence_types,
        trace_id,
        retrieval_warnings,
        retrieval_incomplete,
    )
    if any(value is not None for value in supplied) and not all(value is not None for value in supplied):
        raise StructuredGenerationError(
            "FMEA_RETRIEVAL_PROVENANCE_REQUIRED",
            "FMEA retrieval provenance must be supplied as all six values or omitted.",
        )
    if all(value is not None for value in supplied):
        if (
            not isinstance(evidence_types, tuple)
            or not isinstance(retrieval_warnings, tuple)
            or type(retrieval_incomplete) is not bool
        ):
            raise StructuredGenerationError(
                "FMEA_RETRIEVAL_PROVENANCE_REQUIRED",
                "FMEA retrieval provenance is invalid.",
            )
        try:
            provenance = RetrievalProvenance(
                requested_profile=cast(EvidenceSelectionProfile, requested_evidence_profile),
                resolved_profile=cast(EvidenceSelectionProfile, resolved_evidence_profile),
                evidence_types=cast(tuple[CitationType, ...], evidence_types),
                trace_id=cast(str, trace_id),
                warnings=cast(tuple[str, ...], retrieval_warnings),
                incomplete=cast(bool, retrieval_incomplete),
            )
        except (TypeError, ValueError) as exc:
            raise StructuredGenerationError(
                "FMEA_RETRIEVAL_PROVENANCE_REQUIRED",
                "FMEA retrieval provenance is invalid.",
            ) from exc
        return (
            provenance.requested_profile,
            provenance.resolved_profile,
            provenance.evidence_types,
            provenance.trace_id,
            provenance.warnings,
            provenance.incomplete,
        )

    inferred_types: list[CitationType] = []
    for ref in evidence_pack.refs:
        citation_type = _LEGACY_SOURCE_TYPES.get(ref.source_type)
        if citation_type is None:
            raise StructuredGenerationError(
                "FMEA_RETRIEVAL_PROVENANCE_REQUIRED",
                "FMEA retrieval provenance cannot be inferred from the evidence pack.",
            )
        if citation_type not in inferred_types:
            inferred_types.append(citation_type)
    return (
        EvidenceSelectionProfile.CUSTOM,
        EvidenceSelectionProfile.CUSTOM,
        tuple(inferred_types),
        run_id,
        ("FMEA_RETRIEVAL_PROVENANCE_INFERRED",),
        False,
    )


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
        budget: GenerationBudget | None = None,
    ) -> GenerationRunRequest:
        template = self._registry.get(template_id, version)
        return GenerationRunRequest(
            run_id=run_id,
            task=task,
            template=template,
            evidence_pack=evidence_pack,
            budget=budget or GenerationBudget(),
        )

    def run(
        self,
        *,
        run_id: str,
        task: str,
        template_id: str,
        version: str,
        evidence_pack: EvidencePack,
        budget: GenerationBudget | None = None,
    ) -> GenerationRunResult:
        request = self._request(
            run_id=run_id,
            task=task,
            template_id=template_id,
            version=version,
            evidence_pack=evidence_pack,
            budget=budget,
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
        budget: GenerationBudget | None = None,
        requested_evidence_profile: EvidenceSelectionProfile | None = None,
        resolved_evidence_profile: EvidenceSelectionProfile | None = None,
        evidence_types: tuple[CitationType, ...] | None = None,
        trace_id: str | None = None,
        retrieval_warnings: tuple[str, ...] | None = None,
        retrieval_incomplete: bool | None = None,
    ) -> tuple[GenerationRunResult, FmeaAdaptationResult]:
        if self._fmea_adapter is None:
            raise StructuredGenerationError(
                "FMEA_ADAPTER_UNAVAILABLE",
                "Structured-generation FMEA adaptation is not configured.",
            )
        (
            requested_profile,
            resolved_profile,
            resolved_types,
            resolved_trace_id,
            resolved_warnings,
            resolved_incomplete,
        ) = _fmea_provenance(
            run_id=run_id,
            evidence_pack=evidence_pack,
            requested_evidence_profile=requested_evidence_profile,
            resolved_evidence_profile=resolved_evidence_profile,
            evidence_types=evidence_types,
            trace_id=trace_id,
            retrieval_warnings=retrieval_warnings,
            retrieval_incomplete=retrieval_incomplete,
        )
        request = self._request(
            run_id=run_id,
            task=task,
            template_id=template_id,
            version=version,
            evidence_pack=evidence_pack,
            budget=budget,
        )
        result = self._pipeline.run(request)
        if result.batch is None:
            return result, FmeaAdaptationResult(
                rows=(),
                source_snapshots=(),
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
            generation_run_id=run_id,
            requested_evidence_profile=requested_profile,
            resolved_evidence_profile=resolved_profile,
            evidence_types=resolved_types,
            trace_id=resolved_trace_id,
            retrieval_warnings=resolved_warnings,
            retrieval_incomplete=resolved_incomplete,
        )
        return result, adaptation


__all__ = ["StructuredGenerationService"]
