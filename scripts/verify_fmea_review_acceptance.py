"""Independent fail-closed verifier for the offline FMEA review acceptance pack."""

from __future__ import annotations

import argparse
import json
import re
import sys
from hashlib import sha256
from pathlib import Path
from typing import NoReturn, cast

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from structured_output_application.compiler import TemplateCompiler  # noqa: E402
from structured_output_infrastructure.jsonschema_adapter import Draft202012SchemaAdapter  # noqa: E402
from structured_output_infrastructure.source_loader import load_template_source  # noqa: E402

SCHEMA_VERSION = "graphrag.fmea.review.acceptance.v1"
_FMEA_SCHEMA_VERSION = "graphrag.fmea.v1"
_TEMPLATE_PATH = ROOT / "templates" / "examples" / "fmea-row-review.yaml"
_ARTIFACTS = (
    "context.json",
    "suggestion-run.json",
    "suggestion.json",
    "decision.json",
    "audit-summary.json",
    "acceptance-summary.json",
)
_PROFILE_CASES = (
    ("rag_only", "rag_only", ["text"]),
    ("graphrag_local_only", "graphrag_local_only", ["graph"]),
    ("graphrag_global_only", "graphrag_global_only", ["community"]),
    ("graphrag_only", "graphrag_only", ["graph", "community"]),
    ("combined", "combined", ["text", "graph", "community"]),
    ("auto", "combined", ["text", "graph", "community"]),
    ("custom", "custom", ["text", "graph"]),
)
_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
_MARKERS = tuple(
    marker.encode("utf-8")
    for marker in (
        "DEEPSEEK_API_KEY",
        "Authorization",
        "Bearer ",
        "sk-",
        "TOPSECRET",
        "C:\\private",
        "REQUEST_PRIVATE_MARKER",
        "EVIDENCE_PRIVATE_MARKER",
    )
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_ROW_KEYS = {
    "row_id", "analysis_id", "evidence_pack_id", "item_id", "function_id", "failure_mode", "causes",
    "mechanisms", "effects", "symptoms", "controls", "barriers", "actions", "risk_assessment",
    "field_evidence", "field_support", "claim_status", "review_status", "publication_status", "record_version",
}
_RUN_KEYS = {
    "run_id", "row_id", "source_record_version", "status", "suggestion_id", "error_code", "retryable",
    "request_id", "trace_id", "created_at", "started_at", "finished_at",
}
_SUGGESTION_KEYS = {
    "suggestion_id", "run_id", "row_id", "source_record_version", "recommended_action", "field_findings",
    "proposed_edits", "evidence_requests", "missing_evidence", "conflicts", "rationale", "model_manifest",
    "actor_type", "applied", "stale", "created_at",
}
_DECISION_KEYS = {
    "decision_id", "row", "previous_record_version", "record_version", "review_status", "publication_status",
    "audit_event_id", "suggestion_id", "evidence_requests", "persisted", "request_id", "trace_id",
}
_AUDIT_KEYS = {
    "event_id", "occurred_at_server", "workspace_id", "actor_id", "actor_type", "actor_roles", "command", "action",
    "reason_code", "reason", "analysis_id", "row_id", "suggestion_id", "decision_id", "expected_record_version",
    "applied_record_version", "before_hash", "after_hash", "changed_fields", "evidence_ids", "evidence_request_targets",
    "idempotency_key_hash", "canonical_payload_hash", "versions", "template_id", "template_version", "profile_id",
    "profile_version", "model_manifest", "request_id", "trace_id", "retrieval_trace_id",
}


class AcceptanceVerificationError(ValueError):
    """Stable failure with no path, input, key, or provider text."""

    def __init__(self, code: str) -> None:
        super().__init__("FMEA acceptance verification failed.")
        self.code = code


def _fail(code: str) -> NoReturn:
    raise AcceptanceVerificationError(code)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _hash_json(value: object) -> str:
    return _hash_bytes(_canonical(value))


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    _fail("JSON_INVALID")


def _load(path: Path) -> tuple[dict[str, object], bytes]:
    try:
        raw = path.read_bytes()
    except OSError:
        _fail("ARTIFACT_MISSING")
    if len(raw) > _MAX_ARTIFACT_BYTES:
        _fail("ARTIFACT_TOO_LARGE")
    if any(marker in raw for marker in _MARKERS):
        _fail("OUTPUT_PRIVATE_MARKER")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
        _fail("JSON_INVALID")
    if not isinstance(value, dict):
        _fail("JSON_SHAPE_INVALID")
    if _canonical(value) != raw:
        _fail("JSON_NOT_CANONICAL")
    return value, raw


def _exact(value: object, keys: set[str], code: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        _fail(code)
    return cast(dict[str, object], value)


def _schema(value: dict[str, object], expected: str) -> None:
    if value.get("schema_version") != expected:
        _fail("SCHEMA_MISMATCH")


def _validate_profiles(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) != len(_PROFILE_CASES):
        _fail("PROFILE_MATRIX_INVALID")
    expected = {requested: (resolved, types) for requested, resolved, types in _PROFILE_CASES}
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in value:
        case = _exact(
            item,
            {"case_id", "requested_profile", "resolved_profile", "evidence_types", "retrieval_warnings", "retrieval_incomplete"},
            "PROFILE_MATRIX_INVALID",
        )
        requested = case.get("requested_profile")
        if not isinstance(requested, str) or requested in seen or requested not in expected:
            _fail("PROFILE_MATRIX_INVALID")
        resolved, types = expected[requested]
        if case.get("resolved_profile") != resolved or case.get("evidence_types") != types:
            _fail("PROFILE_MATRIX_INVALID")
        if not isinstance(case.get("retrieval_warnings"), list) or not isinstance(case.get("retrieval_incomplete"), bool):
            _fail("PROFILE_MATRIX_INVALID")
        seen.add(requested)
        result.append(case)
    if seen != set(expected):
        _fail("PROFILE_MATRIX_INVALID")
    return result


def _validate_row(value: object, *, version: int, code: str) -> dict[str, object]:
    row = _exact(value, _ROW_KEYS, code)
    if row.get("row_id") != "row-1" or row.get("record_version") != version:
        _fail(code)
    if row.get("publication_status") != "unpublished":
        _fail("PUBLICATION_STATE_INVALID")
    return row


def _validate_template_hash(expected: object) -> None:
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        _fail("TEMPLATE_HASH_INVALID")
    try:
        compiler = TemplateCompiler(
            schema_validator=Draft202012SchemaAdapter(),
            source_loader=load_template_source,
        )
        compiled = compiler.compile_path(_TEMPLATE_PATH)
    except Exception:
        _fail("TEMPLATE_INVALID")
    if compiled.template_hash != expected:
        _fail("TEMPLATE_HASH_MISMATCH")


def verify_acceptance_directory(directory: str | Path) -> dict[str, object]:  # noqa: C901
    """Parse and independently verify exactly one six-file acceptance pack."""

    root = Path(directory)
    if not root.is_dir():
        _fail("ARTIFACT_DIRECTORY_INVALID")
    try:
        entries = tuple(root.iterdir())
    except OSError:
        _fail("ARTIFACT_DIRECTORY_INVALID")
    if any(entry.is_dir() for entry in entries) or {entry.name for entry in entries} != set(_ARTIFACTS):
        _fail("ARTIFACT_SET_INVALID")
    loaded = {name: _load(root / name) for name in _ARTIFACTS}
    context, _ = loaded["context.json"]
    run, _ = loaded["suggestion-run.json"]
    suggestion, _ = loaded["suggestion.json"]
    decision, _ = loaded["decision.json"]
    audit, _ = loaded["audit-summary.json"]
    summary, _summary_raw = loaded["acceptance-summary.json"]

    context = _exact(context, {"schema_version", "resource_type", "data"}, "CONTEXT_SHAPE_INVALID")
    _schema(context, _FMEA_SCHEMA_VERSION)
    if context.get("resource_type") != "review_context":
        _fail("CONTEXT_SHAPE_INVALID")
    context_data = _exact(context["data"], {"row", "row_hash", "retrieval", "evidence", "profile_cases"}, "CONTEXT_SHAPE_INVALID")
    row_before = _validate_row(context_data["row"], version=1, code="ROW_BEFORE_INVALID")
    if context_data["row_hash"] != _hash_json(row_before):
        _fail("ROW_HASH_MISMATCH")
    _validate_profiles(context_data["profile_cases"])
    retrieval = _exact(
        context_data["retrieval"],
        {"requested_profile", "resolved_profile", "evidence_types", "trace_id", "warnings", "incomplete"},
        "RETRIEVAL_INVALID",
    )
    if retrieval["requested_profile"] != "combined" or retrieval["resolved_profile"] != "combined":
        _fail("RETRIEVAL_INVALID")
    evidence = _exact(context_data["evidence"], {"pack_id", "pack_hash", "refs"}, "EVIDENCE_INVALID")
    if evidence["pack_id"] != "pack-1" or not isinstance(evidence["pack_hash"], str) or not _SHA256.fullmatch(evidence["pack_hash"]):
        _fail("EVIDENCE_INVALID")
    if not isinstance(evidence["refs"], list) or not evidence["refs"]:
        _fail("EVIDENCE_INVALID")
    for ref in evidence["refs"]:
        _exact(ref, {"evidence_id", "source_type", "quote"}, "EVIDENCE_INVALID")
        if not isinstance(ref["quote"], str) or len(ref["quote"]) > 4000:
            _fail("EVIDENCE_INVALID")

    run = _exact(run, {"schema_version", "data"}, "RUN_ENVELOPE_INVALID")
    _schema(run, SCHEMA_VERSION)
    run_data = _exact(run["data"], _RUN_KEYS, "RUN_INVALID")
    if run_data.get("status") != "succeeded" or run_data.get("source_record_version") != 1:
        _fail("RUN_INVALID")
    run_id = run_data.get("run_id")
    if not isinstance(run_id, str):
        _fail("RUN_INVALID")

    suggestion = _exact(suggestion, {"schema_version", "data"}, "SUGGESTION_ENVELOPE_INVALID")
    _schema(suggestion, SCHEMA_VERSION)
    suggestion_data = _exact(suggestion["data"], _SUGGESTION_KEYS, "SUGGESTION_INVALID")
    if (
        suggestion_data.get("run_id") != run_id
        or suggestion_data.get("source_record_version") != 1
        or suggestion_data.get("actor_type") != "model"
        or suggestion_data.get("applied") is not False
    ):
        _fail("SUGGESTION_INVALID")

    decision = _exact(decision, {"schema_version", "data"}, "DECISION_ENVELOPE_INVALID")
    _schema(decision, SCHEMA_VERSION)
    decision_data = _exact(decision["data"], _DECISION_KEYS, "DECISION_INVALID")
    row_after = _validate_row(decision_data["row"], version=2, code="ROW_AFTER_INVALID")
    if decision_data.get("previous_record_version") != 1 or decision_data.get("record_version") != 2:
        _fail("DECISION_INVALID")
    if decision_data.get("review_status") != "accepted" or decision_data.get("persisted") is not True:
        _fail("DECISION_INVALID")
    if decision_data.get("suggestion_id") != suggestion_data.get("suggestion_id"):
        _fail("DECISION_BINDING_INVALID")

    audit = _exact(audit, {"schema_version", "events", "counts", "decision_ids", "audit_event_ids"}, "AUDIT_SUMMARY_INVALID")
    _schema(audit, SCHEMA_VERSION)
    events = audit.get("events")
    if not isinstance(events, list) or len(events) != 3:
        _fail("AUDIT_SUMMARY_INVALID")
    event_ids: list[str] = []
    commands: set[str] = set()
    for event in events:
        event_data = _exact(event, _AUDIT_KEYS, "AUDIT_EVENT_INVALID")
        event_id = event_data.get("event_id")
        command = event_data.get("command")
        if not isinstance(event_id, str) or not isinstance(command, str):
            _fail("AUDIT_EVENT_INVALID")
        event_ids.append(event_id)
        commands.add(command)
        if command == "review.decision" and event_data.get("actor_type") != "human":
            _fail("MODEL_DECISION_FORBIDDEN")
        if command.startswith("publish.") or command.startswith("publication."):
            _fail("PUBLICATION_EVENT_FORBIDDEN")
    if {"review.suggestion.create", "review.suggestion.complete", "review.decision"} != commands:
        _fail("AUDIT_SUMMARY_INVALID")
    if audit.get("decision_ids") != [decision_data.get("decision_id")] or audit.get("audit_event_ids") != event_ids:
        _fail("AUDIT_BINDING_INVALID")
    counts = _exact(audit["counts"], {"audit_count", "model_decision_count", "publication_event_count"}, "AUDIT_SUMMARY_INVALID")
    if counts != {"audit_count": 3, "model_decision_count": 0, "publication_event_count": 0}:
        _fail("AUDIT_COUNT_INVALID")

    summary = _exact(
        summary,
        {"schema_version", "status", "counts", "profile_cases", "hashes", "safe_errors"},
        "SUMMARY_SHAPE_INVALID",
    )
    _schema(summary, SCHEMA_VERSION)
    if summary.get("status") != "passed" or summary.get("safe_errors") != []:
        _fail("SUMMARY_STATUS_INVALID")
    if summary.get("profile_cases") != context_data.get("profile_cases"):
        _fail("PROFILE_SUMMARY_MISMATCH")
    summary_counts = _exact(
        summary["counts"],
        {"row_count", "suggestion_count", "decision_count", "model_decision_count", "audit_count", "publication_event_count"},
        "SUMMARY_COUNTS_INVALID",
    )
    if summary_counts != {
        "row_count": 1,
        "suggestion_count": 1,
        "decision_count": 1,
        "model_decision_count": 0,
        "audit_count": 3,
        "publication_event_count": 0,
    }:
        _fail("SUMMARY_COUNTS_INVALID")
    hashes = _exact(summary["hashes"], {"schema_hash", "template_hash", "row_before_hash", "row_after_hash", "artifacts"}, "SUMMARY_HASHES_INVALID")
    if hashes.get("schema_hash") != _hash_json(SCHEMA_VERSION):
        _fail("SCHEMA_HASH_MISMATCH")
    _validate_template_hash(hashes.get("template_hash"))
    if hashes.get("row_before_hash") != _hash_json(row_before) or hashes.get("row_after_hash") != _hash_json(row_after):
        _fail("ROW_HASH_MISMATCH")
    artifact_hashes = _exact(hashes["artifacts"], set(_ARTIFACTS) - {"acceptance-summary.json"}, "SUMMARY_HASHES_INVALID")
    for name in artifact_hashes:
        if artifact_hashes[name] != _hash_bytes(loaded[name][1]):
            _fail("ARTIFACT_HASH_MISMATCH")
    return summary


def _latest(root: Path) -> Path:
    if not root.is_dir():
        _fail("ARTIFACT_DIRECTORY_INVALID")
    candidates = [path for path in root.iterdir() if path.is_dir()]
    if not candidates:
        _fail("ARTIFACT_DIRECTORY_INVALID")
    return max(candidates, key=lambda path: path.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--directory")
    args = parser.parse_args(argv)
    try:
        if bool(args.latest) == (args.directory is not None):
            _fail("CLI_USAGE_INVALID")
        directory = _latest(ROOT / ".local" / "fmea-review-acceptance") if args.latest else Path(args.directory)
        summary = verify_acceptance_directory(directory)
        sys.stdout.write(json.dumps({"status": "passed", "schema_version": summary["schema_version"]}, separators=(",", ":")) + "\n")
    except Exception as exc:
        code = exc.code if isinstance(exc, AcceptanceVerificationError) else "VERIFIER_FAILED"
        sys.stdout.write(json.dumps({"status": "failed", "error": {"code": code}}, separators=(",", ":")) + "\n")
        return 2
    else:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SCHEMA_VERSION", "AcceptanceVerificationError", "main", "verify_acceptance_directory"]
