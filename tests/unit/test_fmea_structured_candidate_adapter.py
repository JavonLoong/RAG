from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from core_domain.fmea.entities import FmeaAnalysis
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.policies import validate_row_evidence
from core_domain.fmea.states import ClaimStatus, EvidenceSupportStatus, PublicationStatus, ReviewStatus
from core_domain.fmea.value_objects import EvidencePack
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile
from core_domain.structured_generation import (
    CriticFinding,
    CriticReport,
    CriticVerdict,
    SemanticSupport,
)
from core_domain.structured_output import (
    CandidateClaim,
    ClaimState,
    StructuredCandidate,
    StructuredCandidateBatch,
    ValidationIssue,
)
from fmea_application import StructuredCandidateFmeaAdapter
from fmea_infrastructure import load_fmea_template_profile
from structured_output_application import TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source

ROOT = Path(__file__).parents[2]
TEMPLATE_PATH = ROOT / "templates" / "examples" / "fuel-combustion-fmea-full.yaml"
PROFILE_PATH = ROOT / "templates" / "fmea_profiles" / "fuel-combustion-fmea-full.json"
FIELD_TARGETS = (
    ("item_id", "/item"),
    ("function_id", "/function"),
    ("failure_mode", "/failure_mode"),
    ("causes", "/causes/0"),
    ("mechanisms", "/mechanisms/0"),
    ("effects", "/effects/0"),
    ("symptoms", "/symptoms/0"),
    ("controls", "/controls/0"),
    ("barriers", "/barriers/0"),
    ("actions", "/actions/0"),
)


def _template():
    return TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=load_template_source,
    ).compile_path(TEMPLATE_PATH)


def _payload() -> dict[str, object]:
    return {
        "item": "Fuel  Filter",
        "function": "Filter particles",
        "failure_mode": "Blocked fuel flow",
        "causes": ["Excess particles"],
        "mechanisms": ["Pressure drop rises"],
        "effects": ["Combustion instability"],
        "symptoms": ["Differential pressure alarm"],
        "controls": ["Pressure transmitter"],
        "barriers": ["Low-pressure trip"],
        "actions": ["Replace filter element"],
    }


def _candidate(candidate_id: str = "candidate-1", *, payload: dict[str, object] | None = None):
    return StructuredCandidate(
        candidate_id=candidate_id,
        payload=payload or _payload(),
        claims=tuple(CandidateClaim(target, ClaimState.KNOWN, ("ev-1",)) for _, target in FIELD_TARGETS),
    )


def _batch(pack: EvidencePack, *candidates: StructuredCandidate) -> StructuredCandidateBatch:
    template = _template()
    return StructuredCandidateBatch(
        template_id=template.metadata.template_id,
        template_version=template.metadata.version,
        template_hash=template.template_hash,
        evidence_pack_id=pack.pack_id,
        candidates=candidates or (_candidate(),),
    )


def _critic(
    *,
    support_by_target: dict[str, SemanticSupport] | None = None,
    verdict: CriticVerdict = CriticVerdict.ACCEPT,
) -> CriticReport:
    support_by_target = support_by_target or {}
    return CriticReport(
        verdict=verdict,
        findings=tuple(
            CriticFinding(
                candidate_id="candidate-1",
                target=target,
                support=support_by_target.get(target, SemanticSupport.SUPPORTED),
                code="EVIDENCE_SUPPORTS_CLAIM",
                evidence_ids=("ev-1",),
                explanation="The evidence was checked.",
            )
            for _, target in FIELD_TARGETS
        ),
        summary="Critic completed.",
    )


