from __future__ import annotations

from dataclasses import replace

import pytest

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.scoring import (
    RiskAssessment,
    RiskAssessmentRecord,
    RiskProposal,
    ScoreDimension,
    ScoringRulePack,
    calculate_risk,
    validate_risk_confirmation,
)
from core_domain.fmea.states import FMEA_SCHEMA_ID, RiskStatus
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, VersionSet


def rules() -> ScoringRulePack:
    return ScoringRulePack(
        rule_pack_id="gas-turbine-risk",
        version="1.0.0",
        applicable_analysis_types=("fuel_system", "combustion_system"),
        severity_anchors=((1, "negligible"), (5, "moderate"), (9, "severe")),
        occurrence_window="operating_hours",
        occurrence_denominator="1000_hours",
        detection_positions=("sensor", "logic", "operator"),
        score_min=1,
        score_max=10,
        rpn_formula_version="S*O*D-1",
        risk_matrix_version="matrix-1",
        decision_priority_version="priority-1",
        high_priority_rpn=200,
    )


@pytest.mark.parametrize("invalid_target", (8.5, "8", True))
def test_non_integer_target_residual_risk_is_rejected(invalid_target) -> None:
    with pytest.raises(FmeaDomainError, match="target_residual_risk must be an integer"):
        calculate_risk(
            rule_pack=rules(),
            severity_by_consequence_class=(("safety", 5),),
            occurrence=1,
            detection=1,
            inherent_risk=None,
            current_risk=None,
            target_residual_risk=invalid_target,
            verified_residual_risk=8,
            uncertainty=None,
            reason="invalid target residual risk",
            evidence_ids=("ev-1",),
        )


@pytest.mark.parametrize(
    ("target_residual_risk", "evidence_ids"),
    (
        (8, ()),
        (None, ("ev-1",)),
    ),
)
def test_verified_residual_risk_requires_target_and_evidence(target_residual_risk, evidence_ids) -> None:
    result = calculate_risk(
        rule_pack=rules(),
        severity_by_consequence_class=(("safety", 5),),
        occurrence=1,
        detection=1,
        inherent_risk=None,
        current_risk=None,
        target_residual_risk=target_residual_risk,
        verified_residual_risk=99,
        uncertainty=None,
        reason="missing verification gate input",
        evidence_ids=evidence_ids,
    )

    assert result.verified_residual_risk is None


@pytest.mark.parametrize(
    (
        "severity_by_consequence_class",
        "occurrence",
        "detection",
        "expected_decision_severity",
        "expected_rpn",
        "expected_priority",
    ),
    (
        (
            (("safety", 5), ("asset", 7)),
            10,
            2,
            7,
            140,
            "medium",
        ),
        ((("safety", 5),), 10, 4, 5, 200, "high"),
        ((("safety", 4),), 5, 4, 4, 80, "normal"),
        ((("safety", 2),), 1, 1, 2, 2, "normal"),
    ),
)
def test_risk_values_are_literal_and_deterministic(
    severity_by_consequence_class,
    occurrence,
    detection,
    expected_decision_severity,
    expected_rpn,
    expected_priority,
) -> None:
    result = calculate_risk(
        rule_pack=rules(),
        severity_by_consequence_class=severity_by_consequence_class,
        occurrence=occurrence,
        detection=detection,
        inherent_risk=140,
        current_risk=40,
        target_residual_risk=12,
        verified_residual_risk=12,
        uncertainty=None,
        reason="reviewed operating data",
        evidence_ids=("ev-1",),
    )
    assert isinstance(result, RiskAssessment)
    assert result.decision_severity == expected_decision_severity
    assert result.rpn == expected_rpn
    assert result.decision_priority == expected_priority
    assert result.verified_residual_risk == 12


def test_missing_score_does_not_become_zero_or_rpn() -> None:
    result = calculate_risk(
        rule_pack=rules(),
        severity_by_consequence_class=(("safety", 9),),
        occurrence=None,
        detection=2,
        inherent_risk=None,
        current_risk=None,
        target_residual_risk=8,
        verified_residual_risk=8,
        uncertainty="occurrence evidence missing",
        reason="no observation window",
        evidence_ids=(),
    )
    assert result.rpn is None
    assert result.decision_priority == "critical"
    assert result.verified_residual_risk is None


