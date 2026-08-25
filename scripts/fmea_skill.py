"""Single-JSON service-facing CLI for the local FMEA review workflow."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Final, Literal, NoReturn, cast
from uuid import uuid4

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_PACKAGES = REPO_ROOT / ".venv" / "Lib" / "site-packages"
POC_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
for import_path in (REPO_ROOT, SITE_PACKAGES, POC_SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from chroma_rag_poc.workspace_registry import (  # type: ignore[import-untyped]  # noqa: E402
    WorkspaceConfigError,
    WorkspaceNotFoundError,
    WorkspaceRegistry,
)

from core_domain.fmea.entities import FmeaRow  # noqa: E402
from core_domain.fmea.scoring import RiskAssessment  # noqa: E402
from core_domain.fmea.states import (  # noqa: E402
    ClaimStatus,
    EvidenceSupportStatus,
    RunStatus,
)

_REVIEW_CONTRACTS = import_module("fmea_application.review_contracts")
_REVIEW_ERRORS = import_module("fmea_application.review_errors")
ActorContext = Any
EvidenceRequestItem = cast(Any, _REVIEW_CONTRACTS.EvidenceRequestItem)
FieldReviewEdit = cast(Any, _REVIEW_CONTRACTS.FieldReviewEdit)
ReviewAction = cast(Any, _REVIEW_CONTRACTS.ReviewAction)
ReviewDecisionCommand = cast(Any, _REVIEW_CONTRACTS.ReviewDecisionCommand)
ReviewError = cast(Any, _REVIEW_ERRORS.ReviewError)
ReviewPriority = cast(Any, _REVIEW_CONTRACTS.ReviewPriority)
ReviewReasonCode = cast(Any, _REVIEW_CONTRACTS.ReviewReasonCode)
ReviewSuggestionRun = Any
StartReviewSuggestionCommand = cast(Any, _REVIEW_CONTRACTS.StartReviewSuggestionCommand)
UnresolvedAcknowledgement = cast(Any, _REVIEW_CONTRACTS.UnresolvedAcknowledgement)

FMEA_REVIEW_COMMANDS: Final = frozenset(
    {"context", "suggest", "suggestion-status", "decide", "decisions"}
)
SUGGESTION_POLL_INTERVAL_SECONDS: Final = 0.2
SUGGESTION_DEADLINE_SECONDS: Final = 360.0
DECISION_REQUEST_MAX_BYTES: Final = 256 * 1024
_SCHEMA_VERSION: Final = "graphrag.fmea.v1"
_RESOURCE_VERSION: Final = "1.0.0"
_DECISION_REQUEST_KEYS: Final = frozenset(
    {
        "row_id",
        "expected_record_version",
        "idempotency_key",
        "action",
        "suggestion_id",
        "reason_code",
        "reason",
        "edits",
        "evidence_requests",
        "unresolved_acknowledgements",
    }
)
_EDIT_KEYS: Final = frozenset(
    {"target_field", "operation", "value", "claim_status", "support_status", "evidence_ids", "reason"}
)
_EVIDENCE_REQUEST_KEYS: Final = frozenset(
    {"target_field", "question", "preferred_source_types", "priority"}
)
_ACKNOWLEDGEMENT_KEYS: Final = frozenset({"target_field", "claim_status", "reason"})

_EXIT_CODES: Final = {
    "request": 2,
    "configuration": 3,
    "auth": 4,
    "conflict": 5,
    "model": 6,
    "storage": 7,
    "internal": 10,
}
_ERROR_EXIT_GROUPS: Final = {
    **dict.fromkeys(("FMEA_REVIEW_REQUEST_INVALID", "FMEA_REVIEW_CONFIRMATION_REQUIRED", "FMEA_REVIEW_ACTION_INVALID", "FMEA_REVIEW_FIELD_INVALID", "FMEA_EVIDENCE_INVALID", "FMEA_UNRESOLVED_ACK_REQUIRED", "FMEA_REVIEW_SOURCE_MISSING"), _EXIT_CODES["request"]),
    **dict.fromkeys(("FMEA_WORKSPACE_CONFIGURATION_INVALID", "FMEA_WORKSPACE_NOT_FOUND", "FMEA_ROW_NOT_FOUND", "FMEA_REVIEW_SUGGESTION_NOT_FOUND", "FMEA_AUTH_CONFIGURATION_INVALID"), _EXIT_CODES["configuration"]),
    **dict.fromkeys(("FMEA_AUTH_REQUIRED", "FMEA_REVIEW_FORBIDDEN"), _EXIT_CODES["auth"]),
    **dict.fromkeys(("FMEA_IDEMPOTENCY_CONFLICT", "FMEA_REVIEW_TERMINAL", "FMEA_REVIEW_SUGGESTION_STALE", "FMEA_VERSION_CONFLICT", "FMEA_PRECONDITION_REQUIRED", "FMEA_REVIEW_RATE_LIMITED"), _EXIT_CODES["conflict"]),
    **dict.fromkeys(("FMEA_MODEL_SUGGESTION_INVALID", "FMEA_MODEL_SUGGESTION_UNAVAILABLE", "FMEA_REVIEW_RUN_INTERRUPTED"), _EXIT_CODES["model"]),
    "FMEA_REVIEW_STORAGE_UNAVAILABLE": _EXIT_CODES["storage"],
}


class CliUsageError(ValueError):
    """A parser or bounded request-file failure with no raw-input detail."""

    def __init__(self, detail: str = "invalid review CLI request") -> None:
        super().__init__(detail)


class _InvalidRequestFileError(CliUsageError):
    def __init__(self) -> None:
        super().__init__("invalid review request file")


class _CliArgumentParser(argparse.ArgumentParser):
    """Argparse parser that never writes usage text for invalid input."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(add_help=False, allow_abbrev=False, **kwargs)

    def error(self, _message: str) -> NoReturn:
        raise CliUsageError


