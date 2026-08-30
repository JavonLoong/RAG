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

ActorContext = Any
ReviewSuggestionRun = Any

FMEA_REVIEW_COMMANDS: Final = frozenset(
    {"context", "suggest", "suggestion-status", "decide", "decisions"}
)
FMEA_PROPAGATION_COMMANDS: Final = frozenset({"start", "status", "show", "paths", "review"})
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
_SCOPE_REQUEST_KEYS: Final = frozenset(
    {
        "target_id", "target_record_version", "evidence_pack_ids", "payload",
        "domain_pack_id", "domain_pack_version", "template_id", "template_version",
        "rule_pack_id", "rule_pack_version", "idempotency_key",
    }
)
_ASSIST_DECISION_KEYS: Final = frozenset(
    {"suggestion_id", "suggestion_record_version", "target_record_version", "action", "idempotency_key", "reason", "edits"}
)
_RISK_CONFIRM_KEYS: Final = frozenset({"row_id", "proposal_id", "expected_assessment_version", "idempotency_key"})
_RISK_REJECT_KEYS: Final = _RISK_CONFIRM_KEYS | {"reason"}
_PROPAGATION_REVIEW_KEYS: Final = frozenset(
    {"graph_revision_id", "expected_graph_record_version", "edge_decisions", "acknowledgements", "idempotency_key"}
)
_PROPAGATION_EDGE_DECISION_KEYS: Final = frozenset({"edge_id", "action", "reason"})

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
    **dict.fromkeys(("FMEA_REVIEW_REQUEST_INVALID", "FMEA_REVIEW_CONFIRMATION_REQUIRED", "FMEA_RISK_HUMAN_CONFIRMATION_REQUIRED", "FMEA_REVIEW_ACTION_INVALID", "FMEA_REVIEW_FIELD_INVALID", "FMEA_EVIDENCE_INVALID", "FMEA_UNRESOLVED_ACK_REQUIRED", "FMEA_REVIEW_SOURCE_MISSING"), _EXIT_CODES["request"]),
    **dict.fromkeys(("FMEA_WORKSPACE_CONFIGURATION_INVALID", "FMEA_WORKSPACE_NOT_FOUND", "FMEA_ROW_NOT_FOUND", "FMEA_REVIEW_SUGGESTION_NOT_FOUND", "FMEA_AUTH_CONFIGURATION_INVALID"), _EXIT_CODES["configuration"]),
    **dict.fromkeys(("FMEA_AUTH_REQUIRED", "FMEA_REVIEW_FORBIDDEN"), _EXIT_CODES["auth"]),
    **dict.fromkeys(("FMEA_IDEMPOTENCY_CONFLICT", "FMEA_REVIEW_TERMINAL", "FMEA_REVIEW_SUGGESTION_STALE", "FMEA_VERSION_CONFLICT", "FMEA_RISK_VERSION_CONFLICT", "FMEA_PRECONDITION_REQUIRED", "FMEA_REVIEW_RATE_LIMITED"), _EXIT_CODES["conflict"]),
    **dict.fromkeys(("FMEA_MODEL_SUGGESTION_INVALID", "FMEA_MODEL_SUGGESTION_UNAVAILABLE", "FMEA_REVIEW_RUN_INTERRUPTED"), _EXIT_CODES["model"]),
    **dict.fromkeys((
        "FMEA_ANALYSIS_NOT_FOUND",
        "FMEA_EVIDENCE_INVALID",
        "FMEA_PROPAGATION_RISK_INVALID",
        "FMEA_PROPAGATION_REGISTRY_INVALID",
        "FMEA_PROPAGATION_TOPOLOGY_INVALID",
        "FMEA_PROPAGATION_DEPTH_INVALID",
        "FMEA_PROPAGATION_BUDGET_INVALID",
        "FMEA_PROPAGATION_SUGGESTION_INVALID",
        "FMEA_PROPAGATION_ENDPOINT_INVALID",
        "FMEA_PROPAGATION_RELATION_INVALID",
        "FMEA_PROPAGATION_EVIDENCE_INVALID",
        "FMEA_PROPAGATION_SOURCE_INVALID",
        "FMEA_PROPAGATION_EDGE_INVALID",
        "FMEA_PROPAGATION_GRAPH_INVALID",
        "FMEA_PROPAGATION_REVIEW_INCOMPLETE",
        "FMEA_PROPAGATION_ACKNOWLEDGEMENT_REQUIRED",
        "FMEA_PROPAGATION_ACKNOWLEDGEMENT_INVALID",
        "FMEA_PROPAGATION_FAILED",
    ), _EXIT_CODES["request"]),
    **dict.fromkeys((
        "FMEA_ANALYSIS_VERSION_CONFLICT",
        "FMEA_PROPAGATION_REVIEW_TERMINAL",
        "FMEA_PROPAGATION_VERSION_CONFLICT",
    ), _EXIT_CODES["conflict"]),
    **dict.fromkeys(("FMEA_PROPAGATION_REVIEW_FORBIDDEN", "FMEA_PROPAGATION_GRAPH_NOT_FOUND", "FMEA_PROPAGATION_RUN_NOT_FOUND"), _EXIT_CODES["auth"]),
    "FMEA_PROPAGATION_PERSISTENCE_INVALID": _EXIT_CODES["storage"],
    "FMEA_REVIEW_STORAGE_UNAVAILABLE": _EXIT_CODES["storage"],
}
_SAFE_ERROR_DETAILS: Final = {
    "FMEA_MODEL_SUGGESTION_INVALID": "review suggestion is invalid",
    "FMEA_MODEL_SUGGESTION_UNAVAILABLE": "review suggestion generation is unavailable",
    "FMEA_REVIEW_RUN_INTERRUPTED": "review suggestion run was interrupted",
    "FMEA_PROPAGATION_ENDPOINT_INVALID": "propagation endpoint is invalid",
    "FMEA_PROPAGATION_RELATION_INVALID": "propagation relation is invalid",
    "FMEA_PROPAGATION_EVIDENCE_INVALID": "propagation evidence is invalid",
    "FMEA_PROPAGATION_SOURCE_INVALID": "propagation source is invalid",
}


