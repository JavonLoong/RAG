from __future__ import annotations

from pathlib import Path

from core_domain.fmea.policies import validate_row_evidence
from core_domain.fmea.states import PublicationStatus, ReviewStatus
from core_domain.structured_generation import CriticFinding, CriticReport, CriticVerdict, SemanticSupport
from core_domain.structured_output import (
    CandidateClaim,
    ClaimState,
    StructuredCandidate,
    StructuredCandidateBatch,
)
from fmea_application import StructuredCandidateFmeaAdapter
from fmea_infrastructure import load_fmea_template_profile
from structured_output_application import StructuredCandidateValidator, TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source

ROOT = Path(__file__).parents[2]
TARGETS = (
    "/item",
    "/function",
    "/failure_mode",
    "/causes/0",
    "/mechanisms/0",
    "/effects/0",
    "/symptoms/0",
    "/controls/0",
    "/barriers/0",
    "/actions/0",
)


def _batch(template, fixture_pack) -> StructuredCandidateBatch:
    candidate = StructuredCandidate(
        candidate_id="candidate-1",
        payload={
            "item": "Fuel Filter",
            "function": "Filter particles",
            "failure_mode": "Blocked fuel flow",
            "causes": ["Excess particles"],
            "mechanisms": ["Pressure drop rises"],
            "effects": ["Combustion instability"],
            "symptoms": ["Differential pressure alarm"],
            "controls": ["Pressure transmitter"],
            "barriers": ["Low-pressure trip"],
            "actions": ["Replace filter element"],
        },
        claims=tuple(CandidateClaim(target, ClaimState.KNOWN, ("ev-1",)) for target in TARGETS),
    )
    return StructuredCandidateBatch(
        template_id=template.metadata.template_id,
        template_version=template.metadata.version,
        template_hash=template.template_hash,
        evidence_pack_id=fixture_pack.pack_id,
        candidates=(candidate,),
    )


def _critic() -> CriticReport:
    return CriticReport(
        verdict=CriticVerdict.ACCEPT,
        findings=tuple(
            CriticFinding(
                candidate_id="candidate-1",
                target=target,
                support=SemanticSupport.SUPPORTED,
                code="EVIDENCE_SUPPORTS_CLAIM",
                evidence_ids=("ev-1",),
                explanation="The evidence was checked.",
            )
            for target in TARGETS
        ),
        summary="All mapped claims are supported.",
    )


def test_validated_generic_candidate_hands_off_without_persistence(
    fixture_analysis,
    fixture_pack,
) -> None:
    schema = Draft202012SchemaAdapter()
    template = TemplateCompiler(schema_validator=schema, source_loader=load_template_source).compile_path(
        ROOT / "templates" / "examples" / "fuel-combustion-fmea-full.yaml"
    )
    batch = _batch(template, fixture_pack)
    validation = StructuredCandidateValidator(schema).validate(batch, template, fixture_pack)

    result = StructuredCandidateFmeaAdapter().adapt(
        analysis=fixture_analysis,
        evidence_pack=fixture_pack,
        template=template,
        batch=batch,
        critic_report=_critic(),
        profile=load_fmea_template_profile(
            ROOT / "templates" / "fmea_profiles" / "fuel-combustion-fmea-full.json"
        ),
        repair_count=0,
        deterministic_issues=validation.issues,
    )

    assert validation.valid is True
    assert len(result.rows) == 1
    assert result.rows[0].review_status is ReviewStatus.SUGGESTED
    assert result.rows[0].publication_status is PublicationStatus.UNPUBLISHED
    validate_row_evidence(result.rows[0], fixture_pack)
    assert not hasattr(StructuredCandidateFmeaAdapter, "save")
