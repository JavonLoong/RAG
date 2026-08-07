"""Versioned, non-streaming GraphRAG query endpoint."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from core_domain.query_contracts import (
    ErrorDetail,
    ErrorEvent,
    QueryErrorResponse,
    QueryRequest,
    QueryResponse,
    QueryStreamEvent,
)

from .query_service import QueryExecutionError, QueryService, encode_sse
from .workspace_registry import WorkspaceNotFoundError

router = APIRouter(prefix="/api/v1", tags=["query-v1"])

_ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 422,
    "WORKSPACE_NOT_FOUND": 404,
    "INDEX_NOT_READY": 409,
    "MODE_UNAVAILABLE": 409,
    "LLM_UNAVAILABLE": 503,
    "QUERY_FAILED": 500,
}
_ERROR_MESSAGE: dict[str, str] = {
    "INVALID_REQUEST": "Request validation failed.",
    "WORKSPACE_NOT_FOUND": "Workspace was not found.",
    "INDEX_NOT_READY": "The workspace index is not ready.",
    "MODE_UNAVAILABLE": "The requested query mode is unavailable.",
    "LLM_UNAVAILABLE": "The language model service is unavailable.",
    "QUERY_FAILED": "Query execution failed.",
}
_ERROR_RETRYABLE: dict[str, bool] = {
    "INVALID_REQUEST": False,
    "WORKSPACE_NOT_FOUND": False,
    "INDEX_NOT_READY": True,
    "MODE_UNAVAILABLE": False,
    "LLM_UNAVAILABLE": True,
    "QUERY_FAILED": True,
}


def get_query_service(request: Request) -> QueryService:
    """Resolve the production service while remaining dependency-override friendly."""

    return request.app.state.query_service


def _error_response(
    *,
    code: str,
    status_code: int,
    retryable: bool,
) -> JSONResponse:
    payload = QueryErrorResponse(
        request_id=str(uuid4()),
        trace_id=str(uuid4()),
        error=ErrorDetail(
            code=code,
            message=_ERROR_MESSAGE[code],
            retryable=retryable,
        ),
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def _known_error_response(error: QueryExecutionError) -> JSONResponse:
    code = error.code if error.code in _ERROR_STATUS else "QUERY_FAILED"
    return _error_response(
        code=code,
        status_code=_ERROR_STATUS[code],
        retryable=_ERROR_RETRYABLE[code],
    )


def validation_error_response(_request: Request, _error: RequestValidationError) -> JSONResponse:
    """Return the v1 validation envelope without exposing FastAPI's detail array."""

    return _error_response(code="INVALID_REQUEST", status_code=422, retryable=False)


def _stream_failure_event(*, request_id: str, sequence: int) -> ErrorEvent:
    return ErrorEvent(
        request_id=request_id,
        sequence=sequence,
        error=ErrorDetail(
            code="STREAM_FAILED",
            message="stream generation failed",
            retryable=True,
        ),
    )


def _encode_stream(first_event: QueryStreamEvent, events: Iterator[QueryStreamEvent]) -> Iterator[bytes]:
    sequence = first_event.sequence
    yield encode_sse(first_event)
    try:
        for event in events:
            sequence = event.sequence
            yield encode_sse(event)
            if event.event in {"error", "final"}:
                return
    except Exception:
        yield encode_sse(_stream_failure_event(request_id=first_event.request_id, sequence=sequence + 1))


@router.post(
    "/query",
    response_model=QueryResponse,
    responses={
        404: {"model": QueryErrorResponse},
        409: {"model": QueryErrorResponse},
        422: {"model": QueryErrorResponse},
        500: {"model": QueryErrorResponse},
        503: {"model": QueryErrorResponse},
    },
)
def query_v1(
    payload: QueryRequest,
    service: QueryService = Depends(get_query_service),  # noqa: B008
) -> QueryResponse:
    try:
        return service.query(payload)
    except WorkspaceNotFoundError:
        return _error_response(
            code="WORKSPACE_NOT_FOUND",
            status_code=404,
            retryable=False,
        )  # type: ignore[return-value]
    except QueryExecutionError as error:
        return _known_error_response(error)  # type: ignore[return-value]
    except Exception:
        return _error_response(
            code="QUERY_FAILED",
            status_code=500,
            retryable=True,
        )  # type: ignore[return-value]


@router.post(
    "/query/stream",
    response_model=None,
    responses={
        404: {"model": QueryErrorResponse},
        409: {"model": QueryErrorResponse},
        422: {"model": QueryErrorResponse},
        500: {"model": QueryErrorResponse},
        503: {"model": QueryErrorResponse},
    },
)
def query_stream_v1(
    payload: QueryRequest,
    service: QueryService = Depends(get_query_service),  # noqa: B008
) -> StreamingResponse | JSONResponse:
    try:
        events = iter(service.stream(payload))
        first_event = next(events)
        if first_event.event != "meta":
            return _error_response(
                code="QUERY_FAILED",
                status_code=500,
                retryable=True,
            )
    except WorkspaceNotFoundError:
        return _error_response(
            code="WORKSPACE_NOT_FOUND",
            status_code=404,
            retryable=False,
        )
    except QueryExecutionError as error:
        return _known_error_response(error)
    except Exception:
        return _error_response(
            code="QUERY_FAILED",
            status_code=500,
            retryable=True,
        )

    return StreamingResponse(
        _encode_stream(first_event, events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["get_query_service", "query_stream_v1", "query_v1", "router", "validation_error_response"]