@dataclass(frozen=True, slots=True)
class _ProjectDependencies:
    """Project modules loaded only after the CLI safe boundary is active."""

    workspace_registry: Any
    review_contracts: Any
    states: Any
    local_auth: Any


def _load_project_dependencies() -> _ProjectDependencies:
    return _ProjectDependencies(
        workspace_registry=import_module("chroma_rag_poc.workspace_registry"),
        review_contracts=import_module("fmea_application.review_contracts"),
        states=import_module("core_domain.fmea.states"),
        local_auth=import_module("fmea_infrastructure.local_auth"),
    )


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
    analysis_service: Any | None = None
    decision_service: Any | None = None
    risk_service: Any | None = None
    model_actor: ActorContext | None = None
    propagation_service: Any | None = None
    propagation_start_defaults: Mapping[str, object] | None = None


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

    assist = commands.add_parser("assist")
    assist_commands = assist.add_subparsers(dest="assist_command", required=True, parser_class=_CliArgumentParser)
    assist_scope = assist_commands.add_parser("scope")
    assist_scope.add_argument("--request-file", required=True)
    _add_pretty(assist_scope)
    assist_decide = assist_commands.add_parser("decide")
    assist_decide.add_argument("--request-file", required=True)
    assist_decide.add_argument("--confirm-human-assistance-decision", action="store_true")
    _add_pretty(assist_decide)

    risk = commands.add_parser("risk")
    risk_commands = risk.add_subparsers(dest="risk_command", required=True, parser_class=_CliArgumentParser)
    risk_show = risk_commands.add_parser("show")
    risk_show.add_argument("--row-id", required=True)
    _add_pretty(risk_show)
    risk_propose = risk_commands.add_parser("propose")
    risk_propose.add_argument("--row-id", required=True)
    risk_propose.add_argument("--record-version", required=True, type=_positive_int)
    risk_propose.add_argument("--evidence-pack-id", required=True)
    risk_propose.add_argument("--domain-pack-id", required=True)
    risk_propose.add_argument("--domain-pack-version", required=True)
    risk_propose.add_argument("--template-id", required=True)
    risk_propose.add_argument("--template-version", required=True)
    risk_propose.add_argument("--rule-pack-id", required=True)
    risk_propose.add_argument("--rule-pack-version", required=True)
    risk_propose.add_argument("--idempotency-key", required=True)
    _add_pretty(risk_propose)
    risk_status = risk_commands.add_parser("proposal-status")
    risk_status.add_argument("--run-id", required=True)
    _add_pretty(risk_status)
    for name in ("confirm", "reject"):
        transition = risk_commands.add_parser(name)
        transition.add_argument("--request-file", required=True)
        transition.add_argument("--confirm-human-risk-review", action="store_true")
        _add_pretty(transition)

    propagation = commands.add_parser("propagation")
    propagation_commands = propagation.add_subparsers(
        dest="propagation_command", required=True, parser_class=_CliArgumentParser
    )
    propagation_start = propagation_commands.add_parser("start")
    propagation_start.add_argument("--analysis-id", required=True)
    propagation_start.add_argument("--record-version", required=True, type=_positive_int)
    propagation_start.add_argument("--idempotency-key", required=True)
    _add_pretty(propagation_start)
    propagation_status = propagation_commands.add_parser("status")
    propagation_status.add_argument("--run-id", required=True)
    _add_pretty(propagation_status)
    propagation_show = propagation_commands.add_parser("show")
    propagation_show.add_argument("--graph-id", required=True)
    _add_pretty(propagation_show)
    propagation_paths = propagation_commands.add_parser("paths")
    propagation_paths.add_argument("--graph-id", required=True)
    _add_pretty(propagation_paths)
    propagation_review = propagation_commands.add_parser("review")
    propagation_review.add_argument("--request-file", required=True)
    propagation_review.add_argument("--confirm-human-propagation-review", action="store_true")
    _add_pretty(propagation_review)
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


def _strict_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")  # noqa: TRY003
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    del value
    raise ValueError("non-finite JSON number")  # noqa: TRY003


