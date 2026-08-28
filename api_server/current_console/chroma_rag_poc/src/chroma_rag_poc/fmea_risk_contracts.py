"""Strict HTTP request contracts for FMEA risk proposal and review."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from core_domain.fmea.states import RiskStatus

from .fmea_review_contracts import RiskAssessmentData


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RiskProposalBody(_StrictRequest):
    evidence_pack_id: StrictStr
    domain_pack_id: StrictStr
    domain_pack_version: StrictStr
    template_id: StrictStr
    template_version: StrictStr
    rule_pack_id: StrictStr
    rule_pack_version: StrictStr


class RiskConfirmationBody(_StrictRequest):
    proposal_id: StrictStr


class RiskRejectionBody(_StrictRequest):
    proposal_id: StrictStr
    reason: StrictStr = Field(max_length=4096)


class RiskDimensionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: int | None
    evidence_ids: list[str]
    reason: str
    uncertainty: str | None


class RiskAssessmentRecordData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_id: str
    workspace_id: str
    row_id: str
    source_record_version: StrictInt
    evidence_pack_id: str
    domain_pack_id: str
    domain_pack_version: str
    rule_pack_id: str
    rule_pack_version: str
    status: RiskStatus
    dimensions: list[RiskDimensionData]
    derived: RiskAssessmentData | None
    proposal_id: str | None
    assistance_suggestion_id: str | None
    confirmer_actor_id: str | None
    invalidated_reason: str | None
    record_version: StrictInt
    created_at: str
    updated_at: str


class RiskProposalRunData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: Literal["succeeded"] = "succeeded"
    assessment: RiskAssessmentRecordData


class RiskConfirmationResultData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment: RiskAssessmentRecordData
    decision_id: str
    audit_event_id: str
    outbox_event_id: str
    replayed: StrictBool
    persisted: StrictBool


__all__ = [
    "RiskAssessmentRecordData",
    "RiskConfirmationBody",
    "RiskConfirmationResultData",
    "RiskDimensionData",
    "RiskProposalBody",
    "RiskProposalRunData",
    "RiskRejectionBody",
]