@pytest.mark.parametrize(
    ("severity_by_consequence_class", "occurrence", "detection"),
    (
        ((), 2, 3),
        ((("safety", 5),), None, 3),
        ((("safety", 5),), 2, None),
    ),
)
def test_any_missing_severity_occurrence_or_detection_leaves_rpn_none(
    severity_by_consequence_class,
    occurrence,
    detection,
) -> None:
    result = calculate_risk(
        rule_pack=rules(),
        severity_by_consequence_class=severity_by_consequence_class,
        occurrence=occurrence,
        detection=detection,
        inherent_risk=None,
        current_risk=None,
        target_residual_risk=None,
        verified_residual_risk=None,
        uncertainty=None,
        reason="missing S/O/D input",
        evidence_ids=(),
    )

    assert result.rpn is None


def test_scores_outside_rule_pack_range_fail() -> None:
    with pytest.raises(FmeaDomainError, match="score must be between 1 and 10"):
        calculate_risk(
            rule_pack=rules(),
            severity_by_consequence_class=(("safety", 0),),
            occurrence=1,
            detection=1,
            inherent_risk=1,
            current_risk=1,
            target_residual_risk=1,
            verified_residual_risk=None,
            uncertainty=None,
            reason="invalid score",
            evidence_ids=(),
        )


def test_duplicate_consequence_classes_fail() -> None:
    with pytest.raises(FmeaDomainError, match="duplicate consequence class"):
        calculate_risk(
            rule_pack=rules(),
            severity_by_consequence_class=(("safety", 5), ("safety", 7)),
            occurrence=1,
            detection=1,
            inherent_risk=None,
            current_risk=None,
            target_residual_risk=None,
            verified_residual_risk=None,
            uncertainty=None,
            reason="duplicate consequence",
            evidence_ids=(),
        )


def test_calculate_risk_rejects_alternative_dimensions_before_calculation() -> None:
    alternative = replace(rules(), required_dimensions=("severity", "likelihood", "detection"))

    with pytest.raises(FmeaDomainError, match="required dimensions"):
        calculate_risk(
            rule_pack=alternative,
            severity_by_consequence_class=(("safety", 5), ("safety", 7)),
            occurrence=1,
            detection=1,
            inherent_risk=None,
            current_risk=None,
            target_residual_risk=None,
            verified_residual_risk=None,
            uncertainty=None,
            reason="alternative dimensions must fail closed",
            evidence_ids=(),
        )


def test_scoring_rule_pack_requires_complete_dimension_anchors() -> None:
    with pytest.raises(FmeaDomainError, match="dimension anchors"):
        ScoringRulePack(
            rule_pack_id="gas-turbine-risk",
            version="1.0.0",
            applicable_analysis_types=("fuel_system",),
            severity_anchors=((1, "low"),),
            occurrence_window="hours",
            occurrence_denominator="1000_hours",
            detection_positions=("sensor",),
            score_min=1,
            score_max=2,
            rpn_formula_version="S*O*D-1",
            risk_matrix_version="matrix-1",
            decision_priority_version="priority-1",
            high_priority_rpn=2,
            dimension_anchors=(("severity", ((1, "low"),)),),
        )


def test_scoring_rule_pack_legacy_constructor_gets_compatible_policy_defaults() -> None:
    pack = rules()

    assert pack.decision_severity_policy == "max_consequence"
    assert pack.rpn_formula == "S*O*D"
    assert pack.critical_severity_threshold == 9
    assert pack.medium_priority_rpn is None
    assert pack.missing_score_policy == "unknown_no_zero"
    assert pack.conflict_score_policy == "block_rpn"
    assert pack.uncertainty_policy == "preserve_require_review"
    assert pack.policy_basis == "project_default_non_certification"


