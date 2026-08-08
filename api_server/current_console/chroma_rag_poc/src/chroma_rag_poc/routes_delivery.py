"""Callable M2-M5 delivery workflow endpoints."""
# ruff: noqa: TRY003, TRY301

from __future__ import annotations

import base64
import binascii
import os
import sys
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core_domain.delivery import FMEATaskRequest, GraphDomainSchema, ReviewDecision  # noqa: E402
from data_pipeline.document_intake import DocumentIntakeOptions, run_document_intake  # noqa: E402
from kg_pipeline.governed_extraction import GovernedExtractionError, extract_governed_statements  # noqa: E402
from rag_orchestrator.delivery_remediation import DeliveryRemediationService  # noqa: E402
from rag_orchestrator.fmea import FMEAService  # noqa: E402
from storage_layer.governance_store import GovernanceError, GovernanceStore  # noqa: E402
from storage_layer.governed_index import GovernedDocumentIndex, GovernedIndexError  # noqa: E402
from storage_layer.graph_store import GraphStore, normalize_kg_payload  # noqa: E402

from .embeddings import DEFAULT_SENTENCE_TRANSFORMER_MODEL, create_embedding_backend  # noqa: E402

router = APIRouter(prefix="/api/delivery", tags=["governed-delivery"])


class IntakeRequest(BaseModel):
    document_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    content_base64: str = Field(min_length=1)
    chunk_size: int = Field(default=500, ge=80, le=5000)
    overlap: int = Field(default=50, ge=0, le=1000)
    parser_backend: Literal["auto", "native", "deepdoc", "mineru", "docling", "unstructured"] = "auto"
    use_ocr: Literal["auto", "always", "never"] = "auto"
    metadata: dict[str, Any] = Field(default_factory=dict)


class OCRPagePayload(BaseModel):
    page: int = Field(ge=1)
    text: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reading_order_risk: Literal["low", "medium", "high", "unknown"] = "unknown"
    block_id: str | None = None
    table_id: str | None = None
    image_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OCRResultIntakeRequest(BaseModel):
    document_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    pages: list[OCRPagePayload] = Field(min_length=1)
    expected_pages: int | None = Field(default=None, ge=1)
    low_confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentRevisionRequest(BaseModel):
    reviewer: str = Field(min_length=1)
    comment: str = ""
    corrections: dict[str, Any] = Field(min_length=1)


class ReviewRequest(BaseModel):
    reviewer: str = Field(min_length=1)
    decision: str
    comment: str = ""
    corrections: dict[str, Any] = Field(default_factory=dict)


class RollbackRequest(BaseModel):
    target_version_id: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    comment: str = ""


class GraphCandidateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_document_version_ids: list[str] = Field(min_length=1)
    statements: list[dict[str, Any]] = Field(min_length=1)
    graph_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphExtractionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_document_version_ids: list[str] = Field(min_length=1)
    backend: Literal["rules", "small-model", "llm"] = "rules"
    model: str | None = None
    graph_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")
    metadata: dict[str, Any] = Field(default_factory=dict)


class FMEARunRequest(BaseModel):
    requested_by: str = Field(min_length=1)
    graph_version_id: str = Field(min_length=1)
    document_version_ids: list[str] = Field(min_length=1)
    template: str = "gas_turbine_minimum_v1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    created_by: str = Field(min_length=1)
    item_id: str | None = None


class FeedbackRemediationRequest(BaseModel):
    actor: str = Field(min_length=1)
    document_version_id: str | None = None
    corrections: dict[str, Any] = Field(default_factory=dict)


def _store(request: Request) -> GovernanceStore:
    store = getattr(request.app.state, "governance_store", None)
    if store is not None:
        return store
    persist_dir = Path(getattr(request.app.state, "persist_dir", _REPO_ROOT / "build" / "runtime"))
    store = GovernanceStore(persist_dir / "governance" / "delivery.sqlite3")
    request.app.state.governance_store = store
    return store


