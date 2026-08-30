"""Strict, bounded HTTP contracts for FMEA propagation resources."""

# Pydantic validators expose concise messages that the shared HTTP adapter
# redacts into stable public problem details.
# ruff: noqa: TRY003

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator

from core_domain.fmea.states import (
    ClaimStatus,
    EvidenceSupportStatus,
    PropagationStatus,
    PublicationStatus,
    ReviewStatus,
    RunStatus,
)

from .fmea_review_contracts import HistoryPage

_ID_MAX = 128
_VERSION_MAX = 64
_REASON_MAX = 4096
_ISSUE_MAX = 64
_MAX_EDGES = 40


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PropagationStartBody(_StrictRequest):
    """Client-owned row and evidence references; resource packs stay server-owned."""

    source_row_ids: list[StrictStr] = Field(min_length=1, max_length=_MAX_EDGES)
    evidence_pack_id: StrictStr = Field(min_length=1, max_length=_ID_MAX)

    @property
    def record_version(self) -> int:
        """Compatibility projection; the write precondition is the If-Match header."""

        return 1

    @field_validator("source_row_ids")
    @classmethod
    def _unique_source_rows(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized) or len(normalized) != len(set(normalized)):
            raise ValueError("source_row_ids must contain unique non-empty IDs")
        return normalized


class PropagationEdgeDecisionBody(_StrictRequest):
    edge_id: StrictStr = Field(min_length=1, max_length=_ID_MAX)
    action: Literal["accept", "reject"]
    reason: StrictStr = Field(min_length=1, max_length=_REASON_MAX)


class PropagationReviewBody(_StrictRequest):
    edge_decisions: list[PropagationEdgeDecisionBody] = Field(min_length=1, max_length=_MAX_EDGES)
    acknowledgements: list[StrictStr] = Field(default_factory=list, max_length=16)

    @field_validator("acknowledgements")
    @classmethod
    def _unique_acknowledgements(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item or len(item) > _ISSUE_MAX for item in normalized):
            raise ValueError("acknowledgements must contain bounded non-empty issue codes")
        if len(normalized) != len(set(normalized)):
            raise ValueError("acknowledgements must be unique")
        return normalized


class PropagationNodeData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(max_length=_ID_MAX)
    node_type: str = Field(max_length=_ID_MAX)
    operating_modes: list[str] = Field(max_length=16)


class PropagationEdgeData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_id: str = Field(max_length=_ID_MAX)
    analysis_id: str = Field(max_length=_ID_MAX)
    source_entity_id: str = Field(max_length=_ID_MAX)
    target_entity_id: str = Field(max_length=_ID_MAX)
    relation_type: str = Field(max_length=_ID_MAX)
    interface_variable: str = Field(max_length=_ID_MAX)
    unit: str = Field(max_length=_ID_MAX)
    direction: str = Field(max_length=_ID_MAX)
    threshold: str | None = Field(default=None, max_length=_REASON_MAX)
    operating_modes: list[str] = Field(max_length=16)
    delay_ms: int | None = None
    response_time_ms: int | None = None
    fault_tolerance_time_ms: int | None = None
    barrier_ids: list[str] = Field(max_length=_MAX_EDGES)
    evidence_pack_id: str = Field(max_length=_ID_MAX)
    evidence_ids: list[str] = Field(max_length=64)
    evidence_support: EvidenceSupportStatus
    claim_status: ClaimStatus
    review_status: ReviewStatus
    publication_status: PublicationStatus
    path_length: StrictInt = Field(ge=1, le=40)
    is_cyclic: StrictBool
    is_unprocessed: StrictBool
    is_external: StrictBool
    is_terminal: StrictBool
    risk_priority: str | None = Field(default=None, max_length=_ID_MAX)
    record_version: StrictInt = Field(ge=1)


class PropagationPathData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path_id: str = Field(max_length=_ID_MAX)
    analysis_id: str = Field(max_length=_ID_MAX)
    source_entity_id: str = Field(max_length=_ID_MAX)
    target_entity_id: str = Field(max_length=_ID_MAX)
    edges: list[PropagationEdgeData] = Field(min_length=1, max_length=_MAX_EDGES)
    path_length: StrictInt = Field(ge=1, le=40)
    is_cyclic: StrictBool
    requires_human_review: StrictBool


class PropagationGraphData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph_revision_id: str = Field(max_length=_ID_MAX)
    workspace_id: str = Field(max_length=_ID_MAX)
    analysis_id: str = Field(max_length=_ID_MAX)
    analysis_record_version: StrictInt = Field(ge=1)
    topology_snapshot_id: str = Field(max_length=_ID_MAX)
    topology_hash: str = Field(max_length=128)
    evidence_pack_ids: list[str] = Field(max_length=64)
    domain_pack_id: str = Field(max_length=_ID_MAX)
    domain_pack_version: str = Field(max_length=_VERSION_MAX)
    rule_pack_id: str = Field(max_length=_ID_MAX)
    rule_pack_version: str = Field(max_length=_VERSION_MAX)
    status: PropagationStatus
    assistance_suggestion_ids: list[str] = Field(max_length=64)
    nodes: list[PropagationNodeData] = Field(max_length=_MAX_EDGES)
    edges: list[PropagationEdgeData] = Field(max_length=_MAX_EDGES)
    paths: list[PropagationPathData] = Field(max_length=_MAX_EDGES)
    unresolved_issue_codes: list[str] = Field(max_length=16)
    parent_graph_revision_id: str | None = Field(default=None, max_length=_ID_MAX)
    record_version: StrictInt = Field(ge=1)
    created_at: str = Field(max_length=128)


class PropagationRunData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(max_length=_ID_MAX)
    workspace_id: str = Field(max_length=_ID_MAX)
    analysis_id: str = Field(max_length=_ID_MAX)
    status: RunStatus
    graph: PropagationGraphData | None
    error_code: str | None = Field(default=None, max_length=_ID_MAX)
    assistance_suggestion_ids: list[str] = Field(max_length=64)
    created_at: str = Field(max_length=128)
    updated_at: str = Field(max_length=128)


class PropagationReviewResultData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph: PropagationGraphData
    decision_id: str = Field(max_length=_ID_MAX)
    audit_event_id: str = Field(max_length=_ID_MAX)
    outbox_event_id: str = Field(max_length=_ID_MAX)
    replayed: StrictBool
    persisted: StrictBool


PropagationRunBody = PropagationStartBody
GraphReviewBody = PropagationReviewBody
EdgeDecisionBody = PropagationEdgeDecisionBody
PropagationPathPage = HistoryPage[PropagationPathData]


__all__ = [
    "EdgeDecisionBody",
    "GraphReviewBody",
    "PropagationEdgeData",
    "PropagationEdgeDecisionBody",
    "PropagationGraphData",
    "PropagationNodeData",
    "PropagationPathData",
    "PropagationPathPage",
    "PropagationReviewBody",
    "PropagationReviewResultData",
    "PropagationRunBody",
    "PropagationRunData",
    "PropagationStartBody",
]