def _adapt(
    analysis: FmeaAnalysis,
    pack: EvidencePack,
    *,
    batch: StructuredCandidateBatch | None = None,
    critic: CriticReport | None = None,
    repair_count: int = 0,
    deterministic_issues: tuple[ValidationIssue, ...] = (),
):
    return StructuredCandidateFmeaAdapter().adapt(
        analysis=analysis,
        evidence_pack=pack,
        template=_template(),
        batch=batch or _batch(pack),
        critic_report=_critic() if critic is None and repair_count == 0 else critic,
        profile=load_fmea_template_profile(PROFILE_PATH),
        repair_count=repair_count,
        deterministic_issues=deterministic_issues,
        generation_run_id="generation-1",
        requested_evidence_profile=EvidenceSelectionProfile.AUTO,
        resolved_evidence_profile=EvidenceSelectionProfile.COMBINED,
        evidence_types=tuple(CitationType),
        trace_id="trace-1",
        retrieval_warnings=(),
        retrieval_incomplete=False,
    )


def test_supported_candidate_maps_to_server_owned_fmea_row(
    fixture_analysis: FmeaAnalysis,
    fixture_pack: EvidencePack,
) -> None:
    template = _template()
    result = _adapt(fixture_analysis, fixture_pack)
    row = result.rows[0]
    expected_row_digest = hashlib.sha256(
        f"{fixture_analysis.analysis_id}|{template.template_hash}|{fixture_pack.pack_hash}|candidate-1".encode()
    ).hexdigest()[:24]

    assert row.row_id == "fmea-row-" + expected_row_digest
    assert row.item_id == "item-6dbf475ac4924d25b126a8fe"
    assert row.function_id == "function-46e8432139d44de40972e322"
    assert row.failure_mode == "Blocked fuel flow"
    assert row.risk_assessment is None
    assert row.review_status is ReviewStatus.SUGGESTED
    assert row.publication_status is PublicationStatus.UNPUBLISHED
    assert row.claim_status is ClaimStatus.KNOWN
    assert row.field_evidence == tuple((field, ("ev-1",)) for field, _ in FIELD_TARGETS)
    assert all(status is EvidenceSupportStatus.SUPPORTED for _, status in row.field_support)
    assert result.needs_review is False
    validate_row_evidence(row, fixture_pack)
    source = result.source_snapshots[0]
    assert source.item_label == "Fuel  Filter"
    assert source.function_label == "Filter particles"
    assert dict(source.field_claim_statuses)["failure_mode"] is ClaimStatus.KNOWN
    assert source.source_hash.startswith("sha256:")


def test_source_snapshot_aggregates_claim_states_by_profile_field(
    fixture_analysis: FmeaAnalysis,
    fixture_pack: EvidencePack,
) -> None:
    payload = {
        **_payload(),
        "causes": [
            "Excess particles",
            "Wrong maintenance interval",
            "Unverified operating condition",
            "Contradictory maintenance record",
        ],
        "mechanisms": ["Pressure drop rises", "Flow restriction"],
        "effects": ["Combustion instability", "Flameout"],
        "symptoms": ["Differential pressure alarm", "Low flow"],
    }
    candidate = replace(
        _candidate(payload=payload),
        claims=(
            *tuple(
                CandidateClaim(target, ClaimState.KNOWN, ("ev-1",))
                for _, target in FIELD_TARGETS
                if target != "/causes/0"
            ),
            CandidateClaim("/causes/0", ClaimState.NOT_APPLICABLE, ()),
            CandidateClaim("/causes/1", ClaimState.UNKNOWN, ()),
            CandidateClaim("/causes/2", ClaimState.INSUFFICIENT_EVIDENCE, ()),
            CandidateClaim("/causes/3", ClaimState.CONFLICT, ("ev-1", "ev-2")),
            CandidateClaim("/mechanisms/1", ClaimState.UNKNOWN, ()),
            CandidateClaim("/effects/1", ClaimState.INSUFFICIENT_EVIDENCE, ()),
            CandidateClaim("/symptoms/1", ClaimState.CONFLICT, ("ev-1", "ev-2")),
        ),
    )

    source = _adapt(
        fixture_analysis,
        fixture_pack,
        batch=_batch(fixture_pack, candidate),
    ).source_snapshots[0]

    statuses = dict(source.field_claim_statuses)
    assert statuses["causes"] is ClaimStatus.CONFLICT
    assert statuses["mechanisms"] is ClaimStatus.UNKNOWN
    assert statuses["effects"] is ClaimStatus.INSUFFICIENT_EVIDENCE
    assert statuses["symptoms"] is ClaimStatus.CONFLICT


