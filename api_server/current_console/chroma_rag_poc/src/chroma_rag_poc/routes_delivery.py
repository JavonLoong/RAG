"""Callable M2-M5 delivery workflow endpoints."""
# ruff: noqa: TRY003, TRY301

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import sys
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core_domain.delivery import (  # noqa: E402
    ContentStatus,
    FMEATaskRequest,
    GraphDomainSchema,
    ReviewDecision,
    TaskStatus,
)
from data_pipeline.document_intake import DocumentIntakeOptions, run_document_intake  # noqa: E402
from kg_pipeline.governed_extraction import GovernedExtractionError, extract_governed_statements  # noqa: E402
from rag_orchestrator.delivery_remediation import DeliveryRemediationService  # noqa: E402
from rag_orchestrator.fmea import FMEAService  # noqa: E402
from rag_orchestrator.fmea_templates import FMEATemplateError, FMEATemplateRegistry  # noqa: E402
from rag_orchestrator.governed_community_summary import build_governed_community_summaries  # noqa: E402
from rag_orchestrator.governed_graphrag import GovernedGraphRAGService  # noqa: E402
from rag_orchestrator.m2_delivery import M2DeliveryService  # noqa: E402
from storage_layer.governance_store import GovernanceError, GovernanceStore  # noqa: E402
from storage_layer.governed_index import GovernedDocumentIndex, GovernedIndexError  # noqa: E402
from storage_layer.graph_store import GraphStore, normalize_kg_payload  # noqa: E402
from storage_layer.project_workspace import (  # noqa: E402
    ProjectWorkspaceError,
    ProjectWorkspaceRegistry,
)

from .embeddings import DEFAULT_SENTENCE_TRANSFORMER_MODEL, create_embedding_backend  # noqa: E402

router = APIRouter(prefix="/api/delivery", tags=["governed-delivery"])


class ProjectCreateRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=63)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    domain: str = "gas_turbine"
    created_by: str = Field(default="local-user", min_length=1)
    configuration: dict[str, Any] = Field(default_factory=dict)
    data_policy: dict[str, Any] = Field(default_factory=dict)
    acceptance: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdateRequest(BaseModel):
    expected_version: str = Field(min_length=1)
    actor: str = Field(default="local-user", min_length=1)
    reason: str = ""
    name: str | None = None
    description: str | None = None
    status: str | None = None
    configuration: dict[str, Any] | None = None
    data_policy: dict[str, Any] | None = None
    acceptance: dict[str, Any] | None = None


class ProjectTemplateCopyRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=63)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    created_by: str = "local-user"


class DeliveryTaskCreateRequest(BaseModel):
    task_type: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    created_by: str = Field(default="local-user", min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    object_type: str | None = None
    object_id: str | None = None
    severity: str = "info"
    idempotency_key: str | None = None
    correlation_id: str | None = None
    retryable: bool = True


class DeliveryTaskActionRequest(BaseModel):
    actor: str = Field(default="local-user", min_length=1)
    reason: str = ""
    idempotency_key: str | None = None


class DeliveryTaskAssignRequest(BaseModel):
    assignee: str = Field(min_length=1, max_length=200)
    actor: str = "local-user"


class DeliveryTaskCommentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    actor: str = "local-user"


class DeliveryTaskBatchRetryRequest(BaseModel):
    task_ids: list[str] = Field(min_length=1, max_length=100)
    actor: str = "local-user"
    idempotency_key: str | None = None


class DeliveryTaskHeartbeatRequest(BaseModel):
    worker_id: str = Field(min_length=1)
    progress: float = Field(ge=0.0, le=1.0)
    stage: str | None = None
    lease_seconds: int = Field(default=120, ge=5, le=3600)


class PublishRequest(BaseModel):
    actor: str = Field(default="local-user", min_length=1)
    comment: str = ""
    idempotency_key: str | None = None
    expected_version: str | None = None


class IntakeRequest(BaseModel):
    document_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    content_base64: str = Field(min_length=1)
    chunk_size: int = Field(default=500, ge=80, le=5000)
    overlap: int = Field(default=50, ge=0, le=1000)
    parser_backend: Literal["auto", "native", "deepdoc", "mineru", "docling", "unstructured"] = "auto"
    use_ocr: Literal["auto", "always", "never"] = "auto"
    translation_target: Literal["zh", "en"] | None = None
    auto_run_ocr: bool = True
    ocr_page_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OCRBlockPayload(BaseModel):
    block_id: str | None = None
    type: str = "Para"
    text: str = ""
    order: int = Field(default=0, ge=0)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    table_id: str | None = None
    image_id: str | None = None
    caption_for: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OCRTablePayload(BaseModel):
    table_id: str | None = None
    rows: list[list[str]] = Field(default_factory=list)
    expected_columns: int | None = Field(default=None, ge=1)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OCRPagePayload(BaseModel):
    page: int = Field(ge=1)
    text: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reading_order_risk: Literal["low", "medium", "high", "unknown"] = "unknown"
    block_id: str | None = None
    table_id: str | None = None
    image_id: str | None = None
    status: Literal["ok", "error", "timeout"] = "ok"
    error: str = ""
    blocks: list[OCRBlockPayload] = Field(default_factory=list)
    tables: list[OCRTablePayload] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OCRResultIntakeRequest(BaseModel):
    document_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    pages: list[OCRPagePayload] = Field(min_length=1)
    expected_pages: int | None = Field(default=None, ge=1)
    low_confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    source_asset_id: str | None = None
    source_content_base64: str | None = None
    job_id: str | None = None
    timeout_pages: list[int] = Field(default_factory=list)
    failed_pages: list[int] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OCRPageRetryRequest(BaseModel):
    pages: list[int] = Field(min_length=1)
    idempotency_key: str | None = None


class DocumentRevisionRequest(BaseModel):
    reviewer: str = Field(min_length=1)
    comment: str = ""
    corrections: dict[str, Any] = Field(min_length=1)
    expected_version: str | None = None


class DocumentBatchReviewRequest(BaseModel):
    version_ids: list[str] = Field(min_length=1, max_length=100)
    decision: Literal["approve", "reject"]
    reviewer: str = "local-user"
    comment: str = ""
    idempotency_key: str | None = None


class ReviewRequest(BaseModel):
    reviewer: str = Field(min_length=1)
    decision: str
    comment: str = ""
    corrections: dict[str, Any] = Field(default_factory=dict)
    expected_version: str | None = None


class RollbackRequest(BaseModel):
    target_version_id: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    comment: str = ""


class GraphCandidateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_document_version_ids: list[str] = Field(min_length=1)
    statements: list[dict[str, Any]] = Field(min_length=1)
    schema_id: str | None = None
    schema_version: str | None = None
    graph_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphExtractionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_document_version_ids: list[str] = Field(min_length=1)
    backend: Literal["rules", "small-model", "llm"] = "rules"
    model: str | None = None
    provider_id: str | None = None
    prompt_version: str = Field(default="graph-extraction-v1", min_length=1, max_length=100)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    timeout_seconds: float | None = Field(default=None, gt=0.0, le=3600.0)
    retries: int = Field(default=0, ge=0, le=5)
    schema_id: str | None = None
    schema_version: str | None = None
    graph_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphStatementReviewRequest(BaseModel):
    reviewer: str = Field(default="local-user", min_length=1)
    decisions: dict[str, Literal["approve", "reject"]] = Field(min_length=1)
    comment: str = ""
    expected_version: str | None = None


class ProviderUpsertRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=100)
    capability: Literal[
        "document_parsing",
        "ocr",
        "translation",
        "embedding",
        "graph_extraction",
        "answer_generation",
    ]
    provider_type: Literal["local", "external"] = "local"
    model: str = ""
    version: str = ""
    timeout_seconds: float = Field(default=120.0, ge=1.0, le=3600.0)
    cost_class: str = "local"
    data_policy: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    health_status: Literal["ready", "degraded", "failed", "unknown", "disabled"] = "unknown"
    enabled: bool = True
    configuration: dict[str, Any] = Field(default_factory=dict)
    actor: str = "local-user"


class GraphSchemaRegistrationRequest(BaseModel):
    schema_id: str = Field(min_length=2, max_length=100)
    version: str = Field(min_length=1, max_length=50)
    definition: dict[str, Any]
    actor: str = Field(default="local-user", min_length=1)
    status: Literal["draft", "approved"] = "draft"


class GraphSchemaApprovalRequest(BaseModel):
    actor: str = Field(default="local-user", min_length=1)


class FMEATemplateRegistrationRequest(BaseModel):
    template_id: str = Field(min_length=2, max_length=100)
    version: str = Field(min_length=1, max_length=50)
    definition: dict[str, Any]
    actor: str = Field(default="local-user", min_length=1)
    status: Literal["draft", "approved"] = "draft"


class FMEATemplateApprovalRequest(BaseModel):
    actor: str = Field(default="local-user", min_length=1)


class GraphRollbackRequest(BaseModel):
    target_graph_version_id: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    comment: str = ""


class GraphQueryRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=50)
    max_hops: int = Field(default=4, ge=1, le=10)
    allow_fallback: bool = True


class RAGComparisonRequest(BaseModel):
    questions: list[dict[str, Any] | str] = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=50)


class CommunitySummaryRequest(BaseModel):
    actor: str = Field(default="local-user", min_length=1)
    level: int = Field(default=0, ge=0, le=10)


class FMEARunRequest(BaseModel):
    requested_by: str = Field(min_length=1)
    graph_version_id: str = Field(min_length=1)
    document_version_ids: list[str] = Field(min_length=1)
    template: str = "gas_turbine_minimum_v1"
    template_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FMEAFieldReviewRequest(BaseModel):
    reviewer: str = Field(default="local-user", min_length=1)
    decisions: dict[str, dict[str, Literal["approve", "reject"]]] = Field(min_length=1)
    corrections: dict[str, Any] = Field(default_factory=dict)
    comment: str = ""
    expected_version: str | None = None


class FeedbackRequest(BaseModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    created_by: str = Field(min_length=1)
    item_id: str | None = None


class FeedbackRemediationRequest(BaseModel):
    actor: str = Field(min_length=1)
    document_version_id: str | None = None
    graph_version_id: str | None = None
    corrections: dict[str, Any] = Field(default_factory=dict)


def _registry(request: Request) -> ProjectWorkspaceRegistry:
    registry = getattr(request.app.state, "project_workspace_registry", None)
    if registry is not None:
        return registry
    persist_dir = Path(getattr(request.app.state, "persist_dir", _REPO_ROOT / "build" / "runtime"))
    registry = ProjectWorkspaceRegistry(persist_dir / "projects")
    request.app.state.project_workspace_registry = registry
    return registry


def _project_id(request: Request, explicit: str | None = None) -> str:
    return str(
        explicit
        or getattr(request.state, "delivery_project_id", "")
        or request.headers.get("X-Project-ID")
        or request.query_params.get("project_id")
        or "default"
    ).strip().lower()


def _store(request: Request, project_id: str | None = None) -> GovernanceStore:
    resolved_project_id = _project_id(request, project_id)
    if resolved_project_id == "default":
        store = getattr(request.app.state, "governance_store", None)
        if store is not None:
            return store
        persist_dir = Path(getattr(request.app.state, "persist_dir", _REPO_ROOT / "build" / "runtime"))
        store = GovernanceStore(
            persist_dir / "governance" / "delivery.sqlite3",
            project_id="default",
        )
        request.app.state.governance_store = store
        return store
    stores = getattr(request.app.state, "project_governance_stores", None)
    if stores is None:
        stores = {}
        request.app.state.project_governance_stores = stores
    if resolved_project_id not in stores:
        stores[resolved_project_id] = _registry(request).governance_store(resolved_project_id)
    return stores[resolved_project_id]


def _index(request: Request, project_id: str | None = None) -> GovernedDocumentIndex:
    resolved_project_id = _project_id(request, project_id)
    if resolved_project_id == "default":
        index = getattr(request.app.state, "governed_document_index", None)
        if index is not None:
            return index
    persist_dir = Path(getattr(request.app.state, "persist_dir", _REPO_ROOT / "build" / "runtime"))
    backend_name = str(
        getattr(request.app.state, "delivery_embedding_backend", "")
        or os.environ.get("RAG_DELIVERY_EMBEDDING_BACKEND", "sentence-transformer")
    )
    model_name = str(
        getattr(request.app.state, "delivery_embedding_model", "")
        or os.environ.get("RAG_DELIVERY_EMBEDDING_MODEL", DEFAULT_SENTENCE_TRANSFORMER_MODEL)
    )
    resolved = create_embedding_backend(backend_name, model_name)
    index_dir = (
        persist_dir / "governance" / "retrieval_chroma"
        if resolved_project_id == "default"
        else _registry(request).project_dir(resolved_project_id) / "retrieval" / "chroma"
    )
    index = GovernedDocumentIndex(
        index_dir,
        embedding_function=resolved.function,
        embedding_backend=resolved.name,
        embedding_model=resolved.model_name,
        embedding_warning=resolved.warning,
        project_id=resolved_project_id,
    )
    if resolved_project_id == "default":
        request.app.state.governed_document_index = index
    else:
        indexes = getattr(request.app.state, "project_document_indexes", None)
        if indexes is None:
            indexes = {}
            request.app.state.project_document_indexes = indexes
        existing = indexes.get(resolved_project_id)
        if existing is not None:
            return existing
        indexes[resolved_project_id] = index
    return index


def _graph_store(request: Request, project_id: str | None = None) -> GraphStore:
    resolved_project_id = _project_id(request, project_id)
    if resolved_project_id == "default":
        store = getattr(request.app.state, "governed_graph_store", None)
        if store is not None:
            return store
    persist_dir = Path(getattr(request.app.state, "persist_dir", _REPO_ROOT / "build" / "runtime"))
    graph_path = (
        persist_dir / "graph_store.sqlite"
        if resolved_project_id == "default"
        else _registry(request).project_dir(resolved_project_id) / "graph" / "graph.sqlite3"
    )
    store = GraphStore(graph_path)
    store.initialize(reset=False)
    if resolved_project_id == "default":
        request.app.state.governed_graph_store = store
    else:
        stores = getattr(request.app.state, "project_graph_stores", None)
        if stores is None:
            stores = {}
            request.app.state.project_graph_stores = stores
        existing = stores.get(resolved_project_id)
        if existing is not None:
            return existing
        stores[resolved_project_id] = store
    return store


def _m2(request: Request) -> M2DeliveryService:
    return M2DeliveryService(
        _store(request),
        ocr_provider=getattr(request.app.state, "m2_ocr_provider", None),
    )


def _fmea_service(request: Request, project_id: str | None = None) -> FMEAService:
    resolved_project_id = _project_id(request, project_id)
    catalog = _registry(request).list_fmea_templates(project_id=resolved_project_id)
    return FMEAService(
        _store(request, resolved_project_id),
        template_registry=FMEATemplateRegistry(definitions=catalog["items"]),
    )


def _governed_graphrag(request: Request) -> GovernedGraphRAGService:
    return GovernedGraphRAGService(
        _store(request),
        _index(request),
        llm=getattr(request.app.state, "delivery_answer_llm", None),
    )


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": str(getattr(exc, "code", "delivery_request_invalid")),
            "message": str(exc),
            "stage": str(getattr(exc, "stage", "delivery")),
            "retryable": False,
            "details": dict(getattr(exc, "details", {}) or {}),
            "correlation_id": uuid4().hex,
        },
    )


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": str(getattr(exc, "code", "delivery_resource_not_found")),
            "message": str(exc),
            "stage": str(getattr(exc, "stage", "delivery")),
            "retryable": False,
            "details": dict(getattr(exc, "details", {}) or {}),
            "correlation_id": uuid4().hex,
        },
    )


