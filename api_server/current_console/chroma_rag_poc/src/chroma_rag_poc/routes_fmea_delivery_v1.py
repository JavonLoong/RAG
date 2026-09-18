"""Thin REST transport for DomainPack, migration, and export delivery."""

# The transport owns validation, identity, and projection only.  Decisions stay
# in the application services injected by the workspace composition layer.
# ruff: noqa: B008

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi import APIRouter, Body, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from core_domain.fmea.states import ActorType
from fmea_application.domain_pack_service import (
    AcceptTemplatePatchCommand,
    ImportTemplateCommand,
    RejectTemplatePatchCommand,
    SuggestTemplatePatchCommand,
)
from fmea_application.export_service import ExportServiceError, StartExportCommand
from fmea_application.migration_service import (
    ConfirmMigrationCommand,
    MigrationCommand,
    migration_report_id,
)
from fmea_application.review_contracts import ActorContext
from fmea_application.template_patch_contracts import TemplatePatchDecision
from fmea_infrastructure.local_auth import LocalReviewAuthProvider

from .fmea_delivery_contracts import (
    ExportNarrativeRunRequest,
    ExportRunRequest,
    MigrationConfirmationRequest,
    MigrationDryRunRequest,
    TemplatePatchAcceptanceRequest,
    TemplatePatchRejectionRequest,
    TemplatePatchRunRequest,
    export_artifact_manifest_data,
    export_run_data,
    migration_report_data,
    migration_result_data,
    narrative_data,
    template_draft_data,
    template_patch_data,
    template_patch_decision_data,
    template_registration_data,
)
from .workspace_registry import WorkspaceConfig, WorkspaceNotFoundError

router = APIRouter(prefix="/api/v1/fmea", tags=["fmea-delivery-v1"])
_BEARER = re.compile(r"^Bearer ([^\s]+)$")
_ETAG = re.compile(r'^"([1-9][0-9]*)"$')
_MAX_ID = 256
_MAX_UPLOAD_BYTES = 256 * 1024

_ERROR_STATUS: dict[str, int] = {
    "FMEA_PRECONDITION_REQUIRED": 428,
    "FMEA_DELIVERY_REQUEST_INVALID": 400,
    "FMEA_REVIEW_REQUEST_INVALID": 400,
    "FMEA_REVIEW_FORBIDDEN": 403,
    "FMEA_TEMPLATE_ADMIN_REQUIRED": 403,
    "FMEA_MIGRATION_FORBIDDEN": 403,
    "FMEA_EXPORT_FORBIDDEN": 403,
    "FMEA_EXPORT_NARRATIVE_FORBIDDEN": 403,
    "FMEA_TEMPLATE_CONFIRMATION_REQUIRED": 422,
    "FMEA_MIGRATION_CONFIRMATION_REQUIRED": 422,
    "FMEA_EXPORT_PUBLICATION_CONFIRMATION_REQUIRED": 422,
    "FMEA_AUTH_REQUIRED": 401,
    "FMEA_AUTH_CONFIGURATION_INVALID": 503,
    "FMEA_WORKSPACE_CONFIGURATION_INVALID": 503,
    "FMEA_MIGRATION_STORAGE_UNAVAILABLE": 503,
    "FMEA_EXPORT_STORAGE_UNAVAILABLE": 503,
    "FMEA_REVIEW_STORAGE_UNAVAILABLE": 503,
    "FMEA_DELIVERY_STORAGE_UNAVAILABLE": 503,
}
for _code in (
    "FMEA_TEMPLATE_DRAFT_NOT_FOUND",
    "FMEA_TEMPLATE_PATCH_NOT_FOUND",
    "FMEA_MIGRATION_REPORT_NOT_FOUND",
    "FMEA_MIGRATION_SOURCE_MISSING",
    "FMEA_MIGRATION_TARGET_MISSING",
    "FMEA_EXPORT_RUN_NOT_FOUND",
    "FMEA_EXPORT_ARTIFACT_NOT_FOUND",
    "FMEA_EXPORT_SNAPSHOT_NOT_FOUND",
    "FMEA_EXPORT_PUBLICATION_NOT_FOUND",
):
    _ERROR_STATUS[_code] = 404
