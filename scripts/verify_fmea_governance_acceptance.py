"""Independent verifier for Phase 3 governance acceptance artifacts.

This module intentionally has no import path to the acceptance runner.  It
reads raw bytes, applies its own bounded path walk and strict JSON parser, and
recomputes the artifact identities before accepting a directory.
"""

# Verification intentionally keeps the complete invariant matrix in one
# fail-closed boundary; it remains auditable as a single independent gate.
# ruff: noqa: C901, E402, TRY301

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core_domain.fmea.governance import canonical_hash, canonical_json_bytes

SCHEMA_VERSION = "graphrag.fmea.governance.acceptance.v1"
ARTIFACT_NAMES = (
    "revisions.json",
    "readiness.json",
    "approval-submissions.json",
    "approvals.json",
    "approval-withdrawals.json",
    "manifests.json",
    "publications.json",
    "snapshots.json",
    "publication-withdrawals.json",
    "supersessions.json",
    "audits.json",
    "outbox.json",
    "idempotency.json",
    "provenance-profiles.json",
    "lifecycle.json",
    "acceptance-summary.json",
)
_RESOURCE_TYPES = {
    "revisions.json": "revisions",
    "readiness.json": "readiness",
    "approval-submissions.json": "approval_submissions",
    "approvals.json": "approvals",
    "approval-withdrawals.json": "approval_withdrawals",
    "manifests.json": "manifests",
    "publications.json": "publications",
    "snapshots.json": "snapshots",
    "publication-withdrawals.json": "publication_withdrawals",
    "supersessions.json": "supersessions",
    "audits.json": "audits",
    "outbox.json": "outbox",
    "idempotency.json": "idempotency",
    "provenance-profiles.json": "provenance_profiles",
    "lifecycle.json": "lifecycle",
}
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_TOTAL_BYTES = 64 * 1024 * 1024
_HASH = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_ARTIFACT_ID = re.compile(r"^acceptance-[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_SERVER_ID_PREFIXES = (
    "revision-",
    "submission-",
    "approval-",
    "approval-withdrawal-",
    "publication-",
    "publication-withdrawal-",
    "manifest-",
    "supersession-",
    "audit-",
    "outbox-",
)
_PRIVATE_KEY_MARKERS = (
    b'"access_token"',
    b'"api_key"',
    b'"authorization"',
    b'"credential',
    b'"password"',
    b'"private_key"',
    b'"private_path"',
    b'"prompt"',
    b'"provider_error"',
    b'"provider_output"',
    b'"model_output"',
    b'"raw_model_output"',
    b'"raw_output"',
    b'"secret"',
    b'"source_url"',
    b'"traceback"',
    b'file://',
    b'http://',
    b'https://',
    b'/users/',
    b'/home/',
    b'\\users\\',
)


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    artifact_id: str
    error_code: str | None


class _VerificationFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


def _safe_component_walk(path: Path) -> Path:
    candidate = Path(path).absolute()
    current = Path(candidate.anchor)
    for component in candidate.parts[1:]:
        current /= component
        try:
            info = current.lstat()
        except FileNotFoundError:
            raise _VerificationFailure("FMEA_ARTIFACT_PATH_INVALID") from None
        attributes = getattr(info, "st_file_attributes", 0)
        if stat.S_ISLNK(info.st_mode) or attributes & 0x400 or not stat.S_ISDIR(info.st_mode):
            raise _VerificationFailure("FMEA_ARTIFACT_PATH_INVALID")
    return candidate


def _safe_artifact_directory(directory: str | Path) -> Path:
    candidate = _safe_component_walk(Path(directory))
    if not candidate.is_dir():
        raise _VerificationFailure("FMEA_ARTIFACT_PATH_INVALID")
    return candidate


def _strict_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _VerificationFailure("FMEA_DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise _VerificationFailure("FMEA_NONFINITE_NUMBER")


def _parse(raw: bytes) -> tuple[object, bool]:
    if len(raw) > _MAX_FILE_BYTES:
        raise _VerificationFailure("FMEA_ARTIFACT_BOUNDS")
    try:
        text = raw.removesuffix(b"\n").decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_constant,
        )
    except _VerificationFailure:
        raise
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
        raise _VerificationFailure("FMEA_INVALID_JSON") from None
    return value, raw.endswith(b"\n") and raw == canonical_json_bytes(value) + b"\n"