def _workspace_http_error(exc: Exception) -> HTTPException:
    code = str(getattr(exc, "code", "project_workspace_error"))
    status_code = 400
    if code in {"project_not_found", "task_not_found", "graph_schema_not_found"}:
        status_code = 404
    elif code in {
        "project_already_exists",
        "version_conflict",
        "graph_statement_review_incomplete",
        "fmea_field_review_incomplete",
        "citation_integrity_error",
        "duplicate_source_asset",
        "task_claim_conflict",
        "task_terminal",
        "graph_schema_version_exists",
        "graph_schema_lineage_conflict",
        "graph_schema_restore_conflict",
        "fmea_template_version_exists",
        "fmea_template_restore_conflict",
        "graph_projection_stale",
    }:
        status_code = 409
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": str(exc),
            "stage": "product_control",
            "retryable": code in {"task_claim_conflict", "version_conflict"},
            "details": dict(getattr(exc, "details", {}) or {}),
            "correlation_id": uuid4().hex,
        },
    )


def _actor(request: Request, claimed: str | None = None) -> str:
    authenticated = str(getattr(request.state, "delivery_actor", "") or "").strip()
    if authenticated:
        return authenticated
    configured = str(
        getattr(request.app.state, "delivery_local_actor", "")
        or os.environ.get("RAG_DELIVERY_LOCAL_ACTOR", "")
    ).strip()
    if configured:
        return configured
    return str(claimed or "local-user").strip() or "local-user"


def _without_secrets(value: Any) -> Any:
    """Copy project/provider templates without propagating credentials."""

    secret_tokens = ("secret", "password", "api_key", "apikey", "access_token", "refresh_token")
    if isinstance(value, Mapping):
        return {
            str(key): _without_secrets(item)
            for key, item in value.items()
            if not any(token in str(key).casefold() for token in secret_tokens)
        }
    if isinstance(value, list):
        return [_without_secrets(item) for item in value]
    return value


def _identity_can_access_project(request: Request, project: Mapping[str, Any]) -> bool:
    configuration = dict(project.get("configuration") or {})
    allowed_actors = {str(item) for item in configuration.get("allowed_actors") or []}
    allowed_groups = {str(item) for item in configuration.get("allowed_groups") or []}
    if not allowed_actors and not allowed_groups:
        return True
    actor = _actor(request)
    groups = {str(item) for item in getattr(request.state, "delivery_groups", [])}
    return actor in allowed_actors or bool(groups & allowed_groups)


def _graph_statement_issue_codes(graph) -> dict[str, set[str]]:
    issue_by_statement: dict[str, set[str]] = {item.statement_id: set() for item in graph.statements}
    for issue in graph.quality_issues:
        statement_id = str(issue.metadata.get("statement_id") or "")
        if statement_id in issue_by_statement:
            issue_by_statement[statement_id].add(issue.code)
        for statement in graph.statements:
            if set(issue.evidence_ids) & set(statement.evidence_ids):
                issue_by_statement[statement.statement_id].add(issue.code)
    return issue_by_statement


def _graph_statement_matches(
    statement,
    *,
    cursor: str,
    relationship: str,
    subject_type: str,
    object_type: str,
    model: str,
    min_confidence: float | None,
    evidence_status: str,
    issue_code: str,
    issue_codes: set[str],
) -> bool:
    return all((
        not cursor or statement.statement_id > cursor,
        not relationship or statement.predicate == relationship,
        not subject_type or statement.subject_type == subject_type,
        not object_type or statement.object_type == object_type,
        not model or model in statement.model_scope,
        min_confidence is None or float(statement.confidence or 0.0) >= min_confidence,
        evidence_status != "bound" or bool(statement.evidence_ids),
        evidence_status != "missing" or not statement.evidence_ids,
        not issue_code or issue_code in issue_codes,
    ))


def _authorize_graph_extraction_provider(
    request: Request,
    *,
    project_id: str,
    payload: GraphExtractionRequest,
    documents,
) -> dict[str, Any]:
    provider_id = str(payload.provider_id or ("rules-graph" if payload.backend == "rules" else "")).strip()
    if not provider_id:
        raise ProjectWorkspaceError(
            "small-model and llm extraction require an explicit registered provider_id",
            code="provider_required",
            details={"backend": payload.backend},
        )
    registry = _registry(request)
    registered = registry.get_provider(project_id, provider_id)
    supported_backends = {str(item) for item in registered["capabilities"].get("backends") or []}
    if supported_backends and payload.backend not in supported_backends:
        raise ProjectWorkspaceError(
            "Registered provider does not support the selected extraction backend",
            code="provider_backend_mismatch",
            details={
                "provider_id": provider_id,
                "backend": payload.backend,
                "supported_backends": sorted(supported_backends),
            },
        )
    return registry.authorize_provider_call(
        project_id=project_id,
        provider_id=provider_id,
        capability="graph_extraction",
        actor=_actor(request, str(payload.metadata.get("actor") or "")),
        data_scope={
            "document_version_ids": [item.version_id for item in documents],
            "content_hashes": [item.content_hash for item in documents],
            "raw_text_included": payload.backend in {"small-model", "llm"},
        },
        correlation_id=request.headers.get("X-Correlation-ID"),
    )


def _check_expected_version(expected: str | None, *, allowed: set[str]) -> None:
    if expected and str(expected) not in allowed:
        raise ProjectWorkspaceError(
            "Object version changed before this operation",
            code="version_conflict",
            details={"expected_version": expected, "actual_versions": sorted(allowed)},
        )


def _begin_idempotent_operation(
    request: Request,
    *,
    project_id: str,
    action: str,
    actor: str,
    object_type: str,
    object_id: str,
    idempotency_key: str | None,
):
    if not idempotency_key:
        return None, None
    registry = _registry(request)
    task = registry.create_task(
        project_id=project_id,
        task_type=action,
        stage="write",
        created_by=actor,
        object_type=object_type,
        object_id=object_id,
        idempotency_key=idempotency_key,
        correlation_id=request.headers.get("X-Correlation-ID"),
        retryable=False,
    )
    if task.status is TaskStatus.COMPLETED:
        return task, task.result.get("response")
    if task.status is not TaskStatus.QUEUED:
        raise ProjectWorkspaceError(
            "Idempotent operation is already in progress",
            code="task_claim_conflict",
            details={"task_id": task.task_id, "status": task.status.value},
        )
    worker_id = f"api-write-{os.getpid()}"
    registry.claim_task(task.task_id, worker_id=worker_id, lease_seconds=120)
    return registry.get_task(task.task_id), None


def _complete_idempotent_operation(
    request: Request,
    task,
    *,
    response: Mapping[str, Any],
    actor: str,
) -> None:
    if task is None:
        return
    _registry(request).finish_task(
        task.task_id,
        status=TaskStatus.COMPLETED,
        result={"response": dict(response)},
        retryable=False,
        actor=actor,
    )


def _fail_idempotent_operation(request: Request, task, exc: Exception, *, actor: str) -> None:
    if task is None:
        return
    with suppress(Exception):
        _registry(request).finish_task(
            task.task_id,
            status=TaskStatus.FAILED,
            error_code=str(getattr(exc, "code", "write_failed")),
            error_message=str(exc),
            retryable=False,
            actor=actor,
        )


def _audit_action(
    request: Request,
    *,
    project_id: str,
    object_type: str,
    object_id: str,
    object_version: str | None,
    action: str,
    actor: str,
    reason: str,
    change_summary: Mapping[str, Any],
) -> None:
    _registry(request).append_audit(
        project_id=project_id,
        object_type=object_type,
        object_id=object_id,
        object_version=object_version,
        action=action,
        actor=actor,
        reason=reason,
        change_summary=change_summary,
        correlation_id=request.headers.get("X-Correlation-ID") or uuid4().hex,
        client_request_id=request.headers.get("X-Client-Request-ID"),
        result="success",
    )


def _run_uploaded_intake(
    *,
    request: Request,
    project_id: str,
    task_id: str,
    source_asset_id: str,
    document_id: str,
    source_name: str,
    chunk_size: int,
    overlap: int,
    parser_backend: str,
    use_ocr: str,
    translation_target: str | None,
) -> None:
    registry = _registry(request)
    worker_id = f"local-intake-{os.getpid()}"
    try:
        registry.claim_task(task_id, worker_id=worker_id, lease_seconds=600)
        store = _store(request, project_id)
        asset = store.get_source_asset(source_asset_id, include_content=True)
        registry.heartbeat_task(
            task_id,
            worker_id=worker_id,
            progress=0.1,
            stage="source_registered",
            lease_seconds=600,
        )
        intake = run_document_intake(
            source_name,
            bytes(asset["content"]),
            chunk_size=chunk_size,
            overlap=overlap,
            options=DocumentIntakeOptions(
                parser_backend=parser_backend,
                use_ocr=use_ocr,
                translation_target=translation_target,
            ),
            translator=getattr(request.app.state, "m2_translation_provider", None),
        )
        registry.heartbeat_task(
            task_id,
            worker_id=worker_id,
            progress=0.65,
            stage="candidate_persisting",
            lease_seconds=600,
        )
        version = store.create_document_candidate_from_intake(
            document_id,
            intake,
            metadata={
                "project_id": project_id,
                "source_asset_id": source_asset_id,
                "delivery_task_id": task_id,
            },
            created_by=registry.get_task(task_id).created_by,
        )
        service = M2DeliveryService(
            store,
            ocr_provider=getattr(request.app.state, "m2_ocr_provider", None),
        )
        review_task = service.create_review_task(version, source_asset_id)
        result: dict[str, Any] = {
            "document_version": version.to_dict(include_evidence=False),
            "review_task": review_task,
            "intake": {
                "status": intake.status,
                "quality": intake.quality,
                "errors": intake.errors,
                "warnings": intake.warnings,
                "processing_plan": intake.processing_plan,
            },
        }
        if intake.status == "needs_ocr" or (intake.status == "failed" and intake.profile.requires_ocr):
            result["ocr_job"] = service.queue_ocr(
                document_id=document_id,
                source_asset_id=source_asset_id,
                timeout_seconds=120.0,
            )
        registry.finish_task(
            task_id,
            status=TaskStatus.NEEDS_REVIEW,
            result=result,
            actor=worker_id,
        )
    except Exception as exc:  # pragma: no cover - exercised through task status contract
        with suppress(Exception):
            registry.record_task_failure(project_id, task_id, exc)
        with suppress(Exception):
            registry.finish_task(
                task_id,
                status=TaskStatus.FAILED,
                error_code=str(getattr(exc, "code", "document_intake_failed")),
                error_message=str(exc),
                retryable=True,
                actor=worker_id,
            )


def _run_index_rebuild_task(*, request: Request, project_id: str, task_id: str) -> None:
    registry = _registry(request)
    worker_id = f"local-index-{os.getpid()}"
    try:
        registry.claim_task(task_id, worker_id=worker_id, lease_seconds=600)
        registry.heartbeat_task(
            task_id,
            worker_id=worker_id,
            progress=0.2,
            stage="loading_published_versions",
            lease_seconds=600,
        )
        documents = _store(request, project_id).list_published_document_versions()
        registry.heartbeat_task(
            task_id,
            worker_id=worker_id,
            progress=0.45,
            stage="rebuilding_index",
            lease_seconds=600,
        )
        result = _index(request, project_id).rebuild(
            documents,
            created_by=registry.get_task(task_id).created_by,
        )
        _registry(request).record_projection_state(
            project_id,
            "governed_materials",
            status="ready",
            source_version_id=str(result.get("index_snapshot", {}).get("snapshot_id") or ""),
            item_count=int(result.get("indexed_chunks") or 0),
            details=result,
        )
        registry.finish_task(
            task_id,
            status=TaskStatus.COMPLETED,
            result=result,
            actor=worker_id,
        )
    except Exception as exc:  # pragma: no cover - task contract covers visible failure
        with suppress(Exception):
            registry.record_task_failure(project_id, task_id, exc)
        with suppress(Exception):
            _registry(request).record_projection_state(
                project_id,
                "governed_materials",
                status="failed",
                details={"task_id": task_id, "error_code": str(getattr(exc, "code", "index_rebuild_failed"))},
            )
        with suppress(Exception):
            registry.finish_task(
                task_id,
                status=TaskStatus.FAILED,
                error_code=str(getattr(exc, "code", "index_rebuild_failed")),
                error_message=str(exc),
                retryable=True,
                actor=worker_id,
            )


def _run_ocr_page_retry_task(
    *,
    request: Request,
    project_id: str,
    task_id: str,
    payload_data: Mapping[str, Any],
) -> None:
    registry = _registry(request)
    worker_id = f"local-ocr-retry-{os.getpid()}"
    try:
        registry.claim_task(task_id, worker_id=worker_id, lease_seconds=900)
        registry.heartbeat_task(
            task_id,
            worker_id=worker_id,
            progress=0.15,
            stage="rendering_selected_pages",
            lease_seconds=900,
        )
        result = M2DeliveryService(
            _store(request, project_id),
            ocr_provider=getattr(request.app.state, "m2_ocr_provider", None),
        ).retry_ocr_pages(
            str(payload_data["ocr_job_id"]),
            [int(page) for page in payload_data["pages"]],
        )
        status = TaskStatus.NEEDS_REVIEW if result.get("document_version") else TaskStatus.FAILED
        registry.finish_task(
            task_id,
            status=status,
            result=result,
            error_code=None if result.get("document_version") else "ocr_provider_unavailable",
            error_message="" if result.get("document_version") else "OCR provider is unavailable",
            retryable=not bool(result.get("document_version")),
            actor=worker_id,
        )
    except Exception as exc:  # pragma: no cover - task contract covers visible failure
        with suppress(Exception):
            registry.record_task_failure(project_id, task_id, exc)
        with suppress(Exception):
            registry.finish_task(
                task_id,
                status=TaskStatus.FAILED,
                error_code=str(getattr(exc, "code", "ocr_page_retry_failed")),
                error_message=str(exc),
                retryable=True,
                actor=worker_id,
            )


