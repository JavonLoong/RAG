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
PUBLICATION_BODY_SCHEMA_VERSION = "graphrag.fmea.body.v1"
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
    "authority-denials.json",
    "replay-evidence.json",
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
    "authority-denials.json": "authority_denials",
    "replay-evidence.json": "replay_evidence",
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
    "snapshot:",
    "eligibility-",
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
    b'"traceback"',
    b"file://",
)
_REPARSE_POINT = 0x400
_URL_TOKEN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_DRIVE_ABSOLUTE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]+")
_UNC_ABSOLUTE = re.compile(r"(?<![A-Za-z0-9])(?:\\\\|//)(?=[^\\/\s]+[\\/][^\\/\s]+)")
_WINDOWS_ROOT_RELATIVE = re.compile(r"(?<![A-Za-z0-9/\\])\\(?=[^\\/\s])")
_POSIX_ABSOLUTE = re.compile(r"(?<![A-Za-z0-9])/(?![/\s])")
_TRAVERSAL = re.compile(r"(?:^|[\\/])\.\.(?:$|[\\/])")


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
        if stat.S_ISLNK(info.st_mode) or attributes & _REPARSE_POINT or not stat.S_ISDIR(info.st_mode):
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


def _same_hash(left: object, right: object) -> bool:
    return _normal_hash(left) == _normal_hash(right)


def _contains_forbidden_local_path(value: str) -> bool:
    masked = _URL_TOKEN.sub(lambda match: " " * len(match.group(0)), value)
    return any(
        pattern.search(masked) is not None
        for pattern in (_DRIVE_ABSOLUTE, _UNC_ABSOLUTE, _WINDOWS_ROOT_RELATIVE, _POSIX_ABSOLUTE, _TRAVERSAL)
    )


def _reject_decoded_private_paths(value: object) -> None:
    if isinstance(value, str) and _contains_forbidden_local_path(value):
        raise _VerificationFailure("FMEA_PRIVATE_MARKER")
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and _contains_forbidden_local_path(key):
                raise _VerificationFailure("FMEA_PRIVATE_MARKER")
            _reject_decoded_private_paths(item)
    elif isinstance(value, list):
        for item in value:
            _reject_decoded_private_paths(item)


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


def _exact_map(payloads: dict[str, dict[str, object]], name: str, count: int, key: str) -> dict[str, dict[str, object]]:
    values = _items(payloads, name)
    if len(values) != count:
        raise _VerificationFailure("FMEA_AUTHORITY_EVIDENCE_INCOMPLETE")
    result: dict[str, dict[str, object]] = {}
    for item in values:
        identifier = item.get(key)
        if not isinstance(identifier, str) or identifier in result:
            raise _VerificationFailure("FMEA_DUPLICATE_ID")
        result[identifier] = item
    return result


def _scope(item: dict[str, object], workspace_id: str, analysis_id: str) -> None:
    if item.get("workspace_id") != workspace_id:
        raise _VerificationFailure("FMEA_SCOPE_BINDING_INVALID")
    if "analysis_id" in item and item.get("analysis_id") != analysis_id:
        raise _VerificationFailure("FMEA_SCOPE_BINDING_INVALID")


def _export_hash(value: object) -> str:
    return _normal_hash(value)


def _identity(value: object) -> list[object]:
    if not isinstance(value, list) or len(value) != 3 or any(not isinstance(item, str) for item in value):
        raise _VerificationFailure("FMEA_IDENTITY_BINDING_INVALID")
    _normal_hash(value[2])
    return [value[0], value[1], _export_hash(value[2])]


def _expected_snapshot_version_manifest(
    revision: dict[str, object], *, body_schema_version: str | None
) -> dict[str, object]:
    expected = {
        "analysis_hash": _export_hash(revision.get("analysis_hash")),
        "domain_pack_identity": _identity(revision.get("domain_pack_identity")),
        "template_identities": [_identity(item) for item in revision.get("template_identities", [])],
        "scoring_rule_identities": [_identity(item) for item in revision.get("scoring_rule_identities", [])],
        "propagation_rule_identity": (
            None
            if revision.get("propagation_rule_identity") is None
            else _identity(revision.get("propagation_rule_identity"))
        ),
        "retrieval_provenance": revision.get("retrieval_provenance"),
    }
    if body_schema_version is not None:
        expected["body_schema_version"] = body_schema_version
    return expected


def _expected_manifest_version_hash(revision: dict[str, object], *, body_schema_version: str | None) -> str:
    expected = {
        "revision_hash": revision.get("revision_hash"),
        "analysis_hash": revision.get("analysis_hash"),
        "domain_pack_identity": revision.get("domain_pack_identity"),
        "template_identities": revision.get("template_identities"),
        "scoring_rule_identities": revision.get("scoring_rule_identities"),
        "propagation_rule_identity": revision.get("propagation_rule_identity"),
    }
    if body_schema_version is not None:
        expected["body_schema_version"] = body_schema_version
    return canonical_hash(expected, prefixed=True)


