from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scoring import RiskAssessment

from .states import ClaimStatus, EvidenceSupportStatus, PublicationStatus, ReviewStatus
from .value_objects import VersionSet


@dataclass(frozen=True, slots=True)
class FmeaAnalysis:
    analysis_id: str
    project_id: str
    analysis_type: str
    lifecycle_stage: str
    scope: str
    system_boundary: str
    exclusions: tuple[str, ...]
    equipment_configuration: str
    control_software_version: str
    fuel_type: str
    operating_modes: tuple[str, ...]
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]
    unanalysed_parts: tuple[str, ...]
    versions: VersionSet
    owner_actor_id: str
    reviewer_actor_ids: tuple[str, ...]
    approver_actor_id: str | None
    approved_at: str | None
    parent_revision_id: str | None
    current_revision_id: str | None
    record_version: int = 1


@dataclass(frozen=True, slots=True)
class FmeaRow:
    row_id: str
    analysis_id: str
    evidence_pack_id: str
    item_id: str
    function_id: str
    failure_mode: str
    causes: tuple[str, ...]
    mechanisms: tuple[str, ...]
    effects: tuple[str, ...]
    symptoms: tuple[str, ...]
    controls: tuple[str, ...]
    barriers: tuple[str, ...]
    actions: tuple[str, ...]
    risk_assessment: RiskAssessment | None
    field_evidence: tuple[tuple[str, tuple[str, ...]], ...]
    field_support: tuple[tuple[str, EvidenceSupportStatus], ...]
    claim_status: ClaimStatus
    review_status: ReviewStatus
    publication_status: PublicationStatus
    record_version: int = 1