def _run_graph_extraction_task(
    *,
    request: Request,
    project_id: str,
    task_id: str,
    payload_data: Mapping[str, Any],
) -> None:
    registry = _registry(request)
    worker_id = f"local-graph-{os.getpid()}"
    try:
        registry.claim_task(task_id, worker_id=worker_id, lease_seconds=900)
        payload = GraphExtractionRequest.model_validate(payload_data)
        store = _store(request, project_id)
        documents = [store.get_document_version(item) for item in payload.source_document_version_ids]
        provider = _authorize_graph_extraction_provider(
            request,
            project_id=project_id,
            payload=payload,
            documents=documents,
        )
        registry.heartbeat_task(
            task_id,
            worker_id=worker_id,
            progress=0.25,
            stage="extracting_statements",
            lease_seconds=900,
        )
        model_client = None
        if payload.backend in {"small-model", "llm"}:
            model_client = getattr(request.app.state, "delivery_graph_extractor", None)
        schema, schema_lineage = _resolve_graph_schema(
            registry,
            project_id,
            schema_id=payload.schema_id,
            schema_version=payload.schema_version,
            inline_definition=payload.graph_schema,
        )
        extraction = extract_governed_statements(
            documents,
            backend=payload.backend,
            schema=schema,
            model_client=model_client,
            model_name=payload.model,
            prompt_version=payload.prompt_version,
            temperature=payload.temperature,
            timeout_seconds=float(payload.timeout_seconds or provider["timeout_seconds"]),
            retries=payload.retries,
        )
        if not extraction.statements:
            raise GovernedExtractionError(
                "Automatic extraction produced no statements; keep the material for review or configure a small-model extractor"
            )
        registry.heartbeat_task(
            task_id,
            worker_id=worker_id,
            progress=0.8,
            stage="persisting_graph_candidate",
            lease_seconds=900,
        )
        graph = store.create_graph_candidate(
            source_document_version_ids=payload.source_document_version_ids,
            statements=extraction.statements,
            schema=schema,
            metadata={
                **payload.metadata,
                "delivery_task_id": task_id,
                "extraction": extraction.diagnostics,
                "provider": provider,
                "schema_lineage": schema_lineage,
                "require_statement_review": True,
            },
            created_by=registry.get_task(task_id).created_by,
        )
        registry.finish_task(
            task_id,
            status=TaskStatus.NEEDS_REVIEW,
            result={"graph_version": graph.to_dict(), "extraction": extraction.diagnostics},
            actor=worker_id,
        )
    except Exception as exc:  # pragma: no cover - task contract covers visible failure
        with suppress(Exception):
            registry.record_task_failure(project_id, task_id, exc)
        with suppress(Exception):
            registry.finish_task(
                task_id,
                status=TaskStatus.FAILED,
                error_code=str(getattr(exc, "code", "graph_extraction_failed")),
                error_message=str(exc),
                retryable=True,
                actor=worker_id,
            )


def _run_fmea_generation_task(
    *,
    request: Request,
    project_id: str,
    task_id: str,
    payload_data: Mapping[str, Any],
) -> None:
    registry = _registry(request)
    worker_id = f"local-fmea-{os.getpid()}"
    try:
        registry.claim_task(task_id, worker_id=worker_id, lease_seconds=600)
        payload = FMEARunRequest.model_validate(payload_data)
        registry.heartbeat_task(
            task_id,
            worker_id=worker_id,
            progress=0.35,
            stage="resolving_graph_lineage",
            lease_seconds=600,
        )
        service = _fmea_service(request, project_id)
        task = service.run(
            FMEATaskRequest(
                requested_by=_actor(request, payload.requested_by),
                graph_version_id=payload.graph_version_id,
                document_version_ids=tuple(payload.document_version_ids),
                project_id=project_id,
                template=payload.template,
                template_version=payload.template_version,
                metadata={
                    **payload.metadata,
                    "delivery_task_id": task_id,
                    "require_field_review": True,
                },
            )
        )
        registry.finish_task(
            task_id,
            status=TaskStatus.NEEDS_REVIEW,
            result={"fmea": service.result_payload(task.task_id)},
            actor=worker_id,
        )
    except Exception as exc:  # pragma: no cover - task contract covers visible failure
        with suppress(Exception):
            registry.record_task_failure(project_id, task_id, exc)
        with suppress(Exception):
            registry.finish_task(
                task_id,
                status=TaskStatus.FAILED,
                error_code=str(getattr(exc, "code", "fmea_generation_failed")),
                error_message=str(exc),
                retryable=True,
                actor=worker_id,
            )


def _run_graphrag_evaluation_task(
    *,
    request: Request,
    project_id: str,
    task_id: str,
    payload_data: Mapping[str, Any],
) -> None:
    registry = _registry(request)
    worker_id = f"local-graphrag-eval-{os.getpid()}"
    try:
        registry.claim_task(task_id, worker_id=worker_id, lease_seconds=900)
        graph_version_id = str(payload_data.get("graph_version_id") or "")
        payload = RAGComparisonRequest.model_validate(
            {key: value for key, value in payload_data.items() if key != "graph_version_id"}
        )
        registry.heartbeat_task(
            task_id,
            worker_id=worker_id,
            progress=0.2,
            stage="evaluating_same_question_set",
            lease_seconds=900,
        )
        result = _governed_graphrag(request).compare_same_questions(
            graph_version_id,
            payload.questions,
            top_k=payload.top_k,
        )
        registry.finish_task(
            task_id,
            status=TaskStatus.COMPLETED,
            result={"evaluation": result},
            actor=worker_id,
        )
    except Exception as exc:  # pragma: no cover - visible through durable task state
        with suppress(Exception):
            registry.record_task_failure(project_id, task_id, exc)
        with suppress(Exception):
            registry.finish_task(
                task_id,
                status=TaskStatus.FAILED,
                error_code=str(getattr(exc, "code", "graphrag_evaluation_failed")),
                error_message=str(exc),
                retryable=True,
                actor=worker_id,
            )


def _run_community_summary_task(
    *,
    request: Request,
    project_id: str,
    task_id: str,
    payload_data: Mapping[str, Any],
) -> None:
    registry = _registry(request)
    worker_id = f"local-community-summary-{os.getpid()}"
    try:
        registry.claim_task(task_id, worker_id=worker_id, lease_seconds=900)
        graph_version_id = str(payload_data.get("graph_version_id") or "")
        level = int(payload_data.get("level") or 0)
        projection = registry.get_projection_state(project_id, "graph_store")
        if not projection or projection.get("source_version_id") != graph_version_id:
            raise ProjectWorkspaceError(
                "Community summary requires the requested graph version to be active in GraphStore",
                code="graph_projection_stale",
                details={"graph_version_id": graph_version_id, "projection": projection},
            )
        registry.heartbeat_task(
            task_id,
            worker_id=worker_id,
            progress=0.25,
            stage="detecting_graph_communities",
            lease_seconds=900,
        )
        result = build_governed_community_summaries(
            _graph_store(request, project_id),
            graph_version_id=graph_version_id,
            level=level,
        )
        registry.finish_task(
            task_id,
            status=TaskStatus.COMPLETED,
            result={"community_summary": result},
            actor=worker_id,
        )
    except Exception as exc:  # pragma: no cover - visible through durable task state
        with suppress(Exception):
            registry.record_task_failure(project_id, task_id, exc)
        with suppress(Exception):
            registry.finish_task(
                task_id,
                status=TaskStatus.FAILED,
                error_code=str(getattr(exc, "code", "community_summary_failed")),
                error_message=str(exc),
                retryable=True,
                actor=worker_id,
            )


def _run_feedback_remediation_task(
    *,
    request: Request,
    project_id: str,
    task_id: str,
    payload_data: Mapping[str, Any],
) -> None:
    registry = _registry(request)
    worker_id = f"local-remediation-{os.getpid()}"
    try:
        registry.claim_task(task_id, worker_id=worker_id, lease_seconds=900)
        feedback_id = str(payload_data.get("feedback_id") or "")
        payload = FeedbackRemediationRequest.model_validate(
            {key: value for key, value in payload_data.items() if key != "feedback_id"}
        )
        registry.heartbeat_task(
            task_id,
            worker_id=worker_id,
            progress=0.25,
            stage="remediating_governed_lineage",
            lease_seconds=900,
        )
        result = DeliveryRemediationService(
            _store(request, project_id),
            document_index=_index(request, project_id),
            graph_store=_graph_store(request, project_id),
        ).remediate(
            feedback_id,
            actor=_actor(request, payload.actor),
            document_version_id=payload.document_version_id,
            graph_version_id=payload.graph_version_id,
            corrections=payload.corrections,
        )
        registry.finish_task(
            task_id,
            status=TaskStatus.COMPLETED,
            result={"remediation": result},
            actor=worker_id,
        )
    except Exception as exc:  # pragma: no cover - visible through durable task state
        with suppress(Exception):
            registry.record_task_failure(project_id, task_id, exc)
        with suppress(Exception):
            registry.finish_task(
                task_id,
                status=TaskStatus.FAILED,
                error_code=str(getattr(exc, "code", "feedback_remediation_failed")),
                error_message=str(exc),
                retryable=True,
                actor=worker_id,
            )


def _schedule_retryable_delivery_task(
    background_tasks: BackgroundTasks,
    *,
    request: Request,
    task,
) -> None:
    payload = dict(task.payload)
    if task.task_type == "document_intake":
        background_tasks.add_task(
            _run_uploaded_intake,
            request=request,
            project_id=task.project_id,
            task_id=task.task_id,
            source_asset_id=str(payload["source_asset_id"]),
            document_id=str(payload["document_id"]),
            source_name=str(payload["source_name"]),
            chunk_size=int(payload.get("chunk_size") or 500),
            overlap=int(payload.get("overlap") or 50),
            parser_backend=str(payload.get("parser_backend") or "auto"),
            use_ocr=str(payload.get("use_ocr") or "auto"),
            translation_target=payload.get("translation_target"),
        )
    elif task.task_type == "index_rebuild":
        background_tasks.add_task(
            _run_index_rebuild_task,
            request=request,
            project_id=task.project_id,
            task_id=task.task_id,
        )
    elif task.task_type == "ocr_page_retry":
        background_tasks.add_task(
            _run_ocr_page_retry_task,
            request=request,
            project_id=task.project_id,
            task_id=task.task_id,
            payload_data=payload,
        )
    elif task.task_type == "graph_extraction":
        background_tasks.add_task(
            _run_graph_extraction_task,
            request=request,
            project_id=task.project_id,
            task_id=task.task_id,
            payload_data=payload,
        )
    elif task.task_type == "fmea_generation":
        background_tasks.add_task(
            _run_fmea_generation_task,
            request=request,
            project_id=task.project_id,
            task_id=task.task_id,
            payload_data=payload,
        )
    elif task.task_type == "graphrag_evaluation":
        background_tasks.add_task(
            _run_graphrag_evaluation_task,
            request=request,
            project_id=task.project_id,
            task_id=task.task_id,
            payload_data=payload,
        )
    elif task.task_type == "community_summary":
        background_tasks.add_task(
            _run_community_summary_task,
            request=request,
            project_id=task.project_id,
            task_id=task.task_id,
            payload_data=payload,
        )
    elif task.task_type == "feedback_remediation":
        background_tasks.add_task(
            _run_feedback_remediation_task,
            request=request,
            project_id=task.project_id,
            task_id=task.task_id,
            payload_data=payload,
        )
    else:
        raise ProjectWorkspaceError(
            f"Task type cannot be dispatched for retry: {task.task_type}",
            code="task_retry_dispatch_unsupported",
            details={"task_type": task.task_type},
        )


@router.post("/projects", status_code=201)
async def create_project(request: Request, payload: ProjectCreateRequest):
    try:
        actor = _actor(request, payload.created_by)
        return _registry(request).create_project(
            project_id=payload.project_id,
            name=payload.name,
            description=payload.description,
            domain=payload.domain,
            configuration=payload.configuration,
            data_policy=payload.data_policy,
            acceptance=payload.acceptance,
            created_by=actor,
        ).to_dict()
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/projects/{source_project_id}/copy-template", status_code=201)
async def copy_project_template(
    request: Request,
    source_project_id: str,
    payload: ProjectTemplateCopyRequest,
):
    try:
        registry = _registry(request)
        source = registry.get_project(source_project_id)
        actor = _actor(request, payload.created_by)
        copied = registry.create_project(
            project_id=payload.project_id,
            name=payload.name,
            description=payload.description or f"Template copied from {source_project_id}",
            domain=source.domain,
            configuration=_without_secrets(source.configuration),
            data_policy=_without_secrets(source.data_policy),
            acceptance=_without_secrets(source.acceptance),
            created_by=actor,
        )
        copied_providers: list[str] = []
        for provider in registry.list_providers(project_id=source_project_id)["items"]:
            if str(provider["provider_id"]) in {
                "native-parser",
                "local-ocr",
                "hashing-embedding",
                "rules-graph",
                "local-answer",
            }:
                continue
            clone = {
                key: value
                for key, value in provider.items()
                if key not in {"project_id", "updated_by", "updated_at"}
            }
            clone["configuration"] = _without_secrets(clone.get("configuration") or {})
            clone["health_status"] = "unknown"
            registry.upsert_provider(project_id=payload.project_id, actor=actor, **clone)
            copied_providers.append(str(provider["provider_id"]))
        copied_schemas: list[str] = []
        for schema in registry.list_graph_schemas(project_id=source_project_id)["items"]:
            registry.register_graph_schema(
                project_id=payload.project_id,
                schema_id=str(schema["schema_id"]),
                version=str(schema["version"]),
                definition=_without_secrets(schema["definition"]),
                actor=actor,
                status=str(schema["status"]),
            )
            copied_schemas.append(f"{schema['schema_id']}@{schema['version']}")
        copied_fmea_templates: list[str] = []
        for template in registry.list_fmea_templates(project_id=source_project_id)["items"]:
            registry.register_fmea_template(
                project_id=payload.project_id,
                template_id=str(template["template_id"]),
                version=str(template["version"]),
                definition=_without_secrets(template["definition"]),
                actor=actor,
                status=str(template["status"]),
            )
            copied_fmea_templates.append(f"{template['template_id']}@{template['version']}")
        registry.append_audit(
            project_id=payload.project_id,
            object_type="project",
            object_id=payload.project_id,
            object_version=copied.updated_at,
            action="copy_template",
            actor=actor,
            reason=f"Copied project template from {source_project_id}",
            change_summary={
                "source_project_id": source_project_id,
                "copied_provider_ids": copied_providers,
                "copied_graph_schemas": copied_schemas,
                "copied_fmea_templates": copied_fmea_templates,
                "credentials_copied": False,
            },
            correlation_id=request.headers.get("X-Correlation-ID") or uuid4().hex,
            result="success",
        )
        return {
            **copied.to_dict(),
            "copied_provider_ids": copied_providers,
            "copied_graph_schemas": copied_schemas,
            "copied_fmea_templates": copied_fmea_templates,
            "credentials_copied": False,
        }
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/identity")
async def delivery_identity(request: Request):
    return {
        "actor": _actor(request),
        "identity_source": str(getattr(request.state, "delivery_identity_source", "local")),
        "groups": list(getattr(request.state, "delivery_groups", [])),
        "project_id": _project_id(request),
    }


