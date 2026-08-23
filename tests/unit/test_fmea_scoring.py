from __future__ import annotations

import pytest

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.scoring import RiskAssessment, ScoringRulePack, calculate_risk


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
