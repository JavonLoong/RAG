"""Shared delivery contracts for the governed M2 -> M5 GraphRAG workflow.

The project already has capable parsers, retrievers, and graph components.  This
module defines the small, stable vocabulary that joins those components: every
published fact is versioned, every professional field can point back to source
evidence, and every human decision is auditable.
"""
# ruff: noqa: TRY003

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ContentStatus(str, Enum):
    CANDIDATE = "candidate"
    NEEDS_REVIEW = "needs_review"
    PUBLISHED = "published"
    RETIRED = "retired"


class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"
    ROLLBACK = "rollback"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    FAILED = "failed"


class IssueSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class EvidenceLocator:
    """A stable pointer from derived content back to an original source span."""

    evidence_id: str
    document_version_id: str
    chunk_id: str
    text: str
    source_file: str
    page: str | None = None
    block_id: str | None = None
    table_id: str | None = None
    image_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("evidence_id", "document_version_id", "chunk_id", "text", "source_file"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"EvidenceLocator.{field_name} must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class QualityIssue:
    issue_id: str
    code: str
    message: str
    severity: IssueSeverity = IssueSeverity.WARNING
    evidence_ids: tuple[str, ...] = ()
    resolved: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["severity"] = self.severity.value
        return payload


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    review_id: int
    target_type: str
    target_id: str
    reviewer: str
    decision: ReviewDecision
    comment: str
    corrections: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision"] = self.decision.value
        return payload


@dataclass(frozen=True, slots=True)
class CanonicalDocumentVersion:
    version_id: str
    document_id: str
    version: int
    source_name: str
    content_hash: str
    status: ContentStatus
    evidence: tuple[EvidenceLocator, ...] = ()
    quality_issues: tuple[QualityIssue, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    published_at: str | None = None
    supersedes_version_id: str | None = None

    def to_dict(self, *, include_evidence: bool = True) -> dict[str, Any]:
        payload = {
            "version_id": self.version_id,
            "document_id": self.document_id,
            "version": self.version,
            "source_name": self.source_name,
            "content_hash": self.content_hash,
            "status": self.status.value,
            "quality_issues": [issue.to_dict() for issue in self.quality_issues],
            "metadata": self.metadata,
            "created_at": self.created_at,
            "published_at": self.published_at,
            "supersedes_version_id": self.supersedes_version_id,
        }
        if include_evidence:
            payload["evidence"] = [item.to_dict() for item in self.evidence]
        else:
            payload["evidence_count"] = len(self.evidence)
        return payload


DEFAULT_ENTITY_TYPES = (
    "EQUIPMENT",
    "SYSTEM",
    "COMPONENT",
    "FAILURE_MODE",
    "CAUSE",
    "EFFECT",
    "DETECTION_METHOD",
    "ACTION",
)

DEFAULT_RELATION_TYPES = (
    "PART_OF",
    "HAS_FAILURE_MODE",
    "CAUSED_BY",
    "HAS_EFFECT",
    "DETECTED_BY",
    "MITIGATED_BY",
)

DEFAULT_RELATION_ALIASES = {
    "属于": "PART_OF",
    "包含": "PART_OF",
    "故障模式": "HAS_FAILURE_MODE",
    "具有故障模式": "HAS_FAILURE_MODE",
    "原因": "CAUSED_BY",
    "由...导致": "CAUSED_BY",
    "导致": "HAS_EFFECT",
    "影响": "HAS_EFFECT",
    "检测方法": "DETECTED_BY",
    "检测": "DETECTED_BY",
    "措施": "MITIGATED_BY",
    "缓解措施": "MITIGATED_BY",
}


@dataclass(frozen=True, slots=True)
class GraphDomainSchema:
    """Minimal gas-turbine/FMEA schema used to validate graph candidates."""

    entity_types: tuple[str, ...] = DEFAULT_ENTITY_TYPES
    relation_types: tuple[str, ...] = DEFAULT_RELATION_TYPES
    entity_aliases: dict[str, str] = field(default_factory=dict)
    relation_aliases: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_RELATION_ALIASES))
    min_confidence: float = 0.7

    def normalize_entity(self, value: str) -> str:
        clean = " ".join(str(value).split())
        aliases = {str(key).casefold(): str(target).strip() for key, target in self.entity_aliases.items()}
        return aliases.get(clean.casefold(), clean)

    def normalize_relation(self, value: str) -> str:
        clean = " ".join(str(value).split())
        if clean.upper() in self.relation_types:
            return clean.upper()
        aliases = {str(key).casefold(): str(target).strip().upper() for key, target in self.relation_aliases.items()}
        return aliases.get(clean.casefold(), clean.upper())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GraphStatement:
    statement_id: str
    subject: str
    predicate: str
    object_name: str
    subject_type: str
    object_type: str
    evidence_ids: tuple[str, ...]
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GraphVersion:
    graph_version_id: str
    version: int
    status: ContentStatus
    source_document_version_ids: tuple[str, ...]
    statements: tuple[GraphStatement, ...]
    quality_issues: tuple[QualityIssue, ...]
    schema: GraphDomainSchema
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    published_at: str | None = None
    supersedes_version_id: str | None = None

    def to_dict(self, *, include_statements: bool = True) -> dict[str, Any]:
        payload = {
            "graph_version_id": self.graph_version_id,
            "version": self.version,
            "status": self.status.value,
            "source_document_version_ids": list(self.source_document_version_ids),
            "quality_issues": [issue.to_dict() for issue in self.quality_issues],
            "schema": self.schema.to_dict(),
            "metadata": self.metadata,
            "created_at": self.created_at,
            "published_at": self.published_at,
            "supersedes_version_id": self.supersedes_version_id,
        }
        if include_statements:
            payload["statements"] = [item.to_dict() for item in self.statements]
        else:
            payload["statement_count"] = len(self.statements)
        return payload


FMEA_FIELDS = (
    "equipment",
    "component",
    "failure_mode",
    "cause",
    "effect",
    "detection_method",
    "recommended_action",
)


@dataclass(frozen=True, slots=True)
class FMEAItem:
    item_id: str
    fields: dict[str, str | None]
    field_evidence: dict[str, tuple[str, ...]]
    issues: tuple[QualityIssue, ...] = ()
    review_status: str = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = set(self.fields) - set(FMEA_FIELDS)
        if unknown:
            raise ValueError(f"Unknown FMEA fields: {sorted(unknown)}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "fields": self.fields,
            "field_evidence": {key: list(value) for key, value in self.field_evidence.items()},
            "issues": [issue.to_dict() for issue in self.issues],
            "review_status": self.review_status,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class FMEATaskRequest:
    requested_by: str
    graph_version_id: str
    document_version_ids: tuple[str, ...]
    template: str = "gas_turbine_minimum_v1"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FMEATaskResult:
    task_id: str
    request: FMEATaskRequest
    status: TaskStatus
    items: tuple[FMEAItem, ...]
    errors: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    published_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "request": self.request.to_dict(),
            "status": self.status.value,
            "items": [item.to_dict() for item in self.items],
            "errors": list(self.errors),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "published_at": self.published_at,
        }