@router.get("/projects")
async def list_projects(
    request: Request,
    status: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str = "",
):
    try:
        payload = _registry(request).list_projects(
            status=status or None,
            limit=limit,
            cursor=cursor or None,
        )
    except ProjectWorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    else:
        payload["items"] = [
            item for item in payload["items"]
            if _identity_can_access_project(request, item)
        ]
        payload["count"] = len(payload["items"])
        return payload


@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: str):
    try:
        project = _registry(request).get_project(project_id)
        return {**project.to_dict(), "workspace": str(_registry(request).project_dir(project_id))}
    except ProjectWorkspaceError as exc:
        raise _workspace_http_error(exc) from exc


@router.patch("/projects/{project_id}")
async def update_project(request: Request, project_id: str, payload: ProjectUpdateRequest):
    try:
        actor = _actor(request, payload.actor)
        return _registry(request).update_project(
            project_id,
            actor=actor,
            expected_updated_at=payload.expected_version,
            name=payload.name,
            description=payload.description,
            status=payload.status,
            configuration=payload.configuration,
            data_policy=payload.data_policy,
            acceptance=payload.acceptance,
            reason=payload.reason,
            correlation_id=request.headers.get("X-Correlation-ID"),
        ).to_dict()
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/projects/{project_id}/health")
async def project_health(request: Request, project_id: str):
    try:
        return _registry(request).health(project_id)
    except ProjectWorkspaceError as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/projects/{project_id}/metrics/http")
async def project_http_metrics(
    request: Request,
    project_id: str,
    path_prefix: str = "",
    limit: int = Query(default=10000, ge=1, le=50000),
):
    try:
        return _registry(request).http_metrics_summary(
            project_id,
            path_prefix=path_prefix or None,
            limit=limit,
        )
    except ProjectWorkspaceError as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/projects/{project_id}/providers")
async def list_project_providers(
    request: Request,
    project_id: str,
    capability: str = "",
    enabled: bool | None = None,
):
    try:
        return _registry(request).list_providers(
            project_id=project_id,
            capability=capability or None,
            enabled=enabled,
        )
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/projects/{project_id}/providers/health")
async def project_provider_health(request: Request, project_id: str):
    try:
        return _registry(request).provider_health(project_id)
    except ProjectWorkspaceError as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/projects/{project_id}/providers")
