from __future__ import annotations

from dataclasses import replace

import pytest

from core_domain.fmea.scoring import RiskAssessment, RiskAssessmentRecord, RiskProposal, ScoreDimension
from core_domain.fmea.states import ActorType, RiskStatus
from fmea_application.ports import RiskRepository
from fmea_application.review_contracts import AuditEvent, IdempotencyScope
from fmea_application.risk_contracts import (
    OutboxEvent,
    PreparedRiskConfirmation,
    PreparedRiskInvalidation,
    PreparedRiskProposal,
    PreparedRiskRejection,
    RiskConfirmationResult,
    outbox_payload_hash,
    risk_confirmation_payload_hash,
    risk_invalidation_payload_hash,
    risk_proposal_payload_hash,
    risk_rejection_payload_hash,
)

HASH = "sha256:" + "b" * 64


def scope(actor_id: str) -> IdempotencyScope:
    return IdempotencyScope("ws-1", actor_id, "fmea.risk", "/fmea/rows/row-1/risk", HASH)


def audit(
    *,
    actor_id: str,
    actor_type: ActorType,
    decision_id: str | None = None,
    canonical_hash: str = HASH,
) -> AuditEvent:
    from core_domain.fmea.value_objects import VersionSet

    return AuditEvent(
        event_id="audit-1",
        occurred_at_server="2026-01-01T00:00:00Z",
        workspace_id="ws-1",
        actor_id=actor_id,
        actor_type=actor_type,
        actor_roles=(),
        command="fmea.risk",
        action=None,
        reason_code=None,
        reason="risk lifecycle",
        analysis_id="analysis-1",
        row_id="row-1",
        suggestion_id=None,
        decision_id=decision_id,
        expected_record_version=1,
        applied_record_version=2,
        before_hash=HASH,
        after_hash=HASH,
        changed_fields=(),
        evidence_ids=("e-1", "e-2", "e-3"),
        evidence_request_targets=(),
        idempotency_key_hash=HASH,
        canonical_payload_hash=canonical_hash,
        versions=VersionSet("graphrag.fmea.v1", "1", "1", "1", "1", "1", "1", "1", "1", HASH),
        template_id="fuel-fmea",
        template_version="1.0.0",
        profile_id="combined",
        profile_version="1.0.0",
        model_manifest=None,
        request_id="request-1",
        trace_id="trace-1",
        retrieval_trace_id="retrieval-1",
    )


def dimensions() -> tuple[ScoreDimension, ...]:
    return (
        ScoreDimension("severity", 9, ("e-1",), "high consequence", None),
        ScoreDimension("occurrence", 4, ("e-2",), "observed frequency", None),
        ScoreDimension("detection", 3, ("e-3",), "online detection", None),
    )


def proposal() -> RiskProposal:
    return RiskProposal(
        proposal_id="proposal-1",
        workspace_id="ws-1",
        row_id="row-1",
        source_record_version=1,
        evidence_pack_id="pack-1",
        dimensions=dimensions(),
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        rule_pack_id="fuel-sod-rpn",
        rule_pack_version="1.0.0",
        reason="bounded proposal",
        created_at="2026-01-01T00:00:00Z",
    )