def _verify_new_publication_body(
    snapshot: dict[str, object], revision: dict[str, object]
) -> None:
    rows = snapshot.get("rows")
    risks = snapshot.get("risk_records")
    evidence = snapshot.get("evidence_summary")
    propagation = snapshot.get("propagation")
    decisions = snapshot.get("decision_summary")
    if (
        not isinstance(rows, list)
        or not isinstance(risks, list)
        or not isinstance(evidence, list)
        or not isinstance(propagation, dict)
        or not isinstance(decisions, list)
        or snapshot.get("row_count") != len(rows)
    ):
        raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")

    expected_rows = {str(item[0]): item for item in revision.get("row_versions", []) if isinstance(item, list)}
    if len(expected_rows) != len(rows) or {
        str(item.get("row_id")) for item in rows if isinstance(item, dict)
    } != set(expected_rows):
        raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
    for row in rows:
        if not isinstance(row, dict):
            raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
        expected = expected_rows.get(str(row.get("row_id")))
        if expected is None or row.get("record_version") != expected[1] or not _same_hash(row.get("row_hash"), expected[2]):
            raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")

    expected_risks = {str(item[0]): item for item in revision.get("risk_versions", []) if isinstance(item, list)}
    if len(expected_risks) != len(risks):
        raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
    for risk in risks:
        if not isinstance(risk, dict):
            raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
        expected = expected_risks.get(str(risk.get("assessment_id")))
        if expected is None or risk.get("record_version") != expected[1] or not _same_hash(
            risk.get("assessment_hash"), expected[2]
        ):
            raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")

    expected_evidence = {str(item[0]): item for item in revision.get("evidence_pack_hashes", []) if isinstance(item, list)}
    if len(expected_evidence) != len(evidence):
        raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
    for pack in evidence:
        if not isinstance(pack, dict):
            raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
        expected = expected_evidence.get(str(pack.get("pack_id")))
        if expected is None or not _same_hash(pack.get("pack_hash"), expected[1]) or not isinstance(pack.get("refs"), list):
            raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
        for ref in pack["refs"]:
            if not isinstance(ref, dict) or not all(
                isinstance(ref.get(key), str) and ref.get(key) for key in ("evidence_id", "evidence_hash", "content_hash")
            ):
                raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")

    graph_revision_id = revision.get("propagation_graph_revision_id")
    if graph_revision_id is None:
        if propagation is not None:
            raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
    elif (
        propagation.get("graph_revision_id") != graph_revision_id
        or not isinstance(propagation.get("topology_hash"), str)
    ):
        raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
    else:
        _normal_hash(propagation["topology_hash"])
    if not decisions:
        raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
    for decision in decisions:
        if not isinstance(decision, dict) or (
            decision.get("record_type") != "row_review"
            or decision.get("decision") != "accepted"
            or decision.get("role_category") != "human_reviewer"
            or not isinstance(decision.get("decision_id"), str)
        ):
            raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")


def _expected_audit_chain_head(
    previous_head: object,
    revision: dict[str, object],
    approval: dict[str, object],
    snapshot: dict[str, object],
    manifest: dict[str, object],
) -> str:
    return canonical_hash(
        {
            "previous_audit_chain_head": previous_head,
            "revision_hash": revision.get("revision_hash"),
            "approval_hash": canonical_hash(approval, prefixed=True),
            "snapshot_hash": snapshot.get("snapshot_hash"),
            "manifest_hash": manifest.get("manifest_hash"),
        },
        prefixed=True,
    )


def _expected_eligibility_hash(eligibility: dict[str, object]) -> str:
    return canonical_hash(
        {
            "eligibility_id": eligibility.get("eligibility_id"),
            "workspace_id": eligibility.get("workspace_id"),
            "publication_id": eligibility.get("publication_id"),
            "manifest_id": eligibility.get("manifest_id"),
            "eligible": eligibility.get("eligible"),
            "source_hashes": eligibility.get("source_hashes"),
        },
        prefixed=True,
    )


def _strip_fields(item: dict[str, object], fields: set[str]) -> dict[str, object]:
    return {key: value for key, value in item.items() if key not in fields}


def _require_equal(actual: object, expected: object, code: str) -> None:
    if actual != expected:
        raise _VerificationFailure(code)


def _require_hash_equal(actual: object, expected: object, code: str) -> None:
    if not _same_hash(actual, expected):
        raise _VerificationFailure(code)