def test_scoring_rule_pack_accepts_explicit_fuel_policies() -> None:
    pack = replace(
        rules(),
        decision_severity_policy="max_consequence",
        rpn_formula="S*O*D",
        critical_severity_threshold=9,
        medium_priority_rpn=100,
        missing_score_policy="unknown_no_zero",
        conflict_score_policy="block_rpn",
        uncertainty_policy="preserve_require_review",
        policy_basis="project_default_non_certification",
    )

    assert pack.medium_priority_rpn == 100


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("decision_severity_policy", "first_consequence"),
        ("rpn_formula", "S+O+D"),
        ("missing_score_policy", "zero_fill"),
        ("conflict_score_policy", "average"),
        ("uncertainty_policy", "discard"),
        ("policy_basis", "certified_default"),
    ),
)
def test_scoring_rule_pack_rejects_unsupported_policies_and_formula(field_name, invalid_value) -> None:
    with pytest.raises(FmeaDomainError, match=field_name):
        replace(rules(), **{field_name: invalid_value})


@pytest.mark.parametrize("invalid_value", (8.5, True, 0, 11))
def test_scoring_rule_pack_rejects_invalid_critical_severity_threshold(invalid_value) -> None:
    with pytest.raises(FmeaDomainError, match="critical_severity_threshold"):
        replace(rules(), critical_severity_threshold=invalid_value)


@pytest.mark.parametrize("invalid_value", (8.5, True, 0, -1))
def test_scoring_rule_pack_rejects_invalid_medium_priority_rpn(invalid_value) -> None:
    with pytest.raises(FmeaDomainError, match="medium_priority_rpn"):
        replace(rules(), medium_priority_rpn=invalid_value)


@pytest.mark.parametrize("invalid_value", (8.5, True, 0, -1))
def test_scoring_rule_pack_rejects_invalid_high_priority_rpn(invalid_value) -> None:
    with pytest.raises(FmeaDomainError, match="high_priority_rpn"):
        replace(rules(), high_priority_rpn=invalid_value)


def test_scoring_rule_pack_requires_medium_rpn_not_to_exceed_high_rpn() -> None:
    with pytest.raises(FmeaDomainError, match="medium_priority_rpn"):
        replace(rules(), medium_priority_rpn=201)


def test_calculate_risk_uses_missing_score_as_unknown_and_declared_thresholds() -> None:
    pack = replace(rules(), critical_severity_threshold=8, medium_priority_rpn=100)

    critical = calculate_risk(
        rule_pack=pack,
        severity_by_consequence_class=(("safety", 8),),
        occurrence=1,
        detection=1,
        inherent_risk=None,
        current_risk=None,
        target_residual_risk=None,
        verified_residual_risk=None,
        uncertainty=None,
        reason="declared critical threshold",
        evidence_ids=(),
    )
    medium = calculate_risk(
        rule_pack=pack,
        severity_by_consequence_class=(("safety", 5),),
        occurrence=5,
        detection=4,
        inherent_risk=None,
        current_risk=None,
        target_residual_risk=None,
        verified_residual_risk=None,
        uncertainty=None,
        reason="declared medium threshold",
        evidence_ids=(),
    )
    missing_occurrence = calculate_risk(
        rule_pack=pack,
        severity_by_consequence_class=(("safety", 8),),
        occurrence=None,
        detection=4,
        inherent_risk=None,
        current_risk=None,
        target_residual_risk=None,
        verified_residual_risk=None,
        uncertainty="occurrence is unknown",
        reason="missing occurrence remains unknown",
        evidence_ids=(),
    )

    assert critical.decision_priority == "critical"
    assert critical.rpn == 8
    assert medium.decision_priority == "medium"
    assert medium.rpn == 100
    assert missing_occurrence.rpn is None


