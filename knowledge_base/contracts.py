"""Versioned M2→M3 hand-off contract and JSON codecs.

The cross-module boundary is JSON.  Python dataclasses are the in-process
representation only; callers must not depend on M3's SQLite schema.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from .models import (
    AssetInput,
    BlockInput,
    DocumentInput,
    DocumentRevision,
    KnowledgeBaseError,
    PageInput,
    ReviewDecision,
    RevisionStatus,
)
from .store import KnowledgeBaseStore

M2_HANDOFF_SCHEMA_VERSION = "power-rag.m2-document.v1"
M3_SNAPSHOT_SCHEMA_VERSION = "power-rag.m3-snapshot.v1"


class M2ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class M2IssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class M2QualityIssue:
    code: str
    message: str
    severity: M2IssueSeverity
    resolved: bool = False
    page_number: int | None = None
    block_id: str | None = None


@dataclass(frozen=True, slots=True)
class M2DocumentHandoff:
    schema_version: str
    document: DocumentInput
    review_status: M2ReviewStatus
    reviewer: str
    reviewed_at: str | None
    review_comment: str
    evidence_coverage: float
    quality_issues: tuple[M2QualityIssue, ...]

    @property
    def unresolved_blocking_issues(self) -> tuple[M2QualityIssue, ...]:
        return tuple(
            issue
            for issue in self.quality_issues
            if issue.severity is M2IssueSeverity.BLOCKING and not issue.resolved
        )


class M2HandoffService:
    """Validate an approved M2 package and preserve its review in M3."""

    def __init__(self, store: KnowledgeBaseStore) -> None:
        self.store = store

    def accept(
        self,
        handoff: M2DocumentHandoff,
        *,
        actor: str,
        chunk_size: int = 800,
        overlap: int = 100,
    ) -> DocumentRevision:
        _validate_ready_handoff(handoff)

        document = replace(
            handoff.document,
            metadata={
                **handoff.document.metadata,
                "m2_handoff": {
                    "schema_version": handoff.schema_version,
                    "review_status": handoff.review_status.value,
                    "reviewer": handoff.reviewer,
                    "reviewed_at": handoff.reviewed_at,
                    "evidence_coverage": handoff.evidence_coverage,
                    "quality_issues": [quality_issue_to_payload(issue) for issue in handoff.quality_issues],
                },
            },
        )
        revision = self.store.create_candidate(
            document,
            created_by=actor,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        if revision.status is RevisionStatus.PUBLISHED and revision.review_decision is ReviewDecision.APPROVED:
            return revision
        if revision.review_decision is ReviewDecision.REJECTED:
            raise KnowledgeBaseError(
                "M3_REVISION_PREVIOUSLY_REJECTED",
                "The same immutable M2 hand-off was rejected in M3; submit corrected content as a new revision.",
            )
        if revision.status is RevisionStatus.CANDIDATE:
            revision = self.store.submit_for_review(revision.revision_id, actor=actor)
        if revision.status is RevisionStatus.PENDING_REVIEW and revision.review_decision is None:
            revision = self.store.record_review(
                revision.revision_id,
                decision=ReviewDecision.APPROVED,
                reviewer=handoff.reviewer,
                comment=handoff.review_comment or "Imported approved M2 review.",
            )
        if revision.review_decision is not ReviewDecision.APPROVED:
            raise KnowledgeBaseError("M3_REVIEW_STATE_INVALID", "M3 could not preserve the approved M2 review state.")
        return revision


def _validate_ready_handoff(handoff: M2DocumentHandoff) -> None:
    if handoff.schema_version != M2_HANDOFF_SCHEMA_VERSION:
        raise KnowledgeBaseError("M2_SCHEMA_UNSUPPORTED", "Unsupported M2 hand-off schema version.")
    if handoff.review_status is not M2ReviewStatus.APPROVED:
        raise KnowledgeBaseError("M2_REVIEW_NOT_APPROVED", "M2 document must be approved before M3 accepts it.")
    if not handoff.reviewer.strip():
        raise KnowledgeBaseError("M2_REVIEWER_MISSING", "Approved M2 document must identify its human reviewer.")
    if handoff.evidence_coverage < 1.0:
        raise KnowledgeBaseError(
            "M2_EVIDENCE_INCOMPLETE", "Every accepted M2 block must retain a source evidence locator."
        )
    if handoff.unresolved_blocking_issues:
        raise KnowledgeBaseError(
            "M2_BLOCKING_ISSUES",
            "M2 document contains unresolved blocking quality issues.",
        )


def document_from_payload(payload: Mapping[str, Any]) -> DocumentInput:
    value = _mapping(payload, "document")
    pages_value = _sequence(value.get("pages"), "document.pages")
    pages: list[PageInput] = []
    for page_index, raw_page in enumerate(pages_value):
        page = _mapping(raw_page, f"document.pages[{page_index}]")
        blocks_value = _sequence(page.get("blocks"), f"document.pages[{page_index}].blocks")
        blocks: list[BlockInput] = []
        for block_index, raw_block in enumerate(blocks_value):
            block = _mapping(raw_block, f"document.pages[{page_index}].blocks[{block_index}]")
            blocks.append(
                BlockInput(
                    text=_string(block.get("text"), "block.text"),
                    block_type=_optional_string(block.get("block_type")) or "paragraph",
                    ordinal=_integer(block.get("ordinal", block_index), "block.ordinal"),
                    block_id=_optional_string(block.get("block_id")),
                    parent_block_id=_optional_string(block.get("parent_block_id")),
                    metadata=_metadata(block.get("metadata"), "block.metadata"),
                )
            )
        pages.append(
            PageInput(
                page_number=_integer(page.get("page_number"), "page.page_number"),
                blocks=tuple(blocks),
                metadata=_metadata(page.get("metadata"), "page.metadata"),
            )
        )

    assets: list[AssetInput] = []
    for asset_index, raw_asset in enumerate(_sequence(value.get("assets", []), "document.assets")):
        asset = _mapping(raw_asset, f"document.assets[{asset_index}]")
        assets.append(
            AssetInput(
                asset_type=_string(asset.get("asset_type"), "asset.asset_type"),
                page_number=_integer(asset.get("page_number"), "asset.page_number"),
                uri=_string(asset.get("uri"), "asset.uri"),
                caption=_optional_string(asset.get("caption")) or "",
                block_id=_optional_string(asset.get("block_id")),
                checksum=_optional_string(asset.get("checksum")),
                metadata=_metadata(asset.get("metadata"), "asset.metadata"),
            )
        )
    return DocumentInput(
        document_id=_string(value.get("document_id"), "document.document_id"),
        title=_string(value.get("title"), "document.title"),
        source_uri=_string(value.get("source_uri"), "document.source_uri"),
        pages=tuple(pages),
        media_type=_optional_string(value.get("media_type")) or "text/plain",
        assets=tuple(assets),
        metadata=_metadata(value.get("metadata"), "document.metadata"),
    )


def m2_handoff_from_payload(payload: Mapping[str, Any]) -> M2DocumentHandoff:
    value = _mapping(payload, "handoff")
    schema_version = _string(value.get("schema_version"), "schema_version")
    review = _mapping(value.get("review"), "review")
    quality = _mapping(value.get("quality"), "quality")
    status_value = _string(review.get("status"), "review.status")
    try:
        review_status = M2ReviewStatus(status_value)
    except ValueError as exc:
        raise ValueError("review.status must be pending, approved, or rejected") from exc
    issues: list[M2QualityIssue] = []
    for issue_index, raw_issue in enumerate(_sequence(quality.get("issues", []), "quality.issues")):
        issue = _mapping(raw_issue, f"quality.issues[{issue_index}]")
        severity_value = _optional_string(issue.get("severity")) or M2IssueSeverity.WARNING.value
        try:
            severity = M2IssueSeverity(severity_value)
        except ValueError as exc:
            raise ValueError("quality issue severity must be info, warning, or blocking") from exc
        resolved = issue.get("resolved", False)
        if not isinstance(resolved, bool):
            raise TypeError("quality issue resolved must be a boolean")
        page_number = issue.get("page_number")
        issues.append(
            M2QualityIssue(
                code=_string(issue.get("code"), "quality issue code"),
                message=_string(issue.get("message"), "quality issue message"),
                severity=severity,
                resolved=resolved,
                page_number=None if page_number is None else _integer(page_number, "quality issue page_number"),
                block_id=_optional_string(issue.get("block_id")),
            )
        )
    coverage = quality.get("evidence_coverage")
    if isinstance(coverage, bool) or not isinstance(coverage, int | float):
        raise TypeError("quality.evidence_coverage must be a number")
    evidence_coverage = float(coverage)
    if not 0.0 <= evidence_coverage <= 1.0:
        raise ValueError("quality.evidence_coverage must be between 0 and 1")
    handoff = M2DocumentHandoff(
        schema_version=schema_version,
        document=document_from_payload(_mapping(value.get("document"), "document")),
        review_status=review_status,
        reviewer=_optional_string(review.get("reviewer")) or "",
        reviewed_at=_optional_string(review.get("reviewed_at")),
        review_comment=_optional_string(review.get("comment")) or "",
        evidence_coverage=evidence_coverage,
        quality_issues=tuple(issues),
    )
    if handoff.review_status is M2ReviewStatus.APPROVED and not handoff.reviewer:
        raise ValueError("review.reviewer is required when review.status is approved")
    return handoff


def quality_issue_to_payload(issue: M2QualityIssue) -> dict[str, Any]:
    return {
        "code": issue.code,
        "message": issue.message,
        "severity": issue.severity.value,
        "resolved": issue.resolved,
        "page_number": issue.page_number,
        "block_id": issue.block_id,
    }


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a JSON object")
    return value


def _sequence(value: Any, field_name: str) -> Sequence[Any]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a JSON array")
    return value


def _string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("optional string field must be a string or null")
    value = value.strip()
    return value or None


def _integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    return value


def _metadata(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    return dict(_mapping(value, field_name))


__all__ = [
    "M2_HANDOFF_SCHEMA_VERSION",
    "M3_SNAPSHOT_SCHEMA_VERSION",
    "M2DocumentHandoff",
    "M2HandoffService",
    "M2IssueSeverity",
    "M2QualityIssue",
    "M2ReviewStatus",
    "document_from_payload",
    "m2_handoff_from_payload",
]
