from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from core_domain.fmea.policies import validate_row_evidence
from core_domain.fmea.states import PublicationStatus, ReviewStatus
from core_domain.fmea.value_objects import EvidencePack
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile
from core_domain.structured_generation import (
    CriticFinding,
    CriticReport,
    CriticVerdict,
    GenerationRunResult,
    GenerationRunStatus,
    SemanticSupport,
    StructuredGenerationError,
)
from core_domain.structured_output import (
    CandidateClaim,
    ClaimState,
    StructuredCandidate,
    StructuredCandidateBatch,
)
from fmea_application import StructuredCandidateFmeaAdapter
from fmea_application.review_contracts import legacy_citation_type
from fmea_infrastructure import load_fmea_template_profile
from structured_generation_application import StructuredGenerationService
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


def _service(template, batch: StructuredCandidateBatch):
    result = GenerationRunResult(
        run_id="run-1",
        status=GenerationRunStatus.SUCCEEDED,
        batch=batch,
        critic_report=_critic(),
        deterministic_issues=(),
        generation_issues=(),
        traces=(),
        repair_count=0,
    )

    class _Registry:
        def get(self, template_id: str, version: str):
            assert (template_id, version) == (template.metadata.template_id, template.metadata.version)
            return template

    class _Pipeline:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, request):
            self.calls += 1
            return result

    pipeline = _Pipeline()
    return StructuredGenerationService(
        registry=_Registry(),
        pipeline=pipeline,
        fmea_adapter=StructuredCandidateFmeaAdapter(),
    ), pipeline


def _pack_with_source_types(pack: EvidencePack, source_types: tuple[str, ...]) -> EvidencePack:
    refs = tuple(
        replace(
            pack.refs[0],
            evidence_id=f"ev-{index + 1}",
            source_type=source_type,
            evidence_hash=f"{index + 1}" * 64,
        )
        for index, source_type in enumerate(source_types)
    )
    return EvidencePack.build(
        pack_id=pack.pack_id,
        workspace_id=pack.workspace_id,
        acl_scope=pack.acl_scope,
        versions=pack.versions,
        refs=refs,
        created_at=pack.created_at,
        expires_at=pack.expires_at,
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
        generation_run_id="generation-1",
        requested_evidence_profile=EvidenceSelectionProfile.AUTO,
        resolved_evidence_profile=EvidenceSelectionProfile.COMBINED,
        evidence_types=tuple(CitationType),
        trace_id="trace-1",
        retrieval_warnings=(),
        retrieval_incomplete=False,
    )

    assert validation.valid is True
    assert len(result.rows) == 1
    assert result.rows[0].review_status is ReviewStatus.SUGGESTED
    assert result.rows[0].publication_status is PublicationStatus.UNPUBLISHED
    source = result.source_snapshots[0]
    assert source.item_label == "Fuel Filter"
    assert source.function_label == "Filter particles"
    assert result.rows[0].item_id == "item-6dbf475ac4924d25b126a8fe"
    assert result.rows[0].function_id == "function-46e8432139d44de40972e322"
    assert source.row_id == result.rows[0].row_id
    assert source.profile_id == "fuel-combustion-fmea-row"
    assert source.requested_evidence_profile is EvidenceSelectionProfile.AUTO
    assert source.resolved_evidence_profile is EvidenceSelectionProfile.COMBINED
    validate_row_evidence(result.rows[0], fixture_pack)
    assert not hasattr(StructuredCandidateFmeaAdapter, "save")


def test_adapter_owns_row_and_source_metadata_over_model_payload(
    fixture_analysis,
    fixture_pack,
) -> None:
    template = TemplateCompiler(schema_validator=Draft202012SchemaAdapter(), source_loader=load_template_source).compile_path(
        ROOT / "templates" / "examples" / "fuel-combustion-fmea-full.yaml"
    )
    batch = _batch(template, fixture_pack)
    candidate = batch.candidates[0]
    tampered = replace(
        candidate,
        payload={
            **candidate.payload,
            "row_id": "model-row",
            "source_hash": "model-source",
            "profile_id": "model-profile",
            "generation_run_id": "model-run",
        },
    )
    result = StructuredCandidateFmeaAdapter().adapt(
        analysis=fixture_analysis,
        evidence_pack=fixture_pack,
        template=template,
        batch=replace(batch, candidates=(tampered,)),
        critic_report=_critic(),
        profile=load_fmea_template_profile(
            ROOT / "templates" / "fmea_profiles" / "fuel-combustion-fmea-full.json"
        ),
        repair_count=0,
        deterministic_issues=(),
        generation_run_id="generation-1",
        requested_evidence_profile=EvidenceSelectionProfile.AUTO,
        resolved_evidence_profile=EvidenceSelectionProfile.COMBINED,
        evidence_types=tuple(CitationType),
        trace_id="trace-1",
        retrieval_warnings=(),
        retrieval_incomplete=False,
    )

    row = result.rows[0]
    source = result.source_snapshots[0]
    assert row.row_id != "model-row"
    assert source.row_id == row.row_id
    assert source.source_hash != "model-source"
    assert source.profile_id == "fuel-combustion-fmea-row"
    assert source.generation_run_id == "generation-1"