def _mapping(value: object, code: str = "FMEA_ARTIFACT_SCHEMA_INVALID") -> dict[str, object]:
    if not isinstance(value, dict):
        raise _VerificationFailure(code)
    return value


def _items(payloads: dict[str, dict[str, object]], name: str) -> list[dict[str, object]]:
    payload = payloads[name]
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("resource_type") != _RESOURCE_TYPES[name]:
        raise _VerificationFailure("FMEA_ARTIFACT_SCHEMA_INVALID")
    values = payload.get("items")
    if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
        raise _VerificationFailure("FMEA_ARTIFACT_SCHEMA_INVALID")
    return values


def _normal_hash(value: object) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise _VerificationFailure("FMEA_HASH_INVALID")
    return value.removeprefix("sha256:")


def _server_id(value: object) -> str:
    if not isinstance(value, str) or not value.startswith(_SERVER_ID_PREFIXES):
        raise _VerificationFailure("FMEA_SERVER_ID_INVALID")
    return value


def _verify_content_hashes(payloads: dict[str, dict[str, object]]) -> None:
    for item in _items(payloads, "revisions.json"):
        supplied = _normal_hash(item.get("revision_hash"))
        body = {key: value for key, value in item.items() if key not in {"revision_hash", "created_at"}}
        if canonical_hash(body, max_array_items=10_000) != supplied:
            raise _VerificationFailure("FMEA_REVISION_HASH_MISMATCH")
    for item in _items(payloads, "snapshots.json"):
        supplied = _normal_hash(item.get("snapshot_hash"))
        body = {key: value for key, value in item.items() if key != "snapshot_hash"}
        if canonical_hash(body, max_array_items=10_000) != supplied:
            raise _VerificationFailure("FMEA_SNAPSHOT_HASH_MISMATCH")
    for item in _items(payloads, "manifests.json"):
        supplied = _normal_hash(item.get("manifest_hash"))
        body = {
            key: item.get(key)
            for key in (
                "manifest_id",
                "revision_id",
                "revision_hash",
                "approval_id",
                "snapshot_id",
                "snapshot_hash",
                "version_manifest_hash",
                "previous_audit_chain_head",
                "export_eligible",
            )
        }
        if canonical_hash(body, prefixed=True).removeprefix("sha256:") != supplied:
            raise _VerificationFailure("FMEA_MANIFEST_HASH_MISMATCH")


