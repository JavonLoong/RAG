"""Callable M2-M5 delivery workflow endpoints."""

from __future__ import annotations

import base64
import binascii
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
from rag_orchestrator.fmea import FMEAService  # noqa: E402
from storage_layer.governance_store import GovernanceError, GovernanceStore  # noqa: E402

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


def _store(request: Request) -> GovernanceStore:
    store = getattr(request.app.state, "governance_store", None)
    if store is not None:
        return store
    persist_dir = Path(getattr(request.app.state, "persist_dir", _REPO_ROOT / "build" / "runtime"))
    store = GovernanceStore(persist_dir / "governance" / "delivery.sqlite3")
    request.app.state.governance_store = store
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


@router.get("/documents/{version_id}")
async def get_document(request: Request, version_id: str):
    try:
        return _store(request).get_document_version(version_id).to_dict()
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
        return _store(request).publish_document(version_id).to_dict()
    except GovernanceError as exc:
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
        return (
            _store(request)
            .rollback_document(
                document_id,
                payload.target_version_id,
                reviewer=payload.reviewer,
                comment=payload.comment,
            )
            .to_dict()
        )
    except GovernanceError as exc:
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
        return _store(request).publish_graph(graph_version_id).to_dict()
    except GovernanceError as exc:
        raise _bad_request(exc) from exc


@router.get("/graphs/{graph_version_id}/export")
async def export_graph(request: Request, graph_version_id: str):
    try:
        return {"triples": _store(request).graph_as_edge_payload(graph_version_id)}
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