def _index(request: Request) -> GovernedDocumentIndex:
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
    index = GovernedDocumentIndex(
        persist_dir / "governance" / "retrieval_chroma",
        embedding_function=resolved.function,
        embedding_backend=resolved.name,
        embedding_model=resolved.model_name,
        embedding_warning=resolved.warning,
    )
    request.app.state.governed_document_index = index
    return index


def _graph_store(request: Request) -> GraphStore:
    store = getattr(request.app.state, "governed_graph_store", None)
    if store is not None:
        return store
    persist_dir = Path(getattr(request.app.state, "persist_dir", _REPO_ROOT / "build" / "runtime"))
    store = GraphStore(persist_dir / "graph_store.sqlite")
    store.initialize(reset=False)
    request.app.state.governed_graph_store = store
    return store


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.post("/documents/intake")
async def intake_document(request: Request, payload: IntakeRequest):
    try:
        raw_bytes = base64.b64decode(payload.content_base64, validate=True)
        intake = run_document_intake(
            payload.source_name,
            raw_bytes,
            chunk_size=payload.chunk_size,
            overlap=payload.overlap,
            options=DocumentIntakeOptions(
                parser_backend=payload.parser_backend,
                use_ocr=payload.use_ocr,
            ),
        )
        version = _store(request).create_document_candidate_from_intake(
            payload.document_id,
            intake,
            metadata=payload.metadata,
        )
        return {
            "document_version": version.to_dict(include_evidence=False),
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
        page_numbers = [item.page for item in payload.pages]
        if len(page_numbers) != len(set(page_numbers)):
            raise ValueError("OCR pages must use unique page numbers")
        expected_pages = payload.expected_pages or max(page_numbers)
        missing_pages = sorted(set(range(1, expected_pages + 1)) - set(page_numbers))
        blank_pages = sorted(item.page for item in payload.pages if not item.text.strip())
        low_confidence_pages = sorted(
            item.page
            for item in payload.pages
            if item.confidence is not None and item.confidence < payload.low_confidence_threshold
        )
        layout_risk_pages = sorted(
            item.page for item in payload.pages if item.reading_order_risk in {"medium", "high"}
        )
        chunks = [
            {
                "chunk_id": f"page-{item.page:05d}",
                "text": item.text,
                "source_file": payload.source_name,
                "page": item.page,
                "block_id": item.block_id,
                "table_id": item.table_id,
                "image_id": item.image_id,
                "metadata": {
                    **item.metadata,
                    "ocr_confidence": item.confidence,
                    "reading_order_risk": item.reading_order_risk,
                },
            }
            for item in payload.pages
            if item.text.strip()
        ]
        warnings = [
            *(f"Blank OCR page: {page}" for page in blank_pages),
            *(f"Low OCR confidence page: {page}" for page in low_confidence_pages),
            *(f"Reading-order review required for page: {page}" for page in layout_risk_pages),
        ]
        errors = [f"Missing OCR page: {page}" for page in missing_pages]
        quality = {
            "quality_gate_status": "fail" if missing_pages or not chunks else "pass",
            "expected_pages": expected_pages,
            "received_pages": len(page_numbers),
            "text_pages": len(chunks),
            "missing_pages": missing_pages,
            "blank_pages": blank_pages,
            "low_confidence_pages": low_confidence_pages,
            "layout_risk_pages": layout_risk_pages,
            "low_confidence_threshold": payload.low_confidence_threshold,
        }
        version = _store(request).create_document_candidate(
            document_id=payload.document_id,
            source_name=payload.source_name,
            chunks=chunks,
            intake_status="partial" if missing_pages else "parsed",
            quality=quality,
            warnings=warnings,
            errors=errors,
            metadata={**payload.metadata, "ocr_quality": quality, "intake_route": "ocr_result"},
        )
        return {"document_version": version.to_dict(), "ocr_quality": quality}
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.post("/documents/{version_id}/revise")
async def revise_document(request: Request, version_id: str, payload: DocumentRevisionRequest):
    try:
        revised = _store(request).create_document_revision(
            version_id,
            reviewer=payload.reviewer,
            comment=payload.comment,
            corrections=payload.corrections,
        )
        return {
            "document_version": revised.to_dict(),
            "reviews": [item.to_dict() for item in _store(request).list_reviews("document", revised.version_id)],
        }
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


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
):
    try:
        versions = tuple(item.strip() for item in version_ids.split(",") if item.strip())
        return _index(request).query(q, top_k=top_k, document_version_ids=versions)
    except GovernedIndexError as exc:
        raise _bad_request(exc) from exc


