"""Versioned HTTP adapter for evidence-bound FMEA risk review."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from core_domain.fmea.states import ActorType
from fmea_application.review_errors import ReviewError
from fmea_application.risk_contracts import ConfirmRiskCommand, RejectRiskCommand, StartRiskProposalCommand

from .fmea_review_contracts import RiskAssessmentData
from .fmea_risk_contracts import (
    RiskAssessmentRecordData,
    RiskConfirmationBody,
    RiskConfirmationResultData,
    RiskDimensionData,
    RiskProposalBody,
    RiskProposalRunData,
    RiskRejectionBody,
)
from .routes_fmea_assistance_v1 import RiskAccess, get_risk_access, json_response, service_call
from .routes_fmea_review_v1 import parse_idempotency_key, parse_if_match

router = APIRouter(prefix="/api/v1/fmea", tags=["fmea-risk-v1"])


def _derived_data(value: Any | None) -> RiskAssessmentData | None:
    if value is None:
        return None
    return RiskAssessmentData.model_validate(
        {
            "severity_by_consequence_class": [list(item) for item in value.severity_by_consequence_class],
            "decision_severity": value.decision_severity,
            "occurrence": value.occurrence,
            "detection": value.detection,
            "rpn": value.rpn,
            "decision_priority": value.decision_priority,
            "inherent_risk": value.inherent_risk,
            "current_risk": value.current_risk,
            "target_residual_risk": value.target_residual_risk,
            "verified_residual_risk": value.verified_residual_risk,
            "uncertainty": value.uncertainty,
            "reason": value.reason,
            "scoring_rule_pack_id": value.scoring_rule_pack_id,
            "scoring_rule_pack_version": value.scoring_rule_pack_version,
            "evidence_ids": list(value.evidence_ids),
        }
    )


def assessment_data(value: Any) -> RiskAssessmentRecordData:
    return RiskAssessmentRecordData(
        assessment_id=value.assessment_id,
        workspace_id=value.workspace_id,
        row_id=value.row_id,
        source_record_version=value.source_record_version,
        evidence_pack_id=value.evidence_pack_id,
        domain_pack_id=value.domain_pack_id,
        domain_pack_version=value.domain_pack_version,
        rule_pack_id=value.rule_pack_id,
        rule_pack_version=value.rule_pack_version,
        status=value.status,
        dimensions=[
            RiskDimensionData(
                name=item.name,
                value=item.value,
                evidence_ids=list(item.evidence_ids),
                reason=item.reason,
                uncertainty=item.uncertainty,
            )
            for item in value.dimensions
        ],
        derived=_derived_data(value.derived),
        proposal_id=value.proposal_id,
        assistance_suggestion_id=value.assistance_suggestion_id,
        confirmer_actor_id=value.confirmer_actor_id,
        invalidated_reason=value.invalidated_reason,
        record_version=value.record_version,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def confirmation_data(value: Any) -> RiskConfirmationResultData:
    return RiskConfirmationResultData(
        assessment=assessment_data(value.assessment),
        decision_id=value.decision_id,
        audit_event_id=value.audit_event_id,
        outbox_event_id=value.outbox_event_id,
        replayed=value.replayed,
        persisted=value.persisted,
    )


def _require_human_risk_reviewer(access: RiskAccess) -> None:
    if access.actor.actor_type is not ActorType.HUMAN:
        raise ReviewError(
            "FMEA_RISK_HUMAN_CONFIRMATION_REQUIRED",
            "a human risk reviewer is required",
        )
    if "risk_reviewer" not in access.actor.roles:
        raise ReviewError("FMEA_REVIEW_FORBIDDEN", "the risk_reviewer role is required")


@router.get("/rows/{row_id}/risk")
def get_risk(row_id: str, access: RiskAccess = Depends(get_risk_access)) -> Response:  # noqa: B008
    assessment = service_call(lambda: access.runtime.risk_service.get(row_id, access.actor))
    if assessment is None:
        raise ReviewError("FMEA_ROW_NOT_FOUND", "risk assessment was not found")
    return json_response(
        status_code=200,
        resource_type="risk_assessment",
        data=assessment_data(assessment),
        headers={"ETag": f'"{assessment.record_version}"'},
    )


@router.post("/rows/{row_id}/risk-proposal-runs")
def start_risk_proposal(
    row_id: str,
    body: RiskProposalBody,
    request: Request,
    access: RiskAccess = Depends(get_risk_access),  # noqa: B008
) -> Response:
    if access.actor.actor_type is not ActorType.HUMAN or not ({"reviewer", "risk_reviewer"} & access.actor.roles):
        raise ReviewError("FMEA_REVIEW_FORBIDDEN", "a human reviewer is required")
    command = StartRiskProposalCommand(
        row_id=row_id,
        expected_record_version=parse_if_match(request),
        evidence_pack_id=body.evidence_pack_id,
        domain_pack_id=body.domain_pack_id,
        domain_pack_version=body.domain_pack_version,
        template_id=body.template_id,
        template_version=body.template_version,
        rule_pack_id=body.rule_pack_id,
        rule_pack_version=body.rule_pack_version,
        idempotency_key=parse_idempotency_key(request),
    )
    assessment = service_call(lambda: access.runtime.risk_service.propose(command, access.model_actor))
    run_id = assessment.assistance_suggestion_id
    if not isinstance(run_id, str) or not run_id:
        raise ReviewError("FMEA_MODEL_SUGGESTION_INVALID", "risk proposal run identity is unavailable")
    data = RiskProposalRunData(run_id=run_id, assessment=assessment_data(assessment))
    return json_response(
        status_code=202,
        resource_type="risk_proposal_run",
        data=data,
        headers={
            "Location": f"/api/v1/fmea/risk-proposal-runs/{run_id}",
            "ETag": f'"{assessment.record_version}"',
        },
    )


@router.get("/risk-proposal-runs/{run_id}")
def get_risk_proposal_run(
    run_id: str,
    access: RiskAccess = Depends(get_risk_access),  # noqa: B008
) -> Response:
    assessment = service_call(lambda: access.runtime.risk_service.get_proposal_run(run_id, access.actor))
    data = RiskProposalRunData(run_id=run_id, assessment=assessment_data(assessment))
    return json_response(
        status_code=200,
        resource_type="risk_proposal_run",
        data=data,
        headers={"ETag": f'"{assessment.record_version}"'},
    )


@router.post("/rows/{row_id}/risk-confirmations")
def confirm_risk(
    row_id: str,
    body: RiskConfirmationBody,
    request: Request,
    access: RiskAccess = Depends(get_risk_access),  # noqa: B008
) -> Response:
    command = ConfirmRiskCommand(
        row_id=row_id,
        proposal_id=body.proposal_id,
        expected_assessment_version=parse_if_match(request),
        idempotency_key=parse_idempotency_key(request),
    )
    _require_human_risk_reviewer(access)
    result = service_call(lambda: access.runtime.risk_service.confirm(command, access.actor))
    return json_response(
        status_code=200,
        resource_type="risk_confirmation",
        data=confirmation_data(result),
        headers={"ETag": f'"{result.assessment.record_version}"'},
    )


@router.post("/rows/{row_id}/risk-rejections")
def reject_risk(
    row_id: str,
    body: RiskRejectionBody,
    request: Request,
    access: RiskAccess = Depends(get_risk_access),  # noqa: B008
) -> Response:
    command = RejectRiskCommand(
        row_id=row_id,
        proposal_id=body.proposal_id,
        expected_assessment_version=parse_if_match(request),
        idempotency_key=parse_idempotency_key(request),
        reason=body.reason,
    )
    _require_human_risk_reviewer(access)
    assessment = service_call(lambda: access.runtime.risk_service.reject(command, access.actor))
    return json_response(
        status_code=200,
        resource_type="risk_assessment",
        data=assessment_data(assessment),
        headers={"ETag": f'"{assessment.record_version}"'},
    )


__all__ = ["assessment_data", "confirmation_data", "router"]
