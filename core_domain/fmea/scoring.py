from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .errors import FmeaDomainError
from .states import RiskStatus


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
    required_dimensions: tuple[str, ...] = ("severity", "occurrence", "detection")
    dimension_anchors: tuple[tuple[str, tuple[tuple[int, str], ...]], ...] = ()

    def __post_init__(self) -> None:
        required = tuple(self.required_dimensions)
        if not required or any(not isinstance(name, str) or not name.strip() for name in required):
            raise FmeaDomainError("required_dimensions must contain non-empty names")  # noqa: TRY003
        if len(required) != len(set(required)):
            raise FmeaDomainError("duplicate required risk dimension")  # noqa: TRY003
        object.__setattr__(self, "required_dimensions", required)

        if isinstance(self.score_min, bool) or not isinstance(self.score_min, int):
            raise FmeaDomainError("score_min must be an integer")  # noqa: TRY003
        if isinstance(self.score_max, bool) or not isinstance(self.score_max, int) or self.score_min > self.score_max:
            raise FmeaDomainError("score_max must be an integer at least score_min")  # noqa: TRY003

        raw_anchors = tuple(self.dimension_anchors)
        normalized: list[tuple[str, tuple[tuple[int, str], ...]]] = []
        seen: set[str] = set()
        for item in raw_anchors:
            if not isinstance(item, tuple | list) or len(item) != 2:
                raise FmeaDomainError("dimension anchors must contain dimension pairs")  # noqa: TRY003
            name, anchors = item
            if not isinstance(name, str) or not name.strip():
                raise FmeaDomainError("dimension anchor name must not be empty")  # noqa: TRY003
            if name in seen:
                raise FmeaDomainError(f"duplicate dimension anchor: {name}")  # noqa: TRY003
            seen.add(name)
            normalized_anchors: list[tuple[int, str]] = []
            for anchor in tuple(anchors):
                if not isinstance(anchor, tuple | list) or len(anchor) != 2:
                    raise FmeaDomainError("dimension anchors must contain score/description pairs")  # noqa: TRY003
                score, description = anchor
                if isinstance(score, bool) or not isinstance(score, int) or not isinstance(description, str) or not description:
                    raise FmeaDomainError("dimension anchor value is invalid")  # noqa: TRY003
                normalized_anchors.append((score, description))
            scores = tuple(score for score, _ in normalized_anchors)
            if len(scores) != len(set(scores)) or set(scores) != set(range(self.score_min, self.score_max + 1)):
                raise FmeaDomainError("dimension anchors must cover the complete score range")  # noqa: TRY003
            normalized.append((name, tuple(normalized_anchors)))
        if raw_anchors:
            missing = set(required) - seen
            if missing:
                raise FmeaDomainError("dimension anchors are incomplete for required dimensions")  # noqa: TRY003
        object.__setattr__(self, "dimension_anchors", tuple(normalized))


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


@dataclass(frozen=True, slots=True)
class ScoreDimension:
    name: str
    value: int | None
    evidence_ids: tuple[str, ...]
    reason: str
    uncertainty: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise FmeaDomainError("risk dimension name must not be empty")  # noqa: TRY003
        if self.value is not None and (isinstance(self.value, bool) or not isinstance(self.value, int)):
            raise FmeaDomainError("risk dimension value must be an integer or unknown")  # noqa: TRY003
        evidence_ids = tuple(self.evidence_ids)
        if any(not isinstance(item, str) or not item for item in evidence_ids):
            raise FmeaDomainError("risk dimension evidence IDs must be non-empty")  # noqa: TRY003
        if len(evidence_ids) != len(set(evidence_ids)):
            raise FmeaDomainError("risk dimension evidence IDs must not contain duplicates")  # noqa: TRY003
        object.__setattr__(self, "evidence_ids", evidence_ids)
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise FmeaDomainError("risk dimension reason must not be empty")  # noqa: TRY003
        if self.uncertainty is not None and (not isinstance(self.uncertainty, str) or not self.uncertainty.strip()):
            raise FmeaDomainError("risk dimension uncertainty must not be empty")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class RiskProposal:
    proposal_id: str = "proposal-1"
    workspace_id: str = "workspace-1"
    row_id: str = "row-1"
    source_record_version: int = 1
    evidence_pack_id: str = "pack-1"
    dimensions: tuple[ScoreDimension, ...] = ()
    domain_pack_id: str = ""
    domain_pack_version: str = ""
    rule_pack_id: str = ""
    rule_pack_version: str = ""
    assistance_suggestion_id: str | None = None
    reason: str = ""
    uncertainty: str | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        for field_name in ("proposal_id", "workspace_id", "row_id", "evidence_pack_id"):
            if not isinstance(getattr(self, field_name), str) or not getattr(self, field_name).strip():
                raise FmeaDomainError(f"{field_name} must not be empty")  # noqa: TRY003
        if isinstance(self.source_record_version, bool) or not isinstance(self.source_record_version, int) or self.source_record_version < 1:
            raise FmeaDomainError("source_record_version must be positive")  # noqa: TRY003
        dimensions = tuple(self.dimensions)
        if any(not isinstance(item, ScoreDimension) for item in dimensions):
            raise FmeaDomainError("dimensions must contain ScoreDimension objects")  # noqa: TRY003
        names = tuple(item.name for item in dimensions)
        if len(names) != len(set(names)):
            raise FmeaDomainError("duplicate risk dimension")  # noqa: TRY003
        object.__setattr__(self, "dimensions", dimensions)