@router.get("/documents-index/status")
async def document_index_status(request: Request):
    try:
        return _index(request).status()
    except GovernedIndexError as exc:
        raise _bad_request(exc) from exc


@router.post("/documents-index/rebuild")
async def rebuild_document_index(request: Request):
    try:
        return _index(request).rebuild(_store(request).list_published_document_versions())
    except (GovernanceError, GovernedIndexError) as exc:
        raise _bad_request(exc) from exc


@router.post("/documents/{version_id}/review")
async def review_document(request: Request, version_id: str, payload: ReviewRequest):
    try:
        review = _store(request).record_review(
            target_type="document",
            target_id=version_id,
            reviewer=payload.reviewer,
            decision=ReviewDecision(payload.decision),
            comment=payload.comment,
            corrections=payload.corrections,
        )
        return review.to_dict()
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.post("/documents/{version_id}/publish")
async def publish_document(request: Request, version_id: str):
    try:
        document = _store(request).publish_document(version_id)
        return {**document.to_dict(), "retrieval_index": _index(request).sync_document(document)}
    except (GovernanceError, GovernedIndexError) as exc:
        raise _bad_request(exc) from exc


@router.get("/documents/compare/{left_id}/{right_id}")
async def compare_documents(request: Request, left_id: str, right_id: str):
    try:
        return _store(request).compare_document_versions(left_id, right_id)
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/documents/{document_id}/rollback")
async def rollback_document(request: Request, document_id: str, payload: RollbackRequest):
    try:
        document = _store(request).rollback_document(
            document_id,
            payload.target_version_id,
            reviewer=payload.reviewer,
            comment=payload.comment,
        )
        return {**document.to_dict(), "retrieval_index": _index(request).sync_document(document)}
    except (GovernanceError, GovernedIndexError) as exc:
        raise _bad_request(exc) from exc


@router.post("/graphs/candidates")
async def create_graph_candidate(request: Request, payload: GraphCandidateRequest):
    try:
        graph = _store(request).create_graph_candidate(
            source_document_version_ids=payload.source_document_version_ids,
            statements=payload.statements,
            schema=_schema(payload.graph_schema),
            metadata=payload.metadata,
        )
        return graph.to_dict()
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.post("/graphs/extract")
async def extract_graph_candidate(request: Request, payload: GraphExtractionRequest):
    try:
        store = _store(request)
        documents = [store.get_document_version(item) for item in payload.source_document_version_ids]
        model_client = None
        if payload.backend in {"small-model", "llm"}:
            model_client = getattr(request.app.state, "delivery_graph_extractor", None)
        schema = _schema(payload.graph_schema)
        extraction = extract_governed_statements(
            documents,
            backend=payload.backend,
            schema=schema,
            model_client=model_client,
            model_name=payload.model,
        )
        if not extraction.statements:
            raise GovernedExtractionError(
                "Automatic extraction produced no statements; keep the material for review or configure a small-model extractor"
            )
        graph = store.create_graph_candidate(
            source_document_version_ids=payload.source_document_version_ids,
            statements=extraction.statements,
            schema=schema,
            metadata={**payload.metadata, "extraction": extraction.diagnostics},
        )
        return {**graph.to_dict(), "extraction": extraction.diagnostics}
    except (ValueError, GovernanceError, GovernedExtractionError) as exc:
        raise _bad_request(exc) from exc


