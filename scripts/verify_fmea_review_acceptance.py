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
_PROFILE_CASE_KEYS = {
    "case_id", "requested_profile", "resolved_profile", "evidence_types", "retrieval_warnings",
    "retrieval_incomplete", "row", "source", "evidence_pack", "model_payload", "decision", "execution",
}
_SOURCE_KEYS = {
    "row_id", "source_record_version", "candidate_id", "item_label", "function_label", "template_id",
    "template_version", "profile_id", "profile_version", "generation_run_id", "requested_evidence_profile",
    "resolved_evidence_profile", "evidence_types", "trace_id", "retrieval_warnings", "retrieval_incomplete",
    "field_claim_statuses", "source_hash",
}
_PACK_KEYS = {"pack_id", "workspace_id", "acl_scope", "versions", "refs", "pack_hash", "created_at", "expires_at"}
_REF_KEYS = {
    "evidence_id", "workspace_id", "document_id", "document_version", "content_hash", "locator", "quote",
    "normalized_quote", "evidence_hash", "acl_scope", "source_type", "source_trust", "is_primary",
    "created_at", "expires_at",
}
_MODEL_PAYLOAD_KEYS = {
    "recommended_action", "field_findings", "proposed_edits", "evidence_requests", "missing_evidence",
    "conflicts", "rationale",
}
_DECISION_INPUT_KEYS = {"action", "reason_code", "reason", "edits", "evidence_requests", "unresolved_acknowledgements"}
_EXECUTION_KEYS = {
    "status", "requested_profile", "resolved_profile", "evidence_types", "template_id", "template_version",
    "template_hash", "row_hash", "row_after_hash", "source_hash", "evidence_pack_hash", "model_payload_hash",
    "run_id", "suggestion_id", "decision_id", "audit_event_ids",
}
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


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _entity_hash(value: object) -> str:
    return "sha256:" + sha256(_canonical_json(value)).hexdigest()


