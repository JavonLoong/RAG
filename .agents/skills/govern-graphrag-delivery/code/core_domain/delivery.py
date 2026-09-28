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
    CONFIRM = "confirm"
    REJECT = "reject"
    MODIFY = "modify"
    ROLLBACK = "rollback"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    APPROVED = "approved"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IssueSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Project:
    """An isolated PowerRAG delivery workspace and its governed configuration."""

    project_id: str
    name: str
    created_by: str
    domain: str = "gas_turbine"
    description: str = ""
    status: str = "active"
    configuration: dict[str, Any] = field(default_factory=dict)
    data_policy: dict[str, Any] = field(default_factory=dict)
    acceptance: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DeliveryTask:
    """A resumable, auditable long-running delivery operation."""

    task_id: str
    project_id: str
    task_type: str
    status: TaskStatus
    stage: str
    created_by: str
    progress: float = 0.0
    severity: str = "info"
    object_type: str | None = None
    object_id: str | None = None
    assigned_to: str | None = None
    correlation_id: str = ""
    idempotency_key: str | None = None
    retryable: bool = False
    error_code: str | None = None
    error_message: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    lease_owner: str | None = None
    lease_expires_at: str | None = None
    heartbeat_at: str | None = None
    duration_ms: float | None = None
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True, slots=True)
class EvidenceLocator:
    """A stable pointer from derived content back to an original source span."""

    evidence_id: str
    document_version_id: str
    chunk_id: str
    text: str
    source_file: str
    project_id: str = "default"
    created_by: str = "system"
    created_at: str = ""
    content_hash: str = ""
    config_hash: str = ""
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
class TaskError:
    """Stable, machine-readable error returned by a governed delivery task."""

    code: str
    message: str
    stage: str = "M5"
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("TaskError.code must not be empty")
        if not self.message.strip():
            raise ValueError("TaskError.message must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TaskStateEvent:
    """Auditable FMEA task state transition."""

    event_id: int
    task_id: str
    from_status: TaskStatus | None
    to_status: TaskStatus
    reason: str
    actor: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["from_status"] = self.from_status.value if self.from_status else None
        payload["to_status"] = self.to_status.value
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
    created_by: str = "system"
    config_hash: str = ""
    project_id: str = "default"
    evidence: tuple[EvidenceLocator, ...] = ()
    quality_issues: tuple[QualityIssue, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    published_at: str | None = None
    supersedes_version_id: str | None = None

    def to_dict(self, *, include_evidence: bool = True) -> dict[str, Any]:
        payload = {
            "version_id": self.version_id,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "version": self.version,
            "source_name": self.source_name,
            "content_hash": self.content_hash,
            "status": self.status.value,
            "created_by": self.created_by,
            "config_hash": self.config_hash,
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
    "MODEL",
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
    "APPLIES_TO_MODEL",
    "VARIANT_OF",
    "DIFFERS_FROM",
)

DEFAULT_KNOWLEDGE_TYPES = (
    "FACT",
    "STRUCTURAL",
    "FAILURE",
    "CAUSAL",
    "EFFECT",
    "DETECTION",
    "MITIGATION",
    "MODEL_APPLICABILITY",
    "MODEL_DIFFERENCE",
)

DEFAULT_RELATION_KNOWLEDGE_TYPES = {
    "PART_OF": "STRUCTURAL",
    "HAS_FAILURE_MODE": "FAILURE",
    "CAUSED_BY": "CAUSAL",
    "HAS_EFFECT": "EFFECT",
    "DETECTED_BY": "DETECTION",
    "MITIGATED_BY": "MITIGATION",
    "APPLIES_TO_MODEL": "MODEL_APPLICABILITY",
    "VARIANT_OF": "MODEL_DIFFERENCE",
    "DIFFERS_FROM": "MODEL_DIFFERENCE",
}

DEFAULT_RELATION_CONSTRAINTS = {
    "PART_OF": (
        ("COMPONENT", "SYSTEM"),
        ("COMPONENT", "EQUIPMENT"),
        ("SYSTEM", "SYSTEM"),
        ("SYSTEM", "EQUIPMENT"),
    ),
    "HAS_FAILURE_MODE": (
        ("EQUIPMENT", "FAILURE_MODE"),
        ("SYSTEM", "FAILURE_MODE"),
        ("COMPONENT", "FAILURE_MODE"),
    ),
    "CAUSED_BY": (("FAILURE_MODE", "CAUSE"),),
    "HAS_EFFECT": (("FAILURE_MODE", "EFFECT"),),
    "DETECTED_BY": (("FAILURE_MODE", "DETECTION_METHOD"),),
    "MITIGATED_BY": (("FAILURE_MODE", "ACTION"),),
    "APPLIES_TO_MODEL": (
        ("EQUIPMENT", "MODEL"),
        ("SYSTEM", "MODEL"),
        ("COMPONENT", "MODEL"),
        ("FAILURE_MODE", "MODEL"),
        ("ACTION", "MODEL"),
    ),
    "VARIANT_OF": (("MODEL", "MODEL"),),
    "DIFFERS_FROM": (("MODEL", "MODEL"),),
}

DEFAULT_MODEL_ALIASES = {
    "M701 F": "M701F",
    "M701-F": "M701F",
    "M7O1F": "M701F",
    "M7OIF": "M701F",
    "PG9351 F": "PG9351F",
    "PG9351FA": "PG9351F",
    "LM 2500": "LM2500",
}

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
    "适用型号": "APPLIES_TO_MODEL",
    "型号变体": "VARIANT_OF",
    "型号差异": "DIFFERS_FROM",
}


@dataclass(frozen=True, slots=True)
class GraphDomainSchema:
    """Minimal gas-turbine/FMEA schema used to validate graph candidates."""

    entity_types: tuple[str, ...] = DEFAULT_ENTITY_TYPES
    relation_types: tuple[str, ...] = DEFAULT_RELATION_TYPES
    knowledge_types: tuple[str, ...] = DEFAULT_KNOWLEDGE_TYPES
    entity_aliases: dict[str, str] = field(default_factory=dict)
    relation_aliases: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_RELATION_ALIASES))
    model_aliases: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MODEL_ALIASES))
    relation_knowledge_types: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_RELATION_KNOWLEDGE_TYPES)
    )
    relation_constraints: dict[str, tuple[tuple[str, str], ...]] = field(
        default_factory=lambda: dict(DEFAULT_RELATION_CONSTRAINTS)
    )
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

    def normalize_model(self, value: str) -> str:
        clean = " ".join(str(value).split()).strip()
        aliases = {str(key).casefold(): str(target).strip() for key, target in self.model_aliases.items()}
        return aliases.get(clean.casefold(), clean)

    def knowledge_type_for_relation(self, relation: str) -> str:
        normalized = self.normalize_relation(relation)
        return str(self.relation_knowledge_types.get(normalized) or "FACT").strip().upper()

    def relation_allows(self, relation: str, subject_type: str, object_type: str) -> bool:
        normalized = self.normalize_relation(relation)
        constraints = self.relation_constraints.get(normalized)
        if not constraints:
            return False
        pair = (str(subject_type).strip().upper(), str(object_type).strip().upper())
        return pair in {tuple(str(value).strip().upper() for value in item) for item in constraints}

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
    knowledge_type: str = "FACT"
    model_scope: tuple[str, ...] = ()
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
    created_by: str = "system"
    content_hash: str = ""
    config_hash: str = ""
    project_id: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    published_at: str | None = None
    supersedes_version_id: str | None = None

    def to_dict(self, *, include_statements: bool = True) -> dict[str, Any]:
        payload = {
            "graph_version_id": self.graph_version_id,
            "project_id": self.project_id,
            "version": self.version,
            "status": self.status.value,
            "source_document_version_ids": list(self.source_document_version_ids),
            "quality_issues": [issue.to_dict() for issue in self.quality_issues],
            "schema": self.schema.to_dict(),
            "created_by": self.created_by,
            "content_hash": self.content_hash,
            "config_hash": self.config_hash,
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
    project_id: str = "default"
    template: str = "gas_turbine_minimum_v1"
    template_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FMEATaskResult:
    task_id: str
    request: FMEATaskRequest
    status: TaskStatus
    items: tuple[FMEAItem, ...]
    errors: tuple[TaskError, ...] = ()
    state_history: tuple[TaskStateEvent, ...] = ()
    created_by: str = "system"
    content_hash: str = ""
    config_hash: str = ""
    created_at: str = ""
    updated_at: str = ""
    published_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "request": self.request.to_dict(),
            "status": self.status.value,
            "items": [item.to_dict() for item in self.items],
            "errors": [item.to_dict() for item in self.errors],
            "state_history": [item.to_dict() for item in self.state_history],
            "created_by": self.created_by,
            "content_hash": self.content_hash,
            "config_hash": self.config_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "published_at": self.published_at,
        }