for _code in (
    "FMEA_IDEMPOTENCY_CONFLICT",
    "FMEA_VERSION_CONFLICT",
    "FMEA_MIGRATION_REPORT_STALE",
    "FMEA_EXPORT_SNAPSHOT_STALE",
    "FMEA_EXPORT_PUBLICATION_STALE",
    "FMEA_EXPORT_NOT_ELIGIBLE",
    "FMEA_EXPORT_PERSISTENCE_INVALID",
    "FMEA_EXPORT_ARTIFACT_INVALID",
    "FMEA_EXPORT_IDEMPOTENCY_CONFLICT",
    "FMEA_MIGRATION_FAILED",
    "FMEA_MIGRATION_IDEMPOTENCY_CONFLICT",
):
    _ERROR_STATUS[_code] = 409
for _code in (
    "FMEA_TEMPLATE_IMPORT_INVALID",
    "FMEA_TEMPLATE_CONTAINER_INVALID",
    "FMEA_TEMPLATE_LIMIT_EXCEEDED",
    "FMEA_EVIDENCE_INVALID",
    "FMEA_MODEL_SUGGESTION_INVALID",
    "FMEA_MODEL_SUGGESTION_UNAVAILABLE",
    "FMEA_MIGRATION_REQUEST_INVALID",
    "FMEA_MIGRATION_SOURCE_INVALID",
    "FMEA_MIGRATION_SOURCE_PACK_INVALID",
    "FMEA_MIGRATION_SOURCE_PACK_STALE",
    "FMEA_MIGRATION_TARGET_INVALID",
    "FMEA_MIGRATION_REPORT_INVALID",
    "FMEA_MIGRATION_EDGE_MISSING",
    "FMEA_MIGRATION_EDGE_AMBIGUOUS",
    "FMEA_MIGRATION_EDGE_CYCLIC",
    "FMEA_MIGRATION_REGISTRY_INVALID",
    "FMEA_MIGRATION_ADAPTER_INVALID",
    "FMEA_EXPORT_REQUEST_INVALID",
    "FMEA_EXPORT_FORMAT_UNSUPPORTED",
    "FMEA_EXPORT_RENDER_FAILED",
    "FMEA_EXPORT_NARRATIVE_REQUEST_INVALID",
    "FMEA_EXPORT_NARRATIVE_INVALID",
):
    _ERROR_STATUS[_code] = 400
for _code in (
    "FMEA_MIGRATION_ADAPTER_FAILED",
    "FMEA_EXPORT_NARRATIVE_UNAVAILABLE",
):
    _ERROR_STATUS[_code] = 503


class DeliveryError(Exception):
    """Safe error boundary for all delivery routes."""

    def __init__(self, code: str, public_message: str, retryable: bool = False) -> None:
        self.code = code
        self.public_message = public_message[:4096]
        self.retryable = retryable
        super().__init__(self.public_message)


@dataclass(frozen=True, slots=True)
class DeliveryAccess:
    actor: ActorContext
    model_actor: ActorContext
    workspace: WorkspaceConfig
    runtime: object