def _require_exact_keys(value: object, keys: frozenset[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys or not all(isinstance(key, str) for key in value):
        raise _invalid_request_file()
    return cast(dict[str, object], value)


def _is_reparse_or_symlink(value: os.stat_result) -> bool:
    reparse_point = 0x400
    attributes = int(getattr(value, "st_file_attributes", 0))
    return stat.S_ISLNK(value.st_mode) or bool(attributes & reparse_point)


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_size,
        left.st_mtime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_size,
        right.st_mtime_ns,
    )


def _request_file_stat(path: Path) -> os.stat_result:
    try:
        value = os.stat(path, follow_symlinks=False)
    except (OSError, ValueError, TypeError, OverflowError, MemoryError) as exc:
        raise _invalid_request_file() from exc
    if _is_reparse_or_symlink(value) or not stat.S_ISREG(value.st_mode):
        raise _invalid_request_file()
    return value


def _read_bounded_request_file(path: Path) -> bytes:
    before_path = _request_file_stat(path)
    flags = os.O_RDONLY | int(getattr(os, "O_BINARY", 0)) | int(getattr(os, "O_NOFOLLOW", 0))
    file_descriptor: int | None = None
    try:
        file_descriptor = os.open(path, flags)
        before_handle = os.fstat(file_descriptor)
        if _is_reparse_or_symlink(before_handle) or not stat.S_ISREG(before_handle.st_mode):
            raise _invalid_request_file()
        if not _same_file_identity(before_path, before_handle):
            raise _invalid_request_file()
        chunks: list[bytes] = []
        total = 0
        while total <= DECISION_REQUEST_MAX_BYTES:
            chunk = os.read(file_descriptor, DECISION_REQUEST_MAX_BYTES + 1 - total)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > DECISION_REQUEST_MAX_BYTES:
                raise _invalid_request_file()
        after_handle = os.fstat(file_descriptor)
        after_path = _request_file_stat(path)
        if not _same_file_identity(before_path, after_path) or not _same_file_identity(after_handle, after_path):
            raise _invalid_request_file()
        return b"".join(chunks)
    except CliUsageError:
        raise
    except (OSError, ValueError, TypeError, OverflowError, MemoryError) as exc:
        raise _invalid_request_file() from exc
    finally:
        if file_descriptor is not None:
            with suppress(OSError):
                os.close(file_descriptor)


def load_decision_request(path: str | Path) -> dict[str, object]:
    """Read and strictly validate one bounded, non-symlink JSON decision request."""

    try:
        raw = _read_bounded_request_file(Path(path))
        decoded = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_json_constant,
        )
        return _require_exact_keys(decoded, _DECISION_REQUEST_KEYS)
    except CliUsageError:
        raise
    except (OSError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError, RecursionError, MemoryError, OverflowError) as exc:
        raise _invalid_request_file() from exc


def load_json_request(path: str | Path) -> dict[str, object]:
    """Read one bounded strict JSON object for Task 5 CLI commands."""

    try:
        raw = _read_bounded_request_file(Path(path))
        decoded = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_json_constant,
        )
        if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
            raise _invalid_request_file()
        return cast(dict[str, object], decoded)
    except CliUsageError:
        raise
    except (OSError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError, RecursionError, MemoryError, OverflowError) as exc:
        raise _invalid_request_file() from exc


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _invalid_request_file()
    return tuple(cast(str, item) for item in value)


def _edit_from_request(value: object, dependencies: _ProjectDependencies) -> Any:
    data = _require_exact_keys(value, _EDIT_KEYS)
    raw_value = data["value"]
    if isinstance(raw_value, str):
        edit_value: str | tuple[str, ...] = raw_value
    else:
        edit_value = _string_tuple(raw_value)
    try:
        return dependencies.review_contracts.FieldReviewEdit(
            target_field=cast(str, data["target_field"]),
            operation=cast(Literal["replace"], data["operation"]),
            value=edit_value,
            claim_status=dependencies.states.ClaimStatus(cast(str, data["claim_status"])),
            support_status=dependencies.states.EvidenceSupportStatus(cast(str, data["support_status"])),
            evidence_ids=_string_tuple(data["evidence_ids"]),
            reason=cast(str, data["reason"]),
        )
    except (TypeError, ValueError) as exc:
        raise _invalid_request_file() from exc


def _evidence_request_from_request(value: object, dependencies: _ProjectDependencies) -> Any:
    data = _require_exact_keys(value, _EVIDENCE_REQUEST_KEYS)
    try:
        return dependencies.review_contracts.EvidenceRequestItem(
            target_field=cast(str, data["target_field"]),
            question=cast(str, data["question"]),
            preferred_source_types=_string_tuple(data["preferred_source_types"]),
            priority=dependencies.review_contracts.ReviewPriority(cast(str, data["priority"])),
        )
    except (TypeError, ValueError) as exc:
        raise _invalid_request_file() from exc


def _acknowledgement_from_request(value: object, dependencies: _ProjectDependencies) -> Any:
    data = _require_exact_keys(value, _ACKNOWLEDGEMENT_KEYS)
    try:
        return dependencies.review_contracts.UnresolvedAcknowledgement(
            target_field=cast(str, data["target_field"]),
            claim_status=dependencies.states.ClaimStatus(cast(str, data["claim_status"])),
            reason=cast(str, data["reason"]),
        )
    except (TypeError, ValueError) as exc:
        raise _invalid_request_file() from exc


def decision_command_from_request(
    data: Mapping[str, object], dependencies: _ProjectDependencies | None = None
) -> Any:
    """Convert one strict request object to the application command contract."""

    dependencies = dependencies or _load_project_dependencies()
    try:
        suggestion_id = data["suggestion_id"]
        if suggestion_id is not None and not isinstance(suggestion_id, str):
            raise _invalid_request_file()
        raw_edits = data["edits"]
        raw_requests = data["evidence_requests"]
        raw_acknowledgements = data["unresolved_acknowledgements"]
        if not isinstance(raw_edits, list) or not isinstance(raw_requests, list) or not isinstance(raw_acknowledgements, list):
            raise _invalid_request_file()

        return dependencies.review_contracts.ReviewDecisionCommand(
            row_id=cast(str, data["row_id"]),
            expected_record_version=cast(int, data["expected_record_version"]),
            idempotency_key=cast(str, data["idempotency_key"]),
            action=dependencies.review_contracts.ReviewAction(cast(str, data["action"])),
            suggestion_id=suggestion_id,
            reason_code=dependencies.review_contracts.ReviewReasonCode(cast(str, data["reason_code"])),
            reason=cast(str, data["reason"]),
            edits=tuple(_edit_from_request(item, dependencies) for item in raw_edits),
            evidence_requests=tuple(_evidence_request_from_request(item, dependencies) for item in raw_requests),
            unresolved_acknowledgements=tuple(
                _acknowledgement_from_request(item, dependencies) for item in raw_acknowledgements
            ),
        )
    except CliUsageError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid_request_file() from exc