def assessment(status: RiskStatus, *, assessment_id: str = "assessment-1", version: int = 1, source_version: int = 1) -> RiskAssessmentRecord:
    derived = None
    confirmer = None
    invalidated_reason = None
    if status is RiskStatus.CONFIRMED:
        derived = RiskAssessment(
            severity_by_consequence_class=(("safety", 9),),
            decision_severity=9,
            occurrence=4,
            detection=3,
            rpn=108,
            decision_priority="critical",
            inherent_risk=None,
            current_risk=None,
            target_residual_risk=None,
            verified_residual_risk=None,
            uncertainty=None,
            reason="confirmed",
            scoring_rule_pack_id="fuel-sod-rpn",
            scoring_rule_pack_version="1.0.0",
            evidence_ids=("e-1", "e-2", "e-3"),
        )
        confirmer = "reviewer-1"
    if status is RiskStatus.INVALIDATED:
        invalidated_reason = "source row changed"
    return RiskAssessmentRecord(
        assessment_id=assessment_id,
        workspace_id="ws-1",
        row_id="row-1",
        source_record_version=source_version,
        evidence_pack_id="pack-1",
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        rule_pack_id="fuel-sod-rpn",
        rule_pack_version="1.0.0",
        status=status,
        dimensions=dimensions(),
        derived=derived,
        proposal_id="proposal-1",
        assistance_suggestion_id=None,
        confirmer_actor_id=confirmer,
        invalidated_reason=invalidated_reason,
        record_version=version,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def prepared_proposal() -> PreparedRiskProposal:
    risk_proposal = proposal()
    risk_assessment = assessment(RiskStatus.PROPOSED)
    prepared_hash = risk_proposal_payload_hash(scope("model-1"), risk_proposal, risk_assessment)
    return PreparedRiskProposal(
        scope=scope("model-1"),
        payload_hash=prepared_hash,
        proposal=risk_proposal,
        assessment=risk_assessment,
        audit=audit(actor_id="model-1", actor_type=ActorType.MODEL, canonical_hash=prepared_hash),
    )


def test_prepared_risk_proposal_reuses_domain_objects_and_is_proposed_only() -> None:
    prepared = prepared_proposal()
    assert isinstance(prepared.proposal, RiskProposal)
    assert isinstance(prepared.assessment, RiskAssessmentRecord)
    assert prepared.assessment.status is RiskStatus.PROPOSED
    assert prepared.assessment.derived is None


def test_confirmation_requires_human_and_increments_expected_assessment_version() -> None:
    previous = assessment(RiskStatus.PROPOSED)
    confirmed = assessment(RiskStatus.CONFIRMED, version=2)
    prepared_hash = risk_confirmation_payload_hash(
        scope("reviewer-1"), proposal(), previous, confirmed, 1, "risk-decision-1"
    )
    prepared = PreparedRiskConfirmation(
        scope=scope("reviewer-1"),
        payload_hash=prepared_hash,
        proposal=proposal(),
        previous_assessment=previous,
        assessment=confirmed,
        expected_assessment_version=1,
        decision_id="risk-decision-1",
        audit=audit(
            actor_id="reviewer-1",
            actor_type=ActorType.HUMAN,
            decision_id="risk-decision-1",
            canonical_hash=prepared_hash,
        ),
    )
    assert prepared.assessment.status is RiskStatus.CONFIRMED

    with pytest.raises(ValueError, match="human actor"):
        PreparedRiskConfirmation(
            scope=scope("model-1"),
            payload_hash=prepared_hash,
            proposal=proposal(),
            previous_assessment=previous,
            assessment=replace(confirmed, confirmer_actor_id="model-1"),
            expected_assessment_version=1,
            decision_id="risk-decision-1",
            audit=audit(
                actor_id="model-1",
                actor_type=ActorType.MODEL,
                decision_id="risk-decision-1",
                canonical_hash=prepared_hash,
            ),
        )


def test_rejection_and_invalidation_have_explicit_status_transitions() -> None:
    previous = assessment(RiskStatus.PROPOSED)
    reviewed = assessment(RiskStatus.REVIEWED, version=2)
    rejection_hash = risk_rejection_payload_hash(
        scope("reviewer-1"), proposal(), previous, reviewed, 1, "risk-decision-2"
    )
    rejected = PreparedRiskRejection(
        scope=scope("reviewer-1"),
        payload_hash=rejection_hash,
        proposal=proposal(),
        previous_assessment=previous,
        assessment=reviewed,
        expected_assessment_version=1,
        decision_id="risk-decision-2",
        audit=audit(
            actor_id="reviewer-1",
            actor_type=ActorType.HUMAN,
            decision_id="risk-decision-2",
            canonical_hash=rejection_hash,
        ),
    )
    assert rejected.assessment.status is RiskStatus.REVIEWED

    invalidated = assessment(RiskStatus.INVALIDATED, assessment_id="assessment-2", version=3, source_version=2)
    invalidation_hash = risk_invalidation_payload_hash(
        scope("risk-system"), assessment(RiskStatus.CONFIRMED, version=2), invalidated, 2, "risk-decision-3"
    )
    invalidation = PreparedRiskInvalidation(
        scope=scope("risk-system"),
        payload_hash=invalidation_hash,
        previous_assessment=assessment(RiskStatus.CONFIRMED, version=2),
        assessment=invalidated,
        expected_assessment_version=2,
        decision_id="risk-decision-3",
        audit=audit(
            actor_id="risk-system",
            actor_type=ActorType.SYSTEM,
            decision_id="risk-decision-3",
            canonical_hash=invalidation_hash,
        ),
    )
    assert invalidation.assessment.status is RiskStatus.INVALIDATED


def test_result_and_outbox_are_immutable_and_canonical() -> None:
    result = RiskConfirmationResult(
        assessment=assessment(RiskStatus.CONFIRMED, version=2),
        decision_id="risk-decision-1",
        audit_event_id="audit-1",
        outbox_event_id="outbox-1",
        replayed=False,
    )
    event = OutboxEvent(
        event_id="outbox-1",
        workspace_id="ws-1",
        aggregate_type="risk_assessment",
        aggregate_id="assessment-1",
        event_type="risk.confirmed",
        payload={"rpn": 108, "status": "confirmed"},
        payload_hash=outbox_payload_hash({"rpn": 108, "status": "confirmed"}),
        created_at="2026-01-01T00:00:00Z",
    )
    assert result.assessment.status is RiskStatus.CONFIRMED
    assert event.payload["status"] == "confirmed"
    with pytest.raises(TypeError):
        event.payload["status"] = "invalid"  # type: ignore[index]


def test_risk_repository_port_contains_atomic_lifecycle_methods() -> None:
    expected = {
        "initialize",
        "get_row",
        "get_evidence_pack",
        "get_current_assessment",
        "save_proposal",
        "replay_confirmation",
        "commit_confirmation",
        "reject",
        "invalidate",
        "list_outbox_events",
    }
    assert expected.issubset(RiskRepository.__dict__)
    assert all("infrastructure" not in str(annotation) for annotation in RiskRepository.__dict__.values())


def test_prepared_risk_payload_hash_is_bound_to_body_and_audit() -> None:
    prepared = prepared_proposal()
    forged_hash = "sha256:" + "c" * 64
    with pytest.raises(ValueError, match="payload hash does not match canonical payload"):
        PreparedRiskProposal(
            scope=prepared.scope,
            payload_hash=forged_hash,
            proposal=prepared.proposal,
            assessment=prepared.assessment,
            audit=prepared.audit,
        )

    with pytest.raises(ValueError, match="audit canonical payload hash"):
        PreparedRiskProposal(
            scope=prepared.scope,
            payload_hash=prepared.payload_hash,
            proposal=prepared.proposal,
            assessment=prepared.assessment,
            audit=replace(prepared.audit, canonical_payload_hash=forged_hash),
        )
