"""Domain contracts for the versioned normative knowledge base.

The models in this module deliberately have no database or model-provider
dependency.  They are the hand-off contract between M2, M3, M4, and M6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class KnowledgeBaseError(RuntimeError):
    """Base error carrying a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RevisionStatus(str, Enum):
    CANDIDATE = "candidate"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class ReviewDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class SearchMode(str, Enum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class BlockInput:
    text: str
    block_type: str = "paragraph"
    ordinal: int = 0
    block_id: str | None = None
    parent_block_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PageInput:
    page_number: int
    blocks: tuple[BlockInput, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AssetInput:
    asset_type: str
    page_number: int
    uri: str
    caption: str = ""
    block_id: str | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DocumentInput:
    document_id: str
    title: str
    source_uri: str
    pages: tuple[PageInput, ...]
    media_type: str = "text/plain"
    assets: tuple[AssetInput, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvidenceLocator:
    document_id: str
    revision_id: str
    page_number: int
    block_id: str
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class StoredChunk:
    chunk_id: str
    revision_id: str
    ordinal: int
    text: str
    content_sha256: str
    evidence: tuple[EvidenceLocator, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DocumentRevision:
    document_id: str
    revision_id: str
    revision_number: int
    title: str
    source_uri: str
    media_type: str
    status: RevisionStatus
    content_sha256: str
    pipeline_fingerprint: str
    created_at: str
    created_by: str
    review_decision: ReviewDecision | None = None
    reviewer: str | None = None
    reviewed_at: str | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeBaseRelease:
    version: int
    release_id: str
    parent_version: int | None
    action: str
    manifest_sha256: str
    created_at: str
    created_by: str
    note: str
    document_count: int
    chunk_count: int


@dataclass(frozen=True, slots=True)
class VersionDiff:
    from_version: int
    to_version: int
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: str
    message: str
    document_id: str | None = None
    revision_id: str | None = None
    chunk_id: str | None = None


@dataclass(frozen=True, slots=True)
class QualityReport:
    passed: bool
    version: int | None
    metrics: dict[str, int | float | str]
    issues: tuple[QualityIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk_id: str
    document_id: str
    revision_id: str
    version: int
    text: str
    score: float
    source_uri: str
    title: str
    evidence: tuple[EvidenceLocator, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    component_scores: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Citation:
    citation_id: str
    document_id: str
    revision_id: str
    chunk_id: str
    source_uri: str
    title: str
    pages: tuple[int, ...]
    quote: str


@dataclass(frozen=True, slots=True)
class EvidenceConflict:
    conflict_group: str
    document_ids: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class RagAnswer:
    query: str
    version: int
    answer: str
    citations: tuple[Citation, ...]
    no_answer: bool
    search_mode: SearchMode
    conflicts: tuple[EvidenceConflict, ...] = ()


@dataclass(frozen=True, slots=True)
class BackupArtifact:
    database_path: str
    manifest_path: str
    sha256: str
    version: int | None
    created_at: str


@dataclass(frozen=True, slots=True)
class PublishedAsset:
    asset_id: str
    asset_type: str
    page_number: int
    uri: str
    caption: str = ""
    block_id: str | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PublishedDocument:
    document_id: str
    revision_id: str
    title: str
    source_uri: str
    media_type: str
    pages: tuple[PageInput, ...]
    assets: tuple[PublishedAsset, ...]
    chunks: tuple[StoredChunk, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KnowledgeBaseSnapshot:
    """Immutable M3 hand-off consumed by M4 graph construction."""

    schema_version: str
    release: KnowledgeBaseRelease
    documents: tuple[PublishedDocument, ...]
