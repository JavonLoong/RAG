"""Strict, versioned HTTP contracts for the FMEA review adapter."""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator

from core_domain.fmea.states import ClaimStatus, EvidenceSupportStatus, PublicationStatus, ReviewStatus, RunStatus
from fmea_application.review_contracts import ReviewAction, ReviewPriority, ReviewReasonCode


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class StartSuggestionBody(_StrictRequest):
    review_policy: Literal["default"] = "default"
    focus_fields: list[StrictStr] = Field(default_factory=list, max_length=16)


class FieldReviewEditBody(_StrictRequest):
    target_field: StrictStr
    operation: Literal["replace"]
    value: StrictStr | list[StrictStr]
    claim_status: ClaimStatus
    support_status: EvidenceSupportStatus
    evidence_ids: list[StrictStr] = Field(default_factory=list, max_length=64)
    reason: StrictStr

    @field_validator("claim_status", mode="before")
    @classmethod
    def _parse_claim_status(cls, value: object) -> ClaimStatus:
        return value if isinstance(value, ClaimStatus) else ClaimStatus(value)

    @field_validator("support_status", mode="before")
    @classmethod
    def _parse_support_status(cls, value: object) -> EvidenceSupportStatus:
        return value if isinstance(value, EvidenceSupportStatus) else EvidenceSupportStatus(value)


class EvidenceRequestBody(_StrictRequest):
    target_field: StrictStr
    question: StrictStr
    preferred_source_types: list[StrictStr] = Field(default_factory=list, max_length=16)
    priority: ReviewPriority = ReviewPriority.NORMAL

    @field_validator("priority", mode="before")
    @classmethod
    def _parse_priority(cls, value: object) -> ReviewPriority:
        return value if isinstance(value, ReviewPriority) else ReviewPriority(value)


class UnresolvedAcknowledgementBody(_StrictRequest):
    target_field: StrictStr
    claim_status: ClaimStatus
    reason: StrictStr

    @field_validator("claim_status", mode="before")
    @classmethod
    def _parse_claim_status(cls, value: object) -> ClaimStatus:
        return value if isinstance(value, ClaimStatus) else ClaimStatus(value)


class ReviewDecisionBody(_StrictRequest):
    action: ReviewAction
    suggestion_id: StrictStr | None = None
    reason_code: ReviewReasonCode
    reason: StrictStr
    edits: list[FieldReviewEditBody] = Field(default_factory=list, max_length=8)
    evidence_requests: list[EvidenceRequestBody] = Field(default_factory=list, max_length=16)
    unresolved_acknowledgements: list[UnresolvedAcknowledgementBody] = Field(default_factory=list, max_length=16)

    @field_validator("action", mode="before")
    @classmethod
    def _parse_action(cls, value: object) -> ReviewAction:
        return value if isinstance(value, ReviewAction) else ReviewAction(value)

    @field_validator("reason_code", mode="before")
    @classmethod
    def _parse_reason_code(cls, value: object) -> ReviewReasonCode:
        return value if isinstance(value, ReviewReasonCode) else ReviewReasonCode(value)


class FmeaIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_id: str
    item_id: str
    function_id: str
    item_label: str
    function_label: str


class RiskAssessmentData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity_by_consequence_class: list[list[str | int | None]]
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
    evidence_ids: list[str]


class FmeaRowData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_id: str
    analysis_id: str
    evidence_pack_id: str
    item_id: str
    function_id: str
    failure_mode: str
    causes: list[str]
    mechanisms: list[str]
    effects: list[str]
    symptoms: list[str]
    controls: list[str]
    barriers: list[str]
    actions: list[str]
    risk_assessment: RiskAssessmentData | None
    claim_status: ClaimStatus
    review_status: ReviewStatus
    publication_status: PublicationStatus
    record_version: StrictInt


class FieldReviewData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_field: str
    value: str | list[str]
    claim_status: ClaimStatus
    support_status: EvidenceSupportStatus
    evidence_ids: list[str]
    last_decision_id: str | None


class EvidenceRefData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_type: str
    source_trust: str
    is_primary: StrictBool
    locator: str
    quote: str


class EvidenceData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id: str
    pack_hash: str
    expires_at: str | None
    refs: list[EvidenceRefData]