async def upsert_project_provider(request: Request, project_id: str, payload: ProviderUpsertRequest):
    try:
        return _registry(request).upsert_provider(
            project_id=project_id,
            provider_id=payload.provider_id,
            capability=payload.capability,
            provider_type=payload.provider_type,
            actor=_actor(request, payload.actor),
            model=payload.model,
            version=payload.version,
            timeout_seconds=payload.timeout_seconds,
            cost_class=payload.cost_class,
            data_policy=payload.data_policy,
            capabilities=payload.capabilities,
            health_status=payload.health_status,
            enabled=payload.enabled,
            configuration=payload.configuration,
            correlation_id=request.headers.get("X-Correlation-ID"),
        )
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/projects/{project_id}/graph-schemas")
async def list_project_graph_schemas(request: Request, project_id: str, status: str = ""):
    try:
        return _registry(request).list_graph_schemas(project_id=project_id, status=status or None)
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/projects/{project_id}/graph-schemas/{schema_id}")
async def get_project_graph_schema(
    request: Request,
    project_id: str,
    schema_id: str,
    version: str | None = None,
    approved_only: bool = True,
):
    try:
        return _registry(request).get_graph_schema(
            project_id,
            schema_id,
            version=version,
            approved_only=approved_only,
        )
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/projects/{project_id}/graph-schemas", status_code=201)
async def register_project_graph_schema(
    request: Request,
    project_id: str,
    payload: GraphSchemaRegistrationRequest,
):
    try:
        return _registry(request).register_graph_schema(
            project_id=project_id,
            schema_id=payload.schema_id,
            version=payload.version,
            definition=payload.definition,
            actor=_actor(request, payload.actor),
            status=payload.status,
            correlation_id=request.headers.get("X-Correlation-ID"),
        )
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/projects/{project_id}/graph-schemas/{schema_id}/{version}/approve")
async def approve_project_graph_schema(
    request: Request,
    project_id: str,
    schema_id: str,
    version: str,
    payload: GraphSchemaApprovalRequest,
):
    try:
        return _registry(request).approve_graph_schema(
            project_id=project_id,
            schema_id=schema_id,
            version=version,
            actor=_actor(request, payload.actor),
            correlation_id=request.headers.get("X-Correlation-ID"),
        )
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/projects/{project_id}/fmea-templates")
async def list_project_fmea_templates(request: Request, project_id: str, status: str = ""):
    try:
        return _registry(request).list_fmea_templates(project_id=project_id, status=status or None)
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/projects/{project_id}/fmea-templates/{template_id}")
async def get_project_fmea_template(
    request: Request,
    project_id: str,
    template_id: str,
    version: str | None = None,
    approved_only: bool = True,
):
    try:
        return _registry(request).get_fmea_template(
            project_id,
            template_id,
            version=version,
            approved_only=approved_only,
        )
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/projects/{project_id}/fmea-templates", status_code=201)
async def register_project_fmea_template(
    request: Request,
    project_id: str,
    payload: FMEATemplateRegistrationRequest,
):
    try:
        return _registry(request).register_fmea_template(
            project_id=project_id,
            template_id=payload.template_id,
            version=payload.version,
            definition=payload.definition,
            actor=_actor(request, payload.actor),
            status=payload.status,
            correlation_id=request.headers.get("X-Correlation-ID"),
        )
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/projects/{project_id}/fmea-templates/{template_id}/{version}/approve")
async def approve_project_fmea_template(
    request: Request,
    project_id: str,
    template_id: str,
    version: str,
    payload: FMEATemplateApprovalRequest,
):
    try:
        return _registry(request).approve_fmea_template(
            project_id=project_id,
            template_id=template_id,
            version=version,
            actor=_actor(request, payload.actor),
            correlation_id=request.headers.get("X-Correlation-ID"),
        )
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/projects/{project_id}/export-package")
async def export_project_package(request: Request, project_id: str):
    try:
        package = _registry(request).build_export_package(project_id)
        path = Path(package["path"])
        return FileResponse(
            path,
            media_type="application/zip",
            filename=path.name,
            headers={
                "X-PowerRAG-Package-SHA256": str(package["sha256"]),
                "X-PowerRAG-Package-Files": str(package["file_count"]),
            },
        )
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/projects/restore", status_code=201)
async def restore_project_package(
    request: Request,
    file: Annotated[UploadFile, File()],
    project_id: Annotated[str, Form()],
    name: Annotated[str, Form()],
    actor: Annotated[str, Form()] = "local-user",
):
    try:
        payload = await file.read()
        if not payload:
            raise ValueError("Project package is empty")
        registry = _registry(request)
        imports_dir = registry.root_dir / "imports"
        imports_dir.mkdir(parents=True, exist_ok=True)
        package_path = imports_dir / f"{uuid4().hex}.zip"
        package_path.write_bytes(payload)
        return registry.restore_export_package(
            package_path,
            project_id=project_id,
            name=name,
            actor=_actor(request, actor),
        )
    except (ValueError, OSError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/projects/{project_id}/tasks", status_code=201)
async def create_delivery_task(request: Request, project_id: str, payload: DeliveryTaskCreateRequest):
    try:
        actor = _actor(request, payload.created_by)
        task = _registry(request).create_task(
            project_id=project_id,
            task_type=payload.task_type,
            stage=payload.stage,
            created_by=actor,
            payload=payload.payload,
            object_type=payload.object_type,
            object_id=payload.object_id,
            severity=payload.severity,
            idempotency_key=payload.idempotency_key,
            correlation_id=payload.correlation_id or request.headers.get("X-Correlation-ID"),
            retryable=payload.retryable,
        )
        return task.to_dict()
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/projects/{project_id}/tasks")
async def list_delivery_tasks(
    request: Request,
    project_id: str,
    status: str = "",
    stage: str = "",
    severity: str = "",
    task_type: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str = "",
):
    try:
        return _registry(request).list_tasks(
            project_id=project_id,
            statuses=tuple(item.strip() for item in status.split(",") if item.strip()),
            stage=stage or None,
            severity=severity or None,
            task_type=task_type or None,
            limit=limit,
            cursor=cursor or None,
        )
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/tasks/{task_id}")
async def get_delivery_task(request: Request, task_id: str, project_id: str = ""):
    try:
        return _registry(request).get_task(
            task_id,
            project_id=project_id or _project_id(request),
        ).to_dict()
    except ProjectWorkspaceError as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/tasks/{task_id}/heartbeat")
async def heartbeat_delivery_task(request: Request, task_id: str, payload: DeliveryTaskHeartbeatRequest):
    try:
        _registry(request).get_task(task_id, project_id=_project_id(request))
        return _registry(request).heartbeat_task(
            task_id,
            worker_id=payload.worker_id,
            progress=payload.progress,
            stage=payload.stage,
            lease_seconds=payload.lease_seconds,
        ).to_dict()
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/tasks/{task_id}/cancel")
async def cancel_delivery_task(request: Request, task_id: str, payload: DeliveryTaskActionRequest):
    try:
        actor = _actor(request, payload.actor)
        _registry(request).get_task(task_id, project_id=_project_id(request))
        return _registry(request).cancel_task(
            task_id,
            actor=actor,
            reason=payload.reason or "Cancelled by user",
        ).to_dict()
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/tasks/{task_id}/retry", status_code=201)
async def retry_delivery_task(
    request: Request,
    background_tasks: BackgroundTasks,
    task_id: str,
    payload: DeliveryTaskActionRequest,
):
    try:
        actor = _actor(request, payload.actor)
        registry = _registry(request)
        original = registry.get_task(task_id, project_id=_project_id(request))
        if original.task_type not in {
            "document_intake",
            "ocr_page_retry",
            "index_rebuild",
            "graph_extraction",
            "fmea_generation",
            "graphrag_evaluation",
            "community_summary",
            "feedback_remediation",
        }:
            raise ProjectWorkspaceError(
                f"Task type cannot be dispatched for retry: {original.task_type}",
                code="task_retry_dispatch_unsupported",
                details={"task_type": original.task_type},
            )
        retried = registry.retry_task(
            task_id,
            actor=actor,
            idempotency_key=payload.idempotency_key,
        )
        _schedule_retryable_delivery_task(background_tasks, request=request, task=retried)
        return retried.to_dict()
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/tasks/batch-retry")
async def batch_retry_delivery_tasks(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: DeliveryTaskBatchRetryRequest,
):
    registry = _registry(request)
    project_id = _project_id(request)
    actor = _actor(request, payload.actor)
    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for task_id in dict.fromkeys(payload.task_ids):
        try:
            original = registry.get_task(task_id, project_id=project_id)
            if original.task_type not in {
                "document_intake",
                "ocr_page_retry",
                "index_rebuild",
                "graph_extraction",
                "fmea_generation",
                "graphrag_evaluation",
                "community_summary",
                "feedback_remediation",
            }:
                raise ProjectWorkspaceError(
                    f"Task type cannot be dispatched for retry: {original.task_type}",
                    code="task_retry_dispatch_unsupported",
                )
            retried = registry.retry_task(
                task_id,
                actor=actor,
                idempotency_key=(
                    f"{payload.idempotency_key}:{task_id}" if payload.idempotency_key else None
                ),
            )
            _schedule_retryable_delivery_task(background_tasks, request=request, task=retried)
            items.append(retried.to_dict())
        except (ValueError, ProjectWorkspaceError) as exc:
            errors.append(
                {
                    "task_id": task_id,
                    "code": str(getattr(exc, "code", "batch_retry_failed")),
                    "message": str(exc),
                }
            )
    return {"project_id": project_id, "items": items, "errors": errors}


@router.post("/tasks/{task_id}/assign")
async def assign_delivery_task(request: Request, task_id: str, payload: DeliveryTaskAssignRequest):
    try:
        registry = _registry(request)
        registry.get_task(task_id, project_id=_project_id(request))
        return registry.assign_task(
            task_id,
            assignee=payload.assignee,
            actor=_actor(request, payload.actor),
        ).to_dict()
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/tasks/{task_id}/comments", status_code=201)
async def add_delivery_task_comment(
    request: Request,
    task_id: str,
    payload: DeliveryTaskCommentRequest,
):
    try:
        registry = _registry(request)
        registry.get_task(task_id, project_id=_project_id(request))
        return registry.add_task_comment(
            task_id,
            actor=_actor(request, payload.actor),
            message=payload.message,
            correlation_id=request.headers.get("X-Correlation-ID"),
        )
    except (ValueError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/tasks/{task_id}/comments")
async def list_delivery_task_comments(request: Request, task_id: str):
    try:
        registry = _registry(request)
        registry.get_task(task_id, project_id=_project_id(request))
        items = registry.list_task_comments(task_id)
        return {"task_id": task_id, "items": items, "count": len(items)}
    except ProjectWorkspaceError as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/projects/{project_id}/audit")
async def list_project_audit(
    request: Request,
    project_id: str,
    object_type: str = "",
    object_id: str = "",
    limit: int = Query(default=100, ge=1, le=500),
    before_audit_id: int | None = None,
):
    try:
        return _registry(request).list_audit(
            project_id=project_id,
            object_type=object_type or None,
            object_id=object_id or None,
            limit=limit,
            before_audit_id=before_audit_id,
        )
    except ProjectWorkspaceError as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/projects/{project_id}/documents/upload", status_code=202)
async def upload_project_document(
    request: Request,
    background_tasks: BackgroundTasks,
    project_id: str,
    file: Annotated[UploadFile, File()],
    document_id: Annotated[str, Form()],
    created_by: Annotated[str, Form()] = "local-user",
    idempotency_key: Annotated[str | None, Form()] = None,
    parser_backend: Annotated[str, Form()] = "auto",
    use_ocr: Annotated[str, Form()] = "auto",
    translation_target: Annotated[str | None, Form()] = None,
    chunk_size: Annotated[int, Form()] = 500,
    overlap: Annotated[int, Form()] = 50,
    allow_duplicate: Annotated[bool, Form()] = False,
):
    try:
        if parser_backend not in {"auto", "native", "deepdoc", "mineru", "docling", "unstructured"}:
            raise ValueError("Unsupported parser_backend")
        if use_ocr not in {"auto", "always", "never"}:
            raise ValueError("use_ocr must be auto, always, or never")
        if translation_target not in {None, "", "zh", "en"}:
            raise ValueError("translation_target must be zh or en")
        if not 80 <= int(chunk_size) <= 5000 or not 0 <= int(overlap) <= 1000:
            raise ValueError("Invalid chunk_size or overlap")
        source_name = Path(str(file.filename or "upload.bin")).name
        raw = await file.read()
        maximum = int(os.environ.get("RAG_DELIVERY_MAX_UPLOAD_BYTES", str(512 * 1024 * 1024)))
        if not raw:
            raise ValueError("Uploaded file is empty")
        if len(raw) > maximum:
            raise ProjectWorkspaceError(
                "Uploaded file exceeds the configured size limit",
                code="upload_too_large",
                details={"byte_size": len(raw), "maximum": maximum},
            )
        registry = _registry(request)
        store = _store(request, project_id)
        content_hash = hashlib.sha256(raw).hexdigest()
        existing_asset = store.find_source_asset_by_content_hash(content_hash)
        if existing_asset is not None and not allow_duplicate:
            raise ProjectWorkspaceError(
                "An asset with the same SHA-256 already exists; confirm duplicate processing explicitly",
                code="duplicate_source_asset",
                details={
                    "content_hash": content_hash,
                    "duplicate_of": existing_asset,
                },
            )
        actor = _actor(request, created_by)
        service = M2DeliveryService(store, ocr_provider=getattr(request.app.state, "m2_ocr_provider", None))
        source_asset = service.register_source(
            document_id=document_id,
            source_name=source_name,
            content=raw,
            created_by=actor,
        )
        asset_path = registry.project_dir(project_id) / "source_assets" / f"{source_asset['asset_id']}_{source_name}"
        asset_path.write_bytes(raw)
        task = registry.create_task(
            project_id=project_id,
            task_type="document_intake",
            stage="queued",
            created_by=actor,
            payload={
                "document_id": document_id,
                "source_name": source_name,
                "source_asset_id": source_asset["asset_id"],
                "byte_size": len(raw),
                "parser_backend": parser_backend,
                "use_ocr": use_ocr,
                "translation_target": translation_target or None,
                "chunk_size": int(chunk_size),
                "overlap": int(overlap),
            },
            object_type="source_asset",
            object_id=str(source_asset["asset_id"]),
            idempotency_key=idempotency_key,
            correlation_id=request.headers.get("X-Correlation-ID"),
            retryable=True,
        )
        if task.status is TaskStatus.QUEUED:
            background_tasks.add_task(
                _run_uploaded_intake,
                request=request,
                project_id=project_id,
                task_id=task.task_id,
                source_asset_id=str(source_asset["asset_id"]),
                document_id=document_id,
                source_name=source_name,
                chunk_size=int(chunk_size),
                overlap=int(overlap),
                parser_backend=parser_backend,
                use_ocr=use_ocr,
                translation_target=translation_target or None,
            )
        return {
            "project_id": project_id,
            "source_asset": {**source_asset, "path": str(asset_path)},
            "task": task.to_dict(),
        }
    except (ValueError, ProjectWorkspaceError, GovernanceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/source-assets")
async def list_source_assets(
    request: Request,
    project_id: str = "",
    document_id: str = "",
    source_name: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    before_created_at: str = "",
):
    try:
        resolved_project_id = _project_id(request, project_id or None)
        items = _store(request, resolved_project_id).list_source_assets(
            document_id=document_id or None,
            source_name=source_name or None,
            limit=limit + 1,
            before_created_at=before_created_at or None,
        )
        has_more = len(items) > limit
        items = items[:limit]
        return {
            "project_id": resolved_project_id,
            "items": items,
            "count": len(items),
            "next_cursor": items[-1]["created_at"] if has_more and items else None,
        }
    except (ValueError, GovernanceError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/documents")
async def list_documents(
    request: Request,
    project_id: str = "",
    status: str = "",
    document_id: str = "",
    source_name: str = "",
    issue_code: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    before_created_at: str = "",
):
    try:
        resolved_project_id = _project_id(request, project_id or None)
        items = _store(request, resolved_project_id).list_document_catalog(
            status=status or None,
            document_id=document_id or None,
            source_name=source_name or None,
            issue_code=issue_code or None,
            limit=limit + 1,
            before_created_at=before_created_at or None,
        )
        has_more = len(items) > limit
        items = items[:limit]
        return {
            "project_id": resolved_project_id,
            "items": [item.to_dict(include_evidence=False) for item in items],
            "count": len(items),
            "next_cursor": items[-1].created_at if has_more and items else None,
        }
    except (ValueError, GovernanceError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/review-queue")
async def review_queue(
    request: Request,
    project_id: str = "",
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        resolved_project_id = _project_id(request, project_id or None)
        store = _store(request, resolved_project_id)
        documents = store.list_open_document_review_tasks(limit=limit)
        graphs = [
            {
                "project_id": resolved_project_id,
                "target_type": "graph",
                "target_id": item.graph_version_id,
                "status": item.status.value,
                "created_at": item.created_at,
                "quality_issues": [issue.to_dict() for issue in item.quality_issues],
            }
            for item in store.list_graph_versions()
            if item.status in {ContentStatus.CANDIDATE, ContentStatus.NEEDS_REVIEW}
        ][:limit]
        fmea = [
            {
                "project_id": resolved_project_id,
                "target_type": "fmea",
                "target_id": item.task_id,
                "status": item.status.value,
                "created_at": item.created_at,
                "error_count": len(item.errors),
            }
            for item in store.list_fmea_tasks(status=TaskStatus.NEEDS_REVIEW, limit=limit)
        ]
        items = [
            *(
                {
                    **item,
                    "target_type": "document",
                    "target_id": item["document_version_id"],
                }
                for item in documents
            ),
            *graphs,
            *fmea,
        ]
        return {
            "project_id": resolved_project_id,
            "items": items[:limit],
            "count": min(len(items), limit),
            "counts": {"documents": len(documents), "graphs": len(graphs), "fmea": len(fmea)},
        }
    except (ValueError, GovernanceError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/documents/intake")
async def intake_document(request: Request, payload: IntakeRequest):
    try:
        actor = _actor(request, str(payload.metadata.get("actor") or ""))
        raw_bytes = base64.b64decode(payload.content_base64, validate=True)
        source_asset = _m2(request).register_source(
            document_id=payload.document_id,
            source_name=payload.source_name,
            content=raw_bytes,
            created_by=actor,
        )
        intake = run_document_intake(
            payload.source_name,
            raw_bytes,
            chunk_size=payload.chunk_size,
            overlap=payload.overlap,
            options=DocumentIntakeOptions(
                parser_backend=payload.parser_backend,
                use_ocr=payload.use_ocr,
                translation_target=payload.translation_target,
            ),
            translator=getattr(request.app.state, "m2_translation_provider", None),
        )
        version = _store(request).create_document_candidate_from_intake(
            payload.document_id,
            intake,
            metadata={**payload.metadata, "source_asset_id": source_asset["asset_id"]},
            created_by=actor,
        )
        review_task = _m2(request).create_review_task(version, str(source_asset["asset_id"]))
        ocr_job = None
        if intake.status == "needs_ocr" or (intake.status == "failed" and intake.profile.requires_ocr):
            ocr_job = _m2(request).queue_ocr(
                document_id=payload.document_id,
                source_asset_id=str(source_asset["asset_id"]),
                timeout_seconds=payload.ocr_page_timeout_seconds,
            )
            if payload.auto_run_ocr:
                completed = _m2(request).execute_ocr(str(ocr_job["job_id"]))
                ocr_job = completed["ocr_job"]
                if completed["document_version"] is not None:
                    return {
                        **completed,
                        "source_asset": source_asset,
                        "initial_document_version": version.to_dict(include_evidence=False),
                        "intake": {
                            "status": intake.status,
                            "quality": intake.quality,
                            "errors": intake.errors,
                            "warnings": intake.warnings,
                            "processing_plan": intake.processing_plan,
                        },
                    }
        return {
            "document_version": version.to_dict(include_evidence=False),
            "source_asset": source_asset,
            "review_task": review_task,
            "ocr_job": ocr_job,
            "intake": {
                "status": intake.status,
                "quality": intake.quality,
                "errors": intake.errors,
                "warnings": intake.warnings,
                "processing_plan": intake.processing_plan,
            },
        }
    except (ValueError, binascii.Error, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.post("/documents/intake/ocr-result")
async def intake_ocr_result(request: Request, payload: OCRResultIntakeRequest):
    """Accept page-level output from the repository OCR pipeline.

    OCR execution may happen in a batch worker, but ingestion remains governed:
    missing/blank/low-confidence/high-layout-risk pages are preserved as
    review issues rather than silently entering the canonical library.
    """

    try:
        actor = _actor(request, str(payload.metadata.get("actor") or ""))
        source_asset_id = payload.source_asset_id
        if payload.source_content_base64:
            source_content = base64.b64decode(payload.source_content_base64, validate=True)
            source_asset_id = str(
                _m2(request).register_source(
                    document_id=payload.document_id,
                    source_name=payload.source_name,
                    content=source_content,
                    created_by=actor,
                )["asset_id"]
            )
        pages = [item.model_dump() for item in payload.pages]
        version, quality, review_task = _m2(request).ingest_ocr_result(
            document_id=payload.document_id,
            source_name=payload.source_name,
            pages=pages,
            expected_pages=payload.expected_pages or max(item.page for item in payload.pages),
            low_confidence_threshold=payload.low_confidence_threshold,
            source_asset_id=source_asset_id,
            job_id=payload.job_id,
            timeout_pages=payload.timeout_pages,
            failed_pages=payload.failed_pages,
            metadata=payload.metadata,
            created_by=actor,
        )
        return {
            "document_version": version.to_dict(),
            "ocr_quality": quality,
            "review_task": review_task,
        }
    except (ValueError, binascii.Error, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.post("/documents/{version_id}/revise")
async def revise_document(request: Request, version_id: str, payload: DocumentRevisionRequest):
    try:
        actor = _actor(request, payload.reviewer)
        store = _store(request)
        current = store.get_document_version(version_id)
        _check_expected_version(
            payload.expected_version,
            allowed={current.version_id, str(current.version), current.content_hash},
        )
        revised = store.create_document_revision(
            version_id,
            reviewer=actor,
            comment=payload.comment,
            corrections=payload.corrections,
        )
        _audit_action(
            request,
            project_id=_project_id(request),
            object_type="document",
            object_id=revised.document_id,
            object_version=revised.version_id,
            action="revise",
            actor=actor,
            reason=payload.comment,
            change_summary={"field_keys": sorted(payload.corrections)},
        )
        return {
            "document_version": revised.to_dict(),
            "reviews": [item.to_dict() for item in _store(request).list_reviews("document", revised.version_id)],
        }
    except ProjectWorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.get("/documents/{version_id}/review-package")
async def document_review_package(
    request: Request,
    version_id: str,
    page: int = Query(default=1, ge=1),
):
    try:
        return _m2(request).review_package(version_id, page=page)
    except GovernanceError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/documents/source-assets/{asset_id}/pages/{page}")
async def get_source_asset_page(request: Request, asset_id: str, page: int):
    try:
        content, media_type = _m2(request).source_page(asset_id, page=page)
        return Response(content=content, media_type=media_type, headers={"Cache-Control": "no-store"})
    except GovernanceError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/documents/ocr-jobs/{job_id}")
async def get_ocr_job(request: Request, job_id: str):
    try:
        return _store(request).get_ocr_job(job_id)
    except GovernanceError as exc:
        raise _not_found(exc) from exc


@router.post("/documents/ocr-jobs/{job_id}/run")
async def run_ocr_job(request: Request, job_id: str):
    try:
        return _m2(request).execute_ocr(job_id)
    except GovernanceError as exc:
        raise _not_found(exc) from exc
    except (ValueError, RuntimeError) as exc:
        raise _bad_request(exc) from exc


@router.post("/documents/ocr-jobs/{job_id}/retry-pages", status_code=202)
async def retry_ocr_job_pages(
    request: Request,
    background_tasks: BackgroundTasks,
    job_id: str,
    payload: OCRPageRetryRequest,
):
    try:
        project_id = _project_id(request)
        store = _store(request, project_id)
        job = store.get_ocr_job(job_id)
        expected_pages = int(job.get("expected_pages") or 0)
        requested_pages = sorted({int(page) for page in payload.pages})
        if not requested_pages or requested_pages[0] < 1:
            raise ValueError("OCR retry requires positive page numbers")
        if expected_pages and requested_pages[-1] > expected_pages:
            raise ValueError(f"OCR page selection must be within 1..{expected_pages}")
        actor = _actor(request)
        task = _registry(request).create_task(
            project_id=project_id,
            task_type="ocr_page_retry",
            stage="queued",
            created_by=actor,
            payload={"ocr_job_id": job_id, "pages": requested_pages},
            object_type="ocr_job",
            object_id=job_id,
            idempotency_key=payload.idempotency_key or request.headers.get("Idempotency-Key"),
            correlation_id=request.headers.get("X-Correlation-ID"),
            retryable=True,
        )
        if task.status is TaskStatus.QUEUED:
            background_tasks.add_task(
                _run_ocr_page_retry_task,
                request=request,
                project_id=project_id,
                task_id=task.task_id,
                payload_data=task.payload,
            )
        return {"project_id": project_id, "task": task.to_dict()}
    except (ValueError, GovernanceError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/documents/{version_id}")
async def get_document(request: Request, version_id: str):
    try:
        return _store(request).get_document_version(version_id).to_dict()
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/documents-search")
async def search_documents(
    request: Request,
    q: str = Query(min_length=1),
    top_k: int = Query(default=5, ge=1, le=50),
    version_ids: str = "",
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid",
):
    try:
        versions = tuple(item.strip() for item in version_ids.split(",") if item.strip())
        return _index(request).query(q, top_k=top_k, document_version_ids=versions, mode=mode)
    except GovernedIndexError as exc:
        raise _bad_request(exc) from exc


@router.get("/evidence/{evidence_id}/open")
async def open_evidence_locator(request: Request, evidence_id: str):
    """Resolve a displayed citation back to the registered source page and block."""

    try:
        store = _store(request)
        evidence = store.get_evidence(evidence_id)
        document = store.get_document_version(evidence.document_version_id)
        source_asset_id = str(document.metadata.get("source_asset_id") or "")
        if not source_asset_id:
            raise ProjectWorkspaceError(
                "Citation cannot be resolved because its document version has no source asset",
                code="citation_integrity_error",
                details={"evidence_id": evidence_id, "document_version_id": document.version_id},
            )
        try:
            page = int(evidence.page or 1)
            image_bytes, mime_type = _m2(request).source_page(source_asset_id, page=page)
        except (TypeError, ValueError, GovernanceError) as exc:
            raise ProjectWorkspaceError(
                "Citation source page cannot be opened",
                code="citation_integrity_error",
                details={
                    "evidence_id": evidence_id,
                    "document_version_id": document.version_id,
                    "source_asset_id": source_asset_id,
                    "page": evidence.page,
                    "cause": str(exc),
                },
            ) from exc
        return {
            "project_id": _project_id(request),
            "evidence": evidence.to_dict(),
            "document": document.to_dict(include_evidence=False),
            "source": {
                "asset_id": source_asset_id,
                "page": page,
                "mime_type": mime_type,
                "content_base64": base64.b64encode(image_bytes).decode("ascii"),
            },
        }
    except (GovernanceError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/documents-index/status")
async def document_index_status(request: Request):
    try:
        return _index(request).status()
    except GovernedIndexError as exc:
        raise _bad_request(exc) from exc


@router.post("/documents-index/rebuild")
async def rebuild_document_index(
    request: Request,
    background_tasks: BackgroundTasks,
    response: Response,
    background: bool = Query(default=False),
):
    try:
        if background:
            project_id = _project_id(request)
            actor = _actor(request)
            task = _registry(request).create_task(
                project_id=project_id,
                task_type="index_rebuild",
                stage="queued",
                created_by=actor,
                payload={"project_id": project_id},
                object_type="index",
                object_id="governed_materials",
                idempotency_key=request.headers.get("Idempotency-Key"),
                correlation_id=request.headers.get("X-Correlation-ID"),
                retryable=True,
            )
            if task.status is TaskStatus.QUEUED:
                background_tasks.add_task(
                    _run_index_rebuild_task,
                    request=request,
                    project_id=project_id,
                    task_id=task.task_id,
                )
            response.status_code = 202
            return {"project_id": project_id, "task": task.to_dict()}
        project_id = _project_id(request)
        result = _index(request).rebuild(
            _store(request).list_published_document_versions(),
            created_by=_actor(request),
        )
        _registry(request).record_projection_state(
            project_id,
            "governed_materials",
            status="ready",
            source_version_id=str(result.get("index_snapshot", {}).get("snapshot_id") or ""),
            item_count=int(result.get("indexed_chunks") or 0),
            details=result,
        )
        return result  # noqa: TRY300
    except (GovernanceError, GovernedIndexError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/documents/{version_id}/review")
async def review_document(request: Request, version_id: str, payload: ReviewRequest):
    try:
        actor = _actor(request, payload.reviewer)
        store = _store(request)
        current = store.get_document_version(version_id)
        _check_expected_version(
            payload.expected_version,
            allowed={current.version_id, str(current.version), current.content_hash},
        )
        review = store.record_review(
            target_type="document",
            target_id=version_id,
            reviewer=actor,
            decision=ReviewDecision(payload.decision),
            comment=payload.comment,
            corrections=payload.corrections,
        )
        _audit_action(
            request,
            project_id=_project_id(request),
            object_type="document",
            object_id=version_id,
            object_version=version_id,
            action=f"review_{review.decision.value}",
            actor=actor,
            reason=payload.comment,
            change_summary={"correction_keys": sorted(payload.corrections)},
        )
        return review.to_dict()
    except ProjectWorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.post("/documents/batch-review")
async def batch_review_documents(request: Request, payload: DocumentBatchReviewRequest):
    project_id = _project_id(request)
    actor = _actor(request, payload.reviewer)
    operation = None
    try:
        operation, cached = _begin_idempotent_operation(
            request,
            project_id=project_id,
            action="batch_review_documents",
            actor=actor,
            object_type="document_batch",
            object_id=hashlib.sha256("\n".join(sorted(set(payload.version_ids))).encode()).hexdigest()[:20],
            idempotency_key=payload.idempotency_key,
        )
        if cached is not None:
            return cached
        store = _store(request)
        items: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for version_id in dict.fromkeys(payload.version_ids):
            try:
                document = store.get_document_version(version_id)
                review = store.record_review(
                    target_type="document",
                    target_id=version_id,
                    reviewer=actor,
                    decision=ReviewDecision(payload.decision),
                    comment=payload.comment,
                    corrections={"batch_review": True},
                )
                items.append(
                    {
                        "version_id": version_id,
                        "document_id": document.document_id,
                        "review": review.to_dict(),
                        "publication_gate_still_required": True,
                    }
                )
                _audit_action(
                    request,
                    project_id=project_id,
                    object_type="document",
                    object_id=document.document_id,
                    object_version=version_id,
                    action=f"batch_review_{payload.decision}",
                    actor=actor,
                    reason=payload.comment,
                    change_summary={"publication_gate_bypassed": False},
                )
            except (ValueError, GovernanceError) as exc:
                errors.append({"version_id": version_id, "code": "batch_review_failed", "message": str(exc)})
        response = {
            "project_id": project_id,
            "items": items,
            "errors": errors,
            "publication_gate_bypassed": False,
        }
        _complete_idempotent_operation(request, operation, response=response, actor=actor)
        return response  # noqa: TRY300
    except (GovernanceError, ProjectWorkspaceError) as exc:
        _fail_idempotent_operation(request, operation, exc, actor=actor)
        raise _workspace_http_error(exc) from exc


@router.post("/documents/{version_id}/publish")
async def publish_document(request: Request, version_id: str, payload: PublishRequest | None = None):
    payload = payload or PublishRequest()
    project_id = _project_id(request)
    actor = _actor(request, payload.actor)
    operation = None
    try:
        store = _store(request)
        current = store.get_document_version(version_id)
        _check_expected_version(
            payload.expected_version,
            allowed={current.version_id, str(current.version), current.content_hash},
        )
        operation, cached = _begin_idempotent_operation(
            request,
            project_id=project_id,
            action="publish_document",
            actor=actor,
            object_type="document",
            object_id=version_id,
            idempotency_key=payload.idempotency_key,
        )
        if cached is not None:
            return cached
        document = store.publish_document(version_id)
        try:
            retrieval_sync = _index(request).sync_document(document, created_by=actor)
            _registry(request).record_projection_state(
                project_id,
                "governed_materials",
                status="ready",
                source_version_id=str(retrieval_sync.get("index_snapshot", {}).get("snapshot_id") or version_id),
                item_count=int(retrieval_sync.get("collection_count") or retrieval_sync.get("indexed_chunks") or 0),
                details=retrieval_sync,
            )
        except Exception as exc:
            _registry(request).record_projection_state(
                project_id,
                "governed_materials",
                status="failed",
                source_version_id=version_id,
                details={"error_code": str(getattr(exc, "code", "retrieval_sync_failed")), "message": str(exc)},
            )
            raise
        response = {**document.to_dict(), "retrieval_index": retrieval_sync}
        reviews = store.list_reviews("document", version_id)
        reviewer = reviews[-1].reviewer if reviews else None
        _audit_action(
            request,
            project_id=project_id,
            object_type="document",
            object_id=document.document_id,
            object_version=version_id,
            action="publish",
            actor=actor,
            reason=payload.comment,
            change_summary={
                "reviewer": reviewer,
                "same_person_role": bool(reviewer and reviewer == actor),
                "retrieval_index": response["retrieval_index"],
            },
        )
        _complete_idempotent_operation(request, operation, response=response, actor=actor)
    except (GovernanceError, GovernedIndexError, ProjectWorkspaceError) as exc:
        _fail_idempotent_operation(request, operation, exc, actor=actor)
        if isinstance(exc, ProjectWorkspaceError):
            raise _workspace_http_error(exc) from exc
        raise _bad_request(exc) from exc
    return response


@router.get("/documents/compare/{left_id}/{right_id}")
async def compare_documents(request: Request, left_id: str, right_id: str):
    try:
        return _store(request).compare_document_versions(left_id, right_id)
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/documents/{document_id}/rollback")
async def rollback_document(request: Request, document_id: str, payload: RollbackRequest):
    try:
        project_id = _project_id(request)
        actor = _actor(request, payload.reviewer)
        document = _store(request).rollback_document(
            document_id,
            payload.target_version_id,
            reviewer=actor,
            comment=payload.comment,
        )
        retrieval_sync = _index(request).sync_document(document, created_by=actor)
        _registry(request).record_projection_state(
            project_id,
            "governed_materials",
            status="ready",
            source_version_id=str(retrieval_sync.get("index_snapshot", {}).get("snapshot_id") or document.version_id),
            item_count=int(retrieval_sync.get("collection_count") or retrieval_sync.get("indexed_chunks") or 0),
            details={**retrieval_sync, "rollback_target": payload.target_version_id},
        )
        _audit_action(
            request,
            project_id=project_id,
            object_type="document",
            object_id=document_id,
            object_version=document.version_id,
            action="rollback",
            actor=actor,
            reason=payload.comment,
            change_summary={"target_version_id": payload.target_version_id, "retrieval_index": retrieval_sync},
        )
        return {**document.to_dict(), "retrieval_index": retrieval_sync}
    except (GovernanceError, GovernedIndexError) as exc:
        raise _bad_request(exc) from exc


@router.post("/graphs/candidates")
async def create_graph_candidate(request: Request, payload: GraphCandidateRequest):
    try:
        project_id = _project_id(request)
        schema, schema_lineage = _resolve_graph_schema(
            _registry(request),
            project_id,
            schema_id=payload.schema_id,
            schema_version=payload.schema_version,
            inline_definition=payload.graph_schema,
        )
        graph = _store(request).create_graph_candidate(
            source_document_version_ids=payload.source_document_version_ids,
            statements=payload.statements,
            schema=schema,
            metadata={**payload.metadata, "schema_lineage": schema_lineage},
            created_by=_actor(request, str(payload.metadata.get("actor") or "")),
        )
        return graph.to_dict()
    except (ValueError, GovernanceError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/graphs/extract")
async def extract_graph_candidate(
    request: Request,
    payload: GraphExtractionRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    background: bool = Query(default=False),
):
    try:
        if background:
            project_id = _project_id(request)
            actor = _actor(request, str(payload.metadata.get("actor") or ""))
            task = _registry(request).create_task(
                project_id=project_id,
                task_type="graph_extraction",
                stage="queued",
                created_by=actor,
                payload=payload.model_dump(by_alias=True),
                object_type="graph",
                idempotency_key=(
                    request.headers.get("Idempotency-Key")
                    or str(payload.metadata.get("idempotency_key") or "")
                    or None
                ),
                correlation_id=request.headers.get("X-Correlation-ID"),
                retryable=True,
            )
            if task.status is TaskStatus.QUEUED:
                background_tasks.add_task(
                    _run_graph_extraction_task,
                    request=request,
                    project_id=project_id,
                    task_id=task.task_id,
                    payload_data=task.payload,
                )
            response.status_code = 202
            return {"project_id": project_id, "task": task.to_dict()}
        store = _store(request)
        documents = [store.get_document_version(item) for item in payload.source_document_version_ids]
        provider = _authorize_graph_extraction_provider(
            request,
            project_id=_project_id(request),
            payload=payload,
            documents=documents,
        )
        model_client = None
        if payload.backend in {"small-model", "llm"}:
            model_client = getattr(request.app.state, "delivery_graph_extractor", None)
        project_id = _project_id(request)
        schema, schema_lineage = _resolve_graph_schema(
            _registry(request),
            project_id,
            schema_id=payload.schema_id,
            schema_version=payload.schema_version,
            inline_definition=payload.graph_schema,
        )
        extraction = extract_governed_statements(
            documents,
            backend=payload.backend,
            schema=schema,
            model_client=model_client,
            model_name=payload.model,
            prompt_version=payload.prompt_version,
            temperature=payload.temperature,
            timeout_seconds=float(payload.timeout_seconds or provider["timeout_seconds"]),
            retries=payload.retries,
        )
        if not extraction.statements:
            raise GovernedExtractionError(
                "Automatic extraction produced no statements; keep the material for review or configure a small-model extractor"
            )
        graph = store.create_graph_candidate(
            source_document_version_ids=payload.source_document_version_ids,
            statements=extraction.statements,
            schema=schema,
            metadata={
                **payload.metadata,
                "provider": provider,
                "extraction": extraction.diagnostics,
                "schema_lineage": schema_lineage,
            },
            created_by=_actor(request, str(payload.metadata.get("actor") or "")),
        )
        return {**graph.to_dict(), "extraction": extraction.diagnostics}
    except (ValueError, GovernanceError, GovernedExtractionError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/graphs")
async def list_graph_versions(request: Request, status: str = ""):
    try:
        graphs = _store(request).list_graph_versions(status=status or None)
        return {
            "items": [item.to_dict(include_statements=False) for item in graphs],
            "count": len(graphs),
            "status_filter": status or None,
        }
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.get("/graphs/compare/{left_id}/{right_id}")
async def compare_graph_versions(request: Request, left_id: str, right_id: str):
    try:
        return _store(request).compare_graph_versions(left_id, right_id)
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/graphs/rollback")
async def rollback_graph(request: Request, payload: GraphRollbackRequest):
    try:
        project_id = _project_id(request)
        actor = _actor(request, payload.reviewer)
        store = _store(request)
        graph = store.rollback_graph(
            payload.target_graph_version_id,
            reviewer=actor,
            comment=payload.comment,
        )
        edges = normalize_kg_payload(store.graph_as_edge_payload(graph.graph_version_id))
        sync = _graph_store(request).import_edges(edges, reset=True)
        _registry(request).record_projection_state(
            project_id,
            "graph_store",
            status="ready",
            source_version_id=graph.graph_version_id,
            item_count=int(sync.get("edge_count") or 0),
            details={**sync, "rollback_target": payload.target_graph_version_id},
        )
        _audit_action(
            request,
            project_id=project_id,
            object_type="graph",
            object_id=graph.graph_version_id,
            object_version=str(graph.version),
            action="rollback",
            actor=actor,
            reason=payload.comment,
            change_summary={"target_graph_version_id": payload.target_graph_version_id, "graph_store_sync": sync},
        )
        return {
            **graph.to_dict(),
            "graph_store_sync": {**sync, "automatic": True},
        }
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.get("/graphs/{graph_version_id}")
async def get_graph(request: Request, graph_version_id: str):
    try:
        return _store(request).get_graph_version(graph_version_id).to_dict()
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/graphs/{graph_version_id}/view")
async def view_graph(request: Request, graph_version_id: str):
    try:
        return _store(request).graph_as_view_payload(graph_version_id)
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/graphs/{graph_version_id}/evidence-audit")
async def audit_graph_evidence(request: Request, graph_version_id: str):
    try:
        return _store(request).audit_graph_evidence(graph_version_id)
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/graphs/{graph_version_id}/query")
async def query_graph_version(request: Request, graph_version_id: str, payload: GraphQueryRequest):
    try:
        return _governed_graphrag(request).graph_rag(
            graph_version_id,
            payload.question,
            top_k=payload.top_k,
            max_hops=payload.max_hops,
            allow_fallback=payload.allow_fallback,
        ).to_dict()
    except (ValueError, GovernanceError, GovernedIndexError) as exc:
        raise _bad_request(exc) from exc


@router.post("/graphs/{graph_version_id}/compare-rag")
async def compare_rag_for_graph(
    request: Request,
    graph_version_id: str,
    payload: RAGComparisonRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    background: bool = Query(default=False),
):
    try:
        if background:
            project_id = _project_id(request)
            task = _registry(request).create_task(
                project_id=project_id,
                task_type="graphrag_evaluation",
                stage="queued",
                created_by=_actor(request),
                payload={"graph_version_id": graph_version_id, **payload.model_dump()},
                object_type="graph",
                object_id=graph_version_id,
                idempotency_key=request.headers.get("Idempotency-Key"),
                correlation_id=request.headers.get("X-Correlation-ID"),
                retryable=True,
            )
            if task.status is TaskStatus.QUEUED:
                background_tasks.add_task(
                    _run_graphrag_evaluation_task,
                    request=request,
                    project_id=project_id,
                    task_id=task.task_id,
                    payload_data=task.payload,
                )
            response.status_code = 202
            return {"project_id": project_id, "task": task.to_dict()}
        return _governed_graphrag(request).compare_same_questions(
            graph_version_id,
            payload.questions,
            top_k=payload.top_k,
        )
    except (ValueError, GovernanceError, GovernedIndexError, ProjectWorkspaceError) as exc:
        if isinstance(exc, ProjectWorkspaceError):
            raise _workspace_http_error(exc) from exc
        raise _bad_request(exc) from exc


@router.post("/graphs/{graph_version_id}/community-summaries", status_code=202)
async def create_graph_community_summaries(
    request: Request,
    graph_version_id: str,
    payload: CommunitySummaryRequest,
    background_tasks: BackgroundTasks,
):
    try:
        project_id = _project_id(request)
        graph = _store(request).get_graph_version(graph_version_id)
        if graph.status is not ContentStatus.PUBLISHED:
            raise GovernanceError("Community summaries require a published graph version")
        projection = _registry(request).get_projection_state(project_id, "graph_store")
        if not projection or projection.get("source_version_id") != graph_version_id:
            raise ProjectWorkspaceError(
                "Community summaries require the requested graph version to be active in GraphStore",
                code="graph_projection_stale",
                details={"graph_version_id": graph_version_id, "projection": projection},
            )
        task = _registry(request).create_task(
            project_id=project_id,
            task_type="community_summary",
            stage="queued",
            created_by=_actor(request, payload.actor),
            payload={"graph_version_id": graph_version_id, **payload.model_dump()},
            object_type="graph",
            object_id=graph_version_id,
            idempotency_key=request.headers.get("Idempotency-Key"),
            correlation_id=request.headers.get("X-Correlation-ID"),
            retryable=True,
        )
        if task.status is TaskStatus.QUEUED:
            background_tasks.add_task(
                _run_community_summary_task,
                request=request,
                project_id=project_id,
                task_id=task.task_id,
                payload_data=task.payload,
            )
        return {"project_id": project_id, "task": task.to_dict()}
    except (ValueError, GovernanceError, ProjectWorkspaceError) as exc:
        if isinstance(exc, ProjectWorkspaceError):
            raise _workspace_http_error(exc) from exc
        raise _bad_request(exc) from exc


@router.get("/graphs/{graph_version_id}/community-summaries")
async def list_graph_community_summaries(
    request: Request,
    graph_version_id: str,
    level: int = Query(default=0, ge=0, le=10),
):
    try:
        _store(request).get_graph_version(graph_version_id)
        projection = _registry(request).get_projection_state(_project_id(request), "graph_store")
        if not projection or projection.get("source_version_id") != graph_version_id:
            raise ProjectWorkspaceError(
                "Requested graph version is not active in GraphStore",
                code="graph_projection_stale",
            )
        items = _graph_store(request).get_community_summaries(level=level)
        return {"graph_version_id": graph_version_id, "level": level, "items": items, "count": len(items)}
    except (GovernanceError, ProjectWorkspaceError) as exc:
        if isinstance(exc, ProjectWorkspaceError):
            raise _workspace_http_error(exc) from exc
        raise _bad_request(exc) from exc


@router.get("/graphs/{graph_version_id}/statements")
async def list_graph_statements(
    request: Request,
    graph_version_id: str,
    relationship: str = "",
    subject_type: str = "",
    object_type: str = "",
    model: str = "",
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    evidence_status: Literal["", "bound", "missing"] = "",
    issue_code: str = "",
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str = "",
):
    try:
        store = _store(request)
        graph = store.get_graph_version(graph_version_id)
        reviews = store.list_reviews("graph", graph_version_id)
        latest_decisions = dict(reviews[-1].corrections.get("statement_decisions") or {}) if reviews else {}
        issue_by_statement = _graph_statement_issue_codes(graph)
        items = [
            {
                **statement.to_dict(),
                "issue_codes": sorted(issue_by_statement[statement.statement_id]),
                "review_decision": latest_decisions.get(statement.statement_id, "pending"),
            }
            for statement in sorted(graph.statements, key=lambda item: item.statement_id)
            if _graph_statement_matches(
                statement,
                cursor=cursor,
                relationship=relationship,
                subject_type=subject_type,
                object_type=object_type,
                model=model,
                min_confidence=min_confidence,
                evidence_status=evidence_status,
                issue_code=issue_code,
                issue_codes=issue_by_statement[statement.statement_id],
            )
        ]
        has_more = len(items) > limit
        page = items[:limit]
        return {
            "project_id": graph.project_id,
            "graph_version_id": graph.graph_version_id,
            "items": page,
            "count": len(page),
            "total_statement_count": len(graph.statements),
            "next_cursor": page[-1]["statement_id"] if has_more and page else None,
            "review_complete": (
                len(latest_decisions) == len(graph.statements)
                and all(latest_decisions.get(item.statement_id) == "approve" for item in graph.statements)
            ),
        }
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.post("/graphs/{graph_version_id}/statement-reviews")
async def review_graph_statements(
    request: Request,
    graph_version_id: str,
    payload: GraphStatementReviewRequest,
):
    try:
        store = _store(request)
        graph = store.get_graph_version(graph_version_id)
        _check_expected_version(
            payload.expected_version,
            allowed={graph.graph_version_id, str(graph.version), graph.content_hash},
        )
        expected = {item.statement_id for item in graph.statements}
        received = set(payload.decisions)
        if received != expected:
            raise ProjectWorkspaceError(
                "Every graph statement must receive an explicit review decision",
                code="graph_statement_review_incomplete",
                details={
                    "missing_statement_ids": sorted(expected - received),
                    "unknown_statement_ids": sorted(received - expected),
                },
            )
        actor = _actor(request, payload.reviewer)
        overall = ReviewDecision.APPROVE if set(payload.decisions.values()) == {"approve"} else ReviewDecision.REJECT
        review = store.record_review(
            target_type="graph",
            target_id=graph_version_id,
            reviewer=actor,
            decision=overall,
            comment=payload.comment,
            corrections={
                "review_mode": "statement_by_statement",
                "statement_decisions": dict(payload.decisions),
            },
        )
        _audit_action(
            request,
            project_id=_project_id(request),
            object_type="graph",
            object_id=graph_version_id,
            object_version=str(graph.version),
            action="statement_review",
            actor=actor,
            reason=payload.comment,
            change_summary={
                "approved": sum(value == "approve" for value in payload.decisions.values()),
                "rejected": sum(value == "reject" for value in payload.decisions.values()),
            },
        )
        return {**review.to_dict(), "statement_decisions": dict(payload.decisions)}
    except ProjectWorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.post("/graphs/{graph_version_id}/review")
async def review_graph(request: Request, graph_version_id: str, payload: ReviewRequest):
    try:
        actor = _actor(request, payload.reviewer)
        graph = _store(request).get_graph_version(graph_version_id)
        _check_expected_version(
            payload.expected_version,
            allowed={graph.graph_version_id, str(graph.version), graph.content_hash},
        )
        review = (
            _store(request)
            .record_review(
                target_type="graph",
                target_id=graph_version_id,
                reviewer=actor,
                decision=ReviewDecision(payload.decision),
                comment=payload.comment,
                corrections=payload.corrections,
            )
        )
        _audit_action(
            request,
            project_id=_project_id(request),
            object_type="graph",
            object_id=graph_version_id,
            object_version=graph_version_id,
            action=f"review_{review.decision.value}",
            actor=actor,
            reason=payload.comment,
            change_summary={"correction_keys": sorted(payload.corrections)},
        )
        return review.to_dict()
    except ProjectWorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.post("/graphs/{graph_version_id}/publish")
async def publish_graph(request: Request, graph_version_id: str, payload: PublishRequest | None = None):
    payload = payload or PublishRequest()
    project_id = _project_id(request)
    actor = _actor(request, payload.actor)
    operation = None
    try:
        store = _store(request)
        current = store.get_graph_version(graph_version_id)
        _check_expected_version(
            payload.expected_version,
            allowed={current.graph_version_id, str(current.version)},
        )
        if current.metadata.get("require_statement_review"):
            reviews = store.list_reviews("graph", graph_version_id)
            latest = reviews[-1] if reviews else None
            decisions = dict(latest.corrections.get("statement_decisions") or {}) if latest else {}
            statement_ids = {item.statement_id for item in current.statements}
            if (
                latest is None
                or latest.decision is not ReviewDecision.APPROVE
                or latest.corrections.get("review_mode") != "statement_by_statement"
                or set(decisions) != statement_ids
                or set(decisions.values()) != {"approve"}
            ):
                raise ProjectWorkspaceError(
                    "Graph publication requires an explicit approval for every statement",
                    code="graph_statement_review_incomplete",
                    details={
                        "statement_count": len(statement_ids),
                        "approved_statement_count": sum(value == "approve" for value in decisions.values()),
                    },
                )
        operation, cached = _begin_idempotent_operation(
            request,
            project_id=project_id,
            action="publish_graph",
            actor=actor,
            object_type="graph",
            object_id=graph_version_id,
            idempotency_key=payload.idempotency_key,
        )
        if cached is not None:
            return cached
        graph = store.publish_graph(graph_version_id)
        edges = normalize_kg_payload(store.graph_as_edge_payload(graph_version_id))
        graph_sync = _graph_store(request).import_edges(edges, reset=True)
        _registry(request).record_projection_state(
            project_id,
            "graph_store",
            status="ready",
            source_version_id=graph_version_id,
            item_count=int(graph_sync.get("edge_count") or 0),
            details=graph_sync,
        )
        response = {
            **graph.to_dict(),
            "graph_store_sync": {
                **graph_sync,
                "graph_version_id": graph_version_id,
                "automatic": True,
            },
        }
        reviews = store.list_reviews("graph", graph_version_id)
        reviewer = reviews[-1].reviewer if reviews else None
        _audit_action(
            request,
            project_id=project_id,
            object_type="graph",
            object_id=graph_version_id,
            object_version=str(graph.version),
            action="publish",
            actor=actor,
            reason=payload.comment,
            change_summary={
                "reviewer": reviewer,
                "same_person_role": bool(reviewer and reviewer == actor),
                "graph_store_sync": response["graph_store_sync"],
            },
        )
        _complete_idempotent_operation(request, operation, response=response, actor=actor)
    except (GovernanceError, FMEATemplateError, ProjectWorkspaceError) as exc:
        _fail_idempotent_operation(request, operation, exc, actor=actor)
        if isinstance(exc, ProjectWorkspaceError):
            raise _workspace_http_error(exc) from exc
        raise _bad_request(exc) from exc
    return response


@router.get("/graphs/{graph_version_id}/export")
async def export_graph(request: Request, graph_version_id: str):
    try:
        return {"triples": _store(request).graph_as_edge_payload(graph_version_id)}
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/graphs/{graph_version_id}/resync")
async def resync_graph_projection(request: Request, graph_version_id: str):
    project_id = _project_id(request)
    actor = _actor(request)
    try:
        store = _store(request)
        graph = store.get_graph_version(graph_version_id)
        if graph.status is not ContentStatus.PUBLISHED:
            raise GovernanceError("Only a published graph version can be synchronized to GraphStore")
        edges = normalize_kg_payload(store.graph_as_edge_payload(graph_version_id))
        sync = _graph_store(request).import_edges(edges, reset=True)
        expected_count = len(graph.statements)
        actual_count = int(sync.get("edge_count") or 0)
        if actual_count != expected_count:
            _registry(request).record_projection_state(
                project_id,
                "graph_store",
                status="failed",
                source_version_id=graph_version_id,
                item_count=actual_count,
                details={**sync, "expected_edge_count": expected_count},
            )
            raise ProjectWorkspaceError(
                "GraphStore edge count does not match the published graph version",
                code="graph_projection_mismatch",
                details={"expected_edge_count": expected_count, "actual_edge_count": actual_count},
            )
        projection = _registry(request).record_projection_state(
            project_id,
            "graph_store",
            status="ready",
            source_version_id=graph_version_id,
            item_count=actual_count,
            details={**sync, "expected_edge_count": expected_count},
        )
        _audit_action(
            request,
            project_id=project_id,
            object_type="graph_projection",
            object_id="graph_store",
            object_version=graph_version_id,
            action="resync",
            actor=actor,
            reason="Operator requested GraphStore resynchronization",
            change_summary={"expected_edge_count": expected_count, "actual_edge_count": actual_count},
        )
        return {  # noqa: TRY300
            "graph_version_id": graph_version_id,
            "graph_store_sync": sync,
            "projection": projection,
        }
    except (GovernanceError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/graphs/{graph_version_id}/path")
async def graph_path(
    request: Request,
    graph_version_id: str,
    source: str = Query(min_length=1),
    target: str = Query(min_length=1),
    max_hops: int = Query(default=4, ge=1, le=10),
):
    try:
        return _store(request).find_graph_path(
            graph_version_id,
            source,
            target,
            max_hops=max_hops,
        )
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.get("/graphs-active/status")
async def active_graph_status(request: Request):
    try:
        project_id = _project_id(request)
        return {
            **_graph_store(request).summary(),
            "project_id": project_id,
            "projection": _registry(request).get_projection_state(project_id, "graph_store"),
        }
    except (ValueError, OSError) as exc:
        raise _bad_request(exc) from exc


@router.get("/fmea/templates")
async def list_fmea_templates(request: Request):
    try:
        items = _fmea_service(request).template_registry.list()
        return {"project_id": _project_id(request), "items": [item.to_dict() for item in items]}
    except (FMEATemplateError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/fmea/templates/{template_id}")
async def get_fmea_template(request: Request, template_id: str, version: str | None = None):
    try:
        return _fmea_service(request).template_registry.get(template_id, version).to_dict()
    except (FMEATemplateError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/fmea/tasks")
async def list_fmea_tasks(
    request: Request,
    project_id: str = "",
    status: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    before_created_at: str = "",
):
    try:
        resolved_project_id = _project_id(request, project_id or None)
        items = _store(request, resolved_project_id).list_fmea_tasks(
            status=status or None,
            limit=limit + 1,
            before_created_at=before_created_at or None,
        )
        has_more = len(items) > limit
        items = items[:limit]
        return {
            "project_id": resolved_project_id,
            "items": [item.to_dict() for item in items],
            "count": len(items),
            "next_cursor": items[-1].created_at if has_more and items else None,
        }
    except (ValueError, GovernanceError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.post("/fmea/tasks")
async def run_fmea(
    request: Request,
    payload: FMEARunRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    background: bool = Query(default=False),
):
    try:
        if background:
            project_id = _project_id(request)
            actor = _actor(request, payload.requested_by)
            task = _registry(request).create_task(
                project_id=project_id,
                task_type="fmea_generation",
                stage="queued",
                created_by=actor,
                payload=payload.model_dump(),
                object_type="fmea",
                idempotency_key=(
                    request.headers.get("Idempotency-Key")
                    or str(payload.metadata.get("idempotency_key") or "")
                    or None
                ),
                correlation_id=request.headers.get("X-Correlation-ID"),
                retryable=True,
            )
            if task.status is TaskStatus.QUEUED:
                background_tasks.add_task(
                    _run_fmea_generation_task,
                    request=request,
                    project_id=project_id,
                    task_id=task.task_id,
                    payload_data=task.payload,
                )
            response.status_code = 202
            return {"project_id": project_id, "task": task.to_dict()}
        service = _fmea_service(request)
        task = service.run(
            FMEATaskRequest(
                requested_by=_actor(request, payload.requested_by),
                graph_version_id=payload.graph_version_id,
                document_version_ids=tuple(payload.document_version_ids),
                project_id=_project_id(request),
                template=payload.template,
                template_version=payload.template_version,
                metadata=payload.metadata,
            )
        )
        return service.result_payload(task.task_id)
    except (ValueError, GovernanceError, FMEATemplateError, ProjectWorkspaceError) as exc:
        raise _workspace_http_error(exc) from exc


@router.get("/fmea/tasks/{task_id}")
async def get_fmea_task(request: Request, task_id: str):
    try:
        return _fmea_service(request).result_payload(task_id)
    except GovernanceError as exc:
        raise _not_found(exc) from exc


@router.post("/fmea/tasks/{task_id}/field-reviews")
async def review_fmea_fields(request: Request, task_id: str, payload: FMEAFieldReviewRequest):
    try:
        service = _fmea_service(request)
        current = _store(request).get_fmea_task(task_id)
        _check_expected_version(
            payload.expected_version,
            allowed={current.task_id, current.updated_at, current.content_hash},
        )
        expected = {
            item.item_id: {field for field, value in item.fields.items() if value not in (None, "")}
            for item in current.items
        }
        received = {item_id: set(fields) for item_id, fields in payload.decisions.items()}
        missing_items = sorted(set(expected) - set(received))
        unknown_items = sorted(set(received) - set(expected))
        mismatched_fields = {
            item_id: {
                "missing": sorted(expected.get(item_id, set()) - received.get(item_id, set())),
                "unknown": sorted(received.get(item_id, set()) - expected.get(item_id, set())),
            }
            for item_id in set(expected) | set(received)
            if expected.get(item_id, set()) != received.get(item_id, set())
        }
        if missing_items or unknown_items or mismatched_fields:
            raise ProjectWorkspaceError(
                "Every populated FMEA field must receive an explicit review decision",
                code="fmea_field_review_incomplete",
                details={
                    "missing_item_ids": missing_items,
                    "unknown_item_ids": unknown_items,
                    "field_mismatches": mismatched_fields,
                },
            )
        actor = _actor(request, payload.reviewer)
        decisions = [
            decision
            for item_decisions in payload.decisions.values()
            for decision in item_decisions.values()
        ]
        overall = ReviewDecision.APPROVE if set(decisions) <= {"approve"} else ReviewDecision.REJECT
        task = service.review(
            task_id,
            reviewer=actor,
            decision=overall,
            comment=payload.comment,
            corrections=payload.corrections,
            review_metadata={
                "review_mode": "field_by_field",
                "field_decisions": payload.decisions,
            },
        )
        _audit_action(
            request,
            project_id=_project_id(request),
            object_type="fmea",
            object_id=task_id,
            object_version=task.updated_at,
            action="field_review",
            actor=actor,
            reason=payload.comment,
            change_summary={
                "approved": sum(decision == "approve" for decision in decisions),
                "rejected": sum(decision == "reject" for decision in decisions),
                "corrected_item_ids": sorted(payload.corrections.get("items", payload.corrections)),
            },
        )
        return service.result_payload(task.task_id)
    except ProjectWorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.post("/fmea/tasks/{task_id}/review")
async def review_fmea(request: Request, task_id: str, payload: ReviewRequest):
    try:
        actor = _actor(request, payload.reviewer)
        service = _fmea_service(request)
        current = _store(request).get_fmea_task(task_id)
        _check_expected_version(
            payload.expected_version,
            allowed={current.task_id, current.updated_at, current.content_hash},
        )
        task = service.review(
            task_id,
            reviewer=actor,
            decision=ReviewDecision(payload.decision),
            comment=payload.comment,
            corrections=payload.corrections,
        )
        _audit_action(
            request,
            project_id=_project_id(request),
            object_type="fmea",
            object_id=task_id,
            object_version=task.updated_at,
            action=f"review_{payload.decision}",
            actor=actor,
            reason=payload.comment,
            change_summary={"corrected_item_ids": sorted(payload.corrections)},
        )
        return service.result_payload(task.task_id)
    except ProjectWorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.post("/fmea/tasks/{task_id}/publish")
async def publish_fmea(request: Request, task_id: str, payload: PublishRequest | None = None):
    payload = payload or PublishRequest()
    project_id = _project_id(request)
    actor = _actor(request, payload.actor)
    operation = None
    try:
        store = _store(request)
        current = store.get_fmea_task(task_id)
        _check_expected_version(
            payload.expected_version,
            allowed={current.task_id, current.updated_at},
        )
        operation, cached = _begin_idempotent_operation(
            request,
            project_id=project_id,
            action="publish_fmea",
            actor=actor,
            object_type="fmea",
            object_id=task_id,
            idempotency_key=payload.idempotency_key,
        )
        if cached is not None:
            return cached
        service = _fmea_service(request)
        task = service.publish(task_id)
        response = service.result_payload(task.task_id)
        reviews = store.list_reviews("fmea", task_id)
        reviewer = reviews[-1].reviewer if reviews else None
        _audit_action(
            request,
            project_id=project_id,
            object_type="fmea",
            object_id=task_id,
            object_version=task.updated_at,
            action="publish",
            actor=actor,
            reason=payload.comment,
            change_summary={
                "reviewer": reviewer,
                "same_person_role": bool(reviewer and reviewer == actor),
                "item_count": len(task.items),
            },
        )
        _complete_idempotent_operation(request, operation, response=response, actor=actor)
    except (GovernanceError, FMEATemplateError, ProjectWorkspaceError) as exc:
        _fail_idempotent_operation(request, operation, exc, actor=actor)
        if isinstance(exc, ProjectWorkspaceError):
            raise _workspace_http_error(exc) from exc
        if getattr(exc, "code", "") == "fmea_field_review_incomplete":
            raise _workspace_http_error(
                ProjectWorkspaceError(
                    str(exc),
                    code="fmea_field_review_incomplete",
                    details=getattr(exc, "details", {}),
                )
            ) from exc
        raise _bad_request(exc) from exc
    return response


@router.get("/fmea/tasks/{task_id}/reviews")
async def list_fmea_reviews(request: Request, task_id: str):
    try:
        store = _store(request)
        store.get_fmea_task(task_id)
        return {"task_id": task_id, "items": [item.to_dict() for item in store.list_reviews("fmea", task_id)]}
    except GovernanceError as exc:
        raise _not_found(exc) from exc


@router.get("/fmea/tasks/{task_id}/status-history")
async def list_fmea_status_history(request: Request, task_id: str):
    try:
        return {
            "task_id": task_id,
            "items": [item.to_dict() for item in _store(request).list_fmea_task_events(task_id)],
        }
    except GovernanceError as exc:
        raise _not_found(exc) from exc


@router.get("/fmea/tasks/{task_id}/export")
async def export_fmea(request: Request, task_id: str, export_format: str = Query("json", alias="format")):
    service = _fmea_service(request)
    normalized_format = export_format.lower()
    if normalized_format not in {"json", "csv", "docx"}:
        raise _bad_request(ValueError("format must be json, csv, or docx"))
    try:
        if normalized_format == "docx":
            return Response(
                service.export_docx(task_id),
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": f'attachment; filename="{task_id}.docx"'},
            )
        if normalized_format == "csv":
            return Response(
                service.export_csv(task_id),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{task_id}.csv"'},
            )
        return Response(
            service.export_json(task_id),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{task_id}.json"'},
        )
    except (GovernanceError, FMEATemplateError) as exc:
        raise _bad_request(exc) from exc


@router.get("/fmea/tasks/{task_id}/export-verify")
async def verify_fmea_export(request: Request, task_id: str):
    try:
        return _fmea_service(request).verify_export_consistency(task_id)
    except (GovernanceError, FMEATemplateError) as exc:
        raise _bad_request(exc) from exc


@router.post("/fmea/tasks/{task_id}/feedback")
async def add_fmea_feedback(request: Request, task_id: str, payload: FeedbackRequest):
    try:
        return _store(request).add_feedback(
            task_id=task_id,
            item_id=payload.item_id,
            code=payload.code,
            message=payload.message,
            created_by=payload.created_by,
        )
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.get("/fmea/tasks/{task_id}/feedback")
async def list_fmea_feedback(request: Request, task_id: str):
    try:
        return {"task_id": task_id, "items": _store(request).list_feedback(task_id)}
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/fmea/feedback/{feedback_id}/remediate")
async def remediate_fmea_feedback(
    request: Request,
    feedback_id: str,
    payload: FeedbackRemediationRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    background: bool = Query(default=False),
):
    try:
        if background:
            project_id = _project_id(request)
            actor = _actor(request, payload.actor)
            task = _registry(request).create_task(
                project_id=project_id,
                task_type="feedback_remediation",
                stage="queued",
                created_by=actor,
                payload={"feedback_id": feedback_id, **payload.model_dump()},
                object_type="feedback",
                object_id=feedback_id,
                idempotency_key=request.headers.get("Idempotency-Key"),
                correlation_id=request.headers.get("X-Correlation-ID"),
                retryable=True,
            )
            if task.status is TaskStatus.QUEUED:
                background_tasks.add_task(
                    _run_feedback_remediation_task,
                    request=request,
                    project_id=project_id,
                    task_id=task.task_id,
                    payload_data=task.payload,
                )
            response.status_code = 202
            return {"project_id": project_id, "task": task.to_dict()}
        return DeliveryRemediationService(
            _store(request),
            document_index=_index(request),
            graph_store=_graph_store(request),
        ).remediate(
            feedback_id,
            actor=payload.actor,
            document_version_id=payload.document_version_id,
            graph_version_id=payload.graph_version_id,
            corrections=payload.corrections,
        )
    except (ValueError, GovernanceError, GovernedIndexError, ProjectWorkspaceError) as exc:
        if isinstance(exc, ProjectWorkspaceError):
            raise _workspace_http_error(exc) from exc
        raise _bad_request(exc) from exc


@router.get("/fmea/feedback/{feedback_id}/runs")
async def list_feedback_runs(request: Request, feedback_id: str):
    try:
        return {"feedback_id": feedback_id, "items": _store(request).list_feedback_runs(feedback_id)}
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _schema(payload: dict[str, Any]) -> GraphDomainSchema:
    default = GraphDomainSchema()
    if not payload:
        return default
    return GraphDomainSchema(
        entity_types=tuple(payload.get("entity_types") or default.entity_types),
        relation_types=tuple(payload.get("relation_types") or default.relation_types),
        knowledge_types=tuple(payload.get("knowledge_types") or default.knowledge_types),
        entity_aliases=dict(payload.get("entity_aliases") or {}),
        relation_aliases={**default.relation_aliases, **dict(payload.get("relation_aliases") or {})},
        model_aliases={**default.model_aliases, **dict(payload.get("model_aliases") or {})},
        relation_knowledge_types={
            **default.relation_knowledge_types,
            **dict(payload.get("relation_knowledge_types") or {}),
        },
        relation_constraints={
            str(relation): tuple(tuple(str(value) for value in pair) for pair in pairs)
            for relation, pairs in dict(payload.get("relation_constraints") or default.relation_constraints).items()
        },
        min_confidence=float(payload.get("min_confidence", default.min_confidence)),
    )


def _resolve_graph_schema(
    registry: ProjectWorkspaceRegistry,
    project_id: str,
    *,
    schema_id: str | None,
    schema_version: str | None,
    inline_definition: Mapping[str, Any],
) -> tuple[GraphDomainSchema, dict[str, Any]]:
    definition = dict(inline_definition or {})
    if schema_id:
        catalog = registry.get_graph_schema(
            project_id,
            schema_id,
            version=schema_version,
            approved_only=True,
        )
        catalog_schema = _schema(dict(catalog["definition"]))
        if definition and _schema(definition).to_dict() != catalog_schema.to_dict():
            raise ProjectWorkspaceError(
                "Inline schema conflicts with the approved catalog version",
                code="graph_schema_lineage_conflict",
                details={"schema_id": schema_id, "schema_version": catalog["version"]},
            )
        return catalog_schema, {
            "schema_id": catalog["schema_id"],
            "version": catalog["version"],
            "content_hash": catalog["content_hash"],
            "status": catalog["status"],
            "source": "project_catalog",
        }
    if definition:
        normalized = _schema(definition)
        return normalized, {
            "schema_id": "inline_compatibility",
            "version": None,
            "content_hash": hashlib.sha256(
                json.dumps(normalized.to_dict(), ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "status": "unregistered",
            "source": "inline_compatibility",
        }
    catalog = registry.get_graph_schema(
        project_id,
        "gas_turbine_fmea",
        version=schema_version,
        approved_only=True,
    )
    return _schema(dict(catalog["definition"])), {
        "schema_id": catalog["schema_id"],
        "version": catalog["version"],
        "content_hash": catalog["content_hash"],
        "status": catalog["status"],
        "source": "project_catalog_default",
    }
