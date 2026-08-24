from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .states import ClaimStatus, EvidenceSupportStatus, PublicationStatus, ReviewStatus
from .value_objects import EvidencePack


class PropagationRelation(str, Enum):
    PROPAGATION = "propagation"
    COMMON_CAUSE = "common_cause"
    DEPENDENCY = "dependency"
    FEEDBACK = "feedback"


RISK_PRIORITIES = frozenset({"normal", "medium", "high", "critical"})
AUTO_ACCEPT_RISK_PRIORITIES = frozenset({"normal", "medium"})


@dataclass(frozen=True, slots=True)
class PropagationEdge:
    edge_id: str
    analysis_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    interface_variable: str
    unit: str
    direction: str
    threshold: str | None
    operating_modes: tuple[str, ...]
    delay_ms: int | None
    response_time_ms: int | None
    fault_tolerance_time_ms: int | None
    barrier_ids: tuple[str, ...]
    evidence_pack_id: str
    evidence_ids: tuple[str, ...]
    evidence_support: EvidenceSupportStatus
    claim_status: ClaimStatus
    review_status: ReviewStatus
    publication_status: PublicationStatus
    path_length: int
    is_cyclic: bool
    is_unprocessed: bool
    is_external: bool
    is_terminal: bool
    risk_priority: str | None
    record_version: int = 1

    @property
    def inferred(self) -> bool:
        return self.path_length > 2

    @property
    def auto_accept_allowed(self) -> bool:
        return (
            self.path_length in {1, 2}
            and not self.is_cyclic
            and not self.is_unprocessed
            and not self.is_external
            and bool(self.evidence_ids)
            and self.evidence_support in {
                EvidenceSupportStatus.SUPPORTED,
                EvidenceSupportStatus.PARTIALLY_SUPPORTED,
            }
            and self.claim_status is ClaimStatus.KNOWN
            and self.risk_priority in AUTO_ACCEPT_RISK_PRIORITIES
        )


def validate_propagation_edge(edge: PropagationEdge, pack: EvidencePack | None) -> None:
    from .policies import validate_propagation_edge as validate_edge

    validate_edge(edge, pack)
