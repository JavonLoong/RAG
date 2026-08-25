from __future__ import annotations

from typing import TYPE_CHECKING

from core_domain.query_contracts import (
    CitationType,
    EvidenceSelectionProfile,
    citation_type_for_source_type,
    validate_resolved_evidence_types,
)

from .entities import FmeaRow
from .errors import FmeaDomainError
from .propagation import RISK_PRIORITIES, PropagationRelation
from .states import (
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
)
from .value_objects import EvidencePack

if TYPE_CHECKING:
    from .propagation import PropagationEdge

_EVIDENCE_FIELDS = frozenset(
    {
        "item_id",
        "function_id",
        "failure_mode",
        "causes",
        "mechanisms",
        "effects",
        "symptoms",
        "controls",
        "barriers",
        "actions",
    }
)

_REVIEW_EDGES = {
    ReviewStatus.DRAFT: {ReviewStatus.SUGGESTED, ReviewStatus.IN_REVIEW, ReviewStatus.REJECTED},
    ReviewStatus.SUGGESTED: {ReviewStatus.IN_REVIEW, ReviewStatus.ACCEPTED, ReviewStatus.REJECTED},
    ReviewStatus.IN_REVIEW: {ReviewStatus.IN_REVIEW, ReviewStatus.ACCEPTED, ReviewStatus.REJECTED},
    ReviewStatus.ACCEPTED: {ReviewStatus.SUPERSEDED},
    ReviewStatus.REJECTED: {ReviewStatus.SUPERSEDED},
    ReviewStatus.SUPERSEDED: set(),
}

_PROPAGATION_RELATION_TYPES = frozenset(item.value for item in PropagationRelation)


def validate_propagation_relation(relation_type: str) -> None:
    if relation_type not in _PROPAGATION_RELATION_TYPES:
        raise FmeaDomainError(f"unknown propagation relation_type: {relation_type}")  # noqa: TRY003


def validate_propagation_edge(edge: PropagationEdge, pack: EvidencePack | None) -> None:
    validate_propagation_relation(edge.relation_type)
    if edge.path_length < 1:
        raise FmeaDomainError("path_length must be at least 1")  # noqa: TRY003
    if edge.risk_priority is not None and edge.risk_priority not in RISK_PRIORITIES:
        raise FmeaDomainError(f"unknown risk_priority: {edge.risk_priority}")  # noqa: TRY003
    if pack is None:
        return

    if edge.evidence_pack_id != pack.pack_id:
        raise FmeaDomainError("edge evidence_pack_id does not match supplied EvidencePack")  # noqa: TRY003

    pack_evidence_ids = {ref.evidence_id for ref in pack.refs}
    for evidence_id in edge.evidence_ids:
        if evidence_id not in pack_evidence_ids:
            raise FmeaDomainError(f"evidence ID {evidence_id} is absent from EvidencePack")  # noqa: TRY003


def _validate_field_names(bindings: tuple[tuple[str, object], ...]) -> set[str]:
    field_names: set[str] = set()
    for field_name, _ in bindings:
        if field_name not in _EVIDENCE_FIELDS:
            raise FmeaDomainError(f"unknown field name: {field_name}")  # noqa: TRY003
        if field_name in field_names:
            raise FmeaDomainError(f"duplicate field name: {field_name}")  # noqa: TRY003
        field_names.add(field_name)
    return field_names


def validate_row_evidence(  # noqa: C901
    row: FmeaRow,
    pack: EvidencePack,
    *,
    resolved_profile: EvidenceSelectionProfile | None = None,
    evidence_types: tuple[CitationType, ...] | None = None,
    retrieval_incomplete: bool = False,
) -> None:
    if row.evidence_pack_id != pack.pack_id:
        raise FmeaDomainError("row evidence_pack_id does not match supplied EvidencePack")  # noqa: TRY003

    evidence_fields = _validate_field_names(row.field_evidence)
    support_fields = _validate_field_names(row.field_support)
    if evidence_fields != support_fields:
        raise FmeaDomainError("field_evidence and field_support must bind the same fields")  # noqa: TRY003

    pack_evidence_ids = {ref.evidence_id for ref in pack.refs}
    for _, evidence_ids in row.field_evidence:
        for evidence_id in evidence_ids:
            if evidence_id not in pack_evidence_ids:
                raise FmeaDomainError(f"evidence ID {evidence_id} is absent from EvidencePack")  # noqa: TRY003

    if row.claim_status is ClaimStatus.KNOWN:
        if not any(evidence_ids for _, evidence_ids in row.field_evidence):
            raise FmeaDomainError("known claim requires evidence")  # noqa: TRY003
        unsupported = {EvidenceSupportStatus.CONTRADICTED, EvidenceSupportStatus.NOT_SUPPORTED}
        if any(status in unsupported for _, status in row.field_support):
            raise FmeaDomainError("known claim cannot use contradicted or not_supported evidence")  # noqa: TRY003

    if (resolved_profile is None) != (evidence_types is None):
        raise FmeaDomainError("resolved profile and evidence types must be supplied together")  # noqa: TRY003
    if resolved_profile is not None and evidence_types is not None:
        try:
            allowed = validate_resolved_evidence_types(
                resolved_profile,
                evidence_types,
                allow_subset=retrieval_incomplete,
                allow_empty=retrieval_incomplete,
            )
        except ValueError as exc:
            raise FmeaDomainError("evidence profile and evidence types are inconsistent") from exc  # noqa: TRY003
        observed: set[CitationType] = set()
        for ref in pack.refs:
            citation_type = citation_type_for_source_type(ref.source_type)
            if citation_type is None:
                raise FmeaDomainError("EvidencePack contains an unmapped evidence source type")  # noqa: TRY003
            observed.add(citation_type)
        if not observed.issubset(set(allowed)):
            raise FmeaDomainError("EvidencePack contains evidence outside the resolved profile")  # noqa: TRY003
        if not retrieval_incomplete and observed != set(evidence_types):
            raise FmeaDomainError("EvidencePack types do not match the resolved evidence types")  # noqa: TRY003


def validate_review_transition(
    *, current: ReviewStatus, requested: ReviewStatus, actor_type: ActorType
) -> None:
    if requested not in _REVIEW_EDGES[current]:
        raise FmeaDomainError(f"invalid review transition: {current.value}->{requested.value}")  # noqa: TRY003
    if requested in {ReviewStatus.IN_REVIEW, ReviewStatus.ACCEPTED, ReviewStatus.REJECTED} and actor_type is not ActorType.HUMAN:
        raise FmeaDomainError("review decision requires a human actor")  # noqa: TRY003


def validate_publication_transition(
    *, current: PublicationStatus, requested: PublicationStatus, actor_type: ActorType
) -> None:
    allowed = {
        PublicationStatus.UNPUBLISHED: {PublicationStatus.PUBLISHED},
        PublicationStatus.PUBLISHED: {PublicationStatus.WITHDRAWN},
        PublicationStatus.WITHDRAWN: set(),
    }
    if requested not in allowed[current]:
        raise FmeaDomainError(f"invalid publication transition: {current.value}->{requested.value}")  # noqa: TRY003
    if requested in {PublicationStatus.PUBLISHED, PublicationStatus.WITHDRAWN} and actor_type is not ActorType.HUMAN:
        raise FmeaDomainError("publication change requires a human actor")  # noqa: TRY003
