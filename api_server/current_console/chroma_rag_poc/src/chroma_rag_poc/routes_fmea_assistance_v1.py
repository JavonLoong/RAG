"""Versioned HTTP adapter for provider-neutral FMEA assistance."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Any, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from core_domain.fmea.states import ActorType
from fmea_application.assistance_contracts import AssistanceKind, AssistanceRequest
from fmea_application.assistance_service import DecideAssistanceCommand
from fmea_application.review_contracts import ActorContext
from fmea_application.review_errors import ReviewError
from fmea_infrastructure.local_auth import LocalReviewAuthProvider

from .fmea_assistance_contracts import (
    AnalysisScopeRunBody,
    AssistanceDecisionBody,
    AssistanceDecisionData,
    AssistanceSuggestionData,
)
from .fmea_review_contracts import FmeaEnvelope
from .routes_fmea_review_v1 import parse_idempotency_key, parse_if_match
from .workspace_registry import WorkspaceConfig, WorkspaceNotFoundError

router = APIRouter(prefix="/api/v1/fmea", tags=["fmea-assistance-v1"])


@dataclass(frozen=True, slots=True)
class RiskAccess:
    actor: ActorContext
    model_actor: ActorContext
    workspace: WorkspaceConfig
    runtime: Any


def _authorization_token(request: Request) -> str:
    header = request.headers.get("authorization")
    if header is None or not header.startswith("Bearer ") or len(header.split()) != 2:
        raise ReviewError("FMEA_AUTH_REQUIRED", "review authentication is required")
    return header.removeprefix("Bearer ")


def _runtime_for(request: Request, workspace: WorkspaceConfig) -> Any:
    cache = cast(dict[str, Any], request.app.state.risk_runtimes)
    lock = cast(Lock, request.app.state.risk_runtime_lock)
    with lock:
        existing = cache.get(workspace.workspace_id)
        if existing is not None:
            return existing
        factory = cast(Callable[[WorkspaceConfig], Any] | None, request.app.state.risk_runtime_factory)
        if factory is None:
            raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "FMEA risk runtime is not configured")
        try:
            runtime = factory(workspace)
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError(
                "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                "FMEA risk runtime is unavailable",
                retryable=True,
            ) from exc
        cache[workspace.workspace_id] = runtime
        return runtime


def get_risk_access(request: Request) -> RiskAccess:
    configured_error = cast(ReviewError | None, request.app.state.review_auth_error)
    if configured_error is not None:
        raise configured_error
    provider = cast(LocalReviewAuthProvider, request.app.state.review_auth_provider)
    remote_host = request.client.host if request.client is not None else None
    actor = provider.authenticate(_authorization_token(request), remote_host)
    try:
        workspace = request.app.state.workspace_registry.get(actor.workspace_id)
    except WorkspaceNotFoundError as exc:
        raise ReviewError("FMEA_REVIEW_FORBIDDEN", "review workspace is not available") from exc
    model_actor = ActorContext(
        actor_id="fmea-model-assistant",
        actor_type=ActorType.MODEL,
        roles=frozenset(),
        workspace_id=actor.workspace_id,
    )
    return RiskAccess(actor, model_actor, workspace, _runtime_for(request, workspace))


def service_call(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except ReviewError:
        raise
    except Exception as exc:
        raise ReviewError(
            "FMEA_REVIEW_STORAGE_UNAVAILABLE",
            "FMEA risk storage is unavailable",
            retryable=True,
        ) from exc


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    return value


def suggestion_data(value: Any) -> AssistanceSuggestionData:
    return AssistanceSuggestionData.model_validate(
        {
            "suggestion_id": value.suggestion_id,
            "kind": value.kind,
            "workspace_id": value.workspace_id,
            "target_type": value.target_type,
            "target_id": value.target_id,
            "target_record_version": value.target_record_version,
            "evidence_pack_ids": list(value.evidence_pack_ids),
            "payload": _json_value(value.payload),
            "evidence_ids": list(value.evidence_ids),
            "conflict_ids": list(value.conflict_ids),
            "uncertainty": value.uncertainty,
            "model_hash": value.model_hash,
            "prompt_hash": value.prompt_hash,
            "run_id": value.run_id,
            "trace_id": value.trace_id,
            "domain_pack_id": value.domain_pack_id,
            "domain_pack_version": value.domain_pack_version,
            "template_id": value.template_id,
            "template_version": value.template_version,
            "rule_pack_id": value.rule_pack_id,
            "rule_pack_version": value.rule_pack_version,
            "record_version": value.record_version,
            "created_at": value.created_at,
            "applied": value.applied,
            "suggestion_hash": value.suggestion_hash,
        }
    )


def decision_data(value: Any) -> AssistanceDecisionData:
    identity = None if value.resulting_resource_identity is None else list(value.resulting_resource_identity)
    return AssistanceDecisionData.model_validate(
        {
            "decision_id": value.decision_id,
            "suggestion_id": value.suggestion_id,
            "suggestion_hash": value.suggestion_hash,
            "suggestion_record_version": value.suggestion_record_version,
            "target_record_version": value.target_record_version,
            "action": value.action,
            "actor_id": value.actor_id,
            "actor_type": value.actor_type,
            "edits": [[field, _json_value(item)] for field, item in value.edits],
            "reason": value.reason,
            "resulting_resource_identity": identity,
            "created_at": value.created_at,
        }
    )


def json_response(
    *,
    status_code: int,
    resource_type: str,
    data: Any,
    request_id: str | None = None,
    trace_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    envelope = FmeaEnvelope(
        resource_type=resource_type,
        request_id=request_id or str(uuid4()),
        trace_id=trace_id or str(uuid4()),
        data=data,
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"), headers=headers)


def _require_human_reviewer(actor: ActorContext) -> None:
    if actor.actor_type is not ActorType.HUMAN or not ({"reviewer", "risk_reviewer"} & actor.roles):
        raise ReviewError("FMEA_REVIEW_FORBIDDEN", "a human reviewer is required")


@router.post("/assistance/analysis-scope-runs")
def start_analysis_scope_run(
    body: AnalysisScopeRunBody,
    request: Request,
    access: RiskAccess = Depends(get_risk_access),  # noqa: B008
) -> Response:
    _require_human_reviewer(access.actor)
    key = parse_idempotency_key(request)
    command = AssistanceRequest(
        request_id=str(uuid4()),
        kind=AssistanceKind.ANALYSIS_SCOPE_DRAFT,
        workspace_id=access.actor.workspace_id,
        target_type="fmea_analysis",
        target_id=body.target_id,
        target_record_version=body.target_record_version,
        evidence_pack_ids=tuple(body.evidence_pack_ids),
        payload=body.payload,
        domain_pack_id=body.domain_pack_id,
        domain_pack_version=body.domain_pack_version,
        template_id=body.template_id,
        template_version=body.template_version,
        rule_pack_id=body.rule_pack_id,
        rule_pack_version=body.rule_pack_version,
        idempotency_key=key,
    )
    suggestion = service_call(lambda: access.runtime.analysis_service.suggest_scope(command, access.model_actor))
    return json_response(
        status_code=202,
        resource_type="assistance_suggestion",
        data=suggestion_data(suggestion),
        request_id=command.request_id,
        trace_id=suggestion.trace_id,
        headers={
            "Location": f"/api/v1/fmea/assistance/suggestions/{suggestion.suggestion_id}",
            "ETag": f'"{suggestion.record_version}"',
        },
    )


@router.get("/assistance/suggestions/{suggestion_id}")
def get_assistance_suggestion(
    suggestion_id: str,
    access: RiskAccess = Depends(get_risk_access),  # noqa: B008
) -> Response:
    suggestion = service_call(lambda: access.runtime.analysis_service.get(suggestion_id, access.actor))
    return json_response(
        status_code=200,
        resource_type="assistance_suggestion",
        data=suggestion_data(suggestion),
        trace_id=suggestion.trace_id,
        headers={"ETag": f'"{suggestion.record_version}"'},
    )


@router.post("/assistance/suggestions/{suggestion_id}/decisions")
def submit_assistance_decision(
    suggestion_id: str,
    body: AssistanceDecisionBody,
    request: Request,
    access: RiskAccess = Depends(get_risk_access),  # noqa: B008
) -> Response:
    _require_human_reviewer(access.actor)
    command = DecideAssistanceCommand(
        suggestion_id=suggestion_id,
        expected_suggestion_version=parse_if_match(request),
        expected_target_record_version=body.target_record_version,
        action=body.action,
        idempotency_key=parse_idempotency_key(request),
        reason=body.reason,
        edits=tuple((item.field, item.value) for item in body.edits),
    )
    decision = service_call(lambda: access.runtime.decision_service.decide(command, access.actor))
    return json_response(
        status_code=200,
        resource_type="assistance_decision",
        data=decision_data(decision),
        headers={"ETag": f'"{decision.suggestion_record_version}"'},
    )


__all__ = ["RiskAccess", "get_risk_access", "json_response", "router", "service_call", "suggestion_data"]