def build_cli_runtime() -> CliRuntime:
    """Build the registry-backed service and authenticate only the loopback environment token."""

    dependencies = _load_project_dependencies()
    registry = dependencies.workspace_registry.WorkspaceRegistry.from_env()
    provider = cast(Any, dependencies.local_auth.LocalReviewAuthProvider).from_env()
    actor = provider.authenticate(os.environ.get("FMEA_REVIEW_TOKEN"), "127.0.0.1")
    workspace = registry.get(actor.workspace_id)
    runtime = build_workspace_review_runtime(workspace)
    composition = import_module("fmea_infrastructure.composition")
    risk_runtime = composition.build_default_workspace_risk_runtime(
        workspace,
        context_provider=runtime.service,
    )
    propagation_runtime = None
    propagation_start_defaults: Mapping[str, object] | None = None
    if composition.propagation_server_environment_present():
        propagation_runtime = composition.build_default_workspace_propagation_runtime(
            workspace,
            risk_repository=risk_runtime.risk_repository,
        )
        propagation_start_defaults = propagation_runtime.start_defaults
    model_actor = dependencies.review_contracts.ActorContext(
        actor_id="fmea-model-assistant",
        actor_type=dependencies.states.ActorType.MODEL,
        roles=frozenset(),
        workspace_id=actor.workspace_id,
    )
    closed = False

    def close() -> None:
        nonlocal closed
        if closed:
            return
        closed = True
        close_nonblocking = getattr(runtime.executor, "close_nonblocking", None)
        if callable(close_nonblocking):
            close_nonblocking()
        else:
            runtime.executor.close()

    return CliRuntime(
        service=runtime.service,
        actor=actor,
        close=close,
        analysis_service=risk_runtime.analysis_service,
        decision_service=risk_runtime.decision_service,
        risk_service=risk_runtime.risk_service,
        model_actor=model_actor,
        propagation_service=None if propagation_runtime is None else propagation_runtime.service,
        propagation_start_defaults=propagation_start_defaults,
    )


def build_workspace_review_runtime(workspace: Any) -> Any:
    """Resolve the shared concrete composition without importing its storage types here."""

    composition = import_module("fmea_infrastructure.composition")
    return cast(Any, composition.build_workspace_review_runtime)(workspace)


def _value_data(value: str | tuple[str, ...]) -> str | list[str]:
    return value if isinstance(value, str) else list(value)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _risk_data(value: Any) -> dict[str, object] | None:
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


def _row_data(row: Any) -> dict[str, object]:
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
        "claim_status": _enum_value(row.claim_status),
        "review_status": _enum_value(row.review_status),
        "publication_status": _enum_value(row.publication_status),
        "record_version": row.record_version,
    }


def _edit_data(value: Any) -> dict[str, object]:
    return {
        "target_field": value.target_field,
        "operation": value.operation,
        "value": _value_data(value.value),
        "claim_status": _enum_value(value.claim_status),
        "support_status": _enum_value(value.support_status),
        "evidence_ids": list(value.evidence_ids),
        "reason": value.reason,
    }


def _evidence_request_data(value: Any) -> dict[str, object]:
    return {
        "target_field": value.target_field,
        "question": value.question,
        "preferred_source_types": list(value.preferred_source_types),
        "priority": _enum_value(value.priority),
    }


def _acknowledgement_data(value: Any) -> dict[str, object]:
    return {
        "target_field": value.target_field,
        "claim_status": _enum_value(value.claim_status),
        "reason": value.reason,
    }