@pytest.mark.parametrize(
    ("overrides", "omitted"),
    [
        pytest.param(
            {"requested_evidence_profile": EvidenceSelectionProfile.AUTO},
            (
                "resolved_evidence_profile",
                "evidence_types",
                "trace_id",
                "retrieval_warnings",
                "retrieval_incomplete",
            ),
            id="partial-provenance",
        ),
        pytest.param(
            {"requested_evidence_profile": "auto"},
            (),
            id="requested-profile-type",
        ),
        pytest.param(
            {"resolved_evidence_profile": EvidenceSelectionProfile.AUTO},
            (),
            id="resolved-profile-auto",
        ),
        pytest.param(
            {"evidence_types": (CitationType.TEXT, CitationType.TEXT)},
            (),
            id="duplicate-evidence-type",
        ),
        pytest.param(
            {"evidence_types": ("text",)},
            (),
            id="evidence-type-member",
        ),
        pytest.param(
            {"trace_id": "t" * 257},
            (),
            id="trace-id-bound",
        ),
        pytest.param(
            {"retrieval_warnings": ["stable-warning"]},
            (),
            id="warnings-tuple",
        ),
        pytest.param(
            {"retrieval_warnings": ("w" * 4001,)},
            (),
            id="warning-bound",
        ),
        pytest.param(
            {"retrieval_incomplete": 1},
            (),
            id="incomplete-bool",
        ),
        pytest.param(
            {
                "resolved_evidence_profile": EvidenceSelectionProfile.CUSTOM,
                "evidence_types": (),
                "retrieval_warnings": (),
                "retrieval_incomplete": False,
            },
            (),
            id="custom-empty-without-incomplete-warning",
        ),
    ],
)
def test_service_rejects_malformed_explicit_retrieval_provenance_before_pipeline(
    fixture_analysis,
    fixture_pack,
    overrides: dict[str, object],
    omitted: tuple[str, ...],
) -> None:
    template = TemplateCompiler(schema_validator=Draft202012SchemaAdapter(), source_loader=load_template_source).compile_path(
        ROOT / "templates" / "examples" / "fuel-combustion-fmea-full.yaml"
    )
    batch = _batch(template, fixture_pack)
    service, pipeline = _service(template, batch)
    provenance: dict[str, object] = {
        "requested_evidence_profile": EvidenceSelectionProfile.AUTO,
        "resolved_evidence_profile": EvidenceSelectionProfile.COMBINED,
        "evidence_types": tuple(CitationType),
        "trace_id": "trace-1",
        "retrieval_warnings": (),
        "retrieval_incomplete": False,
    }
    for field_name in omitted:
        provenance.pop(field_name)
    provenance.update(overrides)

    with pytest.raises(StructuredGenerationError) as error:
        service.run_fmea(
            run_id="run-1",
            task="task",
            template_id=template.metadata.template_id,
            version=template.metadata.version,
            evidence_pack=fixture_pack,
            analysis=fixture_analysis,
            profile=load_fmea_template_profile(
                ROOT / "templates" / "fmea_profiles" / "fuel-combustion-fmea-full.json"
            ),
            **provenance,
        )

    assert error.value.code == "FMEA_RETRIEVAL_PROVENANCE_REQUIRED"
    assert pipeline.calls == 0


def test_service_infers_legacy_custom_provenance_from_pack_source_types(
    fixture_analysis,
    fixture_pack,
) -> None:
    template = TemplateCompiler(schema_validator=Draft202012SchemaAdapter(), source_loader=load_template_source).compile_path(
        ROOT / "templates" / "examples" / "fuel-combustion-fmea-full.yaml"
    )
    pack = _pack_with_source_types(
        fixture_pack,
        ("primary_document", "rag_text", "graphrag_relation", "graphrag_community"),
    )
    service, _ = _service(template, _batch(template, pack))

    _, adaptation = service.run_fmea(
        run_id="run-1",
        task="task",
        template_id=template.metadata.template_id,
        version=template.metadata.version,
        evidence_pack=pack,
        analysis=fixture_analysis,
        profile=load_fmea_template_profile(
            ROOT / "templates" / "fmea_profiles" / "fuel-combustion-fmea-full.json"
        ),
    )

    source = adaptation.source_snapshots[0]
    assert source.requested_evidence_profile is EvidenceSelectionProfile.CUSTOM
    assert source.resolved_evidence_profile is EvidenceSelectionProfile.CUSTOM
    assert tuple(
        legacy_citation_type(source_type)
        for source_type in ("primary_document", "rag_text", "graphrag_relation", "graphrag_community")
    ) == (CitationType.TEXT, CitationType.TEXT, CitationType.GRAPH, CitationType.COMMUNITY)
    assert source.evidence_types == (CitationType.TEXT, CitationType.GRAPH, CitationType.COMMUNITY)
    assert source.trace_id == "run-1"
    assert source.retrieval_warnings == ("FMEA_RETRIEVAL_PROVENANCE_INFERRED",)
    assert source.retrieval_incomplete is False


def test_service_rejects_unmapped_legacy_source_type_without_guessing(
    fixture_analysis,
    fixture_pack,
) -> None:
    template = TemplateCompiler(schema_validator=Draft202012SchemaAdapter(), source_loader=load_template_source).compile_path(
        ROOT / "templates" / "examples" / "fuel-combustion-fmea-full.yaml"
    )
    pack = _pack_with_source_types(fixture_pack, ("unknown_source_type",))
    service, pipeline = _service(template, _batch(template, pack))

    with pytest.raises(StructuredGenerationError) as error:
        service.run_fmea(
            run_id="run-1",
            task="task",
            template_id=template.metadata.template_id,
            version=template.metadata.version,
            evidence_pack=pack,
            analysis=fixture_analysis,
            profile=load_fmea_template_profile(
                ROOT / "templates" / "fmea_profiles" / "fuel-combustion-fmea-full.json"
            ),
        )

    assert error.value.code == "FMEA_RETRIEVAL_PROVENANCE_REQUIRED"
    assert pipeline.calls == 0
