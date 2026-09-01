"""Versioned REST adapter for the FMEA governance lifecycle."""

# ruff: noqa: B008

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from core_domain.fmea.states import ActorType
from fmea_application.governance_contracts import (
    ApprovalCommand,
    ApprovalRejectionCommand,
    AssembleRevisionCommand,
    GovernanceHistoryQuery,
    PublishCommand,
    RevisionAssemblyRequest,
    SubmitApprovalCommand,
    SupersedePublicationCommand,
    WithdrawApprovalCommand,
    WithdrawPublicationCommand,
)
from fmea_application.governance_service import GovernanceServiceError
from fmea_application.review_contracts import ActorContext
from fmea_application.review_errors import ReviewError
from fmea_infrastructure.composition import GovernanceRuntime
from fmea_infrastructure.local_auth import LocalReviewAuthProvider

from .fmea_governance_contracts import (
    EMPTY_FILTER_HASH,
    ApprovalDecisionBody,
    ApprovalSubmissionBody,
    ApprovalWithdrawalBody,
    PublicationBody,
    PublicationWithdrawalBody,
    RevisionAssemblyBody,
    SupersessionBody,
    approval_result_data,
    approval_submission_result_data,
    approval_withdrawal_result_data,
    decode_history_cursor,
    encode_history_cursor,
    governance_envelope,
    history_data,
    publication_data,
    publication_result_data,
    publication_withdrawal_result_data,
    readiness_data,
    readiness_suggestion_data,
    revision_data,
    revision_result_data,
    snapshot_data,
    supersession_result_data,
)
from .workspace_registry import WorkspaceConfig, WorkspaceNotFoundError

router = APIRouter(prefix="/api/v1/fmea", tags=["fmea-governance-v1"])
_BEARER = re.compile(r"^Bearer ([^\s]+)$")
_ETAG = re.compile(r'^"([1-9][0-9]*)"$')
_MAX_HISTORY_PAGE_SIZE = 100

_ERROR_STATUS = {
    "FMEA_GOVERNANCE_REVISION_NOT_FOUND": 404,
    "FMEA_GOVERNANCE_REVISION_STALE": 409,
    "FMEA_GOVERNANCE_NOT_READY": 409,
    "FMEA_GOVERNANCE_ACTIVE_RUN": 409,
    "FMEA_GOVERNANCE_APPROVAL_NOT_FOUND": 404,
    "FMEA_GOVERNANCE_APPROVAL_STATE_INVALID": 409,
    "FMEA_GOVERNANCE_APPROVAL_STALE": 409,
    "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN": 403,
    "FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN": 403,
    "FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID": 409,
    "FMEA_GOVERNANCE_SUPERSESSION_INVALID": 409,
    "FMEA_GOVERNANCE_VERSION_CONFLICT": 412,
    "FMEA_GOVERNANCE_IDEMPOTENCY_CONFLICT": 409,
    "FMEA_GOVERNANCE_CURSOR_INVALID": 400,
    "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE": 503,
    "FMEA_GOVERNANCE_WORKSPACE_CONFIGURATION_INVALID": 503,
    "FMEA_GOVERNANCE_APPROVAL_CONFIRMATION_REQUIRED": 422,
    "FMEA_GOVERNANCE_PUBLICATION_CONFIRMATION_REQUIRED": 422,
    "FMEA_GOVERNANCE_WITHDRAWAL_CONFIRMATION_REQUIRED": 422,
    "FMEA_GOVERNANCE_APPROVAL_WITHDRAWAL_CONFIRMATION_REQUIRED": 422,
    "FMEA_GOVERNANCE_PUBLICATION_WITHDRAWAL_CONFIRMATION_REQUIRED": 422,
    "FMEA_GOVERNANCE_SUPERSESSION_CONFIRMATION_REQUIRED": 422,
    "FMEA_GOVERNANCE_REQUEST_INVALID": 400,
    "FMEA_PRECONDITION_REQUIRED": 428,
}