def test_missing_required_dimension_never_produces_confirmed_rpn() -> None:
    proposal = RiskProposal(
        proposal_id="proposal-1",
        workspace_id="ws-1",
        row_id="row-1",
        source_record_version=3,
        evidence_pack_id="pack-1",
        dimensions=(
            ScoreDimension("severity", 9, ("ev-1",), "severe", None),
            ScoreDimension("occurrence", None, (), "unknown", "missing"),
            ScoreDimension("detection", 6, ("ev-1",), "moderate", None),
        ),
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        rule_pack_id="gas-turbine-risk",
        rule_pack_version="1.0.0",
        reason="reviewed operating data",
        created_at="2026-08-23T00:00:00Z",
    )
    with pytest.raises(FmeaDomainError, match="required risk dimension"):
        validate_risk_confirmation(proposal, rule_pack=rules(), evidence_pack=_evidence_pack())


def _evidence_pack(*, pack_id: str = "pack-1", workspace_id: str = "ws-1") -> EvidencePack:
    versions = VersionSet(
        schema_id=FMEA_SCHEMA_ID,
        data_version="data-1",
        graph_version="graph-1",
        evidence_pack_version="evidence-1",
        profile_version="profile-1",
        template_version="template-1",
        scoring_version="score-1",
        prompt_version="prompt-0",
        model_version="model-0",
        input_snapshot_hash="d" * 64,
    )
    ref = EvidenceRef(
        evidence_id="ev-1",
        workspace_id=workspace_id,
        document_id="doc-1",
        document_version="doc-v1",
        content_hash="e" * 64,
        locator="page:1#span:1",
        quote="pressure is low",
        normalized_quote="pressure is low",
        evidence_hash="f" * 64,
        acl_scope=("engineering",),
        source_type="primary_document",
        source_trust="reviewed",
        is_primary=True,
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )
    return EvidencePack.build(
        pack_id=pack_id,
        workspace_id=workspace_id,
        acl_scope=("engineering",),
        versions=versions,
        refs=(ref,),
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )


def _proposal(*dimensions: ScoreDimension) -> RiskProposal:
    return RiskProposal(
        proposal_id="proposal-1",
        workspace_id="ws-1",
        row_id="row-1",
        source_record_version=3,
        evidence_pack_id="pack-1",
        dimensions=dimensions,
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        rule_pack_id="gas-turbine-risk",
        rule_pack_version="1.0.0",
        reason="reviewed operating data",
        created_at="2026-08-23T00:00:00Z",
    )


def _assessment() -> RiskAssessment:
    return calculate_risk(
        rule_pack=rules(),
        severity_by_consequence_class=(("decision", 9),),
        occurrence=3,
        detection=4,
        inherent_risk=None,
        current_risk=None,
        target_residual_risk=None,
        verified_residual_risk=None,
        uncertainty=None,
        reason="reviewed operating data",
        evidence_ids=("ev-1",),
    )


def _record(**overrides: object) -> RiskAssessmentRecord:
    values: dict[str, object] = {
        "assessment_id": "assessment-1",
        "workspace_id": "ws-1",
        "row_id": "row-1",
        "source_record_version": 3,
        "evidence_pack_id": "pack-1",
        "domain_pack_id": "fuel-combustion",
        "domain_pack_version": "1.0.0",
        "rule_pack_id": "gas-turbine-risk",
        "rule_pack_version": "1.0.0",
        "status": RiskStatus.PROPOSED,
        "dimensions": (
            ScoreDimension("severity", 9, ("ev-1",), "severe", None),
            ScoreDimension("occurrence", 3, ("ev-1",), "occasional", None),
            ScoreDimension("detection", 4, ("ev-1",), "moderate", None),
        ),
        "derived": None,
        "proposal_id": None,
        "assistance_suggestion_id": None,
        "confirmer_actor_id": None,
        "invalidated_reason": None,
        "record_version": 1,
        "created_at": "2026-08-23T00:00:00Z",
        "updated_at": "2026-08-23T00:00:00Z",
    }
    values.update(overrides)
    return RiskAssessmentRecord(**values)