def _evidence_pack_hash(pack: dict[str, object]) -> str:
    refs = pack.get("refs")
    if not isinstance(refs, list):
        _fail("EVIDENCE_PACK_INVALID")
    evidence_content = []
    for ref in refs:
        item = _exact(ref, _REF_KEYS, "EVIDENCE_REF_INVALID")
        evidence_content.append(
            {
                "evidence_id": item["evidence_id"],
                "evidence_hash": item["evidence_hash"],
                "locator": item["locator"],
            }
        )
    payload = json.dumps(sorted(evidence_content, key=lambda item: str(item["evidence_id"])), sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _validate_profile_source(
    value: object,
    row: dict[str, object],
    requested: str,
    resolved: str,
    types: list[str],
) -> dict[str, object]:
    source = _exact(value, _SOURCE_KEYS, "PROFILE_SOURCE_INVALID")
    if (
        source.get("row_id") != row.get("row_id")
        or source.get("source_record_version") != 1
        or source.get("requested_evidence_profile") != requested
        or source.get("resolved_evidence_profile") != resolved
        or source.get("evidence_types") != types
        or source.get("template_id") != "fmea-row-review"
        or source.get("template_version") != "1.0.0"
    ):
        _fail("PROFILE_SOURCE_INVALID")
    source_hash = source.get("source_hash")
    source_without_hash = {key: value for key, value in source.items() if key != "source_hash"}
    if source_hash != _hash_bytes(_canonical_json(source_without_hash)):
        _fail("SOURCE_HASH_MISMATCH")
    return source


def _validate_profile_execution(
    value: object,
    case: dict[str, object],
    row: dict[str, object],
    source: dict[str, object],
    pack: dict[str, object],
    requested: str,
    resolved: str,
    types: list[str],
) -> dict[str, object]:
    execution = _exact(value, _EXECUTION_KEYS, "PROFILE_EXECUTION_INVALID")
    payload = _exact(case.get("model_payload"), _MODEL_PAYLOAD_KEYS, "MODEL_PAYLOAD_INVALID")
    if (
        execution.get("status") != "succeeded"
        or execution.get("requested_profile") != requested
        or execution.get("resolved_profile") != resolved
        or execution.get("evidence_types") != types
        or execution.get("template_id") != "fmea-row-review"
        or execution.get("template_version") != "1.0.0"
        or execution.get("source_hash") != source.get("source_hash")
        or execution.get("evidence_pack_hash") != pack["pack_hash"]
        or execution.get("row_hash") != _hash_json(row)
        or execution.get("model_payload_hash") != _hash_json(payload)
    ):
        _fail("PROFILE_EXECUTION_INVALID")
    if not isinstance(execution.get("template_hash"), str) or not re.fullmatch(r"[0-9a-f]{64}", execution["template_hash"]):
        _fail("PROFILE_EXECUTION_INVALID")
    if not isinstance(execution.get("row_after_hash"), str) or not _SHA256.fullmatch(execution["row_after_hash"]):
        _fail("PROFILE_EXECUTION_INVALID")
    if not isinstance(execution.get("audit_event_ids"), list) or len(execution["audit_event_ids"]) != 3:
        _fail("PROFILE_EXECUTION_INVALID")
    if (
        not isinstance(execution.get("run_id"), str)
        or not isinstance(execution.get("suggestion_id"), str)
        or not isinstance(execution.get("decision_id"), str)
    ):
        _fail("PROFILE_EXECUTION_INVALID")
    return execution


def _validate_profile_case(item: object) -> dict[str, object]:
    case = _exact(item, _PROFILE_CASE_KEYS, "PROFILE_MATRIX_INVALID")
    requested = case.get("requested_profile")
    if not isinstance(requested, str):
        _fail("PROFILE_MATRIX_INVALID")
    expected = {name: (resolved, types) for name, resolved, types in _PROFILE_CASES}
    if requested not in expected:
        _fail("PROFILE_MATRIX_INVALID")
    resolved, types = expected[requested]
    if case.get("resolved_profile") != resolved or case.get("evidence_types") != types:
        _fail("PROFILE_MATRIX_INVALID")
    if not isinstance(case.get("retrieval_warnings"), list) or not isinstance(case.get("retrieval_incomplete"), bool):
        _fail("PROFILE_MATRIX_INVALID")
    row = _validate_row(case.get("row"), version=1, code="PROFILE_ROW_INVALID")
    source = _validate_profile_source(case.get("source"), row, requested, resolved, types)
    pack = _exact(case.get("evidence_pack"), _PACK_KEYS, "EVIDENCE_PACK_INVALID")
    refs = pack.get("refs")
    if not isinstance(refs, list) or not refs or pack.get("pack_id") != row.get("evidence_pack_id"):
        _fail("EVIDENCE_PACK_INVALID")
    if not isinstance(pack.get("pack_hash"), str) or not re.fullmatch(r"[0-9a-f]{64}", pack["pack_hash"]):
        _fail("EVIDENCE_PACK_INVALID")
    if _evidence_pack_hash(pack) != pack["pack_hash"]:
        _fail("EVIDENCE_PACK_HASH_MISMATCH")
    _exact(case.get("decision"), _DECISION_INPUT_KEYS, "DECISION_INPUT_INVALID")
    _validate_profile_execution(case.get("execution"), case, row, source, pack, requested, resolved, types)
    return case


def _validate_profiles(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) != len(_PROFILE_CASES):
        _fail("PROFILE_MATRIX_INVALID")
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in value:
        case = _validate_profile_case(item)
        requested = cast(str, case.get("requested_profile"))
        if requested in seen:
            _fail("PROFILE_MATRIX_INVALID")
        seen.add(requested)
        result.append(case)
    if seen != {requested for requested, _, _ in _PROFILE_CASES}:
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
    profile_cases = _validate_profiles(context_data["profile_cases"])
    combined_case = next(case for case in profile_cases if case["requested_profile"] == "combined")
    combined_pack = cast(dict[str, object], combined_case["evidence_pack"])
    retrieval = _exact(
        context_data["retrieval"],
        {"requested_profile", "resolved_profile", "evidence_types", "trace_id", "warnings", "incomplete"},
        "RETRIEVAL_INVALID",
    )
    if retrieval["requested_profile"] != "combined" or retrieval["resolved_profile"] != "combined":
        _fail("RETRIEVAL_INVALID")
    evidence = _exact(context_data["evidence"], {"pack_id", "pack_hash", "refs"}, "EVIDENCE_INVALID")
    if (
        evidence["pack_id"] != combined_pack["pack_id"]
        or evidence["pack_hash"] != "sha256:" + str(combined_pack["pack_hash"])
        or not isinstance(evidence["pack_hash"], str)
        or not _SHA256.fullmatch(evidence["pack_hash"])
    ):
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
    combined_execution = cast(dict[str, object], combined_case["execution"])
    if (
        run_data.get("status") != "succeeded"
        or run_data.get("source_record_version") != 1
        or run_data.get("run_id") != combined_execution.get("run_id")
        or run_data.get("row_id") != combined_case.get("row")["row_id"]
    ):
        _fail("RUN_INVALID")
    if (
        run_data.get("suggestion_id") != combined_execution.get("suggestion_id")
        or run_data.get("source_record_version") != combined_case.get("source")["source_record_version"]
    ):
        _fail("RUN_SUGGESTION_BINDING_INVALID")
    run_id = run_data.get("run_id")
    if not isinstance(run_id, str):
        _fail("RUN_INVALID")

    suggestion = _exact(suggestion, {"schema_version", "data"}, "SUGGESTION_ENVELOPE_INVALID")
    _schema(suggestion, SCHEMA_VERSION)
    suggestion_data = _exact(suggestion["data"], _SUGGESTION_KEYS, "SUGGESTION_INVALID")
    model_manifest = suggestion_data.get("model_manifest")
    if not isinstance(model_manifest, dict):
        _fail("SUGGESTION_BINDING_INVALID")
    if (
        suggestion_data.get("run_id") != run_id
        or suggestion_data.get("suggestion_id") != run_data.get("suggestion_id")
        or suggestion_data.get("row_id") != run_data.get("row_id")
        or suggestion_data.get("source_record_version") != 1
        or suggestion_data.get("actor_type") != "model"
        or suggestion_data.get("applied") is not False
        or model_manifest.get("template_id") != combined_execution.get("template_id")
        or model_manifest.get("template_version") != combined_execution.get("template_version")
    ):
        _fail("SUGGESTION_BINDING_INVALID")

    decision = _exact(decision, {"schema_version", "data"}, "DECISION_ENVELOPE_INVALID")
    _schema(decision, SCHEMA_VERSION)
    decision_data = _exact(decision["data"], _DECISION_KEYS, "DECISION_INVALID")
    row_after = _validate_row(decision_data["row"], version=2, code="ROW_AFTER_INVALID")
    if (
        decision_data.get("previous_record_version") != 1
        or decision_data.get("record_version") != 2
        or row_after.get("row_id") != run_data.get("row_id")
        or row_after.get("record_version") != decision_data.get("record_version")
    ):
        _fail("DECISION_VERSION_BINDING_INVALID")
    if decision_data.get("review_status") != "accepted" or decision_data.get("persisted") is not True:
        _fail("DECISION_INVALID")
    if decision_data.get("suggestion_id") != suggestion_data.get("suggestion_id"):
        _fail("DECISION_BINDING_INVALID")
    if decision_data.get("audit_event_id") is None:
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
    decision_event = next(event for event in events if event.get("command") == "review.decision")
    complete_event = next(event for event in events if event.get("command") == "review.suggestion.complete")
    if (
        decision_event.get("decision_id") != decision_data.get("decision_id")
        or decision_event.get("suggestion_id") != suggestion_data.get("suggestion_id")
        or decision_event.get("row_id") != row_after.get("row_id")
        or decision_event.get("expected_record_version") != 1
        or decision_event.get("applied_record_version") != 2
        or decision_event.get("before_hash") != _entity_hash(row_before)
        or decision_event.get("after_hash") != _entity_hash(row_after)
        or decision_data.get("audit_event_id") != decision_event.get("event_id")
        or complete_event.get("suggestion_id") != suggestion_data.get("suggestion_id")
        or complete_event.get("row_id") != suggestion_data.get("row_id")
    ):
        _fail("AUDIT_HASH_BINDING_INVALID")
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
    if any(cast(dict[str, object], case["execution"]).get("template_hash") != hashes.get("template_hash") for case in profile_cases):
        _fail("TEMPLATE_HASH_MISMATCH")
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