def test_every_adapted_row_has_one_matching_source_snapshot(
    fixture_analysis: FmeaAnalysis,
    fixture_pack: EvidencePack,
) -> None:
    second_payload = _payload()
    second_payload["item"] = "Fuel valve"
    second_payload["function"] = "Control fuel flow"
    result = _adapt(
        fixture_analysis,
        fixture_pack,
        batch=_batch(fixture_pack, _candidate("candidate-2", payload=second_payload), _candidate()),
        critic=None,
        repair_count=1,
    )

    assert tuple(source.row_id for source in result.source_snapshots) == tuple(row.row_id for row in result.rows)
    assert tuple(source.candidate_id for source in result.source_snapshots) == ("candidate-1", "candidate-2")
    assert tuple(source.item_label for source in result.source_snapshots) == ("Fuel  Filter", "Fuel valve")


def test_repaired_or_uncriticised_candidate_is_never_known(
    fixture_analysis: FmeaAnalysis,
    fixture_pack: EvidencePack,
) -> None:
    result = _adapt(fixture_analysis, fixture_pack, critic=None, repair_count=1)

    assert result.needs_review is True
    assert result.rows[0].claim_status is ClaimStatus.INSUFFICIENT_EVIDENCE
    assert all(status is EvidenceSupportStatus.NOT_SUPPORTED for _, status in result.rows[0].field_support)


def test_array_evidence_is_aggregated_sorted_and_deduplicated(
    fixture_analysis: FmeaAnalysis,
    fixture_pack: EvidencePack,
) -> None:
    second_ref = replace(
        fixture_pack.refs[0],
        evidence_id="ev-2",
        evidence_hash="b" * 64,
    )
    pack = EvidencePack.build(
        pack_id=fixture_pack.pack_id,
        workspace_id=fixture_pack.workspace_id,
        acl_scope=fixture_pack.acl_scope,
        versions=fixture_pack.versions,
        refs=(fixture_pack.refs[0], second_ref),
        created_at=fixture_pack.created_at,
        expires_at=fixture_pack.expires_at,
    )
    payload = {**_payload(), "causes": ["Excess particles", "Wrong maintenance interval"]}
    claims = (
        *(
            CandidateClaim(
                target,
                ClaimState.KNOWN,
                ("ev-2", "ev-1") if target == "/causes/0" else ("ev-1",),
            )
            for _, target in FIELD_TARGETS
        ),
        CandidateClaim("/causes/1", ClaimState.KNOWN, ("ev-2",)),
    )
    candidate = replace(_candidate(payload=payload), claims=claims)
    critic = replace(
        _critic(),
        findings=(
            *_critic().findings,
            CriticFinding(
                candidate_id="candidate-1",
                target="/causes/1",
                support=SemanticSupport.SUPPORTED,
                code="EVIDENCE_SUPPORTS_CLAIM",
                evidence_ids=("ev-2",),
                explanation="The second cause is supported.",
            ),
        ),
    )

    result = _adapt(
        fixture_analysis,
        pack,
        batch=_batch(pack, candidate),
        critic=critic,
    )

    assert dict(result.rows[0].field_evidence)["causes"] == ("ev-1", "ev-2")
    assert result.rows[0].causes == ("Excess particles", "Wrong maintenance interval")