def _verify_bindings(payloads: dict[str, dict[str, object]], summary: dict[str, object]) -> None:
    revisions = _items(payloads, "revisions.json")
    submissions = _items(payloads, "approval-submissions.json")
    approvals = _items(payloads, "approvals.json")
    manifests = _items(payloads, "manifests.json")
    publications = _items(payloads, "publications.json")
    snapshots = _items(payloads, "snapshots.json")
    withdrawals = _items(payloads, "publication-withdrawals.json")
    supersessions = _items(payloads, "supersessions.json")
    lifecycle = _items(payloads, "lifecycle.json")
    if len(revisions) != 2 or len(publications) != 2 or len(snapshots) != 2:
        raise _VerificationFailure("FMEA_LIFECYCLE_INCOMPLETE")
    revisions_by_id = {item.get("revision_id"): item for item in revisions}
    if len(revisions_by_id) != len(revisions):
        raise _VerificationFailure("FMEA_DUPLICATE_ID")
    child = next((item for item in revisions if item.get("parent_revision_id") is not None), None)
    if child is None or child.get("parent_revision_id") not in revisions_by_id:
        raise _VerificationFailure("FMEA_PARENT_BINDING_INVALID")
    for revision in revisions:
        _server_id(revision.get("revision_id"))
        if revision.get("analysis_record_version") != 1:
            raise _VerificationFailure("FMEA_ETAG_INVALID")
    if len(submissions) != 2 or len(approvals) != 2 or len(manifests) != 2:
        raise _VerificationFailure("FMEA_LIFECYCLE_INCOMPLETE")
    approval_ids = {item.get("approval_id") for item in approvals}
    for withdrawal in _items(payloads, "approval-withdrawals.json"):
        _server_id(withdrawal.get("withdrawal_id"))
        if withdrawal.get("approval_id") not in approval_ids:
            raise _VerificationFailure("FMEA_APPROVAL_BINDING_INVALID")
    for submission in submissions:
        if (
            submission.get("status") != "pending"
            or submission.get("revision_id") not in revisions_by_id
            or submission.get("record_version") != 1
        ):
            raise _VerificationFailure("FMEA_APPROVAL_BINDING_INVALID")
        _server_id(submission.get("submission_id"))
    submission_ids = {item.get("submission_id") for item in submissions}
    for approval in approvals:
        if (
            approval.get("status") != "approved"
            or approval.get("submission_id") not in submission_ids
            or approval.get("record_version") != 2
        ):
            raise _VerificationFailure("FMEA_APPROVAL_BINDING_INVALID")
        _server_id(approval.get("approval_id"))
        matching = next(item for item in submissions if item.get("submission_id") == approval.get("submission_id"))
        if approval.get("revision_id") != matching.get("revision_id") or approval.get("approver_actor_id") == matching.get("submitter_actor_id"):
            raise _VerificationFailure("FMEA_ACTOR_SEPARATION_INVALID")
    for manifest in manifests:
        if manifest.get("revision_id") not in revisions_by_id or manifest.get("approval_id") not in approval_ids:
            raise _VerificationFailure("FMEA_MANIFEST_BINDING_INVALID")
        _server_id(manifest.get("manifest_id"))
    publication_ids = {item.get("publication_id") for item in publications}
    for publication in publications:
        _server_id(publication.get("publication_id"))
        if publication.get("record_version") != 1:
            raise _VerificationFailure("FMEA_ETAG_INVALID")
        manifest = next((item for item in manifests if item.get("manifest_id") == publication.get("manifest_id")), None)
        snapshot = next((item for item in snapshots if item.get("snapshot_id") == publication.get("snapshot_id")), None)
        if manifest is None or snapshot is None:
            raise _VerificationFailure("FMEA_PUBLICATION_BINDING_INVALID")
        if publication.get("revision_hash") != manifest.get("revision_hash") or publication.get("snapshot_hash") != snapshot.get("snapshot_hash"):
            raise _VerificationFailure("FMEA_PUBLICATION_BINDING_INVALID")
    for withdrawal in withdrawals:
        if withdrawal.get("publication_id") not in publication_ids:
            raise _VerificationFailure("FMEA_WITHDRAWAL_BINDING_INVALID")
        _server_id(withdrawal.get("withdrawal_id"))
    if len(supersessions) != 1 or supersessions[0].get("old_publication_id") not in publication_ids or supersessions[0].get("new_publication_id") not in publication_ids:
        raise _VerificationFailure("FMEA_SUPERSESSION_BINDING_INVALID")
    _server_id(supersessions[0].get("supersession_id"))
    if supersessions[0].get("old_publication_id") == supersessions[0].get("new_publication_id"):
        raise _VerificationFailure("FMEA_SUPERSESSION_CYCLE")
    statuses = {item.get("effective_status") for item in lifecycle}
    if statuses != {"superseded", "withdrawn"}:
        raise _VerificationFailure("FMEA_LIFECYCLE_STATUS_INVALID")
    audits = _items(payloads, "audits.json")
    expected_order = [
        "fmea.revision.assemble",
        "fmea.approval.submit",
        "fmea.approval.decide",
        "fmea.publication.publish",
        "fmea.revision.assemble",
        "fmea.approval.submit",
        "fmea.approval.decide",
        "fmea.publication.publish",
        "fmea.publication.supersede",
        "fmea.approval.withdraw",
        "fmea.publication.withdraw",
    ]
    if [item.get("command") for item in audits] != expected_order:
        raise _VerificationFailure("FMEA_AUDIT_ORDER_INVALID")
    for item in audits:
        _server_id(item.get("event_id"))
        if item.get("actor_type") != "human":
            raise _VerificationFailure("FMEA_NON_HUMAN_AUTHORITY")
        event = item.get("event")
        if (
            not isinstance(event, dict)
            or event.get("actor_type") != "human"
            or event.get("canonical_payload_hash") != item.get("canonical_payload_hash")
            or item.get("event_hash") != canonical_hash(event, prefixed=True)
            or event.get("model_manifest") is not None
        ):
            raise _VerificationFailure("FMEA_AUDIT_HASH_MISMATCH")
    if summary.get("approval_actor_type") != "human" or summary.get("publisher_actor_type") != "human" or summary.get("model_publication_count") != 0:
        raise _VerificationFailure("FMEA_ACTOR_SEPARATION_INVALID")
    if summary.get("replay_checks") != {"approve": True, "publish": True, "withdraw_publication": True}:
        raise _VerificationFailure("FMEA_REPLAY_INCOMPLETE")
    if summary.get("stale_child_approval_code") != "FMEA_GOVERNANCE_APPROVAL_STALE":
        raise _VerificationFailure("FMEA_APPROVAL_STALENESS_UNPROVEN")
    if summary.get("withdrawn_publication_retained") is not True:
        raise _VerificationFailure("FMEA_IMMUTABLE_PAYLOAD_LOST")
    expected_profiles = {
        "rag_only": ["text"],
        "graphrag_only": ["graph", "community"],
        "combined": ["text", "graph", "community"],
        "auto": ["text", "graph", "community"],
    }
    if summary.get("profile_cases") != expected_profiles or summary.get("retrieval_call_count") != 0:
        raise _VerificationFailure("FMEA_PROVENANCE_INVALID")
    expected_records = {
        "rag_only": {"requested_profile": "rag_only", "resolved_profile": "rag_only", "evidence_types": ["text"], "source_counts": [["text", 1]], "warnings": []},
        "graphrag_only": {"requested_profile": "graphrag_only", "resolved_profile": "graphrag_only", "evidence_types": ["graph", "community"], "source_counts": [["community", 1], ["graph", 1]], "warnings": []},
        "combined": {"requested_profile": "combined", "resolved_profile": "combined", "evidence_types": ["text", "graph", "community"], "source_counts": [["community", 1], ["graph", 1], ["text", 1]], "warnings": []},
        "auto": {"requested_profile": "auto", "resolved_profile": "combined", "evidence_types": ["text", "graph", "community"], "source_counts": [["community", 1], ["graph", 1], ["text", 1]], "warnings": []},
    }
    if summary.get("profile_records") != expected_records:
        raise _VerificationFailure("FMEA_PROVENANCE_INVALID")
    profile_records = _items(payloads, "provenance-profiles.json")
    if len(profile_records) != 4:
        raise _VerificationFailure("FMEA_PROVENANCE_INVALID")
    for record in profile_records:
        requested = record.get("requested_profile")
        expected_resolved = "combined" if requested == "auto" else requested
        if (
            requested not in expected_profiles
            or record.get("resolved_profile") != expected_resolved
            or record.get("evidence_types") != expected_profiles[requested]
            or record.get("source_counts") != expected_records[requested]["source_counts"]
            or record.get("warnings") != []
        ):
            raise _VerificationFailure("FMEA_PROVENANCE_INVALID")
    for item in _items(payloads, "outbox.json"):
        _server_id(item.get("event_id"))
        payload = item.get("payload")
        if not isinstance(payload, dict) or _normal_hash(item.get("payload_hash")) != _normal_hash(canonical_hash(payload, prefixed=True)):
            raise _VerificationFailure("FMEA_OUTBOX_HASH_MISMATCH")
    for item in _items(payloads, "idempotency.json"):
        if item.get("state") != "completed" or not item.get("scope_key") or not isinstance(item.get("response"), dict):
            raise _VerificationFailure("FMEA_IDEMPOTENCY_INVALID")
        resource_id = item.get("resource_id")
        if resource_id is not None:
            _server_id(resource_id)