@dataclass(frozen=True, slots=True)
class RiskAssessmentRecord:
    assessment_id: str
    workspace_id: str
    row_id: str
    source_record_version: int
    evidence_pack_id: str
    domain_pack_id: str
    domain_pack_version: str
    rule_pack_id: str
    rule_pack_version: str
    status: RiskStatus
    dimensions: tuple[ScoreDimension, ...]
    derived: RiskAssessment | None
    proposal_id: str | None
    assistance_suggestion_id: str | None
    confirmer_actor_id: str | None
    invalidated_reason: str | None
    record_version: int
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        for field_name in (
            "assessment_id",
            "workspace_id",
            "row_id",
            "evidence_pack_id",
            "domain_pack_id",
            "domain_pack_version",
            "rule_pack_id",
            "rule_pack_version",
            "created_at",
            "updated_at",
        ):
            if not isinstance(getattr(self, field_name), str) or not getattr(self, field_name).strip():
                raise FmeaDomainError(f"{field_name} must not be empty")  # noqa: TRY003
        if not isinstance(self.status, RiskStatus):
            raise FmeaDomainError("status must be a RiskStatus")  # noqa: TRY003
        dimensions = tuple(self.dimensions)
        if any(not isinstance(item, ScoreDimension) for item in dimensions):
            raise FmeaDomainError("dimensions must contain ScoreDimension objects")  # noqa: TRY003
        object.__setattr__(self, "dimensions", dimensions)
        for field_name in ("source_record_version", "record_version"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise FmeaDomainError(f"{field_name} must be positive")  # noqa: TRY003
        if self.derived is not None and not isinstance(self.derived, RiskAssessment):
            raise FmeaDomainError("derived must be a RiskAssessment")  # noqa: TRY003


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


def _compatibility_rule_pack(
    required_dimensions: tuple[str, ...],
    score_min: int,
    score_max: int,
) -> ScoringRulePack:
    return ScoringRulePack(
        rule_pack_id="domain-confirmation",
        version="1.0.0",
        applicable_analysis_types=("fmea",),
        severity_anchors=(),
        occurrence_window="unspecified",
        occurrence_denominator="unspecified",
        detection_positions=(),
        score_min=score_min,
        score_max=score_max,
        rpn_formula_version="S*O*D",
        risk_matrix_version="unspecified",
        decision_priority_version="unspecified",
        high_priority_rpn=200,
        required_dimensions=required_dimensions,
    )


def validate_risk_confirmation(
    proposal: RiskProposal,
    required_dimensions: tuple[str, ...] | None = None,
    *,
    rule_pack: ScoringRulePack | None = None,
    evidence_pack: object | None = None,
    available_evidence_ids: Iterable[str] | None = None,
) -> RiskAssessment:
    """Validate a proposal before a human may confirm its derived risk."""

    if not isinstance(proposal, RiskProposal):
        raise FmeaDomainError("risk proposal is invalid")  # noqa: TRY003
    required = tuple(
        required_dimensions
        if required_dimensions is not None
        else (rule_pack.required_dimensions if rule_pack is not None else ("severity", "occurrence", "detection"))
    )
    if not required or len(required) != len(set(required)):
        raise FmeaDomainError("required risk dimensions must be unique")  # noqa: TRY003
    dimensions = {dimension.name: dimension for dimension in proposal.dimensions}
    for name in required:
        dimension = dimensions.get(name)
        if dimension is None or dimension.value is None:
            raise FmeaDomainError(f"required risk dimension is unknown: {name}")  # noqa: TRY003

    known_evidence_ids: set[str] | None = None
    if evidence_pack is not None:
        refs = getattr(evidence_pack, "refs", None)
        if refs is None:
            raise FmeaDomainError("evidence pack is invalid")  # noqa: TRY003
        known_evidence_ids = {ref.evidence_id for ref in refs}
    if available_evidence_ids is not None:
        supplied = set(available_evidence_ids)
        known_evidence_ids = supplied if known_evidence_ids is None else known_evidence_ids & supplied
    if known_evidence_ids is not None:
        for dimension in proposal.dimensions:
            missing = set(dimension.evidence_ids) - known_evidence_ids
            if missing:
                raise FmeaDomainError(f"evidence ID is outside EvidencePack: {sorted(missing)[0]}")  # noqa: TRY003

    selected_rule_pack = rule_pack or _compatibility_rule_pack(required, 1, 10)
    for name in required:
        value = dimensions[name].value
        if value is not None and not selected_rule_pack.score_min <= value <= selected_rule_pack.score_max:
            raise FmeaDomainError(
                f"score must be between {selected_rule_pack.score_min} and {selected_rule_pack.score_max}"
            )

    severity = dimensions.get("severity")
    occurrence = dimensions.get("occurrence")
    detection = dimensions.get("detection")
    if severity is None or occurrence is None or detection is None:
        raise FmeaDomainError("required risk dimension names cannot derive RPN")  # noqa: TRY003
    evidence_ids: list[str] = []
    for dimension in proposal.dimensions:
        for evidence_id in dimension.evidence_ids:
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
    return calculate_risk(
        rule_pack=selected_rule_pack,
        severity_by_consequence_class=(("decision", severity.value),),
        occurrence=occurrence.value,
        detection=detection.value,
        inherent_risk=None,
        current_risk=None,
        target_residual_risk=None,
        verified_residual_risk=None,
        uncertainty=proposal.uncertainty,
        reason=proposal.reason or "human-confirmed risk proposal",
        evidence_ids=tuple(evidence_ids),
    )