def _suggestion_data(value: Any) -> dict[str, object]:
    return {
        "suggestion_id": value.suggestion_id,
        "run_id": value.run_id,
        "row_id": value.row_id,
        "source_record_version": value.source_record_version,
        "recommended_action": _enum_value(value.recommended_action),
        "field_findings": [
            {
                "target_field": finding.target_field,
                "judgement": _enum_value(finding.judgement),
                "recommended_claim_status": _enum_value(finding.recommended_claim_status),
                "evidence_ids": list(finding.evidence_ids),
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
        "action": _enum_value(value.action),
        "suggestion_id": value.suggestion_id,
        "reason_code": _enum_value(value.reason_code),
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
        "status": _enum_value(value.status),
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
                "claim_status": _enum_value(item.claim_status),
                "support_status": _enum_value(item.support_status),
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
            "requested_profile": _enum_value(value.retrieval.requested_profile),
            "resolved_profile": _enum_value(value.retrieval.resolved_profile),
            "evidence_types": [_enum_value(item) for item in value.retrieval.evidence_types],
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
        "review_status": _enum_value(value.review_status),
        "publication_status": _enum_value(value.publication_status),
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


def _exception_parts(exc: Exception) -> tuple[str, str, bool]:
    if isinstance(exc, CliUsageError):
        return "FMEA_REVIEW_REQUEST_INVALID", "invalid review request", False
    exception_name = type(exc).__name__
    if exception_name == "WorkspaceNotFoundError":
        return "FMEA_WORKSPACE_NOT_FOUND", "review workspace is not configured", False
    if exception_name == "WorkspaceConfigError":
        return "FMEA_WORKSPACE_CONFIGURATION_INVALID", "review workspace configuration is invalid", False

    code = getattr(exc, "code", None)
    if isinstance(code, str) and code in _ERROR_EXIT_GROUPS:
        public_message = getattr(exc, "public_message", None)
        detail = public_message if isinstance(public_message, str) and public_message else _SAFE_ERROR_DETAILS.get(code)
        if detail is None:
            detail = "review operation failed"
        return code, detail, bool(getattr(exc, "retryable", False))
    if isinstance(exc, ValueError):
        return "FMEA_WORKSPACE_CONFIGURATION_INVALID", "review workspace configuration is invalid", False
    return "FMEA_REVIEW_INTERNAL", "internal review CLI failure", True


def _emit_exception(exc: Exception, *, pretty: bool) -> int:
    code, detail, retryable = _exception_parts(exc)
    return _emit_error(code, detail, retryable=retryable, pretty=pretty)


def _run_status_exit_code(run: ReviewSuggestionRun) -> int:
    if _enum_value(run.status) == "failed":
        return _exit_code_for_error(run.error_code or "FMEA_MODEL_SUGGESTION_UNAVAILABLE")
    return 0


def _emit_failed_suggestion(run: ReviewSuggestionRun, *, pretty: bool) -> int:
    candidate_code = run.error_code
    code = (
        candidate_code
        if isinstance(candidate_code, str) and candidate_code in _ERROR_EXIT_GROUPS
        else "FMEA_MODEL_SUGGESTION_UNAVAILABLE"
    )
    detail = _SAFE_ERROR_DETAILS.get(code, "review suggestion generation failed")
    return _emit_error(
        code,
        detail,
        retryable=bool(run.retryable),
        pretty=pretty,
        data=_run_data(run),
        resource_type="review_suggestion_run",
    )


def _emit_failed_propagation_run(run: Any, *, pretty: bool) -> int:
    candidate_code = run.error_code
    code = (
        candidate_code
        if isinstance(candidate_code, str) and candidate_code in _ERROR_EXIT_GROUPS
        else "FMEA_PROPAGATION_FAILED"
    )
    return _emit_error(
        code,
        _SAFE_ERROR_DETAILS.get(code, "propagation analysis failed"),
        pretty=pretty,
        data=_task5_data("chroma_rag_poc.routes_fmea_propagation_v1", "run_data", run),
        resource_type="propagation_run",
    )


def _await_suggestion(service: Any, actor: ActorContext, run: ReviewSuggestionRun, *, pretty: bool) -> int:
    deadline = time.monotonic() + SUGGESTION_DEADLINE_SECONDS
    latest = run
    while _enum_value(latest.status) not in {"succeeded", "failed"}:
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
    if _enum_value(latest.status) == "failed":
        return _emit_failed_suggestion(latest, pretty=pretty)
    _emit_resource(
        "review_suggestion_run",
        _run_data(latest),
        request_id=latest.request_id,
        trace_id=latest.trace_id,
        pretty=pretty,
    )
    return _run_status_exit_code(latest)


def _task5_data(module_name: str, function_name: str, value: Any) -> dict[str, object]:
    module = import_module(module_name)
    model = getattr(module, function_name)(value)
    return cast(dict[str, object], model.model_dump(mode="json"))


def _review_error(code: str, detail: str) -> Exception:
    module = import_module("fmea_application.review_errors")
    return cast(Exception, module.ReviewError(code, detail))


def _task5_service(runtime: CliRuntime, name: str) -> Any:
    service = getattr(runtime, name, None)
    if service is None:
        raise _review_error("FMEA_REVIEW_STORAGE_UNAVAILABLE", "requested FMEA service is not configured")
    return service


def _task5_model_actor(runtime: CliRuntime) -> ActorContext:
    actor = getattr(runtime, "model_actor", None)
    if actor is None:
        raise _review_error("FMEA_REVIEW_STORAGE_UNAVAILABLE", "FMEA model actor is not configured")
    return actor


def _dispatch_assist(
    args: argparse.Namespace,
    runtime: CliRuntime,
    request: dict[str, object] | None,
) -> int:
    if request is None:
        raise _invalid_request_file()
    pretty = bool(args.pretty)
    if args.assist_command == "scope":
        data = _require_exact_keys(request, _SCOPE_REQUEST_KEYS)
        contracts = import_module("fmea_application.assistance_contracts")
        command = contracts.AssistanceRequest(
            request_id=str(uuid4()),
            kind=contracts.AssistanceKind.ANALYSIS_SCOPE_DRAFT,
            workspace_id=runtime.actor.workspace_id,
            target_type="fmea_analysis",
            target_id=cast(str, data["target_id"]),
            target_record_version=cast(int, data["target_record_version"]),
            evidence_pack_ids=_string_tuple(data["evidence_pack_ids"]),
            payload=data["payload"],
            domain_pack_id=cast(str, data["domain_pack_id"]),
            domain_pack_version=cast(str, data["domain_pack_version"]),
            template_id=cast(str, data["template_id"]),
            template_version=cast(str, data["template_version"]),
            rule_pack_id=cast(str, data["rule_pack_id"]),
            rule_pack_version=cast(str, data["rule_pack_version"]),
            idempotency_key=cast(str, data["idempotency_key"]),
        )
        suggestion = _task5_service(runtime, "analysis_service").suggest_scope(
            command,
            _task5_model_actor(runtime),
        )
        _emit_resource(
            "assistance_suggestion",
            _task5_data("chroma_rag_poc.routes_fmea_assistance_v1", "suggestion_data", suggestion),
            request_id=command.request_id,
            trace_id=suggestion.trace_id,
            pretty=pretty,
        )
        return 0
    if args.assist_command == "decide":
        data = _require_exact_keys(request, _ASSIST_DECISION_KEYS)
        raw_edits = data["edits"]
        if not isinstance(raw_edits, list):
            raise _invalid_request_file()
        edits: list[tuple[str, object]] = []
        for item in raw_edits:
            edit = _require_exact_keys(item, frozenset({"field", "value"}))
            edits.append((cast(str, edit["field"]), edit["value"]))
        contracts = import_module("fmea_application.assistance_contracts")
        service_contracts = import_module("fmea_application.assistance_service")
        command = service_contracts.DecideAssistanceCommand(
            suggestion_id=cast(str, data["suggestion_id"]),
            expected_suggestion_version=cast(int, data["suggestion_record_version"]),
            expected_target_record_version=cast(int, data["target_record_version"]),
            action=contracts.AssistanceDecisionAction(cast(str, data["action"])),
            idempotency_key=cast(str, data["idempotency_key"]),
            reason=cast(str, data["reason"]),
            edits=tuple(edits),
        )
        decision = _task5_service(runtime, "decision_service").decide(command, runtime.actor)
        _emit_resource(
            "assistance_decision",
            _task5_data("chroma_rag_poc.routes_fmea_assistance_v1", "decision_data", decision),
            pretty=pretty,
        )
        return 0
    raise CliUsageError


def _dispatch_risk(
    args: argparse.Namespace,
    runtime: CliRuntime,
    request: dict[str, object] | None,
) -> int:
    service = _task5_service(runtime, "risk_service")
    pretty = bool(args.pretty)
    if args.risk_command == "show":
        assessment = service.get(args.row_id, runtime.actor)
        if assessment is None:
            raise _review_error("FMEA_ROW_NOT_FOUND", "risk assessment was not found")
        _emit_resource(
            "risk_assessment",
            _task5_data("chroma_rag_poc.routes_fmea_risk_v1", "assessment_data", assessment),
            pretty=pretty,
        )
        return 0
    if args.risk_command == "propose":
        contracts = import_module("fmea_application.risk_contracts")
        command = contracts.StartRiskProposalCommand(
            row_id=args.row_id,
            expected_record_version=args.record_version,
            evidence_pack_id=args.evidence_pack_id,
            domain_pack_id=args.domain_pack_id,
            domain_pack_version=args.domain_pack_version,
            template_id=args.template_id,
            template_version=args.template_version,
            rule_pack_id=args.rule_pack_id,
            rule_pack_version=args.rule_pack_version,
            idempotency_key=args.idempotency_key,
        )
        assessment = service.propose(command, _task5_model_actor(runtime))
        run_id = assessment.assistance_suggestion_id
        if not isinstance(run_id, str) or not run_id:
            raise _review_error("FMEA_MODEL_SUGGESTION_INVALID", "risk proposal run identity is unavailable")
        assessment_payload = _task5_data("chroma_rag_poc.routes_fmea_risk_v1", "assessment_data", assessment)
        _emit_resource(
            "risk_proposal_run",
            {"run_id": run_id, "status": "succeeded", "assessment": assessment_payload},
            pretty=pretty,
        )
        return 0
    if args.risk_command == "proposal-status":
        assessment = service.get_proposal_run(args.run_id, runtime.actor)
        assessment_payload = _task5_data("chroma_rag_poc.routes_fmea_risk_v1", "assessment_data", assessment)
        _emit_resource(
            "risk_proposal_run",
            {"run_id": args.run_id, "status": "succeeded", "assessment": assessment_payload},
            pretty=pretty,
        )
        return 0
    if request is None:
        raise _invalid_request_file()
    contracts = import_module("fmea_application.risk_contracts")
    if args.risk_command == "confirm":
        data = _require_exact_keys(request, _RISK_CONFIRM_KEYS)
        command = contracts.ConfirmRiskCommand(
            row_id=cast(str, data["row_id"]),
            proposal_id=cast(str, data["proposal_id"]),
            expected_assessment_version=cast(int, data["expected_assessment_version"]),
            idempotency_key=cast(str, data["idempotency_key"]),
        )
        result = service.confirm(command, runtime.actor)
        _emit_resource(
            "risk_confirmation",
            _task5_data("chroma_rag_poc.routes_fmea_risk_v1", "confirmation_data", result),
            pretty=pretty,
        )
        return 0
    if args.risk_command == "reject":
        data = _require_exact_keys(request, _RISK_REJECT_KEYS)
        command = contracts.RejectRiskCommand(
            row_id=cast(str, data["row_id"]),
            proposal_id=cast(str, data["proposal_id"]),
            expected_assessment_version=cast(int, data["expected_assessment_version"]),
            idempotency_key=cast(str, data["idempotency_key"]),
            reason=cast(str, data["reason"]),
        )
        assessment = service.reject(command, runtime.actor)
        _emit_resource(
            "risk_assessment",
            _task5_data("chroma_rag_poc.routes_fmea_risk_v1", "assessment_data", assessment),
            pretty=pretty,
        )
        return 0
    raise CliUsageError


def _propagation_start_command(args: argparse.Namespace, runtime: CliRuntime) -> Any:
    """Build the full service command from server-owned CLI runtime defaults.

    The public CLI intentionally exposes only the analysis/version/key tuple.
    Resource identities are supplied by the configured runtime, so callers
    cannot replace topology, model, provider, template, or rule selection.
    Injected and concrete runtimes must both provide the same bound defaults.
    """

    defaults = getattr(runtime, "propagation_start_defaults", None)
    if not isinstance(defaults, Mapping):
        raise _review_error(
            "FMEA_WORKSPACE_CONFIGURATION_INVALID",
            "FMEA propagation server defaults are unavailable",
        )
    required = (
        "source_row_ids",
        "evidence_pack_id",
        "topology_id",
        "topology_version",
        "domain_pack_id",
        "domain_pack_version",
        "rule_pack_id",
        "rule_pack_version",
    )
    if any(key not in defaults for key in required):
        raise _review_error(
            "FMEA_WORKSPACE_CONFIGURATION_INVALID",
            "FMEA propagation server defaults are incomplete",
        )
    source_row_ids = defaults["source_row_ids"]
    string_default_keys = tuple(key for key in required if key != "source_row_ids")
    if (
        not isinstance(source_row_ids, Sequence)
        or isinstance(source_row_ids, str | bytes)
        or not source_row_ids
        or any(not isinstance(item, str) or not item.strip() for item in source_row_ids)
        or any(
            not isinstance(defaults[key], str) or not cast(str, defaults[key]).strip()
            for key in string_default_keys
        )
    ):
        raise _review_error(
            "FMEA_WORKSPACE_CONFIGURATION_INVALID",
            "FMEA propagation server defaults are invalid",
        )
    try:
        contracts = import_module("fmea_application.propagation_service")
        return contracts.StartPropagationCommand(
            analysis_id=args.analysis_id,
            expected_analysis_record_version=args.record_version,
            source_row_ids=tuple(cast(Sequence[str], source_row_ids)),
            evidence_pack_id=cast(str, defaults["evidence_pack_id"]),
            topology_id=cast(str, defaults["topology_id"]),
            topology_version=cast(str, defaults["topology_version"]),
            domain_pack_id=cast(str, defaults["domain_pack_id"]),
            domain_pack_version=cast(str, defaults["domain_pack_version"]),
            rule_pack_id=cast(str, defaults["rule_pack_id"]),
            rule_pack_version=cast(str, defaults["rule_pack_version"]),
            idempotency_key=args.idempotency_key,
        )
    except (TypeError, ValueError) as exc:
        raise _review_error("FMEA_REVIEW_REQUEST_INVALID", "propagation CLI defaults are invalid") from exc


def _propagation_review_command(request: Mapping[str, object]) -> Any:
    data = _require_exact_keys(request, _PROPAGATION_REVIEW_KEYS)
    raw_decisions = data["edge_decisions"]
    raw_acknowledgements = data["acknowledgements"]
    expected_version = data["expected_graph_record_version"]
    idempotency_key = data["idempotency_key"]
    if (
        not isinstance(raw_decisions, list)
        or not isinstance(raw_acknowledgements, list)
        or isinstance(expected_version, bool)
        or not isinstance(expected_version, int)
        or expected_version < 1
        or not isinstance(idempotency_key, str)
    ):
        raise _invalid_request_file()
    try:
        from fmea_application.propagation_service import (
            ConfirmPropagationCommand,
            PropagationDecisionAction,
            PropagationEdgeDecision,
        )
        decisions = []
        for item in raw_decisions:
            decision = _require_exact_keys(item, _PROPAGATION_EDGE_DECISION_KEYS)
            if not all(isinstance(decision[key], str) for key in _PROPAGATION_EDGE_DECISION_KEYS):
                raise _invalid_request_file()
            decisions.append(
                PropagationEdgeDecision(
                    edge_id=cast(str, decision["edge_id"]),
                    action=PropagationDecisionAction(cast(str, decision["action"])),
                    reason=cast(str, decision["reason"]),
                )
            )
        acknowledgements = _string_tuple(raw_acknowledgements)
        if not isinstance(data["graph_revision_id"], str) or not isinstance(idempotency_key, str):
            raise _invalid_request_file()
        return ConfirmPropagationCommand(
            graph_revision_id=cast(str, data["graph_revision_id"]),
            expected_graph_record_version=expected_version,
            edge_decisions=tuple(decisions),
            acknowledgements=acknowledgements,
            idempotency_key=idempotency_key,
        )
    except CliUsageError:
        raise
    except (TypeError, ValueError) as exc:
        raise _invalid_request_file() from exc


def _dispatch_propagation(  # noqa: C901
    args: argparse.Namespace,
    runtime: CliRuntime,
    request: dict[str, object] | None,
) -> int:
    service = getattr(runtime, "propagation_service", None)
    if service is None:
        raise _review_error(
            "FMEA_WORKSPACE_CONFIGURATION_INVALID",
            "FMEA propagation server configuration is unavailable",
        )
    pretty = bool(args.pretty)
    if args.propagation_command == "start":
        run = service.start_analysis(_propagation_start_command(args, runtime), runtime.actor)
        if _enum_value(run.status) == "failed":
            return _emit_failed_propagation_run(run, pretty=pretty)
        _emit_resource(
            "propagation_run",
            _task5_data("chroma_rag_poc.routes_fmea_propagation_v1", "run_data", run),
            request_id=run.run_id,
            trace_id=run.run_id,
            pretty=pretty,
        )
        return 0
    if args.propagation_command == "status":
        run = service.get_run(args.run_id, runtime.actor)
        if _enum_value(run.status) == "failed":
            return _emit_failed_propagation_run(run, pretty=pretty)
        _emit_resource(
            "propagation_run",
            _task5_data("chroma_rag_poc.routes_fmea_propagation_v1", "run_data", run),
            request_id=run.run_id,
            trace_id=run.run_id,
            pretty=pretty,
        )
        return 0
    if args.propagation_command == "show":
        graph = service.get_graph(args.graph_id, runtime.actor)
        if graph is None:
            raise _review_error("FMEA_PROPAGATION_GRAPH_NOT_FOUND", "propagation graph revision was not found")
        _emit_resource(
            "propagation_graph",
            _task5_data("chroma_rag_poc.routes_fmea_propagation_v1", "graph_data", graph),
            request_id=graph.graph_revision_id,
            trace_id=graph.graph_revision_id,
            pretty=pretty,
        )
        return 0
    if args.propagation_command == "paths":
        graph = service.get_graph(args.graph_id, runtime.actor)
        if graph is None:
            raise _review_error("FMEA_PROPAGATION_GRAPH_NOT_FOUND", "propagation graph revision was not found")
        paths = tuple(sorted(graph.paths, key=lambda item: item.path_id))
        _emit_resource(
            "propagation_path_history",
            {
                "items": [
                    _task5_data("chroma_rag_poc.routes_fmea_propagation_v1", "path_data", item)
                    for item in paths
                ],
                "next_cursor": None,
                "limit": len(paths),
            },
            request_id=graph.graph_revision_id,
            trace_id=graph.graph_revision_id,
            pretty=pretty,
        )
        return 0
    if args.propagation_command == "review":
        if request is None:
            raise _invalid_request_file()
        if getattr(runtime.actor, "actor_type", None) is not import_module("core_domain.fmea.states").ActorType.HUMAN:
            raise _review_error("FMEA_PROPAGATION_REVIEW_FORBIDDEN", "a human propagation reviewer is required")
        if "propagation_reviewer" not in getattr(runtime.actor, "roles", ()):
            raise _review_error("FMEA_PROPAGATION_REVIEW_FORBIDDEN", "the propagation_reviewer role is required")
        result = service.confirm_graph(_propagation_review_command(request), runtime.actor)
        _emit_resource(
            "propagation_review",
            _task5_data("chroma_rag_poc.routes_fmea_propagation_v1", "review_result_data", result),
            request_id=result.decision_id,
            trace_id=result.decision_id,
            pretty=pretty,
        )
        return 0
    raise CliUsageError


def _dispatch(args: argparse.Namespace, runtime: CliRuntime, request: dict[str, object] | None) -> int:  # noqa: C901
    if args.command == "assist":
        return _dispatch_assist(args, runtime, request)
    if args.command == "risk":
        return _dispatch_risk(args, runtime, request)
    if args.command == "propagation":
        return _dispatch_propagation(args, runtime, request)
    if args.command != "review":
        raise CliUsageError
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
            contracts = _load_project_dependencies().review_contracts
            command = contracts.StartReviewSuggestionCommand(
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
        if _enum_value(run.status) == "failed":
            return _emit_failed_suggestion(run, pretty=pretty)
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
        page = tuple(service.page_decisions(args.row_id, actor, after=None, limit=50))
        decisions = page[:50]
        next_cursor = None
        if len(page) > 50 and decisions:
            last = decisions[-1]
            next_cursor = [last.created_at, last.decision_id]
        data = {"items": [_decision_data(item) for item in decisions], "next_cursor": next_cursor, "limit": 50}
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

    if args.command == "review" and args.review_command == "decide" and not args.confirm_human_review:
        return _emit_error(
            "FMEA_REVIEW_CONFIRMATION_REQUIRED",
            "explicit human review confirmation is required",
            pretty=bool(args.pretty),
        )

    if args.command == "assist" and args.assist_command == "decide" and not args.confirm_human_assistance_decision:
        return _emit_error(
            "FMEA_REVIEW_CONFIRMATION_REQUIRED",
            "explicit human assistance decision confirmation is required",
            pretty=bool(args.pretty),
        )
    if args.command == "risk" and args.risk_command in {"confirm", "reject"} and not args.confirm_human_risk_review:
        return _emit_error(
            "FMEA_RISK_HUMAN_CONFIRMATION_REQUIRED",
            "explicit human risk review confirmation is required",
            pretty=bool(args.pretty),
        )
    if args.command == "propagation" and args.propagation_command == "review" and not args.confirm_human_propagation_review:
        return _emit_error(
            "FMEA_REVIEW_CONFIRMATION_REQUIRED",
            "explicit human propagation review confirmation is required",
            pretty=bool(args.pretty),
        )

    request: dict[str, object] | None = None
    if args.command == "review" and args.review_command == "decide":
        try:
            request = load_decision_request(args.request_file)
        except CliUsageError:
            return _emit_error(
                "FMEA_REVIEW_REQUEST_INVALID",
                "invalid review request file",
                pretty=bool(args.pretty),
            )
    elif args.command == "assist" or (args.command == "risk" and args.risk_command in {"confirm", "reject"}) or (args.command == "propagation" and args.propagation_command == "review"):
        try:
            request = load_json_request(args.request_file)
        except CliUsageError:
            return _emit_error(
                "FMEA_REVIEW_REQUEST_INVALID",
                "invalid FMEA request file",
                pretty=bool(args.pretty),
            )

    try:
        runtime = build_cli_runtime()
    except Exception as exc:
        return _emit_exception(exc, pretty=bool(args.pretty))

    try:
        return _dispatch(args, runtime, request)
    except Exception as exc:
        return _emit_exception(exc, pretty=bool(args.pretty))
    finally:
        with suppress(Exception):
            runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
