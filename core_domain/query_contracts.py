"""Stable Pydantic models for the GraphRAG query v1 interface."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class QueryMode(str, Enum):
    """Supported query execution modes."""

    AUTO = "auto"
    VECTOR = "vector"
    LOCAL = "local"
    GLOBAL = "global"
    HYBRID = "hybrid"


class EvidenceSelectionProfile(str, Enum):
    AUTO = "auto"
    RAG_ONLY = "rag_only"
    GRAPHRAG_LOCAL_ONLY = "graphrag_local_only"
    GRAPHRAG_GLOBAL_ONLY = "graphrag_global_only"
    GRAPHRAG_ONLY = "graphrag_only"
    COMBINED = "combined"
    CUSTOM = "custom"


class QueryStatus(str, Enum):
    """Stable response status values."""

    OK = "ok"
    PARTIAL = "partial"
    ERROR = "error"


class CitationType(str, Enum):
    """Kinds of evidence that can support a query response."""

    TEXT = "text"
    GRAPH = "graph"
    COMMUNITY = "community"


_PROFILE_TYPES: dict[EvidenceSelectionProfile, tuple[CitationType, ...]] = {
    EvidenceSelectionProfile.RAG_ONLY: (CitationType.TEXT,),
    EvidenceSelectionProfile.GRAPHRAG_LOCAL_ONLY: (CitationType.GRAPH,),
    EvidenceSelectionProfile.GRAPHRAG_GLOBAL_ONLY: (CitationType.COMMUNITY,),
    EvidenceSelectionProfile.GRAPHRAG_ONLY: (CitationType.GRAPH, CitationType.COMMUNITY),
    EvidenceSelectionProfile.COMBINED: (
        CitationType.TEXT,
        CitationType.GRAPH,
        CitationType.COMMUNITY,
    ),
}


class _ContractModel(BaseModel):
    """Shared validation policy for every v1 contract model."""

    model_config = ConfigDict(extra="forbid")


class QueryRequest(_ContractModel):
    query: str = Field(min_length=1, max_length=65536)
    workspace_id: str = Field(min_length=1, max_length=128)
    mode: QueryMode = QueryMode.AUTO
    top_k: int = Field(default=5, ge=1, le=100)
    include_context: bool = False
    include_debug: bool = False
    evidence_only: bool = False
    evidence_profile: EvidenceSelectionProfile = EvidenceSelectionProfile.AUTO
    evidence_types: tuple[CitationType, ...] = ()

    @field_validator("query", mode="before")
    @classmethod
    def strip_query(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def validate_evidence_selection(self) -> QueryRequest:
        if not self.evidence_only:
            if self.evidence_profile is not EvidenceSelectionProfile.AUTO or self.evidence_types:
                raise ValueError("evidence selection requires evidence_only=true")  # noqa: TRY003
            return self
        if self.mode is not QueryMode.AUTO:
            raise ValueError("evidence_only requires mode=auto")  # noqa: TRY003
        if len(self.evidence_types) != len(set(self.evidence_types)):
            raise ValueError("evidence_types must not contain duplicates")  # noqa: TRY003
        if self.evidence_profile is EvidenceSelectionProfile.CUSTOM:
            if not self.evidence_types:
                raise ValueError("custom evidence profile requires evidence_types")  # noqa: TRY003
        elif self.evidence_types:
            raise ValueError("evidence_types are only valid for the custom profile")  # noqa: TRY003
        return self


def selected_citation_types(request: QueryRequest) -> tuple[CitationType, ...] | None:
    if not request.evidence_only or request.evidence_profile is EvidenceSelectionProfile.AUTO:
        return None
    if request.evidence_profile is EvidenceSelectionProfile.CUSTOM:
        return request.evidence_types
    return _PROFILE_TYPES[request.evidence_profile]


class SourceRef(_ContractModel):
    document_id: str | None = None
    file: str | None = None
    page: int | str | None = None
    chunk_id: str | None = None


class GraphTriple(_ContractModel):
    subject: str
    predicate: str
    object: str


class Citation(_ContractModel):
    id: str
    type: CitationType
    source: SourceRef | None = None
    quote: str
    score: float | None = Field(default=None, allow_inf_nan=False)
    metadata: dict[str, Any] = Field(default_factory=dict)
    triple: GraphTriple | None = None


class ModeDecision(_ContractModel):
    requested: QueryMode
    used: QueryMode
    reason: str


class AnswerPayload(_ContractModel):
    text: str
    finish_reason: Literal["stop", "length", "content_filter", "error"]


class RetrievalSummary(_ContractModel):
    text_hits: int = 0
    graph_hits: int = 0
    community_hits: int = 0
    communities_searched: int = 0
    reranked: bool = False


class UsageMetrics(_ContractModel):
    latency_ms: float
    llm_calls: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class WarningItem(_ContractModel):
    code: str
    message: str


class ErrorDetail(_ContractModel):
    code: str
    message: str
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ContextItem(_ContractModel):
    id: str
    type: CitationType
    text: str
    source: SourceRef | None = None
    score: float | None = None


class ContextPayload(_ContractModel):
    items: list[ContextItem] = Field(default_factory=list)
    rendered_text: str | None = None


class DebugPayload(_ContractModel):
    prompt: str | None = None
    raw_mode_result: dict[str, Any] | None = None


class QueryResponse(_ContractModel):
    schema_version: Literal["graphrag.query.v1"] = "graphrag.query.v1"
    request_id: str
    trace_id: str
    status: Literal[QueryStatus.OK, QueryStatus.PARTIAL]
    mode: ModeDecision
    answer: AnswerPayload
    citations: list[Citation] = Field(default_factory=list)
    context: ContextPayload | None = None
    retrieval: RetrievalSummary
    usage: UsageMetrics
    warnings: list[WarningItem] = Field(default_factory=list)
    debug: DebugPayload | None = None


class QueryErrorResponse(_ContractModel):
    schema_version: Literal["graphrag.query.v1"] = "graphrag.query.v1"
    request_id: str
    trace_id: str
    status: Literal[QueryStatus.ERROR] = QueryStatus.ERROR
    error: ErrorDetail


class MetaEvent(_ContractModel):
    event: Literal["meta"] = "meta"
    request_id: str
    sequence: int
    mode: ModeDecision
    token_streaming: bool


class CitationEvent(_ContractModel):
    event: Literal["citation"] = "citation"
    request_id: str
    sequence: int
    citation: Citation


class DeltaEvent(_ContractModel):
    event: Literal["delta"] = "delta"
    request_id: str
    sequence: int
    text: str


class FinalEvent(_ContractModel):
    event: Literal["final"] = "final"
    request_id: str
    sequence: int
    response: QueryResponse


class ErrorEvent(_ContractModel):
    event: Literal["error"] = "error"
    request_id: str
    sequence: int
    error: ErrorDetail


QueryStreamEvent = Annotated[
    MetaEvent | CitationEvent | DeltaEvent | FinalEvent | ErrorEvent,
    Field(discriminator="event"),
]


__all__ = [
    "AnswerPayload",
    "Citation",
    "CitationEvent",
    "CitationType",
    "ContextItem",
    "ContextPayload",
    "DebugPayload",
    "DeltaEvent",
    "ErrorDetail",
    "ErrorEvent",
    "EvidenceSelectionProfile",
    "FinalEvent",
    "GraphTriple",
    "MetaEvent",
    "ModeDecision",
    "QueryErrorResponse",
    "QueryMode",
    "QueryRequest",
    "QueryResponse",
    "QueryStatus",
    "QueryStreamEvent",
    "RetrievalSummary",
    "SourceRef",
    "UsageMetrics",
    "WarningItem",
    "selected_citation_types",
]
