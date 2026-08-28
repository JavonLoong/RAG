from enum import Enum

FMEA_SCHEMA_ID = "graphrag.fmea.v1"


class ClaimStatus(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICT = "conflict"
    NOT_APPLICABLE = "not_applicable"


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    SUGGESTED = "suggested"
    IN_REVIEW = "in_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class PublicationStatus(str, Enum):
    UNPUBLISHED = "unpublished"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


class ActorType(str, Enum):
    HUMAN = "human"
    MODEL = "model"
    SYSTEM = "system"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RiskStatus(str, Enum):
    UNSCORED = "unscored"
    PROPOSED = "proposed"
    REVIEWED = "reviewed"
    CONFIRMED = "confirmed"
    INVALIDATED = "invalidated"


class PropagationStatus(str, Enum):
    NOT_ANALYZED = "not_analyzed"
    PROPOSED = "proposed"
    REVIEWED = "reviewed"
    CONFIRMED = "confirmed"
    INVALIDATED = "invalidated"


class EvidenceSupportStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONTRADICTED = "contradicted"
    NOT_SUPPORTED = "not_supported"