@router.get("/graphs/{graph_version_id}")
async def get_graph(request: Request, graph_version_id: str):
    try:
        return _store(request).get_graph_version(graph_version_id).to_dict()
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/graphs/{graph_version_id}/review")
async def review_graph(request: Request, graph_version_id: str, payload: ReviewRequest):
    try:
        return (
            _store(request)
            .record_review(
                target_type="graph",
                target_id=graph_version_id,
                reviewer=payload.reviewer,
                decision=ReviewDecision(payload.decision),
                comment=payload.comment,
                corrections=payload.corrections,
            )
            .to_dict()
        )
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.post("/graphs/{graph_version_id}/publish")
async def publish_graph(request: Request, graph_version_id: str):
    try:
        store = _store(request)
        graph = store.publish_graph(graph_version_id)
        edges = normalize_kg_payload(store.graph_as_edge_payload(graph_version_id))
        graph_sync = _graph_store(request).import_edges(edges, reset=True)
        return {
            **graph.to_dict(),
            "graph_store_sync": {
                **graph_sync,
                "graph_version_id": graph_version_id,
                "automatic": True,
            },
        }
    except GovernanceError as exc:
        raise _bad_request(exc) from exc


@router.get("/graphs/{graph_version_id}/export")
async def export_graph(request: Request, graph_version_id: str):
    try:
        return {"triples": _store(request).graph_as_edge_payload(graph_version_id)}
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
        return _graph_store(request).summary()
    except (ValueError, OSError) as exc:
        raise _bad_request(exc) from exc


@router.post("/fmea/tasks")
async def run_fmea(request: Request, payload: FMEARunRequest):
    try:
        return (
            FMEAService(_store(request))
            .run(
                FMEATaskRequest(
                    requested_by=payload.requested_by,
                    graph_version_id=payload.graph_version_id,
                    document_version_ids=tuple(payload.document_version_ids),
                    template=payload.template,
                    metadata=payload.metadata,
                )
            )
            .to_dict()
        )
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.get("/fmea/tasks/{task_id}")
async def get_fmea_task(request: Request, task_id: str):
    try:
        return _store(request).get_fmea_task(task_id).to_dict()
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/fmea/tasks/{task_id}/review")
async def review_fmea(request: Request, task_id: str, payload: ReviewRequest):
    try:
        return (
            FMEAService(_store(request))
            .review(
                task_id,
                reviewer=payload.reviewer,
                decision=ReviewDecision(payload.decision),
                comment=payload.comment,
                corrections=payload.corrections,
            )
            .to_dict()
        )
    except (ValueError, GovernanceError) as exc:
        raise _bad_request(exc) from exc


@router.post("/fmea/tasks/{task_id}/publish")
async def publish_fmea(request: Request, task_id: str):
    try:
        return FMEAService(_store(request)).publish(task_id).to_dict()
    except GovernanceError as exc:
        raise _bad_request(exc) from exc


@router.get("/fmea/tasks/{task_id}/export")
async def export_fmea(request: Request, task_id: str, export_format: str = Query("json", alias="format")):
    service = FMEAService(_store(request))
    normalized_format = export_format.lower()
    if normalized_format not in {"json", "csv"}:
        raise HTTPException(status_code=400, detail="format must be json or csv")
    try:
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
    except GovernanceError as exc:
        raise _bad_request(exc) from exc


@router.get("/fmea/tasks/{task_id}/export-verify")
async def verify_fmea_export(request: Request, task_id: str):
    try:
        return FMEAService(_store(request)).verify_export_consistency(task_id)
    except GovernanceError as exc:
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
async def remediate_fmea_feedback(request: Request, feedback_id: str, payload: FeedbackRemediationRequest):
    try:
        return DeliveryRemediationService(
            _store(request),
            document_index=_index(request),
            graph_store=_graph_store(request),
        ).remediate(
            feedback_id,
            actor=payload.actor,
            document_version_id=payload.document_version_id,
            corrections=payload.corrections,
        )
    except (ValueError, GovernanceError, GovernedIndexError) as exc:
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
        entity_aliases=dict(payload.get("entity_aliases") or {}),
        relation_aliases={**default.relation_aliases, **dict(payload.get("relation_aliases") or {})},
        min_confidence=float(payload.get("min_confidence", default.min_confidence)),
    )