def test_risk_proposal_requires_explicit_dimensions_and_identities() -> None:
    with pytest.raises(TypeError):
        RiskProposal()

    dimensions = (ScoreDimension("severity", 9, ("ev-1",), "severe", None),)
    for field_name in (
        "proposal_id",
        "workspace_id",
        "row_id",
        "evidence_pack_id",
        "domain_pack_id",
        "domain_pack_version",
        "rule_pack_id",
        "rule_pack_version",
        "reason",
        "created_at",
    ):
        values = {
            "proposal_id": "proposal-1",
            "workspace_id": "ws-1",
            "row_id": "row-1",
            "source_record_version": 3,
            "evidence_pack_id": "pack-1",
            "dimensions": dimensions,
            "domain_pack_id": "fuel-combustion",
            "domain_pack_version": "1.0.0",
            "rule_pack_id": "gas-turbine-risk",
            "rule_pack_version": "1.0.0",
            "reason": "reviewed operating data",
            "created_at": "2026-08-23T00:00:00Z",
        }
        values[field_name] = ""
        with pytest.raises(FmeaDomainError, match=field_name):
            RiskProposal(**values)


def test_confirmation_requires_explicit_rule_and_evidence_packs() -> None:
    proposal = _proposal(
        ScoreDimension("severity", 9, ("ev-1",), "severe", None),
        ScoreDimension("occurrence", 3, ("ev-1",), "occasional", None),
        ScoreDimension("detection", 4, ("ev-1",), "moderate", None),
    )
    with pytest.raises(FmeaDomainError, match="rule pack is required"):
        validate_risk_confirmation(proposal, evidence_pack=_evidence_pack())
    with pytest.raises(FmeaDomainError, match="EvidencePack is required"):
        validate_risk_confirmation(proposal, rule_pack=rules())


def test_confirmation_binds_proposal_to_workspace_packs_and_known_evidence() -> None:
    proposal = _proposal(
        ScoreDimension("severity", 9, ("ev-1",), "severe", None),
        ScoreDimension("occurrence", 3, ("ev-1",), "occasional", None),
        ScoreDimension("detection", 4, ("ev-1",), "moderate", None),
    )
    pack = _evidence_pack()
    with pytest.raises(FmeaDomainError, match="pack ID"):
        validate_risk_confirmation(proposal, rule_pack=rules(), evidence_pack=_evidence_pack(pack_id="pack-2"))
    with pytest.raises(FmeaDomainError, match="workspace"):
        validate_risk_confirmation(proposal, rule_pack=rules(), evidence_pack=_evidence_pack(workspace_id="ws-2"))
    with pytest.raises(FmeaDomainError, match="known evidence"):
        validate_risk_confirmation(
            _proposal(
                ScoreDimension("severity", 9, (), "severe", None),
                ScoreDimension("occurrence", 3, ("ev-1",), "occasional", None),
                ScoreDimension("detection", 4, ("ev-1",), "moderate", None),
            ),
            rule_pack=rules(),
            evidence_pack=pack,
        )


def test_confirmation_rejects_alternative_and_extra_dimensions_and_checks_all_ranges() -> None:
    proposal = _proposal(
        ScoreDimension("severity", 9, ("ev-1",), "severe", None),
        ScoreDimension("occurrence", 3, ("ev-1",), "occasional", None),
        ScoreDimension("detection", 4, ("ev-1",), "moderate", None),
        ScoreDimension("extra", 99, ("ev-1",), "unexpected", None),
    )
    with pytest.raises(FmeaDomainError, match="not declared"):
        validate_risk_confirmation(proposal, rule_pack=rules(), evidence_pack=_evidence_pack())

    alternative = ScoringRulePack(
        rule_pack_id="alternative-risk",
        version="1.0.0",
        applicable_analysis_types=("fuel_system",),
        severity_anchors=(),
        occurrence_window="hours",
        occurrence_denominator="1000_hours",
        detection_positions=(),
        score_min=1,
        score_max=10,
        rpn_formula_version="S*O*D",
        risk_matrix_version="matrix-1",
        decision_priority_version="priority-1",
        high_priority_rpn=200,
        required_dimensions=("severity", "likelihood", "detection"),
    )
    with pytest.raises(FmeaDomainError, match="required dimensions"):
        validate_risk_confirmation(proposal, rule_pack=alternative, evidence_pack=_evidence_pack())

    with pytest.raises(FmeaDomainError, match="score must be between 1 and 10"):
        validate_risk_confirmation(
            _proposal(
                ScoreDimension("severity", 9, ("ev-1",), "severe", None),
                ScoreDimension("occurrence", 3, ("ev-1",), "occasional", None),
                ScoreDimension("detection", 11, ("ev-1",), "unbounded", None),
            ),
            rule_pack=rules(),
            evidence_pack=_evidence_pack(),
        )