def verify_acceptance_directory(directory: str | Path) -> VerificationResult:
    artifact_id = ""
    try:
        root = _safe_artifact_directory(directory)
        names = {item.name for item in root.iterdir()}
        if names != set(ARTIFACT_NAMES):
            raise _VerificationFailure("FMEA_ARTIFACT_SET_INVALID")
        raw_values: dict[str, bytes] = {}
        payloads: dict[str, dict[str, object]] = {}
        canonical_flags: dict[str, bool] = {}
        total = 0
        for name in ARTIFACT_NAMES:
            path = root / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise _VerificationFailure("FMEA_ARTIFACT_PATH_INVALID")
            raw = path.read_bytes()
            total += len(raw)
            if total > _MAX_TOTAL_BYTES:
                raise _VerificationFailure("FMEA_ARTIFACT_BOUNDS")
            lowered = raw.lower()
            if any(marker in lowered for marker in _PRIVATE_KEY_MARKERS) or re.search(rb"[a-z]:\\\\|\\\\[a-z]", lowered):
                raise _VerificationFailure("FMEA_PRIVATE_MARKER")
            value, is_canonical = _parse(raw)
            payload = _mapping(value)
            raw_values[name] = raw
            payloads[name] = payload
            canonical_flags[name] = is_canonical
        summary = payloads["acceptance-summary.json"]
        if summary.get("schema_version") != SCHEMA_VERSION or summary.get("resource_type") != "summary":
            raise _VerificationFailure("FMEA_ARTIFACT_SCHEMA_INVALID")
        artifact_id = str(summary.get("artifact_id", ""))
        is_temp_directory = root.name.startswith(f".acceptance-{artifact_id}.") and root.name.endswith(".tmp")
        if _ARTIFACT_ID.fullmatch(artifact_id) is None or (root.name != artifact_id and not is_temp_directory):
            raise _VerificationFailure("FMEA_ARTIFACT_ID_INVALID")
        for name in ARTIFACT_NAMES[:-1]:
            _items(payloads, name)
        _verify_content_hashes(payloads)
        _verify_bindings(payloads, summary)
        hashes = summary.get("artifact_hashes")
        if not isinstance(hashes, dict) or set(hashes) != set(ARTIFACT_NAMES[:-1]):
            raise _VerificationFailure("FMEA_ARTIFACT_HASHES_INVALID")
        for name in ARTIFACT_NAMES[:-1]:
            if hashes.get(name) != "sha256:" + sha256(raw_values[name]).hexdigest():
                raise _VerificationFailure("FMEA_ARTIFACT_HASHES_INVALID")
        if not all(canonical_flags.values()):
            raise _VerificationFailure("FMEA_NON_CANONICAL_JSON")
        return VerificationResult(True, artifact_id, None)
    except _VerificationFailure as failure:
        return VerificationResult(False, artifact_id, failure.code)
    except Exception:
        return VerificationResult(False, artifact_id, "FMEA_ARTIFACT_VERIFICATION_FAILED")