def _verify_bindings_complete(payloads: dict[str, dict[str, object]], summary: dict[str, object]) -> None:
    if "publication_body_schema_version" not in summary:
        body_schema_version: str | None = None
    else:
        body_schema_version = summary.get("publication_body_schema_version")
        if body_schema_version != PUBLICATION_BODY_SCHEMA_VERSION:
            raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
    revisions = _exact_map(payloads, "revisions.json", 2, "revision_id")
    readiness = _exact_map(payloads, "readiness.json", 2, "revision_id")
    submissions = _exact_map(payloads, "approval-submissions.json", 2, "submission_id")
    approvals = _exact_map(payloads, "approvals.json", 2, "approval_id")
    approval_withdrawals = _exact_map(payloads, "approval-withdrawals.json", 1, "withdrawal_id")
    manifests = _exact_map(payloads, "manifests.json", 2, "manifest_id")
    snapshots = _exact_map(payloads, "snapshots.json", 2, "snapshot_id")
    publications = _exact_map(payloads, "publications.json", 2, "publication_id")
    publication_withdrawals = _exact_map(payloads, "publication-withdrawals.json", 1, "withdrawal_id")
    supersessions = _exact_map(payloads, "supersessions.json", 1, "supersession_id")
    lifecycle_items = _items(payloads, "lifecycle.json")
    if len(lifecycle_items) != 2:
        raise _VerificationFailure("FMEA_AUTHORITY_EVIDENCE_INCOMPLETE")
    lifecycle: dict[str, dict[str, object]] = {}
    for item in lifecycle_items:
        projection = _mapping(item.get("publication"), "FMEA_LIFECYCLE_BINDING_INVALID")
        publication_id = projection.get("publication_id")
        if not isinstance(publication_id, str) or publication_id in lifecycle:
            raise _VerificationFailure("FMEA_DUPLICATE_ID")
        lifecycle[publication_id] = item
    audits = _exact_map(payloads, "audits.json", 11, "event_id")
    outbox = _exact_map(payloads, "outbox.json", 11, "event_id")
    idempotency = _exact_map(payloads, "idempotency.json", 11, "scope_key")
    authority_denials = _items(payloads, "authority-denials.json")
    replay_evidence = _items(payloads, "replay-evidence.json")

    scope_pairs = {(item.get("workspace_id"), item.get("analysis_id")) for item in revisions.values()}
    if len(scope_pairs) != 1:
        raise _VerificationFailure("FMEA_SCOPE_BINDING_INVALID")
    workspace_id, analysis_id = next(iter(scope_pairs))
    if not isinstance(workspace_id, str) or not isinstance(analysis_id, str):
        raise _VerificationFailure("FMEA_SCOPE_BINDING_INVALID")

    for revision_id, revision in revisions.items():
        _server_id(revision_id)
        _scope(revision, workspace_id, analysis_id)
        _require_equal(revision.get("analysis_record_version"), 1, "FMEA_ETAG_INVALID")
        _normal_hash(revision.get("analysis_hash"))
    roots = [item for item in revisions.values() if item.get("parent_revision_id") is None]
    children = [item for item in revisions.values() if item.get("parent_revision_id") is not None]
    if len(roots) != 1 or len(children) != 1:
        raise _VerificationFailure("FMEA_PARENT_BINDING_INVALID")
    root_revision = roots[0]
    child_revision = children[0]
    if (
        child_revision.get("parent_revision_id") != root_revision.get("revision_id")
        or not _same_hash(child_revision.get("parent_revision_hash"), root_revision.get("revision_hash"))
        or root_revision.get("parent_revision_hash") is not None
    ):
        raise _VerificationFailure("FMEA_PARENT_BINDING_INVALID")

    submissions_by_revision: dict[str, dict[str, object]] = {}
    for submission_id, submission in submissions.items():
        _server_id(submission_id)
        _scope(submission, workspace_id, analysis_id)
        revision = revisions.get(str(submission.get("revision_id")))
        if revision is None or submission.get("revision_id") in submissions_by_revision:
            raise _VerificationFailure("FMEA_APPROVAL_BINDING_INVALID")
        if (
            submission.get("status") != "pending"
            or submission.get("record_version") != 1
            or submission.get("revision_hash") != revision.get("revision_hash")
        ):
            raise _VerificationFailure("FMEA_APPROVAL_BINDING_INVALID")
        submissions_by_revision[str(submission["revision_id"])] = submission
    if set(submissions_by_revision) != set(revisions):
        raise _VerificationFailure("FMEA_APPROVAL_BINDING_INVALID")

    approvals_by_submission: dict[str, dict[str, object]] = {}
    for approval_id, approval in approvals.items():
        _server_id(approval_id)
        submission = submissions.get(str(approval.get("submission_id")))
        if submission is None or approval.get("submission_id") in approvals_by_submission:
            raise _VerificationFailure("FMEA_APPROVAL_BINDING_INVALID")
        if (
            approval.get("status") != "approved"
            or approval.get("record_version") != 2
            or approval.get("revision_id") != submission.get("revision_id")
            or approval.get("revision_hash") != submission.get("revision_hash")
            or approval.get("approver_actor_id") == submission.get("submitter_actor_id")
        ):
            raise _VerificationFailure("FMEA_APPROVAL_BINDING_INVALID")
        approvals_by_submission[str(approval["submission_id"])] = approval
    if set(approvals_by_submission) != set(submissions):
        raise _VerificationFailure("FMEA_APPROVAL_BINDING_INVALID")

    readiness_by_revision = readiness
    for revision_id, revision in revisions.items():
        report = readiness_by_revision.get(revision_id)
        if report is None:
            raise _VerificationFailure("FMEA_AUTHORITY_EVIDENCE_INCOMPLETE")
        _scope(report, workspace_id, analysis_id)
        if (
            report.get("revision_hash") != revision.get("revision_hash")
            or report.get("target_record_version") != revision.get("analysis_record_version")
            or report.get("ready") is not True
            or report.get("deterministic") is not True
            or report.get("blocking_codes") != []
            or report.get("issues") != []
        ):
            raise _VerificationFailure("FMEA_READINESS_BINDING_INVALID")

    manifests_by_revision: dict[str, dict[str, object]] = {}
    for manifest_id, manifest in manifests.items():
        _server_id(manifest_id)
        revision = revisions.get(str(manifest.get("revision_id")))
        approval = approvals.get(str(manifest.get("approval_id")))
        if revision is None or approval is None or manifest.get("revision_id") in manifests_by_revision:
            raise _VerificationFailure("FMEA_MANIFEST_BINDING_INVALID")
        if (
            manifest.get("revision_hash") != revision.get("revision_hash")
            or approval.get("revision_id") != revision.get("revision_id")
            or approval.get("revision_hash") != revision.get("revision_hash")
            or manifest.get("export_eligible") is not True
        ):
            raise _VerificationFailure("FMEA_MANIFEST_BINDING_INVALID")
        _require_hash_equal(
            manifest.get("version_manifest_hash"),
            _expected_manifest_version_hash(revision, body_schema_version=body_schema_version),
            "FMEA_MANIFEST_BINDING_INVALID",
        )
        manifests_by_revision[str(manifest["revision_id"])] = manifest
    if set(manifests_by_revision) != set(revisions):
        raise _VerificationFailure("FMEA_MANIFEST_BINDING_INVALID")

    publications_by_revision: dict[str, dict[str, object]] = {}
    for publication_id, publication in publications.items():
        _server_id(publication_id)
        _scope(publication, workspace_id, analysis_id)
        revision = revisions.get(str(publication.get("revision_id")))
        approval = approvals.get(str(publication.get("approval_id")))
        submission = None if approval is None else submissions.get(str(approval.get("submission_id")))
        manifest = manifests.get(str(publication.get("manifest_id")))
        snapshot = snapshots.get(str(publication.get("snapshot_id")))
        if (
            revision is None
            or approval is None
            or submission is None
            or manifest is None
            or snapshot is None
            or publication.get("revision_id") in publications_by_revision
        ):
            raise _VerificationFailure("FMEA_PUBLICATION_BINDING_INVALID")
        try:
            manifest_snapshot_hash_matches = _same_hash(manifest.get("snapshot_hash"), snapshot.get("snapshot_hash"))
            publication_manifest_hash_matches = _same_hash(
                publication.get("snapshot_hash"), manifest.get("snapshot_hash")
            )
        except _VerificationFailure:
            manifest_snapshot_hash_matches = False
            publication_manifest_hash_matches = False
        if (
            manifest.get("snapshot_id") != snapshot.get("snapshot_id")
            or not manifest_snapshot_hash_matches
            or publication.get("snapshot_id") != manifest.get("snapshot_id")
            or not publication_manifest_hash_matches
        ):
            raise _VerificationFailure("FMEA_MANIFEST_BINDING_INVALID")
        if (
            publication.get("record_version") != 1
            or publication.get("revision_hash") != revision.get("revision_hash")
            or publication.get("approval_id") != approval.get("approval_id")
            or publication.get("manifest_id") != manifest.get("manifest_id")
            or publication.get("manifest_hash") != manifest.get("manifest_hash")
            or publication.get("snapshot_id") != snapshot.get("snapshot_id")
            or publication.get("snapshot_hash") != snapshot.get("snapshot_hash")
            or manifest.get("revision_id") != revision.get("revision_id")
            or manifest.get("approval_id") != approval.get("approval_id")
        ):
            raise _VerificationFailure("FMEA_PUBLICATION_BINDING_INVALID")
        publications_by_revision[str(publication["revision_id"])] = publication
    if set(publications_by_revision) != set(revisions):
        raise _VerificationFailure("FMEA_PUBLICATION_BINDING_INVALID")

    snapshots_by_publication: dict[str, dict[str, object]] = {}
    for snapshot_id, snapshot in snapshots.items():
        _server_id(snapshot_id)
        _scope(snapshot, workspace_id, analysis_id)
        revision = revisions.get(str(snapshot.get("revision_id")))
        publication = publications.get(str(snapshot.get("publication_id")))
        manifest = manifests.get(str(snapshot.get("manifest_id")))
        approval = None if manifest is None else approvals.get(str(manifest.get("approval_id")))
        if (
            revision is None
            or publication is None
            or manifest is None
            or approval is None
            or snapshot.get("publication_id") in snapshots_by_publication
        ):
            raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
        if (
            snapshot.get("revision_id") != revision.get("revision_id")
            or snapshot.get("revision_hash") != revision.get("revision_hash")
            or snapshot.get("publication_id") != publication.get("publication_id")
            or snapshot.get("manifest_id") != manifest.get("manifest_id")
            or snapshot_id != f"snapshot:{publication['revision_id']}:{publication['publication_id']}"
            or publication.get("revision_hash") != revision.get("revision_hash")
        ):
            raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
        expected_rows = [
            {"row_id": pair[0], "record_version": pair[1], "row_hash": _export_hash(pair[2])}
            for pair in revision.get("row_versions", [])
        ]
        expected_risks = [
            {"assessment_id": pair[0], "record_version": pair[1], "assessment_hash": _export_hash(pair[2])}
            for pair in revision.get("risk_versions", [])
        ]
        expected_evidence = [
            {"pack_id": pair[0], "pack_hash": _export_hash(pair[1])}
            for pair in revision.get("evidence_pack_hashes", [])
        ]
        expected_propagation = (
            None
            if revision.get("propagation_graph_revision_id") is None
            else {
                "graph_revision_id": revision.get("propagation_graph_revision_id"),
                "graph_hash": _export_hash(revision.get("propagation_graph_hash")),
            }
        )
        expected_decision = [
            {
                "decision_id": approval.get("approval_id"),
                "status": approval.get("status"),
                "revision_id": approval.get("revision_id"),
                "revision_hash": _export_hash(approval.get("revision_hash")),
            }
        ]
        audit_summary = _mapping(snapshot.get("audit_summary"), "FMEA_SNAPSHOT_BINDING_INVALID")
        decision_summary = snapshot.get("decision_summary")
        version_manifest = _mapping(snapshot.get("version_manifest"), "FMEA_SNAPSHOT_BINDING_INVALID")
        if version_manifest.get("body_schema_version") != body_schema_version:
            raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
        if body_schema_version is None:
            snapshot_body_valid = (
                snapshot.get("row_count") == len(expected_rows)
                and snapshot.get("rows") == expected_rows
                and snapshot.get("risk_records") == expected_risks
                and snapshot.get("evidence_summary") == expected_evidence
                and snapshot.get("propagation") == expected_propagation
                and snapshot.get("decision_summary") == expected_decision
            )
        else:
            _verify_new_publication_body(snapshot, revision)
            snapshot_body_valid = True
        if (
            not snapshot_body_valid
            or snapshot.get("version_manifest")
            != _expected_snapshot_version_manifest(revision, body_schema_version=body_schema_version)
            or snapshot.get("unresolved_items") != revision.get("unresolved_items")
            or audit_summary.get("approval_id") != approval.get("approval_id")
            or not _same_hash(audit_summary.get("approval_hash"), canonical_hash(approval, prefixed=True))
            or not _same_hash(
                audit_summary.get("readiness_hash"), canonical_hash(readiness[revision["revision_id"]], prefixed=True)
            )
            or not isinstance(decision_summary, list)
        ):
            raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")
        snapshots_by_publication[str(snapshot["publication_id"])] = snapshot
    if set(snapshots_by_publication) != set(publications):
        raise _VerificationFailure("FMEA_SNAPSHOT_BINDING_INVALID")

    for withdrawal_id, withdrawal in approval_withdrawals.items():
        _server_id(withdrawal_id)
        approval = approvals.get(str(withdrawal.get("approval_id")))
        if approval is None or (
            withdrawal.get("revision_id") != approval.get("revision_id")
            or withdrawal.get("revision_hash") != approval.get("revision_hash")
            or withdrawal.get("actor_id") != approval.get("approver_actor_id")
        ):
            raise _VerificationFailure("FMEA_APPROVAL_BINDING_INVALID")

    for withdrawal_id, withdrawal in publication_withdrawals.items():
        _server_id(withdrawal_id)
        publication = publications.get(str(withdrawal.get("publication_id")))
        if publication is None or withdrawal.get("actor_id") != publication.get("publisher_actor_id"):
            raise _VerificationFailure("FMEA_WITHDRAWAL_BINDING_INVALID")

    supersession = next(iter(supersessions.values()))
    _server_id(supersession["supersession_id"])
    old_publication = publications.get(str(supersession.get("old_publication_id")))
    replacement_publication = publications.get(str(supersession.get("new_publication_id")))
    if (
        old_publication is None
        or replacement_publication is None
        or old_publication["publication_id"] == replacement_publication["publication_id"]
        or old_publication.get("publisher_actor_id") != supersession.get("actor_id")
        or replacement_publication.get("revision_id") != child_revision.get("revision_id")
        or old_publication.get("revision_id") != root_revision.get("revision_id")
    ):
        raise _VerificationFailure("FMEA_SUPERSESSION_BINDING_INVALID")
    if child_revision.get("parent_revision_id") != old_publication.get("revision_id") or not _same_hash(
        child_revision.get("parent_revision_hash"), old_publication.get("revision_hash")
    ):
        raise _VerificationFailure("FMEA_SUPERSESSION_BINDING_INVALID")

    old_manifest = manifests_by_revision[old_publication["revision_id"]]
    replacement_manifest = manifests_by_revision[replacement_publication["revision_id"]]
    if old_manifest.get("previous_audit_chain_head") is not None or not _same_hash(
        replacement_manifest.get("previous_audit_chain_head"), old_publication.get("audit_chain_head")
    ):
        raise _VerificationFailure("FMEA_AUDIT_CHAIN_INVALID")

    lifecycle_by_publication: dict[str, dict[str, object]] = {}
    for item in lifecycle.values():
        publication = _mapping(item.get("publication"), "FMEA_LIFECYCLE_BINDING_INVALID")
        publication_id = publication.get("publication_id")
        if publication_id not in publications or publication_id in lifecycle_by_publication:
            raise _VerificationFailure("FMEA_LIFECYCLE_BINDING_INVALID")
        if publication != publications[publication_id]:
            raise _VerificationFailure("FMEA_LIFECYCLE_BINDING_INVALID")
        lifecycle_by_publication[str(publication_id)] = item
    old_lifecycle = lifecycle_by_publication[old_publication["publication_id"]]
    replacement_lifecycle = lifecycle_by_publication[replacement_publication["publication_id"]]
    if (
        old_lifecycle.get("effective_status") != "superseded"
        or replacement_lifecycle.get("effective_status") != "withdrawn"
    ):
        raise _VerificationFailure("FMEA_LIFECYCLE_STATUS_INVALID")
    if old_lifecycle.get("supersession") != supersession or replacement_lifecycle.get("supersession") is not None:
        raise _VerificationFailure("FMEA_LIFECYCLE_BINDING_INVALID")
    withdrawal = next(iter(publication_withdrawals.values()))
    withdrawal_projection = _strip_fields(withdrawal, {"audit_event_id", "outbox_event_id", "replayed"})
    if replacement_lifecycle.get("withdrawal") != withdrawal_projection or old_lifecycle.get("withdrawal") is not None:
        raise _VerificationFailure("FMEA_LIFECYCLE_BINDING_INVALID")

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
    audit_values = list(audits.values())
    if [item.get("command") for item in audit_values] != expected_order:
        raise _VerificationFailure("FMEA_AUDIT_ORDER_INVALID")
    outbox_by_scope = {str(item.get("idempotency_scope")): item for item in outbox.values()}
    publish_audits: dict[str, dict[str, object]] = {}
    event_types = {
        "fmea.revision.assemble": "revision.assembled",
        "fmea.approval.submit": "approval.submitted",
        "fmea.approval.decide": "approval.approved",
        "fmea.publication.publish": "publication.published",
        "fmea.publication.supersede": "publication.superseded",
        "fmea.approval.withdraw": "approval.withdrawn",
        "fmea.publication.withdraw": "publication.withdrawn",
    }
    authority_resources: dict[str, str] = {}
    for item in audit_values:
        event_id = str(item.get("event_id"))
        _server_id(event_id)
        event = _mapping(item.get("event"), "FMEA_AUDIT_HASH_MISMATCH")
        try:
            _normal_hash(event.get("idempotency_key_hash"))
        except _VerificationFailure:
            raise _VerificationFailure("FMEA_AUDIT_HASH_MISMATCH") from None
        if (
            item.get("actor_type") != "human"
            or event.get("actor_type") != "human"
            or event.get("event_id") != event_id
            or event.get("command") != item.get("command")
            or event.get("workspace_id") != workspace_id
            or event.get("analysis_id") != analysis_id
            or event.get("canonical_payload_hash") != item.get("canonical_payload_hash")
            or not _same_hash(item.get("event_hash"), canonical_hash(event, prefixed=True))
            or event.get("model_manifest") is not None
        ):
            raise _VerificationFailure("FMEA_AUDIT_HASH_MISMATCH")
        outbox_item = outbox_by_scope.get(str(item.get("idempotency_scope")))
        idem_item = idempotency.get(str(item.get("idempotency_scope")))
        if outbox_item is None or idem_item is None:
            raise _VerificationFailure("FMEA_AUTHORITY_EVIDENCE_INCOMPLETE")
        _server_id(str(outbox_item.get("event_id")))
        if (
            outbox_item.get("workspace_id") != workspace_id
            or outbox_item.get("event_type") != event_types.get(str(item.get("command")))
            or outbox_item.get("idempotency_scope") != item.get("idempotency_scope")
            or not _same_hash(
                outbox_item.get("payload_hash"), canonical_hash(outbox_item.get("payload"), prefixed=True)
            )
        ):
            raise _VerificationFailure("FMEA_OUTBOX_BINDING_INVALID")
        response = idem_item.get("response")
        if not isinstance(response, dict):
            raise _VerificationFailure("FMEA_AUTHORITY_EVIDENCE_INVALID")
        if response.get("audit_event_id") != event_id or response.get("outbox_event_id") != outbox_item.get("event_id"):
            raise _VerificationFailure("FMEA_IDEMPOTENCY_BINDING_INVALID")
        if idem_item.get("state") != "completed":
            raise _VerificationFailure("FMEA_AUTHORITY_EVIDENCE_INVALID")
        payload = _mapping(outbox_item.get("payload"), "FMEA_OUTBOX_BINDING_INVALID")
        command = str(item.get("command"))
        if payload.get("operation") != command.removeprefix("fmea."):
            raise _VerificationFailure("FMEA_OUTBOX_BINDING_INVALID")
        resource_id: str
        audit_aggregate_id: str
        if command == "fmea.revision.assemble":
            revision = _mapping(payload.get("revision"), "FMEA_OUTBOX_BINDING_INVALID")
            resource_id = str(revision.get("revision_id"))
            audit_aggregate_id = resource_id
            if revision != revisions.get(resource_id):
                raise _VerificationFailure("FMEA_OUTBOX_BINDING_INVALID")
        elif command == "fmea.approval.submit":
            submission = _mapping(payload.get("submission"), "FMEA_OUTBOX_BINDING_INVALID")
            resource_id = str(submission.get("submission_id"))
            audit_aggregate_id = str(submission.get("revision_id"))
            if submission != submissions.get(resource_id):
                raise _VerificationFailure("FMEA_OUTBOX_BINDING_INVALID")
        elif command == "fmea.approval.decide":
            decision = _mapping(payload.get("decision"), "FMEA_OUTBOX_BINDING_INVALID")
            submission = _mapping(payload.get("submission"), "FMEA_OUTBOX_BINDING_INVALID")
            resource_id = str(decision.get("approval_id"))
            audit_aggregate_id = str(decision.get("revision_id"))
            if decision != approvals.get(resource_id) or submission != submissions.get(
                str(decision.get("submission_id"))
            ):
                raise _VerificationFailure("FMEA_OUTBOX_BINDING_INVALID")
        elif command == "fmea.publication.publish":
            publication = _mapping(payload.get("publication"), "FMEA_OUTBOX_BINDING_INVALID")
            manifest = _mapping(payload.get("manifest"), "FMEA_OUTBOX_BINDING_INVALID")
            snapshot = _mapping(payload.get("snapshot"), "FMEA_OUTBOX_BINDING_INVALID")
            revision = _mapping(payload.get("revision"), "FMEA_OUTBOX_BINDING_INVALID")
            approval = _mapping(payload.get("approval"), "FMEA_OUTBOX_BINDING_INVALID")
            submission = _mapping(payload.get("submission"), "FMEA_OUTBOX_BINDING_INVALID")
            eligibility = _mapping(payload.get("export_eligibility"), "FMEA_OUTBOX_BINDING_INVALID")
            resource_id = str(publication.get("publication_id"))
            audit_aggregate_id = resource_id
            if (
                publication != publications.get(resource_id)
                or manifest != manifests.get(str(publication.get("manifest_id")))
                or snapshot != snapshots.get(str(publication.get("snapshot_id")))
                or revision != revisions.get(str(publication.get("revision_id")))
                or approval != approvals.get(str(publication.get("approval_id")))
                or submission != submissions.get(str(approval.get("submission_id")))
                or eligibility.get("eligible") is not True
                or eligibility.get("workspace_id") != workspace_id
                or eligibility.get("publication_id") != publication.get("publication_id")
                or eligibility.get("manifest_id") != manifest.get("manifest_id")
                or eligibility.get("source_hashes")
                != [
                    ["manifest", manifest.get("manifest_hash")],
                    ["revision", revision.get("revision_hash")],
                    ["snapshot", snapshot.get("snapshot_hash")],
                ]
                or not _same_hash(eligibility.get("eligibility_hash"), _expected_eligibility_hash(eligibility))
            ):
                raise _VerificationFailure("FMEA_OUTBOX_BINDING_INVALID")
            publish_audits[resource_id] = {"audit": item, "event": event}
        elif command == "fmea.publication.supersede":
            old = _mapping(payload.get("old"), "FMEA_OUTBOX_BINDING_INVALID")
            replacement = _mapping(payload.get("replacement"), "FMEA_OUTBOX_BINDING_INVALID")
            link = _mapping(payload.get("supersession"), "FMEA_OUTBOX_BINDING_INVALID")
            resource_id = str(link.get("supersession_id"))
            audit_aggregate_id = str(old.get("publication_id"))
            if (
                old != publications.get(str(old.get("publication_id")))
                or replacement != publications.get(str(replacement.get("publication_id")))
                or link != supersessions.get(resource_id)
            ):
                raise _VerificationFailure("FMEA_OUTBOX_BINDING_INVALID")
        elif command == "fmea.approval.withdraw":
            approval = _mapping(payload.get("approval"), "FMEA_OUTBOX_BINDING_INVALID")
            link = _mapping(payload.get("withdrawal"), "FMEA_OUTBOX_BINDING_INVALID")
            resource_id = str(link.get("withdrawal_id"))
            audit_aggregate_id = str(approval.get("revision_id"))
            if approval != approvals.get(str(approval.get("approval_id"))) or link != approval_withdrawals.get(
                resource_id
            ):
                raise _VerificationFailure("FMEA_OUTBOX_BINDING_INVALID")
        elif command == "fmea.publication.withdraw":
            publication = _mapping(payload.get("publication"), "FMEA_OUTBOX_BINDING_INVALID")
            link = _mapping(payload.get("withdrawal"), "FMEA_OUTBOX_BINDING_INVALID")
            resource_id = str(link.get("withdrawal_id"))
            audit_aggregate_id = str(publication.get("publication_id"))
            if publication != publications.get(str(publication.get("publication_id"))) or link != _strip_fields(
                publication_withdrawals[resource_id], {"audit_event_id", "outbox_event_id", "replayed"}
            ):
                raise _VerificationFailure("FMEA_OUTBOX_BINDING_INVALID")
        else:
            raise _VerificationFailure("FMEA_AUDIT_ORDER_INVALID")
        if not _same_hash(outbox_item.get("payload_hash"), item.get("canonical_payload_hash")) or not _same_hash(
            idem_item.get("payload_hash"), item.get("canonical_payload_hash")
        ):
            raise _VerificationFailure("FMEA_AUTHORITY_EVIDENCE_INVALID")
        if (
            item.get("resource_id") != audit_aggregate_id
            or event.get("row_id") != resource_id
            or outbox_item.get("aggregate_id") != resource_id
        ):
            raise _VerificationFailure("FMEA_AUDIT_BINDING_INVALID")
        response_resource_keys = {
            "fmea.revision.assemble": "revision_id",
            "fmea.approval.submit": "submission_id",
            "fmea.approval.decide": "approval_id",
            "fmea.publication.publish": "publication_id",
            "fmea.publication.supersede": "supersession_id",
            "fmea.approval.withdraw": "withdrawal_id",
            "fmea.publication.withdraw": "withdrawal_id",
        }
        if response.get(response_resource_keys[command]) != resource_id:
            raise _VerificationFailure("FMEA_IDEMPOTENCY_BINDING_INVALID")
        _server_id(resource_id)
        if idem_item.get("resource_id") != resource_id or idem_item["response"].get("resource_id") not in (
            None,
            resource_id,
        ):
            raise _VerificationFailure("FMEA_IDEMPOTENCY_BINDING_INVALID")
        authority_resources[event_id] = resource_id
        if command == "fmea.publication.publish":
            publication = publications[resource_id]
            revision = revisions[str(publication["revision_id"])]
            approval = approvals[str(publication["approval_id"])]
            manifest = manifests[str(publication["manifest_id"])]
            snapshot = snapshots[str(publication["snapshot_id"])]
            if not _same_hash(
                publication.get("audit_chain_head"),
                _expected_audit_chain_head(
                    manifest.get("previous_audit_chain_head"), revision, approval, snapshot, manifest
                ),
            ) or not _same_hash(event.get("after_hash"), publication.get("audit_chain_head")):
                raise _VerificationFailure("FMEA_AUDIT_CHAIN_INVALID")

    if set(outbox_by_scope) != {str(item.get("idempotency_scope")) for item in audit_values} or set(idempotency) != set(
        outbox_by_scope
    ):
        raise _VerificationFailure("FMEA_AUTHORITY_EVIDENCE_INCOMPLETE")

    expected_counts = {
        "fmea_revisions": len(revisions),
        "fmea_approval_submissions": len(submissions),
        "fmea_approval_decisions": len(approvals),
        "fmea_approval_withdrawals": len(approval_withdrawals),
        "fmea_publication_manifests": len(manifests),
        "fmea_normalized_snapshots": len(snapshots),
        "fmea_publications": len(publications),
        "fmea_export_eligibility": sum(
            1 for item in outbox.values() if item.get("event_type") == "publication.published"
        ),
        "fmea_publication_withdrawals": len(publication_withdrawals),
        "fmea_supersessions": len(supersessions),
        "fmea_audit_events": len(audits),
        "fmea_outbox_events": len(outbox),
        "idempotency_records": len(idempotency),
    }
    stale_counts = dict(expected_counts)
    for table in (
        "fmea_approval_withdrawals",
        "fmea_publication_withdrawals",
        "fmea_supersessions",
    ):
        stale_counts[table] -= 1
    for table in (
        "fmea_publication_manifests",
        "fmea_normalized_snapshots",
        "fmea_publications",
        "fmea_export_eligibility",
    ):
        stale_counts[table] -= 1
    for table in ("fmea_audit_events", "fmea_outbox_events", "idempotency_records"):
        stale_counts[table] -= 4
    expected_denial_keys = {
        (actor_type, probe)
        for actor_type in ("model", "system")
        for probe in (
            "assemble",
            "submit",
            "approve",
            "reject",
            "withdraw_approval",
            "publish",
            "withdraw_publication",
            "supersede",
        )
    }
    seen_denial_keys: set[tuple[str, str]] = set()
    stale_codes: list[str] = []
    for denial in authority_denials:
        before = denial.get("before_counts")
        after = denial.get("after_counts")
        probe = denial.get("probe")
        actor_type = denial.get("actor_type")
        if probe == "stale_approval":
            if before != stale_counts or after != stale_counts:
                raise _VerificationFailure("FMEA_AUTHORITY_DENIAL_WRITE")
            if (
                actor_type != "human"
                or denial.get("actor_id") != "human-publisher"
                or denial.get("command") != "fmea.publication.publish"
                or denial.get("error_code") != "FMEA_GOVERNANCE_APPROVAL_STALE"
            ):
                raise _VerificationFailure("FMEA_AUTHORITY_DENIAL_INVALID")
            stale_codes.append(str(denial.get("error_code")))
            continue
        if before != expected_counts or after != expected_counts:
            raise _VerificationFailure("FMEA_AUTHORITY_DENIAL_WRITE")
        key = (str(actor_type), str(probe))
        if key in seen_denial_keys or key not in expected_denial_keys:
            raise _VerificationFailure("FMEA_AUTHORITY_DENIAL_INVALID")
        seen_denial_keys.add(key)
        expected_code = (
            "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN"
            if probe in {"assemble", "submit", "approve", "reject", "withdraw_approval"}
            else "FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN"
        )
        if denial.get("actor_id") != f"{actor_type}-authority-probe" or denial.get("error_code") != expected_code:
            raise _VerificationFailure("FMEA_AUTHORITY_DENIAL_INVALID")
    if (
        len(authority_denials) != 17
        or seen_denial_keys != expected_denial_keys
        or stale_codes != ["FMEA_GOVERNANCE_APPROVAL_STALE"]
    ):
        raise _VerificationFailure("FMEA_AUTHORITY_DENIAL_INVALID")

    expected_replays = {
        "fmea.approval.decide": "approval-",
        "fmea.publication.publish": "publication-",
        "fmea.publication.withdraw": "publication-withdrawal-",
    }
    if len(replay_evidence) != len(expected_replays):
        raise _VerificationFailure("FMEA_REPLAY_INCOMPLETE")
    replay_checks: dict[str, bool] = {}
    for replay in replay_evidence:
        command = replay.get("command")
        resource_id = replay.get("resource_id")
        if (
            command not in expected_replays
            or not isinstance(resource_id, str)
            or not resource_id.startswith(expected_replays[command])
        ):
            raise _VerificationFailure("FMEA_REPLAY_INCOMPLETE")
        if replay.get("replayed") is not True:
            raise _VerificationFailure("FMEA_REPLAY_INCOMPLETE")
        matching = next((item for item in idempotency.values() if item.get("resource_id") == resource_id), None)
        if (
            matching is None
            or replay.get("audit_event_id") != matching.get("response", {}).get("audit_event_id")
            or replay.get("outbox_event_id") != matching.get("response", {}).get("outbox_event_id")
        ):
            raise _VerificationFailure("FMEA_REPLAY_INCOMPLETE")
        if command == "fmea.approval.decide":
            replay_checks["approve"] = True
        elif command == "fmea.publication.publish":
            replay_checks["publish"] = True
        else:
            replay_checks["withdraw_publication"] = True
    if set(replay_checks) != {"approve", "publish", "withdraw_publication"}:
        raise _VerificationFailure("FMEA_REPLAY_INCOMPLETE")
    retention = replacement_lifecycle.get("withdrawal") == withdrawal_projection
    model_publication_count = sum(
        1
        for item in audit_values
        if item.get("command") == "fmea.publication.publish" and item.get("actor_type") == "model"
    )
    profiles = _items(payloads, "provenance-profiles.json")
    if len(profiles) != 4 or payloads["provenance-profiles.json"].get("retrieval_call_count") != 0:
        raise _VerificationFailure("FMEA_PROVENANCE_INVALID")
    expected_profiles = {
        "rag_only": ["text"],
        "graphrag_only": ["graph", "community"],
        "combined": ["text", "graph", "community"],
        "auto": ["text", "graph", "community"],
    }
    profile_cases = {str(record.get("requested_profile")): record.get("evidence_types") for record in profiles}
    if profile_cases != expected_profiles:
        raise _VerificationFailure("FMEA_PROVENANCE_INVALID")
    stale_code = stale_codes[0]
    derived_summary = {
        "approval_actor_type": next(
            item["actor_type"] for item in audit_values if item.get("command") == "fmea.approval.decide"
        ),
        "publisher_actor_type": next(
            item["actor_type"] for item in audit_values if item.get("command") == "fmea.publication.publish"
        ),
        "model_publication_count": model_publication_count,
        "withdrawn_publication_retained": retention,
        "replay_checks": replay_checks,
        "profile_cases": profile_cases,
        "profile_records": {str(record.get("requested_profile")): record for record in profiles},
        "retrieval_call_count": payloads["provenance-profiles.json"].get("retrieval_call_count"),
        "parent_revision_id": root_revision["revision_id"],
        "child_revision_id": child_revision["revision_id"],
        "parent_publication_id": old_publication["publication_id"],
        "child_publication_id": replacement_publication["publication_id"],
        "approval_withdrawal_id": next(iter(approval_withdrawals.values()))["withdrawal_id"],
        "stale_child_approval_code": stale_code,
    }
    for key, expected in derived_summary.items():
        if summary.get(key) != expected:
            raise _VerificationFailure("FMEA_SUMMARY_MISMATCH")


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
            if (
                stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
                or not stat.S_ISREG(info.st_mode)
            ):
                raise _VerificationFailure("FMEA_ARTIFACT_PATH_INVALID")
            raw = path.read_bytes()
            total += len(raw)
            if total > _MAX_TOTAL_BYTES:
                raise _VerificationFailure("FMEA_ARTIFACT_BOUNDS")
            lowered = raw.lower()
            if any(marker in lowered for marker in _PRIVATE_KEY_MARKERS):
                raise _VerificationFailure("FMEA_PRIVATE_MARKER")
            value, is_canonical = _parse(raw)
            _reject_decoded_private_paths(value)
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
        _verify_bindings_complete(payloads, summary)
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
        if (
            stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
            or not stat.S_ISREG(info.st_mode)
        ):
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
    result = (
        verify_latest(args.latest)
        if args.latest is not None
        else verify(args.directory)
        if args.directory is not None
        else VerificationResult(False, "", "FMEA_ARTIFACT_PATH_INVALID")
    )
    print(
        json.dumps(
            {
                "status": "passed" if result.passed else "failed",
                "artifact_id": result.artifact_id,
                "error_code": result.error_code,
            },
            separators=(",", ":"),
        )
    )
    return 0 if result.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["VerificationResult", "verify", "verify_acceptance_directory", "verify_latest"]