@dataclass(frozen=True, slots=True)
class GovernanceAccess:
    actor: ActorContext
    model_actor: ActorContext
    workspace: WorkspaceConfig
    runtime: GovernanceRuntime


def _problem_response(error: ReviewError, *, errors: list[dict[str, object]] | None = None) -> JSONResponse:
    code = error.code if error.code in _ERROR_STATUS else "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE"
    status = _ERROR_STATUS[code]
    trace_id = str(uuid4())
    detail = error.public_message if code == error.code else "FMEA governance request failed"
    problem = {
        "type": f"/problems/{code}",
        "title": "FMEA governance request failed.",
        "status": status,
        "code": code,
        "detail": detail,
        "trace_id": trace_id,
        "retryable": error.retryable if code == error.code else True,
        "errors": errors or [],
        "error": {
            "code": code,
            "detail": detail,
            "trace_id": trace_id,
            "retryable": error.retryable if code == error.code else True,
            "errors": errors or [],
        },
    }
    return JSONResponse(status_code=status, content=problem, media_type="application/problem+json")


def governance_error_response(_request: Request, error: GovernanceServiceError) -> JSONResponse:
    return _problem_response(error)


def is_governance_path(path: str) -> bool:
    return (
        path.startswith("/api/v1/fmea/revisions/")
        or path.startswith("/api/v1/fmea/approval-submissions/")
        or path.startswith("/api/v1/fmea/approvals/")
        or path.startswith("/api/v1/fmea/publications/")
        or re.fullmatch(r"/api/v1/fmea/analyses/[^/]+/revisions", path) is not None
    )


def governance_validation_error_response(_request: Request, error: RequestValidationError) -> JSONResponse:
    safe_errors = [
        {
            "loc": [str(part)[:64] for part in item.get("loc", ()) if str(part) != "body"][:6],
            "message": "invalid request field",
        }
        for item in error.errors()[:16]
    ]
    return _problem_response(
        GovernanceServiceError("FMEA_GOVERNANCE_REQUEST_INVALID", "governance request validation failed"),
        errors=safe_errors,
    )


def _request_id(request: Request) -> str:
    value = request.headers.get("x-request-id")
    return value if value is not None and 1 <= len(value) <= 128 else str(uuid4())


def _trace_id(request: Request) -> str:
    value = request.headers.get("x-trace-id")
    return value if value is not None and 1 <= len(value) <= 128 else str(uuid4())


def _envelope(request: Request, resource_type: str, data: object) -> dict[str, object]:
    return governance_envelope(resource_type, data, request_id=_request_id(request), trace_id=_trace_id(request))