def test_conservative_support_and_claim_priorities_are_stable(
    fixture_analysis: FmeaAnalysis,
    fixture_pack: EvidencePack,
) -> None:
    critic = _critic(
        support_by_target={
            "/causes/0": SemanticSupport.PARTIALLY_SUPPORTED,
            "/effects/0": SemanticSupport.CONTRADICTED,
            "/actions/0": SemanticSupport.NOT_SUPPORTED,
        },
        verdict=CriticVerdict.NEEDS_REVIEW,
    )
    result = _adapt(fixture_analysis, fixture_pack, critic=critic)
    support = dict(result.rows[0].field_support)

    assert support["causes"] is EvidenceSupportStatus.PARTIALLY_SUPPORTED
    assert support["effects"] is EvidenceSupportStatus.CONTRADICTED
    assert support["actions"] is EvidenceSupportStatus.NOT_SUPPORTED
    assert result.rows[0].claim_status is ClaimStatus.CONFLICT
    assert result.needs_review is True


@pytest.mark.parametrize("kind", ["profile", "template", "batch_template", "batch_pack"])
def test_adapter_rejects_identity_mismatches(
    fixture_analysis: FmeaAnalysis,
    fixture_pack: EvidencePack,
    kind: str,
) -> None:
    template = _template()
    profile = load_fmea_template_profile(PROFILE_PATH)
    batch = _batch(fixture_pack)
    if kind == "profile":
        profile = replace(profile, template_version="2.0.0")
    elif kind == "template":
        template = replace(template, template_hash="b" * 64)
    elif kind == "batch_template":
        batch = replace(batch, template_hash="b" * 64)
    else:
        batch = replace(batch, evidence_pack_id="other-pack")

    with pytest.raises(FmeaDomainError):
        StructuredCandidateFmeaAdapter().adapt(
            analysis=fixture_analysis,
            evidence_pack=fixture_pack,
            template=template,
            batch=batch,
            critic_report=_critic(),
            profile=profile,
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


def test_unresolved_and_duplicate_candidates_become_safe_adaptation_issues(
    fixture_analysis: FmeaAnalysis,
    fixture_pack: EvidencePack,
) -> None:
    bad_payload = {**_payload(), "item": 7}
    bad = _candidate("candidate-bad", payload=bad_payload)
    duplicate = _candidate("candidate-duplicate")
    result = _adapt(
        fixture_analysis,
        fixture_pack,
        batch=_batch(fixture_pack, _candidate(), duplicate, bad),
        critic=_critic(),
    )

    assert len(result.rows) == 1
    assert {issue.code for issue in result.issues} == {
        "FMEA_CANDIDATE_DUPLICATE",
        "FMEA_FIELD_UNRESOLVED",
    }
    assert result.needs_review is True


def test_deterministic_issues_refuse_all_adaptation(
    fixture_analysis: FmeaAnalysis,
    fixture_pack: EvidencePack,
) -> None:
    issue = ValidationIssue(
        code="CANDIDATE_SCHEMA_INVALID",
        message="Candidate schema is invalid.",
        pointer="/item",
    )

    result = _adapt(fixture_analysis, fixture_pack, deterministic_issues=(issue,))

    assert result.rows == ()
    assert result.needs_review is True
    assert result.issues[0].code == "CANDIDATE_SCHEMA_INVALID"


def test_row_evidence_policy_accepts_identity_fields_and_preserves_old_rules(
    fixture_analysis: FmeaAnalysis,
    fixture_pack: EvidencePack,
) -> None:
    row = _adapt(fixture_analysis, fixture_pack).rows[0]
    validate_row_evidence(row, fixture_pack)

    unknown = replace(
        row,
        field_evidence=(*row.field_evidence, ("arbitrary", ("ev-1",))),
        field_support=(*row.field_support, ("arbitrary", EvidenceSupportStatus.SUPPORTED)),
    )
    with pytest.raises(FmeaDomainError, match="unknown field"):
        validate_row_evidence(unknown, fixture_pack)

    contradicted = replace(
        row,
        field_support=tuple(
            (field, EvidenceSupportStatus.CONTRADICTED if field == "failure_mode" else status)
            for field, status in row.field_support
        ),
    )
    with pytest.raises(FmeaDomainError, match="known claim"):
        validate_row_evidence(contradicted, fixture_pack)
