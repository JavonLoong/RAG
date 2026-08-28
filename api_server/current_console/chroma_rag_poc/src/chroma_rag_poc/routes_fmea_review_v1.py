"""Versioned HTTP adapter for the local FMEA review workflow."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.types import Message, Receive, Scope, Send

from core_domain.fmea.scoring import RiskAssessment
from fmea_application.review_contracts import (
    ActorContext,
    EvidenceRequestItem,
    FieldReviewEdit,
    ReviewContext,
    ReviewDecisionCommand,
    ReviewDecisionRecord,
    ReviewSuggestion,
    ReviewSuggestionRun,
    StartReviewSuggestionCommand,
    UnresolvedAcknowledgement,
)
from fmea_application.review_errors import ReviewError
from fmea_infrastructure.composition import ReviewRuntime
from fmea_infrastructure.local_auth import LocalReviewAuthProvider

from .fmea_review_contracts import (
    ConflictData,
    DecisionData,
    EvidenceData,
    EvidenceRefData,
    EvidenceRequestBody,
    EvidenceRequestData,
    FieldEditData,
    FieldFindingData,
    FieldReviewData,
    FmeaEnvelope,
    FmeaIdentity,
    FmeaProblem,
    FmeaRowData,
    HistoryPage,
    MissingEvidenceData,
    ModelManifestData,
    RetrievalData,
    ReviewContextData,
    ReviewDecisionBody,
    ReviewDecisionResultData,
    ReviewRunData,
    StartSuggestionBody,
    SuggestionData,
    UnresolvedAcknowledgementData,
)
from .workspace_registry import WorkspaceConfig, WorkspaceNotFoundError

router = APIRouter(prefix="/api/v1/fmea", tags=["fmea-review-v1"])
FMEA_BODY_LIMIT = 256 * 1024
_BEARER = re.compile(r"^Bearer ([^\s]+)$")
_ETAG = re.compile(r'^"([1-9][0-9]*)"$')
_CURSOR_PART = re.compile(r"^[A-Za-z0-9_-]+$")

_ERROR_STATUS = {
    "FMEA_REVIEW_REQUEST_INVALID": 400,
    "FMEA_AUTH_REQUIRED": 401,
    "FMEA_REVIEW_FORBIDDEN": 403,
    "FMEA_ROW_NOT_FOUND": 404,
    "FMEA_REVIEW_SUGGESTION_NOT_FOUND": 404,
    "FMEA_IDEMPOTENCY_CONFLICT": 409,
    "FMEA_REVIEW_TERMINAL": 409,
    "FMEA_REVIEW_SUGGESTION_STALE": 409,
    "FMEA_VERSION_CONFLICT": 412,
    "FMEA_RISK_VERSION_CONFLICT": 412,
    "FMEA_REVIEW_ACTION_INVALID": 422,
    "FMEA_REVIEW_FIELD_INVALID": 422,
    "FMEA_EVIDENCE_INVALID": 422,
    "FMEA_UNRESOLVED_ACK_REQUIRED": 422,
    "FMEA_REVIEW_SOURCE_MISSING": 422,
    "FMEA_PRECONDITION_REQUIRED": 428,
    "FMEA_REVIEW_RATE_LIMITED": 429,
    "FMEA_MODEL_SUGGESTION_INVALID": 502,
    "FMEA_MODEL_SUGGESTION_UNAVAILABLE": 503,
    "FMEA_REVIEW_STORAGE_UNAVAILABLE": 503,
    "FMEA_AUTH_CONFIGURATION_INVALID": 503,
    "FMEA_REVIEW_CONFIRMATION_REQUIRED": 422,
    "FMEA_RISK_HUMAN_CONFIRMATION_REQUIRED": 422,
}
_ERROR_TITLES = {
    "FMEA_AUTH_REQUIRED": "Review authentication required.",
    "FMEA_REVIEW_FORBIDDEN": "Review access forbidden.",
    "FMEA_VERSION_CONFLICT": "Review version conflict.",
    "FMEA_PRECONDITION_REQUIRED": "Review precondition required.",
    "FMEA_REVIEW_REQUEST_INVALID": "Invalid review request.",
}


@dataclass(frozen=True, slots=True)
class ReviewAccess:
    actor: ActorContext
    workspace: WorkspaceConfig
    runtime: ReviewRuntime


def _problem_response(
    *,
    code: str,
    status_code: int,
    detail: str,
    retryable: bool,
    trace_id: str | None = None,
    errors: list[dict[str, object]] | None = None,
) -> JSONResponse:
    problem = FmeaProblem(
        type=f"/problems/{code}",
        title=_ERROR_TITLES.get(code, "FMEA review request failed."),
        status=status_code,
        code=code,
        detail=detail,
        trace_id=trace_id or str(uuid4()),
        retryable=retryable,
        errors=errors or [],
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(mode="json"),
        media_type="application/problem+json",
    )


def review_error_response(_request: Request, error: ReviewError) -> JSONResponse:
    code = error.code if error.code in _ERROR_STATUS else "FMEA_REVIEW_STORAGE_UNAVAILABLE"
    status_code = _ERROR_STATUS[code]
    return _problem_response(
        code=code,
        status_code=status_code,
        detail=error.public_message,
        retryable=error.retryable,
    )


def fmea_validation_error_response(_request: Request, error: RequestValidationError) -> JSONResponse:
    def validation_code(item: dict[str, Any]) -> str:
        location = tuple(str(part) for part in item.get("loc", ()) if str(part) != "body")
        if not location or item.get("type") == "missing":
            return "FMEA_REVIEW_REQUEST_INVALID"
        leaf = location[-1]
        if location == ("action",):
            return "FMEA_REVIEW_ACTION_INVALID"
        if location and location[0] == "edits" and leaf in {
            "target_field",
            "operation",
            "claim_status",
            "support_status",
        }:
            return "FMEA_REVIEW_FIELD_INVALID"
        if location and location[0] == "evidence_requests" and leaf in {
            "target_field",
            "question",
            "preferred_source_types",
            "priority",
        }:
            return "FMEA_EVIDENCE_INVALID"
        if location and location[0] == "unresolved_acknowledgements" and leaf in {
            "target_field",
            "claim_status",
            "reason",
        }:
            return "FMEA_UNRESOLVED_ACK_REQUIRED"
        return "FMEA_REVIEW_REQUEST_INVALID"

    safe_errors: list[dict[str, object]] = []
    codes: list[str] = []
    for item in error.errors()[:16]:
        location = [str(part)[:64] for part in item.get("loc", ()) if str(part) != "body"][:6]
        safe_errors.append({"loc": location, "message": "invalid request field"})
        codes.append(validation_code(cast(dict[str, Any], item)))
    code = next(
        (candidate for candidate in codes if candidate != "FMEA_REVIEW_REQUEST_INVALID"),
        "FMEA_REVIEW_REQUEST_INVALID",
    )
    return _problem_response(
        code=code,
        status_code=_ERROR_STATUS[code],
        detail="review request validation failed",
        retryable=False,
        errors=safe_errors,
    )


class FmeaRequestBodyLimitMiddleware:
    """Buffer and replay only FMEA POST bodies while enforcing the byte cap."""

    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")
        if not path.startswith("/api/v1/fmea/"):
            await self.app(scope, receive, send)
            return

        messages: list[Message] = []
        size = 0
        while True:
            message = await receive()
            if message.get("type") == "http.request":
                chunk = message.get("body", b"")
                if isinstance(chunk, bytes):
                    size += len(chunk)
                if size > FMEA_BODY_LIMIT:
                    response = _problem_response(
                        code="FMEA_REVIEW_REQUEST_INVALID",
                        status_code=400,
                        detail="review request body exceeds 256 KiB",
                        retryable=False,
                    )
                    await response(scope, _empty_receive, send)
                    return
                messages.append(message)
                if not message.get("more_body", False):
                    break
            else:
                messages.append(message)
                break

        async def replay() -> Message:
            if messages:
                return messages.pop(0)
            return {"type": "http.disconnect"}

        await self.app(scope, replay, send)


async def _empty_receive() -> Message:
    return {"type": "http.disconnect"}


def _authorization_token(request: Request) -> str:
    header = request.headers.get("authorization")
    if header is None:
        raise ReviewError("FMEA_AUTH_REQUIRED", "review authentication is required")
    match = _BEARER.fullmatch(header)
    if match is None:
        raise ReviewError("FMEA_AUTH_REQUIRED", "review authentication is required")
    return match.group(1)


def _runtime_for(request: Request, workspace: WorkspaceConfig) -> ReviewRuntime:
    cache = cast(dict[str, ReviewRuntime], request.app.state.review_runtimes)
    lock = cast(Lock, request.app.state.review_runtime_lock)
    with lock:
        existing = cache.get(workspace.workspace_id)
        if existing is not None:
            return existing
        factory = cast(Callable[[WorkspaceConfig], ReviewRuntime], request.app.state.review_runtime_factory)
        try:
            runtime = factory(workspace)
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError(
                "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                "review runtime is unavailable",
                retryable=True,
            ) from exc
        cache[workspace.workspace_id] = runtime
        return runtime


def get_review_access(request: Request) -> ReviewAccess:
    configured_error = cast(ReviewError | None, request.app.state.review_auth_error)
    if configured_error is not None:
        raise configured_error
    provider = cast(LocalReviewAuthProvider, request.app.state.review_auth_provider)
    token = _authorization_token(request)
    remote_host = request.client.host if request.client is not None else None
    actor = provider.authenticate(token, remote_host)
    registry = request.app.state.workspace_registry
    try:
        workspace = registry.get(actor.workspace_id)
    except WorkspaceNotFoundError as exc:
        raise ReviewError("FMEA_REVIEW_FORBIDDEN", "review workspace is not available") from exc
    return ReviewAccess(actor=actor, workspace=workspace, runtime=_runtime_for(request, workspace))


def _service_call(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except ReviewError:
        raise
    except Exception as exc:
        raise ReviewError(
            "FMEA_REVIEW_STORAGE_UNAVAILABLE",
            "review storage is unavailable",
            retryable=True,
        ) from exc


def parse_if_match(request: Request) -> int:
    value = request.headers.get("if-match")
    if value is None:
        raise ReviewError("FMEA_PRECONDITION_REQUIRED", "If-Match is required")
    match = _ETAG.fullmatch(value)
    if match is None:
        raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "If-Match must be a quoted positive integer")
    return int(match.group(1))


def parse_idempotency_key(request: Request) -> str:
    value = request.headers.get("idempotency-key")
    if value is None:
        raise ReviewError("FMEA_PRECONDITION_REQUIRED", "Idempotency-Key is required")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "Idempotency-Key must be a canonical UUID") from exc
    if str(parsed) != value:
        raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "Idempotency-Key must be a canonical UUID")
    return value


def _value(value: str | list[str] | tuple[str, ...]) -> str | tuple[str, ...]:
    return value if isinstance(value, str) else tuple(value)


def _edit_body(value: Any) -> FieldReviewEdit:
    try:
        return FieldReviewEdit(
            target_field=value.target_field,
            operation=value.operation,
            value=_value(value.value),
            claim_status=value.claim_status,
            support_status=value.support_status,
            evidence_ids=tuple(value.evidence_ids),
            reason=value.reason,
        )
    except ValueError as exc:
        raise ReviewError("FMEA_REVIEW_FIELD_INVALID", "review field edit is invalid") from exc


def _evidence_request_body(value: EvidenceRequestBody) -> EvidenceRequestItem:
    try:
        return EvidenceRequestItem(
            target_field=value.target_field,
            question=value.question,
            preferred_source_types=tuple(value.preferred_source_types),
            priority=value.priority,
        )
    except ValueError as exc:
        raise ReviewError("FMEA_EVIDENCE_INVALID", "review evidence request is invalid") from exc


def _acknowledgement_body(value: Any) -> UnresolvedAcknowledgement:
    try:
        return UnresolvedAcknowledgement(
            target_field=value.target_field,
            claim_status=value.claim_status,
            reason=value.reason,
        )
    except ValueError as exc:
        raise ReviewError("FMEA_UNRESOLVED_ACK_REQUIRED", "unresolved acknowledgement is invalid") from exc


def _decision_command(row_id: str, body: ReviewDecisionBody, request: Request) -> ReviewDecisionCommand:
    try:
        return ReviewDecisionCommand(
            row_id=row_id,
            expected_record_version=parse_if_match(request),
            idempotency_key=parse_idempotency_key(request),
            action=body.action,
            suggestion_id=body.suggestion_id,
            reason_code=body.reason_code,
            reason=body.reason,
            edits=tuple(_edit_body(item) for item in body.edits),
            evidence_requests=tuple(_evidence_request_body(item) for item in body.evidence_requests),
            unresolved_acknowledgements=tuple(_acknowledgement_body(item) for item in body.unresolved_acknowledgements),
        )
    except ReviewError:
        raise
    except ValueError as exc:
        raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "review decision action is invalid") from exc


def _suggestion_command(row_id: str, body: StartSuggestionBody, request: Request) -> StartReviewSuggestionCommand:
    try:
        return StartReviewSuggestionCommand(
            row_id=row_id,
            expected_record_version=parse_if_match(request),
            idempotency_key=parse_idempotency_key(request),
            review_policy=body.review_policy,
            focus_fields=tuple(body.focus_fields),
        )
    except ReviewError:
        raise
    except ValueError as exc:
        raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "review suggestion request is invalid") from exc


def _risk_data(value: RiskAssessment | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "severity_by_consequence_class": [[name, score] for name, score in value.severity_by_consequence_class],
        "decision_severity": value.decision_severity,
        "occurrence": value.occurrence,
        "detection": value.detection,
        "rpn": value.rpn,
        "decision_priority": value.decision_priority,
        "inherent_risk": value.inherent_risk,
        "current_risk": value.current_risk,
        "target_residual_risk": value.target_residual_risk,
        "verified_residual_risk": value.verified_residual_risk,
        "uncertainty": value.uncertainty,
        "reason": value.reason,
        "scoring_rule_pack_id": value.scoring_rule_pack_id,
        "scoring_rule_pack_version": value.scoring_rule_pack_version,
        "evidence_ids": list(value.evidence_ids),
    }


def _row_data(row: Any) -> FmeaRowData:
    return FmeaRowData.model_validate(
        {
            "row_id": row.row_id,
            "analysis_id": row.analysis_id,
            "evidence_pack_id": row.evidence_pack_id,
            "item_id": row.item_id,
            "function_id": row.function_id,
            "failure_mode": row.failure_mode,
            "causes": list(row.causes),
            "mechanisms": list(row.mechanisms),
            "effects": list(row.effects),
            "symptoms": list(row.symptoms),
            "controls": list(row.controls),
            "barriers": list(row.barriers),
            "actions": list(row.actions),
            "risk_assessment": _risk_data(row.risk_assessment),
            "claim_status": row.claim_status,
            "review_status": row.review_status,
            "publication_status": row.publication_status,
            "record_version": row.record_version,
        }
    )


def _edit_data(value: FieldReviewEdit) -> FieldEditData:
    return FieldEditData.model_validate(
        {
            "target_field": value.target_field,
            "operation": value.operation,
            "value": _value(value.value),
            "claim_status": value.claim_status,
            "support_status": value.support_status,
            "evidence_ids": list(value.evidence_ids),
            "reason": value.reason,
        }
    )


def _evidence_request_data(value: EvidenceRequestItem) -> EvidenceRequestData:
    return EvidenceRequestData.model_validate(
        {
            "target_field": value.target_field,
            "question": value.question,
            "preferred_source_types": list(value.preferred_source_types),
            "priority": value.priority,
        }
    )


def _acknowledgement_data(value: UnresolvedAcknowledgement) -> UnresolvedAcknowledgementData:
    return UnresolvedAcknowledgementData.model_validate(
        {"target_field": value.target_field, "claim_status": value.claim_status, "reason": value.reason}
    )


def _suggestion_data(value: ReviewSuggestion) -> SuggestionData:
    return SuggestionData.model_validate(
        {
            "suggestion_id": value.suggestion_id,
            "run_id": value.run_id,
            "row_id": value.row_id,
            "source_record_version": value.source_record_version,
            "recommended_action": value.recommended_action,
            "field_findings": [
                FieldFindingData.model_validate(
                    {
                        "target_field": finding.target_field,
                        "judgement": finding.judgement,
                        "recommended_claim_status": finding.recommended_claim_status,
                        "evidence_ids": list(finding.evidence_ids),
                        "rationale": finding.rationale,
                    }
                )
                for finding in value.field_findings
            ],
            "proposed_edits": [_edit_data(edit) for edit in value.proposed_edits],
            "evidence_requests": [_evidence_request_data(item) for item in value.evidence_requests],
            "missing_evidence": [
                MissingEvidenceData.model_validate(
                    {"target_field": item.target_field, "description": item.description}
                )
                for item in value.missing_evidence
            ],
            "conflicts": [
                ConflictData.model_validate(
                    {
                        "target_field": item.target_field,
                        "evidence_ids": list(item.evidence_ids),
                        "description": item.description,
                    }
                )
                for item in value.conflicts
            ],
            "rationale": value.rationale,
            "model_manifest": ModelManifestData.model_validate(
                {
                    "provider": value.model_manifest.provider,
                    "model": value.model_manifest.model,
                    "template_id": value.model_manifest.template_id,
                    "template_version": value.model_manifest.template_version,
                }
            ),
            "applied": value.applied,
            "stale": value.stale,
            "created_at": value.created_at,
        }
    )


def _decision_data(value: ReviewDecisionRecord) -> DecisionData:
    return DecisionData.model_validate(
        {
            "decision_id": value.decision_id,
            "row_id": value.row_id,
            "previous_record_version": value.previous_record_version,
            "record_version": value.record_version,
            "actor_id": value.actor_id,
            "action": value.action,
            "suggestion_id": value.suggestion_id,
            "reason_code": value.reason_code,
            "reason": value.reason,
            "edits": [_edit_data(edit) for edit in value.edits],
            "evidence_requests": [_evidence_request_data(item) for item in value.evidence_requests],
            "unresolved_acknowledgements": [_acknowledgement_data(item) for item in value.unresolved_acknowledgements],
            "created_at": value.created_at,
        }
    )


def _run_data(value: ReviewSuggestionRun) -> ReviewRunData:
    return ReviewRunData.model_validate(
        {
            "run_id": value.run_id,
            "row_id": value.row_id,
            "source_record_version": value.source_record_version,
            "status": value.status,
            "suggestion_id": value.suggestion_id,
            "error_code": value.error_code,
            "retryable": value.retryable,
            "request_id": value.request_id,
            "trace_id": value.trace_id,
            "created_at": value.created_at,
            "started_at": value.started_at,
            "finished_at": value.finished_at,
        }
    )


def _context_data(value: ReviewContext) -> ReviewContextData:
    identity = FmeaIdentity(
        row_id=value.row.row_id,
        item_id=value.row.item_id,
        function_id=value.row.function_id,
        item_label=value.item_label,
        function_label=value.function_label,
    )
    fields = [
        FieldReviewData.model_validate(
            {
                "target_field": item.target_field,
                "value": _value(item.value),
                "claim_status": item.claim_status,
                "support_status": item.support_status,
                "evidence_ids": list(item.evidence_ids),
                "last_decision_id": item.last_decision_id,
            }
        )
        for item in value.field_reviews
    ]
    evidence = EvidenceData(
        pack_id=value.evidence.pack_id,
        pack_hash=value.evidence.pack_hash,
        expires_at=value.evidence.expires_at,
        refs=[
            EvidenceRefData(
                evidence_id=item.evidence_id,
                source_type=item.source_type,
                source_trust=item.source_trust,
                is_primary=item.is_primary,
                locator=item.locator,
                quote=item.quote,
            )
            for item in value.evidence.refs
        ],
    )
    retrieval = RetrievalData(
        requested_profile=value.retrieval.requested_profile.value,
        resolved_profile=value.retrieval.resolved_profile.value,
        evidence_types=[item.value for item in value.retrieval.evidence_types],
        trace_id=value.retrieval.trace_id,
        warnings=list(value.retrieval.warnings),
        incomplete=value.retrieval.incomplete,
    )
    return ReviewContextData(
        identity=identity,
        row=_row_data(value.row),
        reviewability=value.reviewability,
        field_reviews=fields,
        evidence=evidence,
        retrieval=retrieval,
        latest_suggestion=None if value.latest_suggestion is None else _suggestion_data(value.latest_suggestion),
        decision_history=[_decision_data(item) for item in value.decision_history],
        warnings=list(value.warnings),
    )


def _decision_result_data(value: Any) -> ReviewDecisionResultData:
    return ReviewDecisionResultData.model_validate(
        {
            "decision_id": value.decision_id,
            "row": _row_data(value.row),
            "previous_record_version": value.previous_record_version,
            "record_version": value.record_version,
            "review_status": value.review_status,
            "publication_status": value.publication_status,
            "audit_event_id": value.audit_event_id,
            "suggestion_id": value.suggestion_id,
            "evidence_requests": [_evidence_request_data(item) for item in value.evidence_requests],
            "persisted": value.persisted,
        }
    )


def _envelope(resource_type: str, request_id: str, trace_id: str, data: Any) -> dict[str, object]:
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
    request_id: str,
    trace_id: str,
    data: Any,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=_envelope(resource_type, request_id, trace_id, data),
        headers=headers,
    )


def _cursor_secret(request: Request) -> bytes:
    return cast(bytes, request.app.state.review_cursor_secret)


def _encode_cursor(request: Request, created_at: str, stable_id: str) -> str:
    raw = f"{created_at}\x00{stable_id}".encode()
    payload = base64.urlsafe_b64encode(raw).rstrip(b"=")
    signature = hmac.new(_cursor_secret(request), payload, hashlib.sha256).digest()
    return f"{payload.decode('ascii')}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"


def _decode_cursor(request: Request, value: str | None) -> tuple[str, str] | None:
    if value is None:
        return None
    if len(value) > 512 or value.count(".") != 1:
        raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "cursor is invalid")
    payload_text, signature_text = value.split(".")
    if not _CURSOR_PART.fullmatch(payload_text) or not _CURSOR_PART.fullmatch(signature_text):
        raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "cursor is invalid")
    try:
        payload = payload_text.encode("ascii")
        expected = hmac.new(_cursor_secret(request), payload, hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
        raw = base64.urlsafe_b64decode(payload_text + "=" * (-len(payload_text) % 4)).decode("utf-8")
        created_at, stable_id = raw.split("\x00", 1)
    except (ValueError, UnicodeDecodeError, TypeError) as exc:
        raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "cursor is invalid") from exc
    if not hmac.compare_digest(actual, expected) or not created_at or not stable_id:
        raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "cursor is invalid")
    return created_at, stable_id


def _fresh_request_id() -> str:
    return str(uuid4())


@router.get("/rows/{row_id}/review-context")
def review_context(row_id: str, access: ReviewAccess = Depends(get_review_access)) -> Response:  # noqa: B008
    context = _service_call(lambda: access.runtime.service.get_context(row_id, access.actor))
    return _json_response(
        status_code=200,
        resource_type="review_context",
        request_id=_fresh_request_id(),
        trace_id=context.retrieval.trace_id,
        data=_context_data(context),
        headers={"ETag": f'"{context.row.record_version}"'},
    )


@router.post("/rows/{row_id}/review-suggestion-runs")
def start_review_suggestion(
    row_id: str,
    body: StartSuggestionBody,
    request: Request,
    access: ReviewAccess = Depends(get_review_access),  # noqa: B008
) -> Response:
    command = _suggestion_command(row_id, body, request)
    run = _service_call(lambda: access.runtime.service.start_suggestion(command, access.actor))
    return _json_response(
        status_code=202,
        resource_type="review_suggestion_run",
        request_id=run.request_id,
        trace_id=run.trace_id,
        data=_run_data(run),
        headers={"Location": f"/api/v1/fmea/review-suggestion-runs/{run.run_id}"},
    )


@router.get("/review-suggestion-runs/{run_id}")
def get_review_suggestion_run(run_id: str, access: ReviewAccess = Depends(get_review_access)) -> Response:  # noqa: B008
    run = _service_call(lambda: access.runtime.service.get_suggestion_run(run_id, access.actor))
    return _json_response(
        status_code=200,
        resource_type="review_suggestion_run",
        request_id=_fresh_request_id(),
        trace_id=run.trace_id,
        data=_run_data(run),
    )


@router.get("/rows/{row_id}/review-suggestions")
def list_review_suggestions(
    row_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    access: ReviewAccess = Depends(get_review_access),  # noqa: B008
) -> Response:
    position = _decode_cursor(request, cursor)
    trace_id = _service_call(lambda: access.runtime.service.get_retrieval_trace(row_id, access.actor))
    suggestions = _service_call(
        lambda: access.runtime.service.page_suggestions(
            row_id,
            access.actor,
            after=position,
            limit=limit,
        )
    )
    page = suggestions[:limit]
    next_cursor = None
    if len(suggestions) > limit:
        last = page[-1]
        next_cursor = _encode_cursor(request, last.created_at, last.suggestion_id)
    data = HistoryPage[SuggestionData](
        items=[_suggestion_data(item) for item in page],
        next_cursor=next_cursor,
        limit=limit,
    )
    return _json_response(
        status_code=200,
        resource_type="review_suggestion_history",
        request_id=_fresh_request_id(),
        trace_id=trace_id,
        data=data,
    )


@router.post("/rows/{row_id}/review-decisions")
def submit_review_decision(
    row_id: str,
    body: ReviewDecisionBody,
    request: Request,
    access: ReviewAccess = Depends(get_review_access),  # noqa: B008
) -> Response:
    command = _decision_command(row_id, body, request)
    result = _service_call(lambda: access.runtime.service.submit_decision(command, access.actor))
    return _json_response(
        status_code=200,
        resource_type="review_decision",
        request_id=result.request_id,
        trace_id=result.trace_id,
        data=_decision_result_data(result),
        headers={"ETag": f'"{result.record_version}"'},
    )


@router.get("/rows/{row_id}/review-decisions")
def list_review_decisions(
    row_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    access: ReviewAccess = Depends(get_review_access),  # noqa: B008
) -> Response:
    position = _decode_cursor(request, cursor)
    trace_id = _service_call(lambda: access.runtime.service.get_retrieval_trace(row_id, access.actor))
    decisions = _service_call(
        lambda: access.runtime.service.page_decisions(
            row_id,
            access.actor,
            after=position,
            limit=limit,
        )
    )
    page = decisions[:limit]
    next_cursor = None
    if len(decisions) > limit:
        last = page[-1]
        next_cursor = _encode_cursor(request, last.created_at, last.decision_id)
    data = HistoryPage[DecisionData](
        items=[_decision_data(item) for item in page],
        next_cursor=next_cursor,
        limit=limit,
    )
    return _json_response(
        status_code=200,
        resource_type="review_decision_history",
        request_id=_fresh_request_id(),
        trace_id=trace_id,
        data=data,
    )


__all__ = [
    "FMEA_BODY_LIMIT",
    "FmeaRequestBodyLimitMiddleware",
    "fmea_validation_error_response",
    "get_review_access",
    "parse_idempotency_key",
    "parse_if_match",
    "review_error_response",
    "router",
]
