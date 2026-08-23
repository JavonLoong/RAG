from __future__ import annotations

from .entities import FmeaRow
from .errors import FmeaDomainError
from .states import (
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
)
from .value_objects import EvidencePack

_EVIDENCE_FIELDS = frozenset(
    {
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
    ReviewStatus.IN_REVIEW: {ReviewStatus.ACCEPTED, ReviewStatus.REJECTED},
    ReviewStatus.ACCEPTED: {ReviewStatus.SUPERSEDED},
    ReviewStatus.REJECTED: {ReviewStatus.DRAFT, ReviewStatus.SUPERSEDED},
    ReviewStatus.SUPERSEDED: set(),
}


def _validate_field_names(bindings: tuple[tuple[str, object], ...]) -> set[str]:
    field_names: set[str] = set()
    for field_name, _ in bindings:
        if field_name not in _EVIDENCE_FIELDS:
            raise FmeaDomainError(f"unknown field name: {field_name}")  # noqa: TRY003
        if field_name in field_names:
            raise FmeaDomainError(f"duplicate field name: {field_name}")  # noqa: TRY003
        field_names.add(field_name)
    return field_names


def validate_row_evidence(row: FmeaRow, pack: EvidencePack) -> None:
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


def validate_review_transition(
    *, current: ReviewStatus, requested: ReviewStatus, actor_type: ActorType
) -> None:
    if requested not in _REVIEW_EDGES[current]:
        raise FmeaDomainError(f"invalid review transition: {current.value}->{requested.value}")  # noqa: TRY003
    if requested is ReviewStatus.ACCEPTED and actor_type is not ActorType.HUMAN:
        raise FmeaDomainError("accepted requires a human actor")  # noqa: TRY003


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