class RetrievalData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_profile: str
    resolved_profile: str
    evidence_types: list[str]
    trace_id: str
    warnings: list[str]
    incomplete: StrictBool


class FieldFindingData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_field: str
    judgement: str
    recommended_claim_status: ClaimStatus
    evidence_ids: list[str]
    rationale: str


class FieldEditData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_field: str
    operation: Literal["replace"]
    value: str | list[str]
    claim_status: ClaimStatus
    support_status: EvidenceSupportStatus
    evidence_ids: list[str]
    reason: str


class EvidenceRequestData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_field: str
    question: str
    preferred_source_types: list[str]
    priority: ReviewPriority


class MissingEvidenceData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_field: str
    description: str


class ConflictData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_field: str
    evidence_ids: list[str]
    description: str


class UnresolvedAcknowledgementData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_field: str
    claim_status: ClaimStatus
    reason: str


class ModelManifestData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    template_id: str
    template_version: str


class SuggestionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_id: str
    run_id: str
    row_id: str
    source_record_version: StrictInt
    recommended_action: ReviewAction
    field_findings: list[FieldFindingData]
    proposed_edits: list[FieldEditData]
    evidence_requests: list[EvidenceRequestData]
    missing_evidence: list[MissingEvidenceData]
    conflicts: list[ConflictData]
    rationale: str
    model_manifest: ModelManifestData
    applied: StrictBool
    stale: StrictBool
    created_at: str


class DecisionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    row_id: str
    previous_record_version: StrictInt
    record_version: StrictInt
    actor_id: str
    action: ReviewAction
    suggestion_id: str | None
    reason_code: ReviewReasonCode
    reason: str
    edits: list[FieldEditData]
    evidence_requests: list[EvidenceRequestData]
    unresolved_acknowledgements: list[UnresolvedAcknowledgementData]
    created_at: str


class ReviewRunData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    row_id: str
    source_record_version: StrictInt
    status: RunStatus
    suggestion_id: str | None
    error_code: str | None
    retryable: StrictBool
    request_id: str
    trace_id: str
    created_at: str
    started_at: str | None
    finished_at: str | None


class ReviewContextData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: FmeaIdentity
    row: FmeaRowData
    reviewability: StrictBool
    field_reviews: list[FieldReviewData]
    evidence: EvidenceData
    retrieval: RetrievalData
    latest_suggestion: SuggestionData | None
    decision_history: list[DecisionData]
    warnings: list[str]


class ReviewDecisionResultData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    row: FmeaRowData
    previous_record_version: StrictInt
    record_version: StrictInt
    review_status: ReviewStatus
    publication_status: PublicationStatus
    audit_event_id: str
    suggestion_id: str | None
    evidence_requests: list[EvidenceRequestData]
    persisted: StrictBool


T = TypeVar("T")


class HistoryPage(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")

    items: list[T]
    next_cursor: str | None
    limit: StrictInt


class FmeaEnvelope(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["graphrag.fmea.v1"] = "graphrag.fmea.v1"
    resource_type: str
    resource_version: Literal["1.0.0"] = "1.0.0"
    request_id: str
    trace_id: str
    data: T


class FmeaProblem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    status: int
    code: str
    detail: str
    trace_id: str
    retryable: bool
    errors: list[dict[str, object]] = Field(default_factory=list)


__all__ = [
    "ConflictData",
    "DecisionData",
    "EvidenceData",
    "EvidenceRefData",
    "EvidenceRequestBody",
    "EvidenceRequestData",
    "FieldEditData",
    "FieldFindingData",
    "FieldReviewData",
    "FieldReviewEditBody",
    "FmeaEnvelope",
    "FmeaIdentity",
    "FmeaProblem",
    "FmeaRowData",
    "HistoryPage",
    "MissingEvidenceData",
    "ModelManifestData",
    "RetrievalData",
    "ReviewContextData",
    "ReviewDecisionBody",
    "ReviewDecisionResultData",
    "ReviewRunData",
    "RiskAssessmentData",
    "StartSuggestionBody",
    "SuggestionData",
    "UnresolvedAcknowledgementBody",
    "UnresolvedAcknowledgementData",
]