@pytest.mark.parametrize("status", (RiskStatus.UNSCORED, RiskStatus.PROPOSED, RiskStatus.REVIEWED))
def test_non_confirmed_risk_record_cannot_carry_derived_assessment(status: RiskStatus) -> None:
    with pytest.raises(FmeaDomainError, match="derived assessment"):
        _record(status=status, derived=_assessment())


def test_risk_record_rejects_duplicate_dimensions() -> None:
    dimensions = (
        ScoreDimension("severity", 9, ("ev-1",), "severe", None),
        ScoreDimension("severity", 8, ("ev-1",), "high", None),
    )
    with pytest.raises(FmeaDomainError, match="duplicate risk dimension"):
        _record(dimensions=dimensions)


def test_confirmed_risk_record_requires_complete_identity_and_derived_consistency() -> None:
    with pytest.raises(FmeaDomainError, match="proposal_id"):
        _record(status=RiskStatus.CONFIRMED, derived=_assessment(), confirmer_actor_id="actor-1")
    with pytest.raises(FmeaDomainError, match="confirmer_actor_id"):
        _record(status=RiskStatus.CONFIRMED, derived=_assessment(), proposal_id="proposal-1")
    with pytest.raises(FmeaDomainError, match="confirmed risk dimension"):
        _record(
            status=RiskStatus.CONFIRMED,
            derived=_assessment(),
            proposal_id="proposal-1",
            confirmer_actor_id="actor-1",
            dimensions=(
                ScoreDimension("severity", None, (), "unknown", "missing"),
                ScoreDimension("occurrence", 3, ("ev-1",), "occasional", None),
                ScoreDimension("detection", 4, ("ev-1",), "moderate", None),
            ),
        )
    with pytest.raises(FmeaDomainError, match="rule identity"):
        altered_assessment = replace(_assessment(), scoring_rule_pack_id="other-risk")
        _record(
            status=RiskStatus.CONFIRMED,
            derived=altered_assessment,
            proposal_id="proposal-1",
            confirmer_actor_id="actor-1",
        )

    confirmed = _record(
        status=RiskStatus.CONFIRMED,
        derived=_assessment(),
        proposal_id="proposal-1",
        confirmer_actor_id="actor-1",
    )
    assert confirmed.derived is not None
    assert confirmed.derived.rpn == 108


@pytest.mark.parametrize(
    "dimensions",
    (
        (
            ScoreDimension("severity", 9, ("ev-1",), "severe", None),
            ScoreDimension("occurrence", 3, ("ev-1",), "occasional", None),
            ScoreDimension("detection", 4, ("ev-1",), "moderate", None),
            ScoreDimension("temperature", 2, ("ev-1",), "unexpected", None),
        ),
        (
            ScoreDimension("severity", 9, ("ev-1",), "severe", None),
            ScoreDimension("occurrence", 3, ("ev-1",), "occasional", None),
            ScoreDimension("likelihood", 4, ("ev-1",), "unknown name", None),
        ),
    ),
)
def test_confirmed_risk_record_requires_exact_sod_dimension_names(
    dimensions: tuple[ScoreDimension, ...],
) -> None:
    with pytest.raises(FmeaDomainError, match="exactly severity, occurrence, detection"):
        _record(
            status=RiskStatus.CONFIRMED,
            derived=_assessment(),
            proposal_id="proposal-1",
            confirmer_actor_id="actor-1",
            dimensions=dimensions,
        )


def test_invalidated_risk_record_requires_reason() -> None:
    with pytest.raises(FmeaDomainError, match="invalidated reason"):
        _record(status=RiskStatus.INVALIDATED)
