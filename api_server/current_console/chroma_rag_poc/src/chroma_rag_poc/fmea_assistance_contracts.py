"""Strict HTTP request contracts for FMEA model assistance."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator

from core_domain.fmea.states import ActorType
from fmea_application.assistance_contracts import AssistanceDecisionAction, AssistanceKind


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AnalysisScopeRunBody(_StrictRequest):
    target_id: StrictStr
    target_record_version: StrictInt = Field(ge=1)
    evidence_pack_ids: list[StrictStr] = Field(min_length=1, max_length=16)
    payload: dict[StrictStr, Any]
    domain_pack_id: StrictStr
    domain_pack_version: StrictStr
    template_id: StrictStr
    template_version: StrictStr
    rule_pack_id: StrictStr
    rule_pack_version: StrictStr


class AssistanceEditBody(_StrictRequest):
    field: StrictStr
    value: Any


class AssistanceDecisionBody(_StrictRequest):
    action: AssistanceDecisionAction
    target_record_version: StrictInt = Field(ge=1)
    reason: StrictStr
    edits: list[AssistanceEditBody] = Field(default_factory=list, max_length=32)

    @field_validator("action", mode="before")
    @classmethod
    def _parse_action(cls, value: object) -> AssistanceDecisionAction:
        return value if isinstance(value, AssistanceDecisionAction) else AssistanceDecisionAction(value)


class AssistanceSuggestionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_id: str
    kind: AssistanceKind
    workspace_id: str
    target_type: str
    target_id: str
    target_record_version: StrictInt
    evidence_pack_ids: list[str]
    payload: Any
    evidence_ids: list[str]
    conflict_ids: list[str]
    uncertainty: str | None
    model_hash: str
    prompt_hash: str
    run_id: str
    trace_id: str
    domain_pack_id: str | None
    domain_pack_version: str | None
    template_id: str | None
    template_version: str | None
    rule_pack_id: str | None
    rule_pack_version: str | None
    record_version: StrictInt
    created_at: str
    applied: StrictBool
    suggestion_hash: str


class AssistanceDecisionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    suggestion_id: str
    suggestion_hash: str
    suggestion_record_version: StrictInt
    target_record_version: StrictInt
    action: AssistanceDecisionAction
    actor_id: str
    actor_type: ActorType
    edits: list[list[Any]]
    reason: str
    resulting_resource_identity: list[str] | None
    created_at: str


__all__ = [
    "AnalysisScopeRunBody",
    "AssistanceDecisionBody",
    "AssistanceDecisionData",
    "AssistanceEditBody",
    "AssistanceSuggestionData",
]
