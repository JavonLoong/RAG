"""Versioned REST adapter for the FMEA propagation application services."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from enum import Enum
from threading import Lock
from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response

from core_domain.fmea.states import ActorType
from fmea_application.propagation_service import (
    ConfirmPropagationCommand,
    PropagationDecisionAction,
    PropagationEdgeDecision,
    PropagationError,
    PropagationReviewResult,
    PropagationRun,
    StartPropagationCommand,
)
from fmea_application.review_contracts import ActorContext
from fmea_application.review_errors import REVIEW_ERROR_CODES, ReviewError

from .fmea_propagation_contracts import (
    GraphReviewBody,
    PropagationGraphData,
    PropagationPathData,
    PropagationPathPage,
    PropagationReviewResultData,
    PropagationRunData,
    PropagationStartBody,
)
from .fmea_review_contracts import FmeaEnvelope
from .routes_fmea_review_v1 import (
    _decode_cursor,
    _encode_cursor,
    parse_idempotency_key,
    parse_if_match,
)
from .workspace_registry import WorkspaceConfig, WorkspaceNotFoundError

router = APIRouter(prefix="/api/v1/fmea", tags=["fmea-propagation-v1"])
_BEARER = re.compile(r"^Bearer ([^\s]+)$")
_MAX_PATH_PAGE = 100


@dataclass(frozen=True, slots=True)
class PropagationAccess:
    actor: ActorContext
    workspace: WorkspaceConfig
    runtime: Any


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value


def edge_data(value: Any) -> Any:
    from .fmea_propagation_contracts import PropagationEdgeData

    return PropagationEdgeData.model_validate(_jsonable(asdict(value)))


def path_data(value: Any) -> PropagationPathData:
    return PropagationPathData.model_validate(_jsonable(asdict(value)))


def graph_data(value: Any) -> PropagationGraphData:
    return PropagationGraphData.model_validate(_jsonable(asdict(value)))


def run_data(value: PropagationRun) -> PropagationRunData:
    payload = _jsonable(asdict(value))
    payload.pop("error_message", None)
    payload.pop("record_version", None)
    return PropagationRunData.model_validate(payload)


def review_result_data(value: PropagationReviewResult) -> PropagationReviewResultData:
    return PropagationReviewResultData.model_validate(_jsonable(asdict(value)))


def _envelope(resource_type: str, data: Any, *, request_id: str, trace_id: str) -> dict[str, object]:
    return FmeaEnvelope(
        resource_type=resource_type,
        request_id=request_id,
        trace_id=trace_id,
        data=data,
    ).model_dump(mode="json")


def _json_response(
    *,
    status_code: int,
    resource_type: str,
    data: Any,
    request_id: str,
    trace_id: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=_envelope(resource_type, data, request_id=request_id, trace_id=trace_id),
        headers=headers,
    )


def _authorization_token(request: Request) -> str:
    header = request.headers.get("authorization")
    if header is None:
        raise ReviewError("FMEA_AUTH_REQUIRED", "review authentication is required")
    match = _BEARER.fullmatch(header)
    if match is None:
        raise ReviewError("FMEA_AUTH_REQUIRED", "review authentication is required")
    return match.group(1)


def _require_human_propagation_reviewer(actor: ActorContext) -> None:
    if actor.actor_type is not ActorType.HUMAN:
        raise ReviewError("FMEA_PROPAGATION_REVIEW_FORBIDDEN", "a human propagation reviewer is required")
    if "propagation_reviewer" not in actor.roles:
        raise ReviewError("FMEA_PROPAGATION_REVIEW_FORBIDDEN", "the propagation_reviewer role is required")


def _runtime_for(request: Request, workspace: WorkspaceConfig) -> Any:
    cache = cast(dict[str, Any], request.app.state.propagation_runtimes)
    lock = cast(Lock, request.app.state.propagation_runtime_lock)
    with lock:
        existing = cache.get(workspace.workspace_id)
        if existing is not None:
            return existing
        factory = cast(Callable[[WorkspaceConfig], Any] | None, request.app.state.propagation_runtime_factory)
        if factory is None:
            raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "FMEA propagation runtime is not configured")
        try:
            runtime = factory(workspace)
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError(
                "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                "FMEA propagation runtime is unavailable",
                retryable=True,
            ) from exc
        if getattr(runtime, "service", None) is None:
            raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "FMEA propagation service is unavailable")
        cache[workspace.workspace_id] = runtime
        return runtime


def get_propagation_access(request: Request) -> PropagationAccess:
    configured_error = cast(ReviewError | None, request.app.state.review_auth_error)
    if configured_error is not None:
        raise configured_error
    provider = request.app.state.review_auth_provider
    if provider is None:
        raise ReviewError("FMEA_AUTH_CONFIGURATION_INVALID", "review authentication is not configured")
    remote_host = request.client.host if request.client is not None else None
    actor = provider.authenticate(_authorization_token(request), remote_host)
    _require_human_propagation_reviewer(actor)
    try:
        workspace = request.app.state.workspace_registry.get(actor.workspace_id)
    except WorkspaceNotFoundError as exc:
        raise ReviewError("FMEA_REVIEW_FORBIDDEN", "review workspace is not available") from exc
    return PropagationAccess(actor=actor, workspace=workspace, runtime=_runtime_for(request, workspace))


def _service_call(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except ReviewError:
        raise
    except PropagationError as exc:
        if exc.code in REVIEW_ERROR_CODES:
            raise ReviewError(exc.code, str(exc)) from exc
        raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "FMEA propagation operation failed") from exc
    except Exception as exc:
        raise ReviewError(
            "FMEA_REVIEW_STORAGE_UNAVAILABLE",
            "FMEA propagation storage is unavailable",
            retryable=True,
        ) from exc


def _start_command(analysis_id: str, body: PropagationStartBody, request: Request) -> StartPropagationCommand:
    try:
        return StartPropagationCommand(
            analysis_id=analysis_id,
            expected_analysis_record_version=parse_if_match(request),
            source_row_ids=tuple(body.source_row_ids),
            evidence_pack_id=body.evidence_pack_id,
            topology_id=body.topology_id,
            topology_version=body.topology_version,
            domain_pack_id=body.domain_pack_id,
            domain_pack_version=body.domain_pack_version,
            rule_pack_id=body.rule_pack_id,
            rule_pack_version=body.rule_pack_version,
            idempotency_key=parse_idempotency_key(request),
        )
    except ReviewError:
        raise
    except (TypeError, ValueError) as exc:
        raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "propagation start request is invalid") from exc


def _review_command(graph_revision_id: str, body: GraphReviewBody, request: Request) -> ConfirmPropagationCommand:
    try:
        decisions = tuple(
            PropagationEdgeDecision(
                edge_id=item.edge_id,
                action=PropagationDecisionAction(item.action),
                reason=item.reason,
            )
            for item in body.edge_decisions
        )
        return ConfirmPropagationCommand(
            graph_revision_id=graph_revision_id,
            expected_graph_record_version=parse_if_match(request),
            edge_decisions=decisions,
            acknowledgements=tuple(body.acknowledgements),
            idempotency_key=parse_idempotency_key(request),
        )
    except ReviewError:
        raise
    except (TypeError, ValueError) as exc:
        raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "propagation review request is invalid") from exc


@router.post("/analyses/{analysis_id}/propagation-runs")
def start_propagation_run(
    analysis_id: str,
    body: PropagationStartBody,
    request: Request,
    access: PropagationAccess = Depends(get_propagation_access),  # noqa: B008
) -> Response:
    command = _start_command(analysis_id, body, request)
    run = _service_call(lambda: access.runtime.service.start_analysis(command, access.actor))
    return _json_response(
        status_code=202,
        resource_type="propagation_run",
        data=run_data(run),
        request_id=run.run_id,
        trace_id=run.run_id,
        headers={
            "Location": f"/api/v1/fmea/propagation-runs/{run.run_id}",
            "ETag": f'"{run.record_version}"',
        },
    )


@router.get("/propagation-runs/{run_id}")
def get_propagation_run(
    run_id: str,
    access: PropagationAccess = Depends(get_propagation_access),  # noqa: B008
) -> Response:
    run = _service_call(lambda: access.runtime.service.get_run(run_id, access.actor))
    return _json_response(
        status_code=200,
        resource_type="propagation_run",
        data=run_data(run),
        request_id=run.run_id,
        trace_id=run.run_id,
        headers={"ETag": f'"{run.record_version}"'},
    )


@router.get("/propagation-graphs/{graph_revision_id}")
def get_propagation_graph(
    graph_revision_id: str,
    access: PropagationAccess = Depends(get_propagation_access),  # noqa: B008
) -> Response:
    graph = _service_call(lambda: access.runtime.service.get_graph(graph_revision_id, access.actor))
    if graph is None:
        raise ReviewError("FMEA_PROPAGATION_GRAPH_NOT_FOUND", "propagation graph revision was not found")
    return _json_response(
        status_code=200,
        resource_type="propagation_graph",
        data=graph_data(graph),
        request_id=graph.graph_revision_id,
        trace_id=graph.graph_revision_id,
        headers={"ETag": f'"{graph.record_version}"'},
    )


@router.get("/propagation-graphs/{graph_revision_id}/paths")
def list_propagation_paths(
    graph_revision_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=_MAX_PATH_PAGE),
    cursor: str | None = Query(default=None),
    access: PropagationAccess = Depends(get_propagation_access),  # noqa: B008
) -> Response:
    graph = _service_call(lambda: access.runtime.service.get_graph(graph_revision_id, access.actor))
    if graph is None:
        raise ReviewError("FMEA_PROPAGATION_GRAPH_NOT_FOUND", "propagation graph revision was not found")
    position = _decode_cursor(request, cursor)
    paths = tuple(sorted(graph.paths, key=lambda item: item.path_id))
    start = 0
    if position is not None:
        cursor_graph_id, cursor_path_id = position
        if cursor_graph_id != graph_revision_id:
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "cursor is invalid")
        for index, path in enumerate(paths):
            if path.path_id == cursor_path_id:
                start = index + 1
                break
        else:
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "cursor is invalid")
    page = paths[start : start + limit]
    next_cursor = None
    if start + len(page) < len(paths) and page:
        next_cursor = _encode_cursor(request, graph_revision_id, page[-1].path_id)
    data = PropagationPathPage(
        items=[path_data(item) for item in page],
        next_cursor=next_cursor,
        limit=limit,
    )
    return _json_response(
        status_code=200,
        resource_type="propagation_path_history",
        data=data,
        request_id=graph_revision_id,
        trace_id=graph_revision_id,
    )


@router.post("/propagation-graphs/{graph_revision_id}/reviews")
def review_propagation_graph(
    graph_revision_id: str,
    body: GraphReviewBody,
    request: Request,
    access: PropagationAccess = Depends(get_propagation_access),  # noqa: B008
) -> Response:
    command = _review_command(graph_revision_id, body, request)
    result = _service_call(lambda: access.runtime.service.confirm_graph(command, access.actor))
    stable_request_id = result.decision_id
    return _json_response(
        status_code=200,
        resource_type="propagation_review",
        data=review_result_data(result),
        request_id=stable_request_id,
        trace_id=stable_request_id,
        headers={"ETag": f'"{result.graph.record_version}"'},
    )


__all__ = [
    "PropagationAccess",
    "edge_data",
    "get_propagation_access",
    "get_propagation_graph",
    "get_propagation_run",
    "graph_data",
    "list_propagation_paths",
    "path_data",
    "review_propagation_graph",
    "review_result_data",
    "router",
    "run_data",
    "start_propagation_run",
]