def verify(directory: str | Path) -> VerificationResult:
    return verify_acceptance_directory(directory)


def verify_latest(output_root: str | Path) -> VerificationResult:
    try:
        root = _safe_artifact_directory(output_root)
        latest = root / "latest"
        info = latest.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise _VerificationFailure("FMEA_LATEST_POINTER_INVALID")
        raw = latest.read_bytes()
        if len(raw) > 256 or not raw.endswith(b"\n"):
            raise _VerificationFailure("FMEA_LATEST_POINTER_INVALID")
        artifact_id = raw[:-1].decode("ascii")
        if _ARTIFACT_ID.fullmatch(artifact_id) is None:
            raise _VerificationFailure("FMEA_LATEST_POINTER_INVALID")
        target = root / artifact_id
        if target.parent != root:
            raise _VerificationFailure("FMEA_LATEST_POINTER_INVALID")
        return verify_acceptance_directory(target)
    except _VerificationFailure as failure:
        return VerificationResult(False, "", failure.code)
    except Exception:
        return VerificationResult(False, "", "FMEA_LATEST_POINTER_INVALID")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 3 FMEA governance acceptance artifacts")
    parser.add_argument("directory", type=Path, nargs="?")
    parser.add_argument(
        "--latest",
        nargs="?",
        const=_REPO_ROOT / ".local" / "fmea-governance-acceptance",
        type=Path,
        default=None,
    )
    args = parser.parse_args(argv)
    result = verify_latest(args.latest) if args.latest is not None else verify(args.directory) if args.directory is not None else VerificationResult(False, "", "FMEA_ARTIFACT_PATH_INVALID")
    print(json.dumps({"status": "passed" if result.passed else "failed", "artifact_id": result.artifact_id, "error_code": result.error_code}, separators=(",", ":")))
    return 0 if result.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["VerificationResult", "verify", "verify_acceptance_directory", "verify_latest"]