@dataclass(frozen=True, slots=True)
class CliRuntime:
    """The service and authenticated actor plus an idempotent close hook."""

    service: Any
    actor: ActorContext
    close: Callable[[], None]


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise CliUsageError from exc
    if parsed <= 0:
        raise CliUsageError
    return parsed


def _add_pretty(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pretty", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = _CliArgumentParser(description="Run one FMEA review operation.")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_CliArgumentParser)
    review = commands.add_parser("review")
    review_commands = review.add_subparsers(dest="review_command", required=True, parser_class=_CliArgumentParser)

    context = review_commands.add_parser("context")
    context.add_argument("--row-id", required=True)
    _add_pretty(context)

    suggest = review_commands.add_parser("suggest")
    suggest.add_argument("--row-id", required=True)
    suggest.add_argument("--record-version", required=True, type=_positive_int)
    suggest.add_argument("--idempotency-key", required=True)
    suggest.add_argument("--focus-field", action="append", default=[])
    _add_pretty(suggest)

    suggestion_status = review_commands.add_parser("suggestion-status")
    suggestion_status.add_argument("--run-id", required=True)
    _add_pretty(suggestion_status)

    decide = review_commands.add_parser("decide")
    decide.add_argument("--request-file", required=True)
    decide.add_argument("--confirm-human-review", action="store_true")
    _add_pretty(decide)

    decisions = review_commands.add_parser("decisions")
    decisions.add_argument("--row-id", required=True)
    _add_pretty(decisions)
    return parser


def parse_cli_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments while replacing argparse diagnostics with one safe error."""

    try:
        return build_parser().parse_args(argv)
    except CliUsageError:
        raise
    except (SystemExit, TypeError, ValueError) as exc:
        raise CliUsageError from exc


def _invalid_request_file() -> CliUsageError:
    return _InvalidRequestFileError()


def _require_exact_keys(value: object, keys: frozenset[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys or not all(isinstance(key, str) for key in value):
        raise _invalid_request_file()
    return cast(dict[str, object], value)


def load_decision_request(path: str | Path) -> dict[str, object]:
    """Read and strictly validate one bounded, non-symlink JSON decision request."""

    candidate = Path(path)
    try:
        if candidate.is_symlink() or not candidate.exists() or not candidate.is_file():
            raise _invalid_request_file()
        if not stat.S_ISREG(candidate.stat().st_mode):
            raise _invalid_request_file()
        raw = candidate.read_bytes()
    except CliUsageError:
        raise
    except (OSError, ValueError) as exc:
        raise _invalid_request_file() from exc
    if len(raw) > DECISION_REQUEST_MAX_BYTES:
        raise _invalid_request_file()
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _invalid_request_file() from exc
    return _require_exact_keys(decoded, _DECISION_REQUEST_KEYS)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _invalid_request_file()
    return tuple(cast(str, item) for item in value)


def _edit_from_request(value: object) -> Any:
    data = _require_exact_keys(value, _EDIT_KEYS)
    raw_value = data["value"]
    if isinstance(raw_value, str):
        edit_value: str | tuple[str, ...] = raw_value
    else:
        edit_value = _string_tuple(raw_value)
    try:
        return FieldReviewEdit(
            target_field=cast(str, data["target_field"]),
            operation=cast(Literal["replace"], data["operation"]),
            value=edit_value,
            claim_status=ClaimStatus(cast(str, data["claim_status"])),
            support_status=EvidenceSupportStatus(cast(str, data["support_status"])),
            evidence_ids=_string_tuple(data["evidence_ids"]),
            reason=cast(str, data["reason"]),
        )
    except (TypeError, ValueError) as exc:
        raise _invalid_request_file() from exc


def _evidence_request_from_request(value: object) -> Any:
    data = _require_exact_keys(value, _EVIDENCE_REQUEST_KEYS)
    try:
        return EvidenceRequestItem(
            target_field=cast(str, data["target_field"]),
            question=cast(str, data["question"]),
            preferred_source_types=_string_tuple(data["preferred_source_types"]),
            priority=ReviewPriority(cast(str, data["priority"])),
        )
    except (TypeError, ValueError) as exc:
        raise _invalid_request_file() from exc


def _acknowledgement_from_request(value: object) -> Any:
    data = _require_exact_keys(value, _ACKNOWLEDGEMENT_KEYS)
    try:
        return UnresolvedAcknowledgement(
            target_field=cast(str, data["target_field"]),
            claim_status=ClaimStatus(cast(str, data["claim_status"])),
            reason=cast(str, data["reason"]),
        )
    except (TypeError, ValueError) as exc:
        raise _invalid_request_file() from exc


def decision_command_from_request(data: Mapping[str, object]) -> Any:
    """Convert one strict request object to the application command contract."""

    try:
        suggestion_id = data["suggestion_id"]
        if suggestion_id is not None and not isinstance(suggestion_id, str):
            raise _invalid_request_file()
        raw_edits = data["edits"]
        raw_requests = data["evidence_requests"]
        raw_acknowledgements = data["unresolved_acknowledgements"]
        if not isinstance(raw_edits, list) or not isinstance(raw_requests, list) or not isinstance(raw_acknowledgements, list):
            raise _invalid_request_file()

        return ReviewDecisionCommand(
            row_id=cast(str, data["row_id"]),
            expected_record_version=cast(int, data["expected_record_version"]),
            idempotency_key=cast(str, data["idempotency_key"]),
            action=ReviewAction(cast(str, data["action"])),
            suggestion_id=suggestion_id,
            reason_code=ReviewReasonCode(cast(str, data["reason_code"])),
            reason=cast(str, data["reason"]),
            edits=tuple(_edit_from_request(item) for item in raw_edits),
            evidence_requests=tuple(_evidence_request_from_request(item) for item in raw_requests),
            unresolved_acknowledgements=tuple(_acknowledgement_from_request(item) for item in raw_acknowledgements),
        )
    except CliUsageError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid_request_file() from exc


def build_cli_runtime() -> CliRuntime:
    """Build the registry-backed service and authenticate only the loopback environment token."""

    registry = WorkspaceRegistry.from_env()
    auth_module = import_module("fmea_infrastructure.local_auth")
    provider = cast(Any, auth_module.LocalReviewAuthProvider).from_env()
    actor = provider.authenticate(os.environ.get("FMEA_REVIEW_TOKEN"), "127.0.0.1")
    workspace = registry.get(actor.workspace_id)
    runtime = build_workspace_review_runtime(workspace)
    closed = False

    def close() -> None:
        nonlocal closed
        if closed:
            return
        closed = True
        runtime.executor.close()

    return CliRuntime(service=runtime.service, actor=actor, close=close)


def build_workspace_review_runtime(workspace: Any) -> Any:
    """Resolve the shared concrete composition without importing its storage types here."""

    composition = import_module("fmea_infrastructure.composition")
    return cast(Any, composition.build_workspace_review_runtime)(workspace)


def _value_data(value: str | tuple[str, ...]) -> str | list[str]:
    return value if isinstance(value, str) else list(value)


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


def _row_data(row: FmeaRow) -> dict[str, object]:
    return {
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
        "claim_status": row.claim_status.value,
        "review_status": row.review_status.value,
        "publication_status": row.publication_status.value,
        "record_version": row.record_version,
    }


def _edit_data(value: Any) -> dict[str, object]:
    return {
        "target_field": value.target_field,
        "operation": value.operation,
        "value": _value_data(value.value),
        "claim_status": value.claim_status.value,
        "support_status": value.support_status.value,
        "evidence_ids": list(value.evidence_ids),
        "reason": value.reason,
    }


def _evidence_request_data(value: Any) -> dict[str, object]:
    return {
        "target_field": value.target_field,
        "question": value.question,
        "preferred_source_types": list(value.preferred_source_types),
        "priority": value.priority.value,
    }


def _acknowledgement_data(value: Any) -> dict[str, object]:
    return {
        "target_field": value.target_field,
        "claim_status": value.claim_status.value,
        "reason": value.reason,
    }


def _suggestion_data(value: Any) -> dict[str, object]:
    return {
        "suggestion_id": value.suggestion_id,
        "run_id": value.run_id,
        "row_id": value.row_id,
        "source_record_version": value.source_record_version,
        "recommended_action": value.recommended_action.value,
        "field_findings": [
            {
                "target_field": finding.target_field,
                "judgement": finding.judgement.value,
                "recommended_claim_status": finding.recommended_claim_status.value,
                "evidence_ids": list(finding.evidence_ids),
                "rationale": finding.rationale,
            }
            for finding in value.field_findings
        ],
        "proposed_edits": [_edit_data(edit) for edit in value.proposed_edits],
        "evidence_requests": [_evidence_request_data(item) for item in value.evidence_requests],
        "missing_evidence": [
            {"target_field": item.target_field, "description": item.description} for item in value.missing_evidence
        ],
        "conflicts": [
            {
                "target_field": item.target_field,
                "evidence_ids": list(item.evidence_ids),
                "description": item.description,
            }
            for item in value.conflicts
        ],
        "rationale": value.rationale,
        "model_manifest": {
            "provider": value.model_manifest.provider,
            "model": value.model_manifest.model,
            "template_id": value.model_manifest.template_id,
            "template_version": value.model_manifest.template_version,
        },
        "applied": value.applied,
        "stale": value.stale,
        "created_at": value.created_at,
    }


def _decision_data(value: Any) -> dict[str, object]:
    return {
        "decision_id": value.decision_id,
        "row_id": value.row_id,
        "previous_record_version": value.previous_record_version,
        "record_version": value.record_version,
        "actor_id": value.actor_id,
        "action": value.action.value,
        "suggestion_id": value.suggestion_id,
        "reason_code": value.reason_code.value,
        "reason": value.reason,
        "edits": [_edit_data(edit) for edit in value.edits],
        "evidence_requests": [_evidence_request_data(item) for item in value.evidence_requests],
        "unresolved_acknowledgements": [_acknowledgement_data(item) for item in value.unresolved_acknowledgements],
        "created_at": value.created_at,
    }


def _run_data(value: ReviewSuggestionRun) -> dict[str, object]:
    return {
        "run_id": value.run_id,
        "row_id": value.row_id,
        "source_record_version": value.source_record_version,
        "status": value.status.value,
        "suggestion_id": value.suggestion_id,
        "error_code": value.error_code,
        "retryable": value.retryable,
        "request_id": value.request_id,
        "trace_id": value.trace_id,
        "created_at": value.created_at,
        "started_at": value.started_at,
        "finished_at": value.finished_at,
    }


def _context_data(value: Any) -> dict[str, object]:
    return {
        "identity": {
            "row_id": value.row.row_id,
            "item_id": value.row.item_id,
            "function_id": value.row.function_id,
            "item_label": value.item_label,
            "function_label": value.function_label,
        },
        "row": _row_data(value.row),
        "reviewability": value.reviewability,
        "field_reviews": [
            {
                "target_field": item.target_field,
                "value": _value_data(item.value),
                "claim_status": item.claim_status.value,
                "support_status": item.support_status.value,
                "evidence_ids": list(item.evidence_ids),
                "last_decision_id": item.last_decision_id,
            }
            for item in value.field_reviews
        ],
        "evidence": {
            "pack_id": value.evidence.pack_id,
            "pack_hash": value.evidence.pack_hash,
            "expires_at": value.evidence.expires_at,
            "refs": [
                {
                    "evidence_id": item.evidence_id,
                    "source_type": item.source_type,
                    "source_trust": item.source_trust,
                    "is_primary": item.is_primary,
                    "locator": item.locator,
                    "quote": item.quote,
                }
                for item in value.evidence.refs
            ],
        },
        "retrieval": {
            "requested_profile": value.retrieval.requested_profile.value,
            "resolved_profile": value.retrieval.resolved_profile.value,
            "evidence_types": [item.value for item in value.retrieval.evidence_types],
            "trace_id": value.retrieval.trace_id,
            "warnings": list(value.retrieval.warnings),
            "incomplete": value.retrieval.incomplete,
        },
        "latest_suggestion": None
        if value.latest_suggestion is None
        else _suggestion_data(value.latest_suggestion),
        "decision_history": [_decision_data(item) for item in value.decision_history],
        "warnings": list(value.warnings),
    }


def _decision_result_data(value: Any) -> dict[str, object]:
    return {
        "decision_id": value.decision_id,
        "row": _row_data(value.row),
        "previous_record_version": value.previous_record_version,
        "record_version": value.record_version,
        "review_status": value.review_status.value,
        "publication_status": value.publication_status.value,
        "audit_event_id": value.audit_event_id,
        "suggestion_id": value.suggestion_id,
        "evidence_requests": [_evidence_request_data(item) for item in value.evidence_requests],
        "persisted": value.persisted,
    }


def _envelope(resource_type: str, request_id: str, trace_id: str, data: object) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "resource_type": resource_type,
        "resource_version": _RESOURCE_VERSION,
        "request_id": request_id,
        "trace_id": trace_id,
        "data": data,
    }


def _pretty_requested(argv: Sequence[str] | None) -> bool:
    values = sys.argv[1:] if argv is None else argv
    return "--pretty" in values


def _write_json(payload: Mapping[str, object], *, pretty: bool) -> None:
    if pretty:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write(encoded)
    sys.stdout.write("\n")


def _emit_resource(
    resource_type: str,
    data: object,
    *,
    request_id: str | None = None,
    trace_id: str | None = None,
    pretty: bool,
) -> None:
    _write_json(
        _envelope(resource_type, request_id or str(uuid4()), trace_id or str(uuid4()), data),
        pretty=pretty,
    )


def _exit_code_for_error(code: str) -> int:
    return _ERROR_EXIT_GROUPS.get(code, _EXIT_CODES["internal"])


def _emit_error(
    code: str,
    detail: str,
    *,
    retryable: bool = False,
    pretty: bool,
    data: object | None = None,
    resource_type: str = "error",
) -> int:
    trace_id = str(uuid4())
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "resource_type": resource_type,
        "resource_version": _RESOURCE_VERSION,
        "request_id": str(uuid4()),
        "trace_id": trace_id,
        "status": "error",
        "error": {
            "code": code,
            "detail": detail,
            "trace_id": trace_id,
            "retryable": retryable,
            "errors": [],
        },
    }
    if data is not None:
        payload["data"] = data
    _write_json(payload, pretty=pretty)
    return _exit_code_for_error(code)


def _run_status_exit_code(run: ReviewSuggestionRun) -> int:
    if run.status is RunStatus.FAILED:
        return _exit_code_for_error(run.error_code or "FMEA_MODEL_SUGGESTION_UNAVAILABLE")
    return 0


def _await_suggestion(service: Any, actor: ActorContext, run: ReviewSuggestionRun, *, pretty: bool) -> int:
    deadline = time.monotonic() + SUGGESTION_DEADLINE_SECONDS
    latest = run
    while latest.status not in {RunStatus.SUCCEEDED, RunStatus.FAILED}:
        if time.monotonic() >= deadline:
            return _emit_error(
                "FMEA_MODEL_SUGGESTION_UNAVAILABLE",
                "review suggestion generation is unavailable",
                retryable=True,
                pretty=pretty,
                data=_run_data(latest),
                resource_type="review_suggestion_run",
            )
        time.sleep(SUGGESTION_POLL_INTERVAL_SECONDS)
        latest = service.get_suggestion_run(run.run_id, actor)
    _emit_resource(
        "review_suggestion_run",
        _run_data(latest),
        request_id=latest.request_id,
        trace_id=latest.trace_id,
        pretty=pretty,
    )
    return _run_status_exit_code(latest)


def _dispatch(args: argparse.Namespace, runtime: CliRuntime, request: dict[str, object] | None) -> int:
    service = runtime.service
    actor = runtime.actor
    pretty = bool(args.pretty)
    if args.review_command == "context":
        context = service.get_context(args.row_id, actor)
        _emit_resource(
            "review_context",
            _context_data(context),
            trace_id=context.retrieval.trace_id,
            pretty=pretty,
        )
        return 0
    if args.review_command == "suggest":
        try:
            command = StartReviewSuggestionCommand(
                row_id=args.row_id,
                expected_record_version=args.record_version,
                idempotency_key=args.idempotency_key,
                review_policy="default",
                focus_fields=tuple(args.focus_field),
            )
        except (TypeError, ValueError) as exc:
            raise CliUsageError from exc
        run = service.start_suggestion(command, actor)
        return _await_suggestion(service, actor, run, pretty=pretty)
    if args.review_command == "suggestion-status":
        run = service.get_suggestion_run(args.run_id, actor)
        _emit_resource(
            "review_suggestion_run",
            _run_data(run),
            trace_id=run.trace_id,
            pretty=pretty,
        )
        return _run_status_exit_code(run)
    if args.review_command == "decide":
        if request is None:
            raise _invalid_request_file()
        result = service.submit_decision(decision_command_from_request(request), actor)
        _emit_resource(
            "review_decision",
            _decision_result_data(result),
            request_id=result.request_id,
            trace_id=result.trace_id,
            pretty=pretty,
        )
        return 0
    if args.review_command == "decisions":
        decisions = service.list_decisions(args.row_id, actor)
        data = {"items": [_decision_data(item) for item in decisions], "next_cursor": None, "limit": 50}
        _emit_resource("review_decision_history", data, pretty=pretty)
        return 0
    raise CliUsageError


def main(argv: Sequence[str] | None = None) -> int:  # noqa: C901
    """Run one CLI operation and emit exactly one JSON object."""

    pretty = _pretty_requested(argv)
    try:
        args = parse_cli_args(argv)
    except CliUsageError:
        return _emit_error(
            "FMEA_REVIEW_REQUEST_INVALID",
            "invalid review CLI request",
            pretty=pretty,
        )

    if args.review_command == "decide" and not args.confirm_human_review:
        return _emit_error(
            "FMEA_REVIEW_CONFIRMATION_REQUIRED",
            "explicit human review confirmation is required",
            pretty=bool(args.pretty),
        )

    request: dict[str, object] | None = None
    if args.review_command == "decide":
        try:
            request = load_decision_request(args.request_file)
        except CliUsageError:
            return _emit_error(
                "FMEA_REVIEW_REQUEST_INVALID",
                "invalid review request file",
                pretty=bool(args.pretty),
            )

    try:
        runtime = build_cli_runtime()
    except WorkspaceNotFoundError:
        return _emit_error(
            "FMEA_WORKSPACE_NOT_FOUND",
            "review workspace is not configured",
            pretty=bool(args.pretty),
        )
    except WorkspaceConfigError:
        return _emit_error(
            "FMEA_WORKSPACE_CONFIGURATION_INVALID",
            "review workspace configuration is invalid",
            pretty=bool(args.pretty),
        )
    except ReviewError as exc:
        return _emit_error(exc.code, exc.public_message, retryable=exc.retryable, pretty=bool(args.pretty))
    except ValueError:
        return _emit_error(
            "FMEA_WORKSPACE_CONFIGURATION_INVALID",
            "review workspace configuration is invalid",
            pretty=bool(args.pretty),
        )
    except Exception:
        return _emit_error(
            "FMEA_REVIEW_INTERNAL",
            "internal review CLI failure",
            retryable=True,
            pretty=bool(args.pretty),
        )

    try:
        return _dispatch(args, runtime, request)
    except CliUsageError:
        return _emit_error(
            "FMEA_REVIEW_REQUEST_INVALID",
            "invalid review request",
            pretty=bool(args.pretty),
        )
    except ReviewError as exc:
        return _emit_error(exc.code, exc.public_message, retryable=exc.retryable, pretty=bool(args.pretty))
    except Exception:
        return _emit_error(
            "FMEA_REVIEW_INTERNAL",
            "internal review CLI failure",
            retryable=True,
            pretty=bool(args.pretty),
        )
    finally:
        with suppress(Exception):
            runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