def _problem_response(
    error: DeliveryError,
    *,
    request: Request | None = None,
    errors: list[dict[str, object]] | None = None,
) -> JSONResponse:
    code = error.code if error.code in _ERROR_STATUS else "FMEA_DELIVERY_STORAGE_UNAVAILABLE"
    status = _ERROR_STATUS[code]
    detail = error.public_message if code == error.code else "FMEA delivery request failed"
    request_id = _request_id(request) if request is not None else str(uuid4())
    trace_id = _trace_id(request) if request is not None else str(uuid4())
    problem = {
        "type": f"/problems/{code}",
        "title": "FMEA delivery request failed.",
        "status": status,
        "code": code,
        "detail": detail,
        "request_id": request_id,
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


def delivery_error_response(request: Request, error: DeliveryError) -> JSONResponse:
    return _problem_response(error, request=request)


def is_delivery_path(path: str) -> bool:
    return (
        path == "/api/v1/fmea/template-drafts"
        or path.startswith("/api/v1/fmea/template-drafts/")
        or path.startswith("/api/v1/fmea/template-patches/")
        or path.startswith("/api/v1/fmea/migration-reports/")
        or path.startswith("/api/v1/fmea/export-runs/")
        or path.startswith("/api/v1/fmea/export-artifacts/")
        or re.fullmatch(r"/api/v1/fmea/revisions/[^/]+/(migration-dry-runs|export-runs|export-narrative-runs)", path)
        is not None
    )


def delivery_validation_error_response(request: Request, error: RequestValidationError) -> JSONResponse:
    safe_errors = [
        {
            "loc": [str(part)[:64] for part in item.get("loc", ()) if str(part) != "body"][:6],
            "message": "invalid request field",
        }
        for item in error.errors()[:16]
    ]
    return _problem_response(
        DeliveryError("FMEA_DELIVERY_REQUEST_INVALID", "delivery request validation failed"),
        request=request,
        errors=safe_errors,
    )


def _wrap_error(exc: Exception, *, fallback: str = "FMEA_DELIVERY_STORAGE_UNAVAILABLE") -> DeliveryError:
    code = getattr(exc, "code", None)
    message = getattr(exc, "public_message", None)
    retryable = getattr(exc, "retryable", False)
    if isinstance(code, str) and code in _ERROR_STATUS and isinstance(message, str) and message.strip():
        return DeliveryError(code, message, retryable if isinstance(retryable, bool) else False)
    if isinstance(exc, ExportServiceError) and isinstance(code, str) and code.startswith("FMEA_EXPORT_"):
        return DeliveryError(code, "export operation failed", bool(retryable))
    return DeliveryError(fallback, "FMEA delivery operation failed", True)


def _service_call(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except DeliveryError:
        raise
    except Exception as exc:
        raise _wrap_error(exc) from None


def _authorization_token(request: Request) -> str:
    header = request.headers.get("authorization")
    if header is None:
        raise DeliveryError("FMEA_AUTH_REQUIRED", "review authentication is required")
    match = _BEARER.fullmatch(header)
    if match is None:
        raise DeliveryError("FMEA_AUTH_REQUIRED", "review authentication is required")
    return match.group(1)


def _runtime_for(request: Request, workspace: WorkspaceConfig) -> object:
    cache = cast(dict[str, object], request.app.state.fmea_delivery_runtimes)
    lock = cast(Lock, request.app.state.fmea_delivery_runtime_lock)
    with lock:
        existing = cache.get(workspace.workspace_id)
        if existing is not None:
            return existing
        factory = cast(Callable[[WorkspaceConfig], object] | None, request.app.state.fmea_delivery_runtime_factory)
        if factory is None:
            raise DeliveryError("FMEA_WORKSPACE_CONFIGURATION_INVALID", "FMEA delivery runtime factory is unavailable")
        try:
            runtime = factory(workspace)
        except DeliveryError:
            raise
        except Exception as exc:
            raise DeliveryError(
                "FMEA_DELIVERY_STORAGE_UNAVAILABLE", "FMEA delivery runtime is unavailable", True
            ) from exc
        if runtime is None:
            raise DeliveryError("FMEA_WORKSPACE_CONFIGURATION_INVALID", "FMEA delivery runtime is incomplete")
        cache[workspace.workspace_id] = runtime
        return runtime


def get_delivery_access(request: Request) -> DeliveryAccess:
    configured_error = cast(Exception | None, request.app.state.review_auth_error)
    if configured_error is not None:
        raise _wrap_error(configured_error, fallback="FMEA_AUTH_CONFIGURATION_INVALID")
    provider = cast(LocalReviewAuthProvider | None, request.app.state.review_auth_provider)
    if provider is None:
        raise DeliveryError("FMEA_AUTH_CONFIGURATION_INVALID", "review authentication is not configured")
    remote_host = request.client.host if request.client is not None else None
    try:
        actor = provider.authenticate(_authorization_token(request), remote_host)
    except DeliveryError:
        raise
    except Exception as exc:
        raise _wrap_error(exc, fallback="FMEA_AUTH_REQUIRED") from None
    registry = request.app.state.workspace_registry
    try:
        workspace = registry.get(actor.workspace_id)
    except WorkspaceNotFoundError as exc:
        raise DeliveryError("FMEA_REVIEW_FORBIDDEN", "FMEA workspace is not available") from exc
    model_actor = ActorContext(actor.actor_id, ActorType.MODEL, frozenset(), actor.workspace_id)
    return DeliveryAccess(
        actor=actor, model_actor=model_actor, workspace=workspace, runtime=_runtime_for(request, workspace)
    )


def _path_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= _MAX_ID or "/" in value or "\\" in value:
        raise DeliveryError("FMEA_DELIVERY_REQUEST_INVALID", f"{field_name} is invalid")
    return value


def _if_match(request: Request) -> int:
    value = request.headers.get("if-match")
    if value is None:
        raise DeliveryError("FMEA_PRECONDITION_REQUIRED", "If-Match is required")
    match = _ETAG.fullmatch(value)
    if match is None:
        raise DeliveryError("FMEA_DELIVERY_REQUEST_INVALID", "If-Match must be a quoted positive integer")
    return int(match.group(1))


def _idempotency_key(request: Request) -> str:
    value = request.headers.get("idempotency-key")
    if value is None:
        raise DeliveryError("FMEA_PRECONDITION_REQUIRED", "Idempotency-Key is required")
    try:
        parsed = UUID(value)
    except (AttributeError, ValueError):
        raise DeliveryError("FMEA_DELIVERY_REQUEST_INVALID", "Idempotency-Key must be a canonical UUID") from None
    if str(parsed) != value:
        raise DeliveryError("FMEA_DELIVERY_REQUEST_INVALID", "Idempotency-Key must be a canonical UUID")
    return value


def _request_id(request: Request) -> str:
    cached = getattr(request.state, "fmea_request_id", None)
    if isinstance(cached, str):
        return cached
    value = request.headers.get("x-request-id")
    request_id = value[:128] if isinstance(value, str) and 1 <= len(value) <= 128 else str(uuid4())
    request.state.fmea_request_id = request_id
    return request_id


def _trace_id(request: Request) -> str:
    cached = getattr(request.state, "fmea_trace_id", None)
    if isinstance(cached, str):
        return cached
    value = request.headers.get("x-trace-id")
    trace_id = value[:128] if isinstance(value, str) and 1 <= len(value) <= 128 else str(uuid4())
    request.state.fmea_trace_id = trace_id
    return trace_id


def _envelope(request: Request, resource_type: str, data: object) -> dict[str, object]:
    return {
        "schema_version": "graphrag.fmea.delivery.v1",
        "resource_type": resource_type,
        "resource_version": "1.0.0",
        "data": data,
        "request_id": _request_id(request),
        "trace_id": _trace_id(request),
    }


def _json_response(
    request: Request,
    resource_type: str,
    data: object,
    *,
    status: int = 200,
    record_version: int | None = None,
) -> JSONResponse:
    headers = {} if record_version is None else {"ETag": f'"{record_version}"'}
    return JSONResponse(status_code=status, content=_envelope(request, resource_type, data), headers=headers)


def _require_role(access: DeliveryAccess, role: str, code: str) -> None:
    if access.actor.actor_type is not ActorType.HUMAN or role not in access.actor.roles:
        raise DeliveryError(code, f"only a human {role} may perform this operation")


def _stable_id(prefix: str, workspace_id: str, idempotency_key: str) -> str:
    identifier = uuid5(NAMESPACE_URL, f"fmea-delivery:{workspace_id}:{idempotency_key}")
    return f"{prefix}-{identifier}"


def _runtime_service(runtime: object, name: str) -> object:
    service = getattr(runtime, name, None)
    if service is None:
        service = getattr(runtime, name.removesuffix("_service"), None)
    if service is None:
        raise DeliveryError("FMEA_WORKSPACE_CONFIGURATION_INVALID", f"FMEA {name} service is unavailable")
    return service


async def _bounded_upload(file: UploadFile) -> tuple[bytes, str]:
    filename = Path(file.filename or "").name
    if not filename or len(filename) > 255 or filename in {".", ".."}:
        raise DeliveryError("FMEA_DELIVERY_REQUEST_INVALID", "template source filename is invalid")
    raw = await file.read(_MAX_UPLOAD_BYTES + 1)
    if not isinstance(raw, bytes) or len(raw) > _MAX_UPLOAD_BYTES:
        raise DeliveryError("FMEA_DELIVERY_REQUEST_INVALID", "template source exceeds 256 KiB")
    return raw, filename


@router.post("/template-drafts")
async def create_template_draft(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    access = get_delivery_access(request)
    key = _idempotency_key(request)
    raw, filename = await _bounded_upload(file)
    service = _runtime_service(access.runtime, "domain_pack_service")
    draft = _service_call(
        lambda: service.import_template(
            ImportTemplateCommand(raw, filename, access.workspace.workspace_id, key), access.actor
        )
    )
    _, version = _service_call(lambda: service.get_draft_record(draft.draft_id, access.actor))
    return _json_response(
        request, "fmea_template_draft", template_draft_data(draft), status=201, record_version=version
    )


@router.post("/template-drafts/{draft_id}/patch-runs")
def create_template_patch_run(
    draft_id: str,
    request: Request,
    body: TemplatePatchRunRequest = Body(...),
) -> JSONResponse:
    access = get_delivery_access(request)
    target_record_version = _if_match(request)
    key = _idempotency_key(request)
    patch_id = _stable_id("template-patch", access.workspace.workspace_id, key)
    run_id = _stable_id("template-patch-run", access.workspace.workspace_id, key)
    trace_id = _trace_id(request)
    service = _runtime_service(access.runtime, "domain_pack_service")
    command = SuggestTemplatePatchCommand(
        draft_id=_path_id(draft_id, "draft_id"),
        patch_id=patch_id,
        input_template_version=body.input_template_version,
        target_template_id=body.target_template_id,
        target_template_version=body.target_template_version,
        target_template_hash=body.target_template_hash,
        domain_pack_id=body.domain_pack_id,
        domain_pack_version=body.domain_pack_version,
        domain_pack_hash=body.domain_pack_hash,
        evidence_pack_id=body.evidence_pack_id,
        evidence_pack_hash=body.evidence_pack_hash,
        run_id=run_id,
        trace_id=trace_id,
        model_version="server-configured",
        prompt_version="server-configured",
        target_record_version=target_record_version,
        idempotency_key=key,
    )
    suggestion = _service_call(lambda: service.suggest_patch(command, access.actor))
    _, version = _service_call(lambda: service.patch_for(patch_id, access.actor))
    return _json_response(
        request, "fmea_template_patch", template_patch_data(suggestion), status=202, record_version=version
    )


@router.get("/template-patches/{patch_id}")
def get_template_patch(patch_id: str, request: Request) -> JSONResponse:
    access = get_delivery_access(request)
    patch_id = _path_id(patch_id, "patch_id")
    service = _runtime_service(access.runtime, "domain_pack_service")
    item, version = _service_call(lambda: service.patch_for(patch_id, access.actor))
    if isinstance(item, TemplatePatchDecision):
        return _json_response(
            request,
            "fmea_template_patch_decision",
            template_patch_decision_data(item),
            record_version=version,
        )
    return _json_response(request, "fmea_template_patch", template_patch_data(item), record_version=version)


@router.post("/template-patches/{patch_id}/acceptance")
def accept_template_patch(
    patch_id: str,
    request: Request,
    body: TemplatePatchAcceptanceRequest = Body(...),
) -> JSONResponse:
    access = get_delivery_access(request)
    _require_role(access, "template_admin", "FMEA_TEMPLATE_ADMIN_REQUIRED")
    expected_version = _if_match(request)
    key = _idempotency_key(request)
    if body.confirm_template_change is not True:
        raise DeliveryError("FMEA_TEMPLATE_CONFIRMATION_REQUIRED", "explicit template confirmation is required")
    if body.patch_id != _path_id(patch_id, "patch_id"):
        raise DeliveryError("FMEA_DELIVERY_REQUEST_INVALID", "patch identity does not match the path")
    service = _runtime_service(access.runtime, "domain_pack_service")
    decision = _service_call(
        lambda: service.accept_patch(
            AcceptTemplatePatchCommand(
                suggestion_id=body.suggestion_id,
                patch_id=body.patch_id,
                draft_id=body.draft_id,
                draft_sha256=body.draft_sha256,
                target_template_version=body.target_template_version,
                target_template_hash=body.target_template_hash,
                new_template_version=body.new_template_version,
                domain_pack_hash=body.domain_pack_hash,
                evidence_pack_hash=body.evidence_pack_hash,
                confirm_template_change=body.confirm_template_change,
                expected_patch_version=expected_version,
                idempotency_key=key,
            ),
            access.actor,
        )
    )
    _, version = _service_call(lambda: service.patch_for(body.patch_id, access.actor))
    return _json_response(
        request,
        "fmea_template_registration",
        template_registration_data(decision),
        status=201,
        record_version=version,
    )


@router.post("/template-patches/{patch_id}/rejection")
def reject_template_patch(
    patch_id: str,
    request: Request,
    body: TemplatePatchRejectionRequest = Body(...),
) -> JSONResponse:
    access = get_delivery_access(request)
    _require_role(access, "template_admin", "FMEA_TEMPLATE_ADMIN_REQUIRED")
    expected_version = _if_match(request)
    key = _idempotency_key(request)
    if body.patch_id != _path_id(patch_id, "patch_id"):
        raise DeliveryError("FMEA_DELIVERY_REQUEST_INVALID", "patch identity does not match the path")
    service = _runtime_service(access.runtime, "domain_pack_service")
    decision = _service_call(
        lambda: service.reject_patch(
            RejectTemplatePatchCommand(
                body.suggestion_id,
                body.patch_id,
                body.reason,
                expected_version,
                key,
            ),
            access.actor,
        )
    )
    _, version = _service_call(lambda: service.patch_for(body.patch_id, access.actor))
    return _json_response(
        request,
        "fmea_template_patch_decision",
        template_patch_decision_data(decision),
        status=201,
        record_version=version,
    )


def _migration_command(
    revision_id: str,
    body: MigrationDryRunRequest,
    idempotency_key: str,
    expected_source_version: int,
) -> MigrationCommand:
    return MigrationCommand(
        migration_id=body.migration_id,
        source_revision_id=_path_id(revision_id, "revision_id"),
        source_revision_hash=body.source_revision_hash,
        target_domain_pack_id=body.target_domain_pack_id,
        target_domain_pack_version=body.target_domain_pack_version,
        target_domain_pack_hash=body.target_domain_pack_hash,
        idempotency_key=idempotency_key,
        expected_source_version=expected_source_version,
    )


@router.post("/revisions/{revision_id}/migration-dry-runs")
def migration_dry_run(
    revision_id: str,
    request: Request,
    body: MigrationDryRunRequest = Body(...),
) -> JSONResponse:
    access = get_delivery_access(request)
    _require_role(access, "template_admin", "FMEA_MIGRATION_FORBIDDEN")
    expected_version = _if_match(request)
    key = _idempotency_key(request)
    service = _runtime_service(access.runtime, "migration_service")
    report = _service_call(
        lambda: service.dry_run(_migration_command(revision_id, body, key, expected_version), access.actor)
    )
    data = migration_report_data(report)
    data["report_id"] = migration_report_id(access.workspace.workspace_id, report.migration_id)
    return _json_response(request, "fmea_migration_report", data, status=202, record_version=1)


@router.post("/migration-reports/{report_id}/confirmations")
def confirm_migration(
    report_id: str,
    request: Request,
    body: MigrationConfirmationRequest = Body(...),
) -> JSONResponse:
    access = get_delivery_access(request)
    _require_role(access, "template_admin", "FMEA_TEMPLATE_ADMIN_REQUIRED")
    expected_report_version = _if_match(request)
    key = _idempotency_key(request)
    if body.confirm_migration is not True:
        raise DeliveryError("FMEA_MIGRATION_CONFIRMATION_REQUIRED", "explicit migration confirmation is required")
    if migration_report_id(access.workspace.workspace_id, body.migration_id) != _path_id(report_id, "report_id"):
        raise DeliveryError("FMEA_DELIVERY_REQUEST_INVALID", "migration report identity does not match the path")
    service = _runtime_service(access.runtime, "migration_service")
    dry_run = _migration_command(
        body.source_revision_id,
        body.dry_run,
        body.dry_run_idempotency_key,
        body.dry_run_source_version,
    )
    result = _service_call(
        lambda: service.confirm(
            ConfirmMigrationCommand(
                migration_id=body.migration_id,
                report_hash=body.report_hash,
                source_revision_id=body.source_revision_id,
                source_revision_hash=body.source_revision_hash,
                target_domain_pack_id=body.target_domain_pack_id,
                target_domain_pack_version=body.target_domain_pack_version,
                target_domain_pack_hash=body.target_domain_pack_hash,
                dry_run_command=dry_run,
                idempotency_key=key,
                confirm_migration=body.confirm_migration,
                expected_report_version=expected_report_version,
            ),
            access.actor,
        )
    )
    return _json_response(request, "fmea_migration_result", migration_result_data(result), status=201, record_version=1)


@router.post("/revisions/{revision_id}/export-runs")
def start_export(
    revision_id: str,
    request: Request,
    body: ExportRunRequest = Body(...),
) -> JSONResponse:
    access = get_delivery_access(request)
    expected_version = _if_match(request)
    key = _idempotency_key(request)
    if not body.draft_preview:
        _require_role(access, "exporter", "FMEA_EXPORT_FORBIDDEN")
        if body.confirm_publication is not True:
            raise DeliveryError(
                "FMEA_EXPORT_PUBLICATION_CONFIRMATION_REQUIRED", "explicit publication confirmation is required"
            )
    service = _runtime_service(access.runtime, "export_service")
    command = StartExportCommand(
        export_run_id=_stable_id("export", access.workspace.workspace_id, key),
        workspace_id=access.workspace.workspace_id,
        revision_id=_path_id(revision_id, "revision_id"),
        snapshot_id=body.snapshot_id,
        snapshot_hash=body.snapshot_hash,
        publication_id=body.publication_id,
        format=body.format,
        draft_preview=body.draft_preview,
        idempotency_key=key,
        expected_revision_version=expected_version,
    )
    run = _service_call(lambda: service.start(command, access.actor))
    return _json_response(
        request,
        "fmea_export_run",
        export_run_data(run),
        status=202,
    )


@router.post("/revisions/{revision_id}/export-narrative-runs")
def suggest_export_narrative(
    revision_id: str,
    request: Request,
    body: ExportNarrativeRunRequest = Body(default=ExportNarrativeRunRequest()),
) -> JSONResponse:
    access = get_delivery_access(request)
    service = _runtime_service(access.runtime, "export_service")
    suggestion = _service_call(
        lambda: service.suggest_narrative_for_revision(
            _path_id(revision_id, "revision_id"),
            access.model_actor,
            snapshot_id=body.snapshot_id,
            snapshot_hash=body.snapshot_hash,
            publication_id=body.publication_id,
        )
    )
    return _json_response(request, "fmea_export_narrative_suggestion", narrative_data(suggestion), status=202)


@router.get("/export-runs/{run_id}")
def get_export_run(run_id: str, request: Request) -> JSONResponse:
    access = get_delivery_access(request)
    service = _runtime_service(access.runtime, "export_service")
    run = _service_call(lambda: service.get_run(_path_id(run_id, "run_id"), access.actor))
    return _json_response(request, "fmea_export_run", export_run_data(run))


@router.get("/export-artifacts/{artifact_id}")
def get_export_artifact(artifact_id: str, request: Request) -> Response:
    access = get_delivery_access(request)
    service = _runtime_service(access.runtime, "export_service")
    artifact = _service_call(lambda: service.get_artifact(_path_id(artifact_id, "artifact_id"), access.actor))
    payload = getattr(artifact, "payload", None)
    manifest = getattr(artifact, "manifest", None)
    filename = getattr(artifact, "filename", None)
    if not isinstance(payload, bytes) or manifest is None or not isinstance(filename, str):
        raise DeliveryError("FMEA_EXPORT_ARTIFACT_INVALID", "verified export artifact is invalid")
    expected_length = getattr(manifest, "byte_length", None)
    expected_hash = getattr(manifest, "sha256", None)
    from hashlib import sha256

    actual_hash = sha256(payload).hexdigest()
    if expected_length != len(payload) or expected_hash not in {actual_hash, f"sha256:{actual_hash}"}:
        raise DeliveryError("FMEA_EXPORT_ARTIFACT_INVALID", "verified export artifact does not match its manifest")
    safe_filename = Path(filename).name
    if safe_filename != filename or not safe_filename:
        raise DeliveryError("FMEA_EXPORT_ARTIFACT_INVALID", "verified export filename is invalid")
    headers = {
        "Content-Length": str(len(payload)),
        "Content-Disposition": f'attachment; filename="{safe_filename}"',
        "ETag": f'"{actual_hash}"',
        "X-FMEA-Artifact-Manifest": str(export_artifact_manifest_data(manifest)),
    }
    return Response(
        content=payload, media_type=getattr(manifest, "media_type", "application/octet-stream"), headers=headers
    )


__all__ = [
    "DeliveryAccess",
    "DeliveryError",
    "delivery_error_response",
    "delivery_validation_error_response",
    "get_delivery_access",
    "is_delivery_path",
    "router",
]
