from __future__ import annotations

from dataclasses import dataclass

from .errors import FmeaDomainError


@dataclass(frozen=True, slots=True)
class ScoringRulePack:
    rule_pack_id: str
    version: str
    applicable_analysis_types: tuple[str, ...]
    severity_anchors: tuple[tuple[int, str], ...]
    occurrence_window: str
    occurrence_denominator: str
    detection_positions: tuple[str, ...]
    score_min: int
    score_max: int
    rpn_formula_version: str
    risk_matrix_version: str
    decision_priority_version: str
    high_priority_rpn: int


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    severity_by_consequence_class: tuple[tuple[str, int | None], ...]
    decision_severity: int | None
    occurrence: int | None
    detection: int | None
    rpn: int | None
    decision_priority: str
    inherent_risk: int | None
    current_risk: int | None
    target_residual_risk: int | None
    verified_residual_risk: int | None
    uncertainty: str | None
    reason: str
    scoring_rule_pack_id: str
    scoring_rule_pack_version: str
    evidence_ids: tuple[str, ...]


def calculate_risk(
    *,
    rule_pack: ScoringRulePack,
    severity_by_consequence_class: tuple[tuple[str, int | None], ...],
    occurrence: int | None,
    detection: int | None,
    inherent_risk: int | None,
    current_risk: int | None,
    target_residual_risk: int | None,
    verified_residual_risk: int | None,
    uncertainty: str | None,
    reason: str,
    evidence_ids: tuple[str, ...],
) -> RiskAssessment:
    consequence_classes: set[str] = set()
    for consequence_class, _ in severity_by_consequence_class:
        if consequence_class in consequence_classes:
            raise FmeaDomainError(f"duplicate consequence class: {consequence_class}")  # noqa: TRY003
        consequence_classes.add(consequence_class)

    scores = [score for _, score in severity_by_consequence_class if score is not None]
    decision_severity = max(scores) if scores else None
    for score in [*scores, occurrence, detection]:
        if score is not None and not rule_pack.score_min <= score <= rule_pack.score_max:
            raise FmeaDomainError(  # noqa: TRY003
                f"score must be between {rule_pack.score_min} and {rule_pack.score_max}"
            )
    if target_residual_risk is not None and (
        not isinstance(target_residual_risk, int) or isinstance(target_residual_risk, bool)
    ):
        raise FmeaDomainError("target_residual_risk must be an integer")  # noqa: TRY003

    rpn = (
        decision_severity * occurrence * detection
        if decision_severity is not None and occurrence is not None and detection is not None
        else None
    )
    if decision_severity is not None and decision_severity >= 9:
        decision_priority = "critical"
    elif rpn is not None and rpn >= rule_pack.high_priority_rpn:
        decision_priority = "high"
    elif rpn is not None and rpn >= rule_pack.high_priority_rpn // 2:
        decision_priority = "medium"
    else:
        decision_priority = "normal"

    verified = verified_residual_risk if target_residual_risk is not None and evidence_ids else None
    return RiskAssessment(
        severity_by_consequence_class=tuple(severity_by_consequence_class),
        decision_severity=decision_severity,
        occurrence=occurrence,
        detection=detection,
        rpn=rpn,
        decision_priority=decision_priority,
        inherent_risk=inherent_risk,
        current_risk=current_risk,
        target_residual_risk=target_residual_risk,
        verified_residual_risk=verified,
        uncertainty=uncertainty,
        reason=reason,
        scoring_rule_pack_id=rule_pack.rule_pack_id,
        scoring_rule_pack_version=rule_pack.version,
        evidence_ids=tuple(evidence_ids),
    )