def _response(
    request: Request, resource_type: str, data: object, *, status: int = 200, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(status_code=status, content=_envelope(request, resource_type, data), headers=headers)


def _authorization_token(request: Request) -> str:
    header = request.headers.get("authorization")
    if header is None:
        raise ReviewError("FMEA_AUTH_REQUIRED", "review authentication is required")
    match = _BEARER.fullmatch(header)
    if match is None:
        raise ReviewError("FMEA_AUTH_REQUIRED", "review authentication is required")
    return match.group(1)


def _runtime_for(request: Request, workspace: WorkspaceConfig) -> GovernanceRuntime:
    cache = cast(dict[str, GovernanceRuntime], request.app.state.governance_runtimes)
    lock = cast(Lock, request.app.state.governance_runtime_lock)
    with lock:
        existing = cache.get(workspace.workspace_id)
        if existing is not None:
            return existing
        factory = cast(
            Callable[[WorkspaceConfig], GovernanceRuntime] | None, request.app.state.governance_runtime_factory
        )
        try:
            if factory is None:
                from fmea_infrastructure.composition import build_default_workspace_governance_runtime

                runtime = build_default_workspace_governance_runtime(workspace)
            else:
                runtime = factory(workspace)
        except ReviewError:
            raise
        except Exception as exc:
            raise GovernanceServiceError(
                "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE",
                "FMEA governance runtime is unavailable",
                retryable=True,
            ) from exc
        service = getattr(runtime, "service", None)
        assistance = getattr(runtime, "assistance_service", None)
        if service is None or assistance is None:
            raise GovernanceServiceError(
                "FMEA_GOVERNANCE_WORKSPACE_CONFIGURATION_INVALID",
                "FMEA governance runtime is incomplete",
            )
        cache[workspace.workspace_id] = runtime
        return runtime


def get_governance_access(request: Request) -> GovernanceAccess:
    configured_error = cast(ReviewError | None, request.app.state.review_auth_error)
    if configured_error is not None:
        raise configured_error
    provider = cast(LocalReviewAuthProvider | None, request.app.state.review_auth_provider)
    if provider is None:
        raise ReviewError("FMEA_AUTH_CONFIGURATION_INVALID", "review authentication is not configured")
    remote_host = request.client.host if request.client is not None else None
    actor = provider.authenticate(_authorization_token(request), remote_host)
    try:
        workspace = request.app.state.workspace_registry.get(actor.workspace_id)
    except WorkspaceNotFoundError as exc:
        raise ReviewError("FMEA_REVIEW_FORBIDDEN", "review workspace is not available") from exc
    model_actor = ActorContext("fmea-model-assistant", ActorType.MODEL, frozenset(), actor.workspace_id)
    return GovernanceAccess(actor, model_actor, workspace, _runtime_for(request, workspace))


def _service_call(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except ReviewError:
        raise
    except (TypeError, ValueError) as exc:
        raise GovernanceServiceError("FMEA_GOVERNANCE_REQUEST_INVALID", "governance request is invalid") from exc
    except Exception as exc:
        raise GovernanceServiceError(
            "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE", "FMEA governance storage is unavailable", retryable=True
        ) from exc


def _if_match(request: Request) -> int:
    raw = request.headers.get("if-match")
    if raw is None:
        raise GovernanceServiceError("FMEA_PRECONDITION_REQUIRED", "If-Match is required")
    match = _ETAG.fullmatch(raw)
    if match is None:
        raise GovernanceServiceError("FMEA_GOVERNANCE_REQUEST_INVALID", "If-Match must be a quoted positive integer")
    return int(match.group(1))


def _idempotency_key(request: Request) -> str:
    raw = request.headers.get("idempotency-key")
    if raw is None:
        raise GovernanceServiceError("FMEA_PRECONDITION_REQUIRED", "Idempotency-Key is required")
    try:
        value = UUID(raw)
    except (AttributeError, ValueError) as exc:
        raise GovernanceServiceError(
            "FMEA_GOVERNANCE_REQUEST_INVALID", "Idempotency-Key must be a canonical UUID"
        ) from exc
    if str(value) != raw:
        raise GovernanceServiceError("FMEA_GOVERNANCE_REQUEST_INVALID", "Idempotency-Key must be a canonical UUID")
    return raw


def _require_confirmation(value: bool, code: str) -> None:
    if value is not True:
        raise GovernanceServiceError(code, "explicit human confirmation is required")


def _headers(*, record_version: int | None = None, location: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if record_version is not None:
        headers["ETag"] = f'"{record_version}"'
    if location is not None:
        headers["Location"] = location
    return headers


def _history(
    request: Request,
    access: GovernanceAccess,
    *,
    resource_type: str,
    resource_id: str,
    cursor: str | None,
    limit: int,
    descending: bool,
    operation: Callable[[GovernanceHistoryQuery], Any],
) -> JSONResponse:
    if limit < 1 or limit > _MAX_HISTORY_PAGE_SIZE:
        raise GovernanceServiceError("FMEA_GOVERNANCE_CURSOR_INVALID", "history page size is invalid")
    secret = cast(bytes, request.app.state.governance_cursor_secret)
    inner_cursor = None
    if cursor is not None:
        try:
            inner_cursor = decode_history_cursor(
                secret,
                cursor,
                workspace_id=access.workspace.workspace_id,
                resource_type=resource_type,
                resource_id=resource_id,
                descending=descending,
                page_size=limit,
                filter_hash=EMPTY_FILTER_HASH,
            )
        except (TypeError, ValueError) as exc:
            raise GovernanceServiceError(
                "FMEA_GOVERNANCE_CURSOR_INVALID", "governance history cursor is invalid"
            ) from exc
    query = GovernanceHistoryQuery(
        workspace_id=access.workspace.workspace_id,
        resource_type=cast(Any, resource_type),
        resource_id=resource_id,
        page_size=limit,
        cursor=inner_cursor,
        descending=descending,
    )
    page = _service_call(lambda: operation(query))
    next_cursor = getattr(page, "next_cursor", None)
    if next_cursor is not None:
        try:
            next_cursor = encode_history_cursor(
                secret,
                workspace_id=access.workspace.workspace_id,
                resource_type=resource_type,
                resource_id=resource_id,
                descending=descending,
                page_size=limit,
                filter_hash=EMPTY_FILTER_HASH,
                repository_cursor=next_cursor,
            )
        except (TypeError, ValueError) as exc:
            raise GovernanceServiceError(
                "FMEA_GOVERNANCE_CURSOR_INVALID", "governance history cursor is invalid"
            ) from exc
    data = history_data(getattr(page, "events", ()), next_cursor=next_cursor, limit=limit)
    return _response(request, f"{resource_type}_history", data)


@router.post("/analyses/{analysis_id}/revisions")
def assemble_revision(
    analysis_id: str,
    body: RevisionAssemblyBody,
    request: Request,
    access: GovernanceAccess = Depends(get_governance_access),
) -> JSONResponse:
    _require_confirmation(body.confirm_human_approval, "FMEA_GOVERNANCE_APPROVAL_CONFIRMATION_REQUIRED")
    expected = _if_match(request)
    key = _idempotency_key(request)
    command = AssembleRevisionCommand(
        RevisionAssemblyRequest(analysis_id, body.parent_revision_id, expected, body.parent_revision_hash), key
    )
    result = _service_call(lambda: access.runtime.service.assemble(command, access.actor))
    data = revision_result_data(result)
    return _response(
        request,
        "revision",
        data,
        status=201,
        headers=_headers(record_version=data.record_version, location=f"/api/v1/fmea/revisions/{data.revision_id}"),
    )


@router.get("/revisions/{revision_id}")
def show_revision(
    revision_id: str, request: Request, access: GovernanceAccess = Depends(get_governance_access)
) -> JSONResponse:
    revision, record_version = _service_call(
        lambda: access.runtime.service.get_revision_record(revision_id, access.actor)
    )
    data = revision_data(revision, record_version=record_version)
    return _response(request, "revision", data, headers=_headers(record_version=record_version))


@router.get("/revisions/{revision_id}/readiness")
def show_readiness(
    revision_id: str, request: Request, access: GovernanceAccess = Depends(get_governance_access)
) -> JSONResponse:
    report = _service_call(lambda: access.runtime.service.readiness(revision_id, access.actor))
    _, record_version = _service_call(lambda: access.runtime.service.get_revision_record(revision_id, access.actor))
    data = readiness_data(report, record_version=record_version)
    return _response(request, "revision_readiness", data, headers=_headers(record_version=record_version))


@router.post("/revisions/{revision_id}/readiness-suggestion-runs")
def suggest_readiness(
    revision_id: str, request: Request, access: GovernanceAccess = Depends(get_governance_access)
) -> JSONResponse:
    report = _service_call(lambda: access.runtime.service.readiness(revision_id, access.actor))
    suggestion = _service_call(
        lambda: access.runtime.assistance_service.suggest_readiness_checklist(report, access.model_actor)
    )
    data = readiness_suggestion_data(suggestion)
    return _response(request, "readiness_suggestion", data, status=202)


@router.post("/revisions/{revision_id}/approval-submissions")
def submit_approval(
    revision_id: str,
    body: ApprovalSubmissionBody,
    request: Request,
    access: GovernanceAccess = Depends(get_governance_access),
) -> JSONResponse:
    _require_confirmation(body.confirm_human_approval, "FMEA_GOVERNANCE_APPROVAL_CONFIRMATION_REQUIRED")
    command = SubmitApprovalCommand(revision_id, body.revision_hash, _if_match(request), _idempotency_key(request))
    result = _service_call(lambda: access.runtime.service.submit_for_approval(command, access.actor))
    data = approval_submission_result_data(result)
    return _response(
        request,
        "approval_submission",
        data,
        status=201,
        headers=_headers(
            record_version=data.record_version, location=f"/api/v1/fmea/approval-submissions/{data.submission_id}"
        ),
    )


def _approval_command(
    submission_id: str, body: ApprovalDecisionBody, request: Request, rejection: bool = False
) -> ApprovalCommand:
    command_type = ApprovalRejectionCommand if rejection else ApprovalCommand
    return command_type(
        submission_id, body.revision_id, body.revision_hash, _if_match(request), body.reason, _idempotency_key(request)
    )


@router.post("/approval-submissions/{submission_id}/approvals")
def approve(
    submission_id: str,
    body: ApprovalDecisionBody,
    request: Request,
    access: GovernanceAccess = Depends(get_governance_access),
) -> JSONResponse:
    _require_confirmation(body.confirm_human_approval, "FMEA_GOVERNANCE_APPROVAL_CONFIRMATION_REQUIRED")
    result = _service_call(
        lambda: access.runtime.service.approve(_approval_command(submission_id, body, request), access.actor)
    )
    data = approval_result_data(result)
    return _response(
        request,
        "approval",
        data,
        status=201,
        headers=_headers(record_version=data.record_version, location=f"/api/v1/fmea/approvals/{data.approval_id}"),
    )


@router.post("/approval-submissions/{submission_id}/rejections")
def reject(
    submission_id: str,
    body: ApprovalDecisionBody,
    request: Request,
    access: GovernanceAccess = Depends(get_governance_access),
) -> JSONResponse:
    _require_confirmation(body.confirm_human_approval, "FMEA_GOVERNANCE_APPROVAL_CONFIRMATION_REQUIRED")
    result = _service_call(
        lambda: access.runtime.service.reject(_approval_command(submission_id, body, request, True), access.actor)
    )
    data = approval_result_data(result)
    return _response(
        request,
        "approval_rejection",
        data,
        status=201,
        headers=_headers(record_version=data.record_version, location=f"/api/v1/fmea/approvals/{data.approval_id}"),
    )


@router.post("/approvals/{approval_id}/withdrawals")
def withdraw_approval(
    approval_id: str,
    body: ApprovalWithdrawalBody,
    request: Request,
    access: GovernanceAccess = Depends(get_governance_access),
) -> JSONResponse:
    _require_confirmation(body.confirm_approval_withdrawal, "FMEA_GOVERNANCE_APPROVAL_WITHDRAWAL_CONFIRMATION_REQUIRED")
    command = WithdrawApprovalCommand(
        approval_id, body.revision_hash, _if_match(request), body.reason, _idempotency_key(request)
    )
    result = _service_call(lambda: access.runtime.service.withdraw_approval(command, access.actor))
    data = approval_withdrawal_result_data(result)
    return _response(
        request,
        "approval_withdrawal",
        data,
        status=201,
        headers=_headers(location=f"/api/v1/fmea/approvals/{data.approval_id}/withdrawals"),
    )


@router.get("/revisions/{revision_id}/approval-events")
def approval_events(
    revision_id: str,
    request: Request,
    cursor: str | None = None,
    limit: int = Query(50),
    descending: bool = False,
    access: GovernanceAccess = Depends(get_governance_access),
) -> JSONResponse:
    return _history(
        request,
        access,
        resource_type="revision",
        resource_id=revision_id,
        cursor=cursor,
        limit=limit,
        descending=descending,
        operation=lambda query: access.runtime.service.list_approval_events(query, access.actor),
    )


@router.post("/revisions/{revision_id}/publications")
def publish_revision(
    revision_id: str, body: PublicationBody, request: Request, access: GovernanceAccess = Depends(get_governance_access)
) -> JSONResponse:
    _require_confirmation(body.confirm_publication, "FMEA_GOVERNANCE_PUBLICATION_CONFIRMATION_REQUIRED")
    if body.revision_hash is None:
        raise GovernanceServiceError("FMEA_GOVERNANCE_REQUEST_INVALID", "revision_hash is required")
    command = PublishCommand(
        revision_id, body.revision_hash, body.approval_id, _if_match(request), _idempotency_key(request)
    )
    result = _service_call(lambda: access.runtime.service.publish(command, access.actor))
    data = publication_result_data(result)
    return _response(
        request,
        "publication",
        data,
        status=201,
        headers=_headers(
            record_version=data.record_version, location=f"/api/v1/fmea/publications/{data.publication_id}"
        ),
    )


@router.get("/publications/{publication_id}")
def show_publication(
    publication_id: str, request: Request, access: GovernanceAccess = Depends(get_governance_access)
) -> JSONResponse:
    lifecycle = _service_call(lambda: access.runtime.service.get_publication(publication_id, access.actor))
    data = publication_data(lifecycle)
    return _response(request, "publication", data, headers=_headers(record_version=data.record_version))


@router.get("/publications/{publication_id}/snapshot")
def show_snapshot(
    publication_id: str, request: Request, access: GovernanceAccess = Depends(get_governance_access)
) -> JSONResponse:
    snapshot = _service_call(lambda: access.runtime.service.get_snapshot(publication_id, access.actor))
    return _response(request, "publication_snapshot", snapshot_data(snapshot))


@router.post("/publications/{publication_id}/withdrawals")
def withdraw_publication(
    publication_id: str,
    body: PublicationWithdrawalBody,
    request: Request,
    access: GovernanceAccess = Depends(get_governance_access),
) -> JSONResponse:
    _require_confirmation(
        body.confirm_publication_withdrawal, "FMEA_GOVERNANCE_PUBLICATION_WITHDRAWAL_CONFIRMATION_REQUIRED"
    )
    command = WithdrawPublicationCommand(
        publication_id, _if_match(request), body.reason, body.replacement_publication_id, _idempotency_key(request)
    )
    result = _service_call(lambda: access.runtime.service.withdraw_publication(command, access.actor))
    data = publication_withdrawal_result_data(result)
    return _response(
        request,
        "publication_withdrawal",
        data,
        status=201,
        headers=_headers(location=f"/api/v1/fmea/publications/{data.publication_id}/withdrawals"),
    )


@router.post("/publications/{publication_id}/supersessions")
def supersede_publication(
    publication_id: str,
    body: SupersessionBody,
    request: Request,
    access: GovernanceAccess = Depends(get_governance_access),
) -> JSONResponse:
    _require_confirmation(body.confirm_supersession, "FMEA_GOVERNANCE_SUPERSESSION_CONFIRMATION_REQUIRED")
    command = SupersedePublicationCommand(
        publication_id,
        body.replacement_publication_id,
        _if_match(request),
        body.replacement_record_version,
        body.reason,
        _idempotency_key(request),
    )
    result = _service_call(lambda: access.runtime.service.supersede(command, access.actor))
    data = supersession_result_data(result)
    return _response(
        request,
        "publication_supersession",
        data,
        status=201,
        headers=_headers(location=f"/api/v1/fmea/publications/{data.old_publication_id}/supersessions"),
    )


@router.get("/publications/{publication_id}/lifecycle-events")
def publication_events(
    publication_id: str,
    request: Request,
    cursor: str | None = None,
    limit: int = Query(50),
    descending: bool = False,
    access: GovernanceAccess = Depends(get_governance_access),
) -> JSONResponse:
    return _history(
        request,
        access,
        resource_type="publication",
        resource_id=publication_id,
        cursor=cursor,
        limit=limit,
        descending=descending,
        operation=lambda query: access.runtime.service.list_publication_events(query, access.actor),
    )


__all__ = [
    "get_governance_access",
    "governance_error_response",
    "governance_validation_error_response",
    "is_governance_path",
    "router",
]
