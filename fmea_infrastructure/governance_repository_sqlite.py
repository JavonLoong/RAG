"""SQLite persistence for the immutable FMEA governance lifecycle."""

# Stored governance JSON is deliberately decoded strictly at the repository
# boundary.  The repository also owns the transaction that joins the object,
# shared idempotency record, audit event, and outbox event.
# ruff: noqa: C901, S608, TRY003, TRY004, TRY300

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, NoReturn, cast
from uuid import NAMESPACE_URL, uuid5

from core_domain.fmea.governance import (
    ApprovalDecision,
    ApprovalStatus,
    ApprovalSubmission,
    ApprovalWithdrawalRecord,
    FmeaRevision,
    PublicationLifecycleView,
    PublicationManifest,
    PublicationWithdrawalRecord,
    PublishedRevision,
    ReadinessIssue,
    RetrievalProvenanceSnapshot,
    SupersessionRecord,
    canonical_hash,
    canonical_json_bytes,
    project_publication_lifecycle,
    validate_approval_binding,
    validate_supersession_binding,
)
from fmea_application.governance_contracts import (
    ApprovalCommand,
    ApprovalRejectionCommand,
    ApprovalResult,
    ApprovalSubmissionResult,
    AssembleRevisionCommand,
    ExportEligibilityRecord,
    GovernanceHistoryQuery,
    PreparedApproval,
    PreparedApprovalSubmission,
    PreparedApprovalWithdrawal,
    PreparedPublication,
    PreparedPublicationWithdrawal,
    PreparedReadinessReport,
    PreparedRevision,
    PreparedSupersession,
    PublicationResult,
    PublicationWithdrawalResult,
    ReadinessReportRecord,
    ReadinessResult,
    RevisionAssemblyRequest,
    RevisionResult,
    SupersessionResult,
    canonical_governance_payload,
    governance_payload_hash,
)
from fmea_application.ports import ApprovalWithdrawalResult, GovernanceHistoryPage
from fmea_application.review_contracts import AuditEvent, IdempotencyScope, encode_review_json, idempotency_key_hash
from fmea_application.review_errors import ReviewError
from fmea_application.revision_assembler import PublicationReadinessReport
from fmea_application.risk_contracts import OutboxEvent, canonical_json, outbox_payload_hash

from .repository_sqlite import SqliteFmeaRepository
from .sqlite_codec import decode_audit_event, load_strict_json

_MAX_BUSY_TIMEOUT_MS = 60_000
_KIND_TYPES: dict[str, type[object]] = {
    "revision": PreparedRevision,
    "readiness": PreparedReadinessReport,
    "approval_submission": PreparedApprovalSubmission,
    "approval": PreparedApproval,
    "approval_withdrawal": PreparedApprovalWithdrawal,
    "publication": PreparedPublication,
    "publication_withdrawal": PreparedPublicationWithdrawal,
    "supersession": PreparedSupersession,
}
_RESULT_FIELDS: dict[str, set[str]] = {
    "revision": {"revision_id", "record_version", "audit_event_id", "outbox_event_id", "replayed"},
    "readiness": {"readiness_id", "record_version", "audit_event_id", "outbox_event_id", "replayed"},
    "approval_submission": {"submission_id", "record_version", "audit_event_id", "outbox_event_id", "replayed"},
    "approval": {"approval_id", "record_version", "audit_event_id", "outbox_event_id", "replayed"},
    "publication": {
        "publication_id",
        "manifest_id",
        "snapshot_id",
        "record_version",
        "audit_event_id",
        "outbox_event_id",
        "replayed",
    },
    "approval_withdrawal": {"withdrawal_id", "approval_id", "audit_event_id", "outbox_event_id", "replayed"},
    "publication_withdrawal": {"withdrawal_id", "publication_id", "audit_event_id", "outbox_event_id", "replayed"},
    "supersession": {
        "supersession_id",
        "old_publication_id",
        "new_publication_id",
        "audit_event_id",
        "outbox_event_id",
        "replayed",
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _json_hash(payload: str) -> str:
    return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _hash(value: object, field_name: str) -> str:
    result = _text(value, field_name)
    if len(result) not in {64, 71} or (len(result) == 71 and not result.startswith("sha256:")):
        raise ValueError(f"{field_name} is invalid")
    raw = result.removeprefix("sha256:")
    if any(character not in "0123456789abcdef" for character in raw):
        raise ValueError(f"{field_name} is invalid")
    return result


def _object_json(value: object) -> tuple[str, str]:
    payload = canonical_json_bytes(value).decode("utf-8")
    return payload, _json_hash(payload)


def _mapping(value: object, kind: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"persisted {kind} must be an object")
    return value


def _sequence(value: object, kind: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise ValueError(f"persisted {kind} must be an array")
    return tuple(value)


def _strict_object(payload: object, kind: str, expected_fields: set[str]) -> dict[str, object]:
    data = load_strict_json(payload, kind)
    if set(data) != expected_fields:
        raise ValueError(f"persisted {kind} fields are invalid")
    return data


def _decode_revision(payload: object) -> FmeaRevision:
    data = _strict_object(payload, "revision", {field.name for field in fields(FmeaRevision)})
    provenance_data = _mapping(data["retrieval_provenance"], "revision retrieval_provenance")
    provenance = RetrievalProvenanceSnapshot(
        requested_profile=cast(str, provenance_data["requested_profile"]),
        resolved_profile=cast(str, provenance_data["resolved_profile"]),
        evidence_types=tuple(cast(list[object], provenance_data["evidence_types"])),
        source_counts=tuple(
            tuple(cast(list[object], item)) for item in _sequence(provenance_data["source_counts"], "source_counts")
        ),
        warnings=tuple(cast(list[object], provenance_data["warnings"])),
    )
    issues = tuple(
        ReadinessIssue(
            code=cast(str, item["code"]),
            severity=cast(str, item["severity"]),
            source_type=cast(str, item["source_type"]),
            source_id=cast(str, item["source_id"]),
            evidence_ids=tuple(cast(list[object], item["evidence_ids"])),
            acknowledgement_decision_id=cast(str | None, item["acknowledgement_decision_id"]),
        )
        for item in (
            _mapping(item, "readiness issue") for item in _sequence(data["unresolved_items"], "unresolved_items")
        )
    )
    try:
        revision = FmeaRevision(
            revision_id=cast(str, data["revision_id"]),
            workspace_id=cast(str, data["workspace_id"]),
            analysis_id=cast(str, data["analysis_id"]),
            analysis_record_version=cast(int, data["analysis_record_version"]),
            analysis_hash=cast(str, data["analysis_hash"]),
            parent_revision_id=cast(str | None, data["parent_revision_id"]),
            parent_revision_hash=cast(str | None, data["parent_revision_hash"]),
            row_versions=tuple(
                tuple(cast(list[object], item)) for item in _sequence(data["row_versions"], "row_versions")
            ),
            risk_versions=tuple(
                tuple(cast(list[object], item)) for item in _sequence(data["risk_versions"], "risk_versions")
            ),
            propagation_graph_revision_id=cast(str | None, data["propagation_graph_revision_id"]),
            propagation_graph_hash=cast(str | None, data["propagation_graph_hash"]),
            evidence_pack_hashes=tuple(
                tuple(cast(list[object], item))
                for item in _sequence(data["evidence_pack_hashes"], "evidence_pack_hashes")
            ),
            retrieval_provenance=provenance,
            domain_pack_identity=tuple(cast(list[object], data["domain_pack_identity"])),
            template_identities=tuple(
                tuple(cast(list[object], item))
                for item in _sequence(data["template_identities"], "template_identities")
            ),
            scoring_rule_identities=tuple(
                tuple(cast(list[object], item))
                for item in _sequence(data["scoring_rule_identities"], "scoring_rule_identities")
            ),
            propagation_rule_identity=None
            if data["propagation_rule_identity"] is None
            else tuple(cast(list[object], data["propagation_rule_identity"])),
            unresolved_items=issues,
            revision_hash=cast(str, data["revision_hash"]),
            created_at=cast(str, data["created_at"]),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("persisted revision is invalid") from exc
    canonical, _ = _object_json(revision)
    if canonical != cast(str, payload):
        raise ValueError("persisted revision is not canonical")
    return revision


def _decode_submission(payload: object) -> ApprovalSubmission:
    data = _strict_object(payload, "approval submission", {field.name for field in fields(ApprovalSubmission)})
    value = ApprovalSubmission(
        submission_id=cast(str, data["submission_id"]),
        workspace_id=cast(str, data["workspace_id"]),
        revision_id=cast(str, data["revision_id"]),
        revision_hash=cast(str, data["revision_hash"]),
        status=ApprovalStatus(cast(str, data["status"])),
        submitter_actor_id=cast(str, data["submitter_actor_id"]),
        record_version=cast(int, data["record_version"]),
        created_at=cast(str, data["created_at"]),
    )
    if _object_json(value)[0] != payload:
        raise ValueError("persisted approval submission is not canonical")
    return value


def _decode_approval(payload: object) -> ApprovalDecision:
    data = _strict_object(payload, "approval decision", {field.name for field in fields(ApprovalDecision)})
    value = ApprovalDecision(
        approval_id=cast(str, data["approval_id"]),
        submission_id=cast(str, data["submission_id"]),
        revision_id=cast(str, data["revision_id"]),
        revision_hash=cast(str, data["revision_hash"]),
        status=ApprovalStatus(cast(str, data["status"])),
        approver_actor_id=cast(str, data["approver_actor_id"]),
        reason=cast(str, data["reason"]),
        record_version=cast(int, data["record_version"]),
        created_at=cast(str, data["created_at"]),
    )
    if _object_json(value)[0] != payload:
        raise ValueError("persisted approval decision is not canonical")
    return value


def _decode_approval_withdrawal(payload: object) -> ApprovalWithdrawalRecord:
    data = _strict_object(payload, "approval withdrawal", {field.name for field in fields(ApprovalWithdrawalRecord)})
    value = ApprovalWithdrawalRecord(**data)
    if _object_json(value)[0] != payload:
        raise ValueError("persisted approval withdrawal is not canonical")
    return value


def _decode_manifest(payload: object) -> PublicationManifest:
    data = _strict_object(payload, "publication manifest", {field.name for field in fields(PublicationManifest)})
    value = PublicationManifest(**data)
    if _object_json(value)[0] != payload:
        raise ValueError("persisted publication manifest is not canonical")
    return value


def _source_hashes_json(source_hashes: tuple[tuple[str, str], ...]) -> str:
    return canonical_json(dict(source_hashes))


def _decode_source_hashes(payload: object) -> tuple[tuple[str, str], ...]:
    data = load_strict_json(payload, "source hashes")
    if not isinstance(data, dict) or canonical_json(data) != payload:
        raise ValueError("persisted source hashes are not canonical")
    pairs = tuple(sorted((str(key), _hash(value, "source hash")) for key, value in data.items()))
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("persisted source hashes contain duplicate identities")
    return pairs


def _decode_readiness(payload: object) -> PublicationReadinessReport:
    data = _strict_object(payload, "readiness report", {field.name for field in fields(PublicationReadinessReport)})
    issues: list[ReadinessIssue] = []
    for item in _sequence(data["issues"], "readiness issues"):
        issue_data = _mapping(item, "readiness issue")
        if set(issue_data) != {field.name for field in fields(ReadinessIssue)}:
            raise ValueError("persisted readiness issue fields are invalid")
        issues.append(
            ReadinessIssue(
                code=cast(str, issue_data["code"]),
                severity=cast(str, issue_data["severity"]),
                source_type=cast(str, issue_data["source_type"]),
                source_id=cast(str, issue_data["source_id"]),
                evidence_ids=tuple(cast(str, value) for value in _sequence(issue_data["evidence_ids"], "evidence_ids")),
                acknowledgement_decision_id=cast(str | None, issue_data["acknowledgement_decision_id"]),
            )
        )
    try:
        value = PublicationReadinessReport(
            revision_id=cast(str, data["revision_id"]),
            workspace_id=cast(str, data["workspace_id"]),
            analysis_id=cast(str, data["analysis_id"]),
            revision_hash=cast(str, data["revision_hash"]),
            target_record_version=cast(int, data["target_record_version"]),
            evidence_pack_ids=tuple(
                cast(str, value) for value in _sequence(data["evidence_pack_ids"], "evidence_pack_ids")
            ),
            ready=cast(bool, data["ready"]),
            issues=tuple(issues),
            blocking_codes=tuple(cast(str, value) for value in _sequence(data["blocking_codes"], "blocking_codes")),
            deterministic=cast(bool, data["deterministic"]),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("persisted readiness report is invalid") from exc
    if _object_json(value)[0] != payload:
        raise ValueError("persisted readiness report is not canonical")
    return value


def _decode_export_eligibility(payload: object) -> ExportEligibilityRecord:
    data = _strict_object(payload, "export eligibility", {field.name for field in fields(ExportEligibilityRecord)})
    source_hashes = tuple(
        tuple(cast(str, value) for value in _sequence(item, "source hash pair"))
        for item in _sequence(data["source_hashes"], "source_hashes")
    )
    try:
        value = ExportEligibilityRecord(
            eligibility_id=cast(str, data["eligibility_id"]),
            workspace_id=cast(str, data["workspace_id"]),
            publication_id=cast(str, data["publication_id"]),
            manifest_id=cast(str, data["manifest_id"]),
            eligible=cast(bool, data["eligible"]),
            source_hashes=source_hashes,
            eligibility_hash=cast(str, data["eligibility_hash"]),
            created_at=cast(str, data["created_at"]),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("persisted export eligibility is invalid") from exc
    if _object_json(value)[0] != payload:
        raise ValueError("persisted export eligibility is not canonical")
    return value


def _decode_publication(payload: object) -> PublishedRevision:
    data = _strict_object(payload, "publication", {field.name for field in fields(PublishedRevision)})
    value = PublishedRevision(**data)
    if _object_json(value)[0] != payload:
        raise ValueError("persisted publication is not canonical")
    return value


def _decode_publication_withdrawal(payload: object) -> PublicationWithdrawalRecord:
    data = _strict_object(
        payload, "publication withdrawal", {field.name for field in fields(PublicationWithdrawalRecord)}
    )
    value = PublicationWithdrawalRecord(**data)
    if _object_json(value)[0] != payload:
        raise ValueError("persisted publication withdrawal is not canonical")
    return value


def _decode_supersession(payload: object) -> SupersessionRecord:
    data = _strict_object(payload, "supersession", {field.name for field in fields(SupersessionRecord)})
    value = SupersessionRecord(**data)
    if _object_json(value)[0] != payload:
        raise ValueError("persisted supersession is not canonical")
    return value


def _error(code: str, message: str, *, retryable: bool = False) -> NoReturn:
    raise ReviewError(code, message, retryable=retryable)


@dataclass(frozen=True, slots=True)
class _PreparedMeta:
    kind: str
    workspace_id: str
    resource_id: str
    history_id: str
    resource_type: str
    command: str
    payload: Mapping[str, object]


class SqliteGovernanceRepository:
    """Persist prepared governance contracts with one SQLite transaction."""

    def __init__(
        self,
        database_path: Path,
        *,
        busy_timeout_ms: int = 5000,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        if isinstance(busy_timeout_ms, bool) or not isinstance(busy_timeout_ms, int):
            raise ValueError("busy_timeout_ms must be an integer")
        if not 1 <= busy_timeout_ms <= _MAX_BUSY_TIMEOUT_MS:
            raise ValueError(f"busy_timeout_ms must be between 1 and {_MAX_BUSY_TIMEOUT_MS}")
        self.database_path = Path(database_path).expanduser().resolve()
        self._busy_timeout_ms = busy_timeout_ms
        self._fault_injector = fault_injector

    def initialize(self) -> None:
        SqliteFmeaRepository(self.database_path, busy_timeout_ms=self._busy_timeout_ms).initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.database_path), timeout=self._busy_timeout_ms / 1000, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _fail(self, step: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(step)

    @staticmethod
    def _workspace(value: object) -> str:
        return _text(value, "workspace_id")

    @staticmethod
    def _expected_path(kind: str, prepared: Any) -> str:
        if kind == "revision":
            return f"/fmea/analyses/{prepared.revision.analysis_id}/revisions"
        if kind == "readiness":
            return f"/fmea/revisions/{prepared.revision.revision_id}/readiness"
        if kind == "approval_submission":
            return f"/fmea/revisions/{prepared.submission.revision_id}/approval-submissions"
        if kind == "approval":
            return f"/fmea/approval-submissions/{prepared.submission.submission_id}/decision"
        if kind == "approval_withdrawal":
            return f"/fmea/approvals/{prepared.approval.approval_id}/withdrawal"
        if kind == "publication":
            return f"/fmea/revisions/{prepared.revision.revision_id}/publications"
        if kind == "publication_withdrawal":
            return f"/fmea/publications/{prepared.publication.publication_id}/withdrawal"
        return f"/fmea/publications/{prepared.old_publication.publication_id}/supersession"

    @classmethod
    def _meta(cls, kind: str, prepared: object) -> _PreparedMeta:
        expected = _KIND_TYPES.get(kind)
        if expected is None or not isinstance(prepared, expected):
            _error("FMEA_REVIEW_REQUEST_INVALID", f"Prepared {kind} contract is invalid.")
        value = cast(Any, prepared)
        if not isinstance(value.scope, IdempotencyScope):
            _error("FMEA_REVIEW_REQUEST_INVALID", "Governance idempotency scope is invalid.")
        if kind == "revision":
            obj = value.revision
            resource_id = obj.revision_id
            history_id = obj.revision_id
            resource_type = "revision"
        elif kind == "readiness":
            obj = value.report
            resource_id = value.readiness_id
            history_id = value.revision.revision_id
            resource_type = "revision"
        elif kind == "approval_submission":
            obj = value.submission
            resource_id = obj.submission_id
            history_id = obj.revision_id
            resource_type = "approval"
        elif kind == "approval":
            obj = value.decision
            resource_id = obj.approval_id
            history_id = obj.revision_id
            resource_type = "approval"
        elif kind == "approval_withdrawal":
            obj = value.withdrawal
            resource_id = obj.withdrawal_id
            history_id = obj.revision_id
            resource_type = "approval"
        elif kind == "publication":
            obj = value.publication
            resource_id = obj.publication_id
            history_id = obj.publication_id
            resource_type = "publication"
        elif kind == "publication_withdrawal":
            obj = value.withdrawal
            resource_id = obj.withdrawal_id
            history_id = value.publication.publication_id
            resource_type = "publication"
        else:
            obj = value.supersession
            resource_id = obj.supersession_id
            history_id = value.old_publication.publication_id
            resource_type = "publication"
        payload = value.payload
        expected_payload_hash = governance_payload_hash(payload)
        if value.payload_hash != expected_payload_hash:
            _error("FMEA_REVIEW_REQUEST_INVALID", "Governance payload hash is invalid.")
        resource_workspace = getattr(obj, "workspace_id", None)
        if resource_workspace is None:
            if kind == "supersession":
                resource_workspace = value.old_publication.workspace_id
            elif kind == "publication_withdrawal":
                resource_workspace = value.publication.workspace_id
            else:
                resource_workspace = value.scope.workspace_id
        if value.scope.workspace_id != resource_workspace:
            _error("FMEA_REVIEW_REQUEST_INVALID", "Governance workspace binding is invalid.")
        if kind in {"revision", "readiness"}:
            resource_actor = None
        elif kind == "approval_submission":
            resource_actor = value.submission.submitter_actor_id
        elif kind == "approval":
            resource_actor = value.decision.approver_actor_id
        elif kind in {"approval_withdrawal", "publication_withdrawal"}:
            resource_actor = value.withdrawal.actor_id
        elif kind == "publication":
            resource_actor = value.publication.publisher_actor_id
        else:
            resource_actor = value.supersession.actor_id
        if resource_actor is not None and value.scope.actor_id != resource_actor:
            _error("FMEA_REVIEW_REQUEST_INVALID", "Governance actor binding is invalid.")
        if value.scope.command != value.audit.command or value.scope.key_hash != value.audit.idempotency_key_hash:
            _error("FMEA_REVIEW_REQUEST_INVALID", "Governance audit binding is invalid.")
        if value.audit.workspace_id != value.scope.workspace_id or value.audit.actor_id != value.scope.actor_id:
            _error("FMEA_REVIEW_REQUEST_INVALID", "Governance audit actor binding is invalid.")
        if value.audit.row_id != resource_id or value.audit.canonical_payload_hash != value.payload_hash:
            _error("FMEA_REVIEW_REQUEST_INVALID", "Governance audit aggregate binding is invalid.")
        if (
            value.outbox.workspace_id != value.scope.workspace_id
            or value.outbox.aggregate_id != resource_id
            or value.outbox.scope_key != value.scope.scope_key
            or value.outbox.payload_hash != outbox_payload_hash(value.outbox.payload)
            or value.outbox.aggregate_type != "fmea_governance"
        ):
            _error("FMEA_REVIEW_REQUEST_INVALID", "Governance outbox binding is invalid.")
        if value.outbox.payload_hash != value.payload_hash:
            _error("FMEA_REVIEW_REQUEST_INVALID", "Governance outbox payload hash is invalid.")
        if value.scope.key_hash != idempotency_key_hash(value.command.idempotency_key):
            _error("FMEA_REVIEW_REQUEST_INVALID", "Governance idempotency key is invalid.")
        if value.scope.resource_path != cls._expected_path(kind, value):
            _error("FMEA_REVIEW_REQUEST_INVALID", "Governance resource path is invalid.")
        return _PreparedMeta(
            kind, value.scope.workspace_id, resource_id, history_id, resource_type, value.scope.command, payload
        )

    @staticmethod
    def _lifecycle_event_type(kind: str, prepared: Any) -> str:
        if kind == "revision":
            return "revision.assembled"
        if kind == "readiness":
            return "revision.readiness"
        if kind == "approval_submission":
            return "approval.submitted"
        if kind == "approval":
            return "approval.approved" if prepared.decision.status is ApprovalStatus.APPROVED else "approval.rejected"
        if kind == "approval_withdrawal":
            return "approval.withdrawn"
        if kind == "publication":
            return "publication.published"
        if kind == "publication_withdrawal":
            return "publication.withdrawn"
        return "publication.superseded"

    @staticmethod
    def _insert_idempotency(
        connection: sqlite3.Connection, scope: IdempotencyScope, payload_hash: str, created_at: str
    ) -> None:
        connection.execute(
            "INSERT INTO idempotency_records "
            "(scope_key, payload_hash, state, status_code, resource_id, response_json, created_at, completed_at) "
            "VALUES (?, ?, 'reserved', NULL, NULL, NULL, ?, NULL)",
            (scope.scope_key, payload_hash, created_at),
        )

    @staticmethod
    def _complete_idempotency(
        connection: sqlite3.Connection,
        scope: IdempotencyScope,
        payload_hash: str,
        resource_id: str,
        result: object,
        completed_at: str,
    ) -> None:
        cursor = connection.execute(
            "UPDATE idempotency_records SET state='completed', status_code=201, resource_id=?, response_json=?, completed_at=? "
            "WHERE scope_key=? AND payload_hash=? AND state='reserved'",
            (resource_id, encode_review_json(result), completed_at, scope.scope_key, payload_hash),
        )
        if cursor.rowcount != 1:
            _error("FMEA_REVIEW_STORAGE_UNAVAILABLE", "Governance idempotency completion failed.", retryable=True)

    @staticmethod
    def _idempotency_row(connection: sqlite3.Connection, scope: IdempotencyScope) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            connection.execute("SELECT * FROM idempotency_records WHERE scope_key=?", (scope.scope_key,)).fetchone(),
        )

    @classmethod
    def _check_existing(cls, connection: sqlite3.Connection, meta: _PreparedMeta, prepared: Any) -> object | None:
        row = cls._idempotency_row(connection, prepared.scope)
        if row is None:
            return None
        if row["payload_hash"] != prepared.payload_hash:
            _error("FMEA_IDEMPOTENCY_CONFLICT", "Idempotency key was already used with a different payload.")
        if row["state"] != "completed":
            _error(
                "FMEA_REVIEW_STORAGE_UNAVAILABLE", "An incomplete governance transaction is present.", retryable=True
            )
        result = cls._decode_result(meta.kind, row["response_json"])
        if row["resource_id"] != meta.resource_id:
            raise ValueError("persisted governance idempotency resource does not match")
        cls._verify_chain(connection, meta, prepared, result)
        return replace(result, replayed=True)

    @staticmethod
    def _decode_result(kind: str, payload: object) -> object:
        data = _strict_object(payload, f"{kind} response", _RESULT_FIELDS[kind])
        if data["replayed"] is not False:
            raise ValueError("persisted governance response replay flag is invalid")
        try:
            if kind == "revision":
                result: object = RevisionResult(**data)
            elif kind == "readiness":
                result = ReadinessResult(**data)
            elif kind == "approval_submission":
                result = __import__(
                    "fmea_application.governance_contracts", fromlist=["ApprovalSubmissionResult"]
                ).ApprovalSubmissionResult(**data)
            elif kind == "approval":
                result = __import__(
                    "fmea_application.governance_contracts", fromlist=["ApprovalResult"]
                ).ApprovalResult(**data)
            elif kind == "publication":
                result = PublicationResult(**data)
            elif kind == "approval_withdrawal":
                result = ApprovalWithdrawalResult(**data)
            elif kind == "publication_withdrawal":
                result = PublicationWithdrawalResult(**data)
            else:
                result = SupersessionResult(**data)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"persisted {kind} response values are invalid") from exc
        if encode_review_json(result) != payload:
            raise ValueError(f"persisted {kind} response is not canonical")
        return result

    @classmethod
    def _verify_chain(cls, connection: sqlite3.Connection, meta: _PreparedMeta, prepared: Any, result: Any) -> None:
        result_resource_id = (
            result.readiness_id
            if meta.kind == "readiness"
            else result.revision_id
            if meta.kind == "revision"
            else result.submission_id
            if meta.kind == "approval_submission"
            else result.approval_id
            if meta.kind == "approval"
            else result.publication_id
            if meta.kind == "publication"
            else result.withdrawal_id
            if meta.kind in {"approval_withdrawal", "publication_withdrawal"}
            else result.supersession_id
        )
        if result_resource_id != meta.resource_id:
            raise ValueError("persisted governance response resource does not match authority")
        authority_table, authority_identifier = cls._authority_table(meta.kind)
        authority_row = connection.execute(
            f"SELECT * FROM {authority_table} WHERE workspace_id=? AND {authority_identifier}=?",
            (meta.workspace_id, meta.resource_id),
        ).fetchone()
        if authority_row is None:
            raise ValueError(f"persisted {meta.kind} is missing")
        cls._verify_authority_result_binding(
            meta.kind,
            authority_row,
            prepared.scope,
            prepared.payload_hash,
            result,
        )
        audit_row = connection.execute(
            "SELECT * FROM fmea_audit_events WHERE workspace_id=? AND event_id=?",
            (meta.workspace_id, result.audit_event_id),
        ).fetchone()
        if audit_row is None:
            raise ValueError("persisted governance audit event is missing")
        audit = decode_audit_event(audit_row["event_json"])
        if (
            audit.workspace_id != meta.workspace_id
            or audit.command != prepared.scope.command
            or audit.row_id != meta.resource_id
            or audit.actor_id != prepared.scope.actor_id
            or audit.idempotency_key_hash != prepared.scope.key_hash
            or audit.canonical_payload_hash != prepared.payload_hash
            or audit_row["actor_id"] != audit.actor_id
            or audit_row["actor_type"] != audit.actor_type.value
            or audit_row["command"] != audit.command
            or audit_row["resource_type"] != meta.resource_type
            or audit_row["resource_id"] != meta.history_id
            or audit_row["idempotency_scope"] != prepared.scope.scope_key
            or audit_row["canonical_payload_hash"] != prepared.payload_hash
            or _object_json(audit)[0] != audit_row["event_json"]
        ):
            raise ValueError("persisted governance audit binding is invalid")
        outbox_row = connection.execute(
            "SELECT * FROM fmea_outbox_events WHERE workspace_id=? AND event_id=?",
            (meta.workspace_id, result.outbox_event_id),
        ).fetchone()
        if outbox_row is None:
            raise ValueError("persisted governance outbox event is missing")
        outbox_payload = load_strict_json(outbox_row["payload_json"], "governance outbox")
        if (
            canonical_json(outbox_payload) != outbox_row["payload_json"]
            or canonical_json(outbox_payload) != canonical_json(prepared.payload)
            or outbox_row["workspace_id"] != meta.workspace_id
            or outbox_row["aggregate_type"] != "fmea_governance"
            or outbox_row["aggregate_id"] != meta.resource_id
            or outbox_row["event_type"] != cls._lifecycle_event_type(meta.kind, prepared)
            or outbox_row["payload_hash"] != prepared.payload_hash
        ):
            raise ValueError("persisted governance outbox is not canonical")
        if (
            outbox_row["payload_hash"] != outbox_payload_hash(outbox_payload)
            or outbox_row["idempotency_scope"] != prepared.scope.scope_key
        ):
            raise ValueError("persisted governance outbox binding is invalid")
        cls._verify_event_binding(
            connection,
            meta.kind,
            meta.workspace_id,
            meta.resource_id,
            result.audit_event_id,
            result.outbox_event_id,
        )
        if meta.kind == "revision":
            revision = cls._revision_from_connection(connection, meta.resource_id, meta.workspace_id)
            if revision != prepared.revision or result.record_version != 1:
                raise ValueError("persisted revision result binding is invalid")
        elif meta.kind == "readiness":
            record = cls._readiness_from_connection(connection, meta.resource_id, meta.workspace_id)
            if (
                record.report != prepared.report
                or record.source_hashes != prepared.source_hashes
                or result.record_version != 1
            ):
                raise ValueError("persisted readiness result binding is invalid")
        elif meta.kind == "approval_submission":
            if cls._submission_from_connection(connection, meta.resource_id, meta.workspace_id) != prepared.submission:
                raise ValueError("persisted approval submission result binding is invalid")
        elif meta.kind == "approval":
            if cls._approval_from_connection(connection, meta.resource_id, meta.workspace_id) != prepared.decision:
                raise ValueError("persisted approval result binding is invalid")
        elif meta.kind == "publication":
            publication = cls._publication_from_connection(connection, meta.resource_id, meta.workspace_id)
            manifest = cls._manifest_from_connection(connection, result.manifest_id, meta.workspace_id)
            snapshot = cls._snapshot_from_connection(connection, result.snapshot_id, meta.workspace_id)
            eligibility = cls._eligibility_from_connection(connection, meta.resource_id, meta.workspace_id)
            if (
                publication != prepared.publication
                or manifest != prepared.manifest
                or snapshot != prepared.snapshot
                or eligibility != prepared.export_eligibility
                or result.manifest_id != publication.manifest_id
                or result.snapshot_id != publication.snapshot_id
                or result.record_version != publication.record_version
            ):
                raise ValueError("persisted publication result binding is invalid")
            cls._verify_persisted_dependency_chain(
                connection,
                "revision",
                meta.workspace_id,
                prepared.revision.revision_id,
            )
            cls._verify_persisted_dependency_chain(
                connection,
                "approval_submission",
                meta.workspace_id,
                prepared.submission.submission_id,
            )
            cls._verify_persisted_dependency_chain(
                connection,
                "approval",
                meta.workspace_id,
                prepared.approval.approval_id,
            )
        elif meta.kind == "approval_withdrawal":
            row = connection.execute(
                "SELECT withdrawal_json,canonical_json_hash FROM fmea_approval_withdrawals "
                "WHERE workspace_id=? AND withdrawal_id=?",
                (meta.workspace_id, meta.resource_id),
            ).fetchone()
            if row is None or _decode_approval_withdrawal(row["withdrawal_json"]) != prepared.withdrawal:
                raise ValueError("persisted approval withdrawal result binding is invalid")
        elif meta.kind == "publication_withdrawal":
            row = connection.execute(
                "SELECT withdrawal_json FROM fmea_publication_withdrawals WHERE workspace_id=? AND withdrawal_id=?",
                (meta.workspace_id, meta.resource_id),
            ).fetchone()
            if row is None or _decode_publication_withdrawal(row["withdrawal_json"]) != prepared.withdrawal:
                raise ValueError("persisted publication withdrawal result binding is invalid")
        else:
            row = connection.execute(
                "SELECT supersession_json FROM fmea_supersessions WHERE workspace_id=? AND supersession_id=?",
                (meta.workspace_id, meta.resource_id),
            ).fetchone()
            if row is None or _decode_supersession(row["supersession_json"]) != prepared.supersession:
                raise ValueError("persisted supersession result binding is invalid")

    @classmethod
    def _verify_replay_chain(
        cls,
        connection: sqlite3.Connection,
        kind: str,
        scope: IdempotencyScope,
        payload_hash: str,
        result: Any,
    ) -> None:
        if kind == "revision":
            resource_id = result.revision_id
        elif kind == "readiness":
            resource_id = result.readiness_id
        elif kind == "approval_submission":
            resource_id = result.submission_id
        elif kind == "approval":
            resource_id = result.approval_id
        elif kind in {"approval_withdrawal", "publication_withdrawal"}:
            resource_id = result.withdrawal_id
        elif kind == "publication":
            resource_id = result.publication_id
        else:
            resource_id = result.supersession_id
        table, identifier = cls._authority_table(kind)
        authority_row = connection.execute(
            f"SELECT * FROM {table} WHERE workspace_id=? AND {identifier}=?",
            (scope.workspace_id, resource_id),
        ).fetchone()
        if authority_row is None:
            raise ValueError(f"persisted {kind} is missing")
        cls._verify_authority_result_binding(kind, authority_row, scope, payload_hash, result)
        if kind == "readiness":
            history_id = authority_row["revision_id"]
            expected_resource_type = "revision"
        elif kind in {"revision"}:
            history_id = resource_id
            expected_resource_type = "revision"
        elif kind in {"approval_submission", "approval", "approval_withdrawal"}:
            history_id = authority_row["revision_id"]
            expected_resource_type = "approval"
        elif kind in {"publication", "publication_withdrawal"}:
            history_id = authority_row["publication_id"]
            expected_resource_type = "publication"
        else:
            history_id = authority_row["old_publication_id"]
            expected_resource_type = "publication"
        audit_row = connection.execute(
            "SELECT * FROM fmea_audit_events WHERE workspace_id=? AND event_id=?",
            (scope.workspace_id, result.audit_event_id),
        ).fetchone()
        if audit_row is None:
            raise ValueError("persisted governance audit event is missing")
        audit = decode_audit_event(audit_row["event_json"])
        expected_command = {
            "revision": "fmea.revision.assemble",
            "readiness": "fmea.revision.readiness",
            "approval_submission": "fmea.approval.submit",
            "approval": "fmea.approval.decide",
            "approval_withdrawal": "fmea.approval.withdraw",
            "publication": "fmea.publication.publish",
            "publication_withdrawal": "fmea.publication.withdraw",
            "supersession": "fmea.publication.supersede",
        }[kind]
        actor_column = {
            "approval_submission": "submitter_actor_id",
            "approval": "approver_actor_id",
            "approval_withdrawal": "actor_id",
            "publication": "publisher_actor_id",
            "publication_withdrawal": "actor_id",
            "supersession": "actor_id",
        }.get(kind)
        if (
            scope.command != expected_command
            or audit.workspace_id != scope.workspace_id
            or audit.command != scope.command
            or audit.row_id != resource_id
            or audit.actor_id != scope.actor_id
            or audit.idempotency_key_hash != scope.key_hash
            or audit.canonical_payload_hash != payload_hash
            or audit_row["actor_id"] != audit.actor_id
            or audit_row["actor_type"] != audit.actor_type.value
            or audit_row["command"] != audit.command
            or audit_row["resource_type"] != expected_resource_type
            or audit_row["resource_id"] != history_id
            or audit_row["idempotency_scope"] != scope.scope_key
            or audit_row["canonical_payload_hash"] != payload_hash
            or _object_json(audit)[0] != audit_row["event_json"]
            or (actor_column is not None and authority_row[actor_column] != audit.actor_id)
        ):
            raise ValueError("persisted governance audit binding is invalid")
        cls._verify_event_binding(
            connection,
            kind,
            scope.workspace_id,
            resource_id,
            result.audit_event_id,
            result.outbox_event_id,
        )
        outbox_row = connection.execute(
            "SELECT * FROM fmea_outbox_events WHERE workspace_id=? AND event_id=?",
            (scope.workspace_id, result.outbox_event_id),
        ).fetchone()
        if outbox_row is None:
            raise ValueError("persisted governance outbox event is missing")
        outbox_payload = load_strict_json(outbox_row["payload_json"], "governance outbox")
        expected_outbox_payload = cls._expected_persisted_event_payload(connection, kind, authority_row)
        expected_event_type = {
            "revision": "revision.assembled",
            "readiness": "revision.readiness",
            "approval_submission": "approval.submitted",
            "approval_withdrawal": "approval.withdrawn",
            "publication": "publication.published",
            "publication_withdrawal": "publication.withdrawn",
            "supersession": "publication.superseded",
        }.get(kind)
        if kind == "approval":
            expected_event_type = "approval." + str(authority_row["status"])
        if (
            canonical_json(outbox_payload) != outbox_row["payload_json"]
            or canonical_json(outbox_payload) != canonical_json(expected_outbox_payload)
            or governance_payload_hash(expected_outbox_payload) != payload_hash
            or outbox_row["workspace_id"] != scope.workspace_id
            or outbox_row["aggregate_type"] != "fmea_governance"
            or outbox_row["aggregate_id"] != resource_id
            or outbox_row["event_type"] != expected_event_type
            or outbox_row["idempotency_scope"] != scope.scope_key
            or outbox_row["payload_hash"] != outbox_payload_hash(outbox_payload)
            or outbox_row["payload_hash"] != payload_hash
        ):
            raise ValueError("persisted governance outbox binding is invalid")
        if kind == "revision":
            if (
                result.record_version != 1
                or cls._revision_from_connection(connection, resource_id, scope.workspace_id).revision_id != resource_id
            ):
                raise ValueError("persisted revision result binding is invalid")
        elif kind == "readiness":
            if (
                result.record_version != 1
                or cls._readiness_from_connection(connection, resource_id, scope.workspace_id).readiness_id
                != resource_id
            ):
                raise ValueError("persisted readiness result binding is invalid")
        elif kind == "approval_submission":
            cls._submission_from_connection(connection, resource_id, scope.workspace_id)
        elif kind == "approval":
            cls._approval_from_connection(connection, resource_id, scope.workspace_id)
        elif kind == "publication":
            publication = cls._publication_from_connection(connection, resource_id, scope.workspace_id)
            manifest = cls._manifest_from_connection(connection, result.manifest_id, scope.workspace_id)
            snapshot = cls._snapshot_from_connection(connection, result.snapshot_id, scope.workspace_id)
            eligibility = cls._eligibility_from_connection(connection, resource_id, scope.workspace_id)
            revision = cls._revision_from_connection(connection, publication.revision_id, scope.workspace_id)
            approval = cls._approval_from_connection(connection, publication.approval_id, scope.workspace_id)
            submission = cls._submission_from_connection(connection, approval.submission_id, scope.workspace_id)
            if (
                result.record_version != publication.record_version
                or result.manifest_id != publication.manifest_id
                or result.snapshot_id != publication.snapshot_id
                or manifest.revision_id != revision.revision_id
                or manifest.revision_hash != revision.revision_hash
                or manifest.approval_id != publication.approval_id
                or manifest.snapshot_id != snapshot.snapshot_id
                or manifest.snapshot_hash != snapshot.snapshot_hash
                or snapshot.publication_id != publication.publication_id
                or snapshot.manifest_id != manifest.manifest_id
                or eligibility.publication_id != publication.publication_id
                or eligibility.manifest_id != manifest.manifest_id
                or eligibility.eligible is not manifest.export_eligible
                or dict(eligibility.source_hashes).get("revision") != revision.revision_hash
                or dict(eligibility.source_hashes).get("manifest") != manifest.manifest_hash
                or dict(eligibility.source_hashes).get("snapshot") != snapshot.snapshot_hash
                or approval.revision_id != revision.revision_id
                or approval.revision_hash != revision.revision_hash
                or submission.submission_id != approval.submission_id
                or submission.revision_id != revision.revision_id
                or submission.revision_hash != revision.revision_hash
            ):
                raise ValueError("persisted publication lineage is invalid")
            cls._verify_persisted_dependency_chain(
                connection,
                "revision",
                scope.workspace_id,
                revision.revision_id,
            )
            cls._verify_persisted_dependency_chain(
                connection,
                "approval_submission",
                scope.workspace_id,
                submission.submission_id,
            )
            cls._verify_persisted_dependency_chain(
                connection,
                "approval",
                scope.workspace_id,
                approval.approval_id,
            )
        elif kind == "approval_withdrawal":
            value = _decode_approval_withdrawal(authority_row["withdrawal_json"])
            if (
                _object_json(value)[0] != authority_row["withdrawal_json"]
                or authority_row["canonical_json_hash"] != _json_hash(authority_row["withdrawal_json"])
                or authority_row["audit_event_id"] != result.audit_event_id
                or authority_row["outbox_event_id"] != result.outbox_event_id
            ):
                raise ValueError("persisted approval withdrawal binding is invalid")
        elif kind == "publication_withdrawal":
            value = _decode_publication_withdrawal(authority_row["withdrawal_json"])
            if (
                _object_json(value)[0] != authority_row["withdrawal_json"]
                or authority_row["canonical_json_hash"] != _json_hash(authority_row["withdrawal_json"])
                or authority_row["audit_event_id"] != result.audit_event_id
                or authority_row["outbox_event_id"] != result.outbox_event_id
            ):
                raise ValueError("persisted publication withdrawal binding is invalid")
        elif (
            _object_json(_decode_supersession(authority_row["supersession_json"]))[0]
            != authority_row["supersession_json"]
            or authority_row["canonical_json_hash"] != _json_hash(authority_row["supersession_json"])
            or authority_row["audit_event_id"] != result.audit_event_id
            or authority_row["outbox_event_id"] != result.outbox_event_id
        ):
            raise ValueError("persisted supersession binding is invalid")

    @classmethod
    def _verify_persisted_dependency_chain(
        cls,
        connection: sqlite3.Connection,
        kind: str,
        workspace_id: str,
        resource_id: str,
    ) -> None:
        table, identifier = cls._authority_table(kind)
        authority_row = connection.execute(
            f"SELECT * FROM {table} WHERE workspace_id=? AND {identifier}=?",
            (workspace_id, resource_id),
        ).fetchone()
        if authority_row is None:
            raise ValueError(f"persisted publication {kind} dependency is missing")
        audit_row = connection.execute(
            "SELECT event_json FROM fmea_audit_events WHERE workspace_id=? AND event_id=?",
            (workspace_id, authority_row["audit_event_id"]),
        ).fetchone()
        if audit_row is None:
            raise ValueError(f"persisted publication {kind} dependency audit is missing")
        audit = decode_audit_event(audit_row["event_json"])
        if kind == "revision":
            path = f"/fmea/analyses/{authority_row['analysis_id']}/revisions"
        elif kind == "approval_submission":
            path = f"/fmea/revisions/{authority_row['revision_id']}/approval-submissions"
        else:
            path = f"/fmea/approval-submissions/{authority_row['submission_id']}/decision"
        dependency_scope = IdempotencyScope(
            workspace_id,
            audit.actor_id,
            audit.command,
            path,
            audit.idempotency_key_hash,
        )
        payload_hash = _hash(authority_row["payload_hash"], f"{kind} payload_hash")
        idempotency = cls._idempotency_row(connection, dependency_scope)
        if (
            authority_row["idempotency_scope"] != dependency_scope.scope_key
            or idempotency is None
            or idempotency["payload_hash"] != payload_hash
            or idempotency["state"] != "completed"
            or idempotency["resource_id"] != resource_id
        ):
            raise ValueError(f"persisted publication {kind} dependency idempotency is invalid")
        result = cls._decode_result(kind, idempotency["response_json"])
        cls._verify_replay_chain(connection, kind, dependency_scope, payload_hash, result)

    @classmethod
    def _expected_persisted_event_payload(
        cls,
        connection: sqlite3.Connection,
        kind: str,
        authority_row: sqlite3.Row,
    ) -> Mapping[str, object]:
        if kind == "revision":
            revision = cls._revision_from_connection(
                connection,
                authority_row["revision_id"],
                authority_row["workspace_id"],
            )
            command = {
                "request": {
                    "analysis_id": revision.analysis_id,
                    "parent_revision_id": revision.parent_revision_id,
                    "expected_analysis_version": revision.analysis_record_version,
                    "parent_revision_hash": revision.parent_revision_hash,
                }
            }
            return canonical_governance_payload("revision.assemble", command, revision=revision)
        if kind == "readiness":
            record = cls._readiness_from_connection(
                connection,
                authority_row["readiness_id"],
                authority_row["workspace_id"],
            )
            command = {
                "revision_id": authority_row["revision_id"],
                "revision_hash": authority_row["revision_hash"],
                "expected_revision_version": authority_row["target_record_version"],
                "readiness_id": authority_row["readiness_id"],
            }
            return canonical_governance_payload(
                "revision.readiness",
                command,
                report=record.report,
                source_hashes=record.source_hashes,
            )
        if kind == "approval_submission":
            submission = cls._submission_from_connection(
                connection,
                authority_row["submission_id"],
                authority_row["workspace_id"],
            )
            revision_row = connection.execute(
                "SELECT record_version FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
                (authority_row["workspace_id"], submission.revision_id),
            ).fetchone()
            if revision_row is None:
                raise ValueError("persisted submission revision is missing")
            command = {
                "revision_id": submission.revision_id,
                "revision_hash": submission.revision_hash,
                "expected_revision_version": revision_row["record_version"],
            }
            return canonical_governance_payload("approval.submit", command, submission=submission)
        if kind == "approval":
            decision = cls._approval_from_connection(
                connection,
                authority_row["approval_id"],
                authority_row["workspace_id"],
            )
            submission = cls._submission_from_connection(
                connection,
                decision.submission_id,
                authority_row["workspace_id"],
            )
            command = {
                "submission_id": decision.submission_id,
                "revision_id": decision.revision_id,
                "revision_hash": decision.revision_hash,
                "expected_submission_version": submission.record_version,
                "reason": decision.reason,
            }
            return canonical_governance_payload(
                "approval.decide",
                command,
                submission=submission,
                decision=decision,
            )
        if kind == "approval_withdrawal":
            withdrawal = _decode_approval_withdrawal(authority_row["withdrawal_json"])
            approval = cls._approval_from_connection(
                connection,
                withdrawal.approval_id,
                authority_row["workspace_id"],
            )
            command = {
                "approval_id": approval.approval_id,
                "revision_hash": approval.revision_hash,
                "expected_approval_version": approval.record_version,
                "reason": withdrawal.reason,
            }
            return canonical_governance_payload(
                "approval.withdraw",
                command,
                approval=approval,
                withdrawal=withdrawal,
            )
        if kind == "publication":
            publication = cls._publication_from_connection(
                connection,
                authority_row["publication_id"],
                authority_row["workspace_id"],
            )
            revision = cls._revision_from_connection(
                connection,
                publication.revision_id,
                authority_row["workspace_id"],
            )
            revision_row = connection.execute(
                "SELECT record_version FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
                (authority_row["workspace_id"], revision.revision_id),
            ).fetchone()
            if revision_row is None:
                raise ValueError("persisted publication revision is missing")
            approval = cls._approval_from_connection(
                connection,
                publication.approval_id,
                authority_row["workspace_id"],
            )
            submission = cls._submission_from_connection(
                connection,
                approval.submission_id,
                authority_row["workspace_id"],
            )
            manifest = cls._manifest_from_connection(
                connection,
                publication.manifest_id,
                authority_row["workspace_id"],
            )
            snapshot = cls._snapshot_from_connection(
                connection,
                publication.snapshot_id,
                authority_row["workspace_id"],
            )
            eligibility = cls._eligibility_from_connection(
                connection,
                publication.publication_id,
                authority_row["workspace_id"],
            )
            command = {
                "revision_id": revision.revision_id,
                "revision_hash": revision.revision_hash,
                "approval_id": approval.approval_id,
                "expected_revision_version": revision_row["record_version"],
            }
            return canonical_governance_payload(
                "publication.publish",
                command,
                revision=revision,
                approval=approval,
                submission=submission,
                manifest=manifest,
                publication=publication,
                snapshot=snapshot,
                export_eligibility=eligibility,
            )
        if kind == "publication_withdrawal":
            withdrawal = _decode_publication_withdrawal(authority_row["withdrawal_json"])
            publication = cls._publication_from_connection(
                connection,
                withdrawal.publication_id,
                authority_row["workspace_id"],
            )
            command = {
                "publication_id": publication.publication_id,
                "expected_publication_version": publication.record_version,
                "reason": withdrawal.reason,
                "replacement_publication_id": withdrawal.replacement_publication_id,
            }
            return canonical_governance_payload(
                "publication.withdraw",
                command,
                publication=publication,
                withdrawal=withdrawal,
            )
        supersession = _decode_supersession(authority_row["supersession_json"])
        old = cls._publication_from_connection(
            connection,
            supersession.old_publication_id,
            authority_row["workspace_id"],
        )
        replacement_publication = cls._publication_from_connection(
            connection,
            supersession.new_publication_id,
            authority_row["workspace_id"],
        )
        old_revision = cls._revision_from_connection(
            connection,
            old.revision_id,
            authority_row["workspace_id"],
        )
        replacement_revision = cls._revision_from_connection(
            connection,
            replacement_publication.revision_id,
            authority_row["workspace_id"],
        )
        command = {
            "publication_id": old.publication_id,
            "replacement_publication_id": replacement_publication.publication_id,
            "expected_publication_version": old.record_version,
            "expected_replacement_version": replacement_publication.record_version,
            "reason": supersession.reason,
        }
        return canonical_governance_payload(
            "publication.supersede",
            command,
            old=old,
            replacement=replacement_publication,
            old_revision=old_revision,
            replacement_revision=replacement_revision,
            supersession=supersession,
        )

    @classmethod
    def _insert_audit(
        cls,
        connection: sqlite3.Connection,
        event: AuditEvent,
        scope: IdempotencyScope,
        payload_hash: str,
        meta: _PreparedMeta,
    ) -> None:
        event_json, _ = _object_json(event)
        connection.execute(
            "INSERT INTO fmea_audit_events "
            "(workspace_id,event_id,resource_type,resource_id,actor_id,actor_type,command,idempotency_scope,canonical_payload_hash,event_json,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                meta.workspace_id,
                event.event_id,
                meta.resource_type,
                meta.history_id,
                event.actor_id,
                event.actor_type.value,
                event.command,
                scope.scope_key,
                payload_hash,
                event_json,
                event.occurred_at_server,
            ),
        )

    @classmethod
    def _insert_outbox(
        cls,
        connection: sqlite3.Connection,
        event: OutboxEvent,
        scope: IdempotencyScope,
        meta: _PreparedMeta,
        event_type: str,
    ) -> None:
        payload_json = canonical_json(event.payload)
        connection.execute(
            "INSERT INTO fmea_outbox_events "
            "(event_id,workspace_id,aggregate_type,aggregate_id,event_type,status,payload_json,payload_hash,idempotency_scope,created_at) "
            "VALUES (?,?,?,?,?,'pending',?,?,?,?)",
            (
                event.event_id,
                meta.workspace_id,
                "fmea_governance",
                meta.resource_id,
                event_type,
                payload_json,
                outbox_payload_hash(event.payload),
                scope.scope_key,
                event.created_at,
            ),
        )

    @staticmethod
    def _authority_table(kind: str) -> tuple[str, str]:
        return {
            "revision": ("fmea_revisions", "revision_id"),
            "readiness": ("fmea_revision_readiness_reports", "readiness_id"),
            "approval_submission": ("fmea_approval_submissions", "submission_id"),
            "approval": ("fmea_approval_decisions", "approval_id"),
            "approval_withdrawal": ("fmea_approval_withdrawals", "withdrawal_id"),
            "publication": ("fmea_publications", "publication_id"),
            "publication_withdrawal": ("fmea_publication_withdrawals", "withdrawal_id"),
            "supersession": ("fmea_supersessions", "supersession_id"),
        }[kind]

    @classmethod
    def _verify_authority_result_binding(
        cls,
        kind: str,
        authority_row: sqlite3.Row,
        scope: IdempotencyScope,
        payload_hash: str,
        result: Any,
    ) -> None:
        if (
            authority_row["idempotency_scope"] != scope.scope_key
            or authority_row["payload_hash"] != payload_hash
            or authority_row["audit_event_id"] != result.audit_event_id
            or authority_row["outbox_event_id"] != result.outbox_event_id
        ):
            raise ValueError(f"persisted {kind} authority chain is invalid")
        valid = False
        if kind == "revision":
            valid = (
                result.revision_id == authority_row["revision_id"]
                and result.record_version == authority_row["record_version"]
            )
        elif kind == "readiness":
            valid = result.readiness_id == authority_row["readiness_id"] and result.record_version == 1
        elif kind == "approval_submission":
            valid = (
                result.submission_id == authority_row["submission_id"]
                and result.record_version == authority_row["record_version"]
            )
        elif kind == "approval":
            valid = (
                result.approval_id == authority_row["approval_id"]
                and result.record_version == authority_row["record_version"]
            )
        elif kind == "approval_withdrawal":
            valid = (
                result.withdrawal_id == authority_row["withdrawal_id"]
                and result.approval_id == authority_row["approval_id"]
            )
        elif kind == "publication":
            valid = (
                result.publication_id == authority_row["publication_id"]
                and result.manifest_id == authority_row["manifest_id"]
                and result.snapshot_id == authority_row["snapshot_id"]
                and result.record_version == authority_row["record_version"]
            )
        elif kind == "publication_withdrawal":
            valid = (
                result.withdrawal_id == authority_row["withdrawal_id"]
                and result.publication_id == authority_row["publication_id"]
            )
        else:
            valid = (
                result.supersession_id == authority_row["supersession_id"]
                and result.old_publication_id == authority_row["old_publication_id"]
                and result.new_publication_id == authority_row["new_publication_id"]
            )
        if not valid:
            raise ValueError(f"persisted {kind} result binding is invalid")

    @classmethod
    def _insert_event_binding(cls, connection: sqlite3.Connection, meta: _PreparedMeta, result: Any) -> None:
        connection.execute(
            "INSERT INTO fmea_governance_event_bindings "
            "(workspace_id,resource_type,resource_id,audit_event_id,outbox_event_id) VALUES (?,?,?,?,?)",
            (
                meta.workspace_id,
                meta.kind,
                meta.resource_id,
                result.audit_event_id,
                result.outbox_event_id,
            ),
        )

    @classmethod
    def _verify_event_binding(
        cls,
        connection: sqlite3.Connection,
        kind: str,
        workspace_id: str,
        resource_id: str,
        audit_event_id: str,
        outbox_event_id: str,
    ) -> None:
        binding = connection.execute(
            "SELECT audit_event_id,outbox_event_id FROM fmea_governance_event_bindings "
            "WHERE workspace_id=? AND resource_type=? AND resource_id=?",
            (workspace_id, kind, resource_id),
        ).fetchone()
        if binding is None or (
            binding["audit_event_id"] != audit_event_id or binding["outbox_event_id"] != outbox_event_id
        ):
            raise ValueError("persisted governance authority event binding is invalid")
        table, identifier = cls._authority_table(kind)
        authority = connection.execute(
            f"SELECT audit_event_id,outbox_event_id FROM {table} WHERE workspace_id=? AND {identifier}=?",
            (workspace_id, resource_id),
        ).fetchone()
        if authority is None or (
            authority["audit_event_id"] != audit_event_id or authority["outbox_event_id"] != outbox_event_id
        ):
            raise ValueError("persisted governance authority row is not bound to its result chain")

    @classmethod
    def _validate_authoritative_analysis(cls, connection: sqlite3.Connection, revision: FmeaRevision) -> None:
        row = connection.execute("SELECT * FROM fmea_analyses WHERE analysis_id=?", (revision.analysis_id,)).fetchone()
        if row is None:
            _error("FMEA_VERSION_CONFLICT", "Authoritative analysis is missing.")
        try:
            analysis = SqliteFmeaRepository._decode_analysis_record(row)
        except (TypeError, ValueError):
            _error("FMEA_VERSION_CONFLICT", "Authoritative analysis payload is invalid.")
        if (
            row["workspace_id"] != revision.workspace_id
            or analysis.analysis_id != revision.analysis_id
            or analysis.record_version != revision.analysis_record_version
            or str(row["analysis_hash"]).removeprefix("sha256:") != revision.analysis_hash.removeprefix("sha256:")
        ):
            _error("FMEA_VERSION_CONFLICT", "Authoritative analysis state is stale or cross-workspace.")

    @classmethod
    def _insert_revision_analysis_binding(cls, connection: sqlite3.Connection, revision: FmeaRevision) -> None:
        connection.execute(
            "INSERT INTO fmea_revision_analysis_bindings "
            "(workspace_id,revision_id,analysis_id,analysis_record_version,analysis_hash) VALUES (?,?,?,?,?)",
            (
                revision.workspace_id,
                revision.revision_id,
                revision.analysis_id,
                revision.analysis_record_version,
                revision.analysis_hash,
            ),
        )

    @classmethod
    def _verify_revision_analysis_binding(cls, connection: sqlite3.Connection, revision: FmeaRevision) -> None:
        row = connection.execute(
            "SELECT analysis_id,analysis_record_version,analysis_hash "
            "FROM fmea_revision_analysis_bindings WHERE workspace_id=? AND revision_id=?",
            (revision.workspace_id, revision.revision_id),
        ).fetchone()
        if row is None or (
            row["analysis_id"] != revision.analysis_id
            or row["analysis_record_version"] != revision.analysis_record_version
            or str(row["analysis_hash"]).removeprefix("sha256:") != revision.analysis_hash.removeprefix("sha256:")
        ):
            raise ValueError("persisted revision analysis lineage binding is invalid")

    @classmethod
    def _insert_publication_lineage_binding(cls, connection: sqlite3.Connection, prepared: PreparedPublication) -> None:
        connection.execute(
            "INSERT INTO fmea_publication_lineage_bindings "
            "(workspace_id,publication_id,manifest_id,snapshot_id,revision_id,analysis_id,revision_hash,manifest_hash,snapshot_hash) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                prepared.scope.workspace_id,
                prepared.publication.publication_id,
                prepared.manifest.manifest_id,
                prepared.snapshot.snapshot_id,
                prepared.revision.revision_id,
                prepared.revision.analysis_id,
                prepared.revision.revision_hash,
                prepared.manifest.manifest_hash,
                prepared.snapshot.snapshot_hash,
            ),
        )

    @classmethod
    def _verify_publication_lineage_binding(
        cls, connection: sqlite3.Connection, publication: PublishedRevision
    ) -> None:
        row = connection.execute(
            "SELECT manifest_id,snapshot_id,revision_id,analysis_id,revision_hash,manifest_hash,snapshot_hash "
            "FROM fmea_publication_lineage_bindings WHERE workspace_id=? AND publication_id=?",
            (publication.workspace_id, publication.publication_id),
        ).fetchone()
        expected = (
            publication.manifest_id,
            publication.snapshot_id,
            publication.revision_id,
            publication.analysis_id,
            publication.revision_hash,
            publication.manifest_hash,
            publication.snapshot_hash,
        )
        if row is None or tuple(row) != expected:
            raise ValueError("persisted publication manifest snapshot lineage binding is invalid")

    @classmethod
    def _snapshot_from_connection(cls, connection: sqlite3.Connection, snapshot_id: str, workspace_id: str) -> Any:
        from fmea_application.snapshot_contracts import NormalizedFmeaSnapshot

        row = connection.execute(
            "SELECT * FROM fmea_normalized_snapshots WHERE workspace_id=? AND snapshot_id=?",
            (workspace_id, snapshot_id),
        ).fetchone()
        if row is None:
            raise ValueError("persisted normalized snapshot is missing")
        data = _strict_object(
            row["snapshot_json"], "normalized snapshot", {field.name for field in fields(NormalizedFmeaSnapshot)}
        )
        try:
            value = NormalizedFmeaSnapshot(
                schema_version=cast(Any, data["schema_version"]),
                snapshot_id=cast(str, data["snapshot_id"]),
                workspace_id=cast(str, data["workspace_id"]),
                analysis_id=cast(str, data["analysis_id"]),
                revision_id=cast(str, data["revision_id"]),
                revision_hash=cast(str, data["revision_hash"]),
                publication_id=cast(str, data["publication_id"]),
                manifest_id=cast(str, data["manifest_id"]),
                rows=tuple(_mapping(item, "snapshot row") for item in _sequence(data["rows"], "snapshot rows")),
                risk_records=tuple(
                    _mapping(item, "snapshot risk") for item in _sequence(data["risk_records"], "snapshot risks")
                ),
                propagation=None
                if data["propagation"] is None
                else _mapping(data["propagation"], "snapshot propagation"),
                evidence_summary=tuple(
                    _mapping(item, "snapshot evidence")
                    for item in _sequence(data["evidence_summary"], "snapshot evidence")
                ),
                decision_summary=tuple(
                    _mapping(item, "snapshot decision")
                    for item in _sequence(data["decision_summary"], "snapshot decisions")
                ),
                version_manifest=_mapping(data["version_manifest"], "snapshot version manifest"),
                unresolved_items=tuple(
                    _mapping(item, "snapshot unresolved")
                    for item in _sequence(data["unresolved_items"], "snapshot unresolved")
                ),
                audit_summary=_mapping(data["audit_summary"], "snapshot audit"),
                row_count=cast(int, data["row_count"]),
                snapshot_hash=cast(str, data["snapshot_hash"]),
                created_at=cast(str, data["created_at"]),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("persisted normalized snapshot is invalid") from exc
        if (
            value.workspace_id != workspace_id
            or value.snapshot_id != row["snapshot_id"]
            or value.publication_id != row["publication_id"]
            or value.manifest_id != row["manifest_id"]
            or value.revision_id != row["revision_id"]
            or value.analysis_id != row["analysis_id"]
            or value.revision_hash != row["revision_hash"]
            or value.snapshot_hash != row["snapshot_hash"]
            or row["canonical_json_hash"] != _json_hash(row["snapshot_json"])
            or _object_json(value)[0] != row["snapshot_json"]
        ):
            raise ValueError("persisted normalized snapshot identity or hash is invalid")
        return value

    @classmethod
    def _readiness_from_connection(
        cls, connection: sqlite3.Connection, readiness_id: str, workspace_id: str
    ) -> ReadinessReportRecord:
        row = connection.execute(
            "SELECT * FROM fmea_revision_readiness_reports WHERE workspace_id=? AND readiness_id=?",
            (workspace_id, readiness_id),
        ).fetchone()
        if row is None:
            raise ValueError("persisted readiness report is missing")
        report = _decode_readiness(row["report_json"])
        source_json = row["source_hashes_json"]
        if source_json is None:
            raise ValueError("persisted readiness source hashes are missing")
        source_hashes = _decode_source_hashes(source_json)
        blocking_codes_json = canonical_json(report.blocking_codes)
        record = ReadinessReportRecord(
            readiness_id=readiness_id,
            report=report,
            source_hashes=source_hashes,
            report_hash=cast(str, row["report_hash"]),
            canonical_json_hash=cast(str, row["canonical_json_hash"]),
            created_at=cast(str, row["created_at"]),
        )
        if (
            row["workspace_id"] != workspace_id
            or row["revision_id"] != report.revision_id
            or row["revision_hash"] != report.revision_hash
            or row["target_record_version"] != report.target_record_version
            or bool(row["ready"]) is not report.ready
            or row["blocking_codes_json"] != blocking_codes_json
            or row["report_hash"] != canonical_hash(report, prefixed=True)
            or row["canonical_json_hash"] != record.canonical_json_hash
            or row["report_json"] != _object_json(report)[0]
            or row["idempotency_scope"] is None
            or row["payload_hash"] is None
            or row["audit_event_id"] is None
            or row["outbox_event_id"] is None
        ):
            raise ValueError("persisted readiness report identity or hash is invalid")
        return record

    @classmethod
    def _eligibility_from_connection(
        cls, connection: sqlite3.Connection, publication_id: str, workspace_id: str
    ) -> ExportEligibilityRecord:
        row = connection.execute(
            "SELECT * FROM fmea_export_eligibility WHERE workspace_id=? AND publication_id=?",
            (workspace_id, publication_id),
        ).fetchone()
        if row is None:
            raise ValueError("persisted export eligibility is missing")
        value = _decode_export_eligibility(row["eligibility_json"])
        source_json = row["source_hashes_json"]
        if source_json is None or _decode_source_hashes(source_json) != value.source_hashes:
            raise ValueError("persisted export eligibility source hashes are invalid")
        if (
            value.workspace_id != workspace_id
            or value.publication_id != publication_id
            or value.manifest_id != row["manifest_id"]
            or value.eligible is not bool(row["eligible"])
            or value.eligibility_hash != row["eligibility_hash"]
            or row["canonical_json_hash"] != _object_json(value)[1]
        ):
            raise ValueError("persisted export eligibility identity or hash is invalid")
        return value

    @classmethod
    def _revision_from_connection(
        cls, connection: sqlite3.Connection, revision_id: str, workspace_id: str
    ) -> FmeaRevision:
        row = connection.execute(
            "SELECT * FROM fmea_revisions WHERE workspace_id=? AND revision_id=?", (workspace_id, revision_id)
        ).fetchone()
        if row is None:
            raise ValueError("persisted revision is missing")
        payload = cast(str, row["revision_json"])
        value = _decode_revision(payload)
        if (
            value.workspace_id != workspace_id
            or value.revision_id != revision_id
            or value.analysis_id != row["analysis_id"]
            or value.parent_revision_id != row["parent_revision_id"]
            or value.parent_revision_hash != row["parent_revision_hash"]
            or value.revision_hash != row["revision_hash"]
            or row["canonical_json_hash"] != _json_hash(payload)
            or value.analysis_record_version != row["analysis_record_version"]
            or row["record_version"] != 1
        ):
            raise ValueError("persisted revision identity or hash is invalid")
        cls._verify_revision_analysis_binding(connection, value)
        return value

    @classmethod
    def _submission_from_connection(
        cls, connection: sqlite3.Connection, submission_id: str, workspace_id: str
    ) -> ApprovalSubmission:
        row = connection.execute(
            "SELECT * FROM fmea_approval_submissions WHERE workspace_id=? AND submission_id=?",
            (workspace_id, submission_id),
        ).fetchone()
        if row is None:
            raise ValueError("persisted approval submission is missing")
        payload = cast(str, row["submission_json"])
        value = _decode_submission(payload)
        if (
            value.workspace_id != workspace_id
            or value.submission_id != submission_id
            or value.revision_id != row["revision_id"]
            or value.revision_hash != row["revision_hash"]
            or value.status.value != row["status"]
            or value.submitter_actor_id != row["submitter_actor_id"]
            or value.record_version != row["record_version"]
            or row["canonical_json_hash"] != _json_hash(payload)
        ):
            raise ValueError("persisted approval submission identity or hash is invalid")
        return value

    @classmethod
    def _approval_from_connection(
        cls, connection: sqlite3.Connection, approval_id: str, workspace_id: str
    ) -> ApprovalDecision:
        row = connection.execute(
            "SELECT * FROM fmea_approval_decisions WHERE workspace_id=? AND approval_id=?", (workspace_id, approval_id)
        ).fetchone()
        if row is None:
            raise ValueError("persisted approval decision is missing")
        payload = cast(str, row["decision_json"])
        value = _decode_approval(payload)
        if (
            value.approval_id != approval_id
            or value.submission_id != row["submission_id"]
            or value.revision_id != row["revision_id"]
            or value.revision_hash != row["revision_hash"]
            or value.status.value != row["status"]
            or value.approver_actor_id != row["approver_actor_id"]
            or value.reason != row["reason"]
            or value.record_version != row["record_version"]
            or row["canonical_json_hash"] != _json_hash(payload)
        ):
            raise ValueError("persisted approval decision identity or hash is invalid")
        return value

    @classmethod
    def _manifest_from_connection(
        cls, connection: sqlite3.Connection, manifest_id: str, workspace_id: str
    ) -> PublicationManifest:
        row = connection.execute(
            "SELECT * FROM fmea_publication_manifests WHERE workspace_id=? AND manifest_id=?",
            (workspace_id, manifest_id),
        ).fetchone()
        if row is None:
            raise ValueError("persisted publication manifest is missing")
        payload = cast(str, row["manifest_json"])
        value = _decode_manifest(payload)
        if (
            value.manifest_id != manifest_id
            or value.revision_id != row["revision_id"]
            or value.revision_hash != row["revision_hash"]
            or value.approval_id != row["approval_id"]
            or value.snapshot_id != row["snapshot_id"]
            or value.snapshot_hash != row["snapshot_hash"]
            or value.manifest_hash != row["manifest_hash"]
            or row["canonical_json_hash"] != _json_hash(payload)
        ):
            raise ValueError("persisted publication manifest identity or hash is invalid")
        return value

    @classmethod
    def _publication_from_connection(
        cls, connection: sqlite3.Connection, publication_id: str, workspace_id: str
    ) -> PublishedRevision:
        row = connection.execute(
            "SELECT * FROM fmea_publications WHERE workspace_id=? AND publication_id=?", (workspace_id, publication_id)
        ).fetchone()
        if row is None:
            raise ValueError("persisted publication is missing")
        payload = cast(str, row["publication_json"])
        value = _decode_publication(payload)
        if (
            value.workspace_id != workspace_id
            or value.publication_id != publication_id
            or value.revision_hash != row["revision_hash"]
            or value.manifest_hash != row["manifest_hash"]
            or value.snapshot_hash != row["snapshot_hash"]
            or value.analysis_id != row["analysis_id"]
            or value.revision_id != row["revision_id"]
            or value.approval_id != row["approval_id"]
            or value.manifest_id != row["manifest_id"]
            or value.snapshot_id != row["snapshot_id"]
            or value.record_version != row["record_version"]
            or row["canonical_json_hash"] != _json_hash(payload)
        ):
            raise ValueError("persisted publication identity or hash is invalid")
        cls._verify_publication_lineage_binding(connection, value)
        return value

    @classmethod
    def _insert_revision_row(
        cls,
        connection: sqlite3.Connection,
        revision: FmeaRevision,
        audit_event_id: str | None = None,
        outbox_event_id: str | None = None,
        idempotency_scope: str | None = None,
        governance_payload_hash: str | None = None,
    ) -> None:
        payload, payload_hash = _object_json(revision)
        connection.execute(
            "INSERT INTO fmea_revisions "
            "(workspace_id,revision_id,analysis_id,analysis_record_version,parent_revision_id,parent_revision_hash,revision_hash,revision_json,record_version,canonical_json_hash,audit_event_id,outbox_event_id,idempotency_scope,payload_hash,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                revision.workspace_id,
                revision.revision_id,
                revision.analysis_id,
                revision.analysis_record_version,
                revision.parent_revision_id,
                revision.parent_revision_hash,
                revision.revision_hash,
                payload,
                1,
                payload_hash,
                audit_event_id,
                outbox_event_id,
                idempotency_scope,
                governance_payload_hash,
                revision.created_at,
            ),
        )

    @classmethod
    def _ensure_revision(
        cls,
        connection: sqlite3.Connection,
        revision: FmeaRevision,
        audit_event_id: str | None = None,
        outbox_event_id: str | None = None,
        idempotency_scope: str | None = None,
        governance_payload_hash: str | None = None,
    ) -> bool:
        row = connection.execute(
            "SELECT revision_json,audit_event_id,outbox_event_id,idempotency_scope,payload_hash FROM fmea_revisions "
            "WHERE workspace_id=? AND revision_id=?",
            (revision.workspace_id, revision.revision_id),
        ).fetchone()
        if row is None:
            if revision.parent_revision_id is not None:
                parent = cls._revision_from_connection(connection, revision.parent_revision_id, revision.workspace_id)
                if parent.revision_hash != revision.parent_revision_hash:
                    _error("FMEA_REVIEW_REQUEST_INVALID", "Parent revision binding is invalid.")
            cls._insert_revision_row(
                connection,
                revision,
                audit_event_id,
                outbox_event_id,
                idempotency_scope,
                governance_payload_hash,
            )
            return True
        if (
            _decode_revision(row["revision_json"]) != revision
            or (audit_event_id is not None and row["audit_event_id"] != audit_event_id)
            or (outbox_event_id is not None and row["outbox_event_id"] != outbox_event_id)
            or (idempotency_scope is not None and row["idempotency_scope"] != idempotency_scope)
            or (governance_payload_hash is not None and row["payload_hash"] != governance_payload_hash)
        ):
            _error("FMEA_IDEMPOTENCY_CONFLICT", "Revision identity is already bound to a different payload.")
        return False

    @classmethod
    def _insert_submission_row(
        cls,
        connection: sqlite3.Connection,
        submission: ApprovalSubmission,
        payload_hash: str,
        scope_key: str,
        audit_id: str,
        outbox_id: str,
    ) -> None:
        payload, json_hash = _object_json(submission)
        connection.execute(
            "INSERT INTO fmea_approval_submissions "
            "(workspace_id,submission_id,revision_id,revision_hash,status,submitter_actor_id,record_version,submission_json,canonical_json_hash,idempotency_scope,payload_hash,audit_event_id,outbox_event_id,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                submission.workspace_id,
                submission.submission_id,
                submission.revision_id,
                submission.revision_hash,
                submission.status.value,
                submission.submitter_actor_id,
                submission.record_version,
                payload,
                json_hash,
                scope_key,
                payload_hash,
                audit_id,
                outbox_id,
                submission.created_at,
            ),
        )

    @classmethod
    def _insert_approval_row(
        cls,
        connection: sqlite3.Connection,
        workspace_id: str,
        decision: ApprovalDecision,
        payload_hash: str,
        scope_key: str,
        audit_id: str,
        outbox_id: str,
    ) -> None:
        payload, json_hash = _object_json(decision)
        connection.execute(
            "INSERT INTO fmea_approval_decisions "
            "(workspace_id,approval_id,submission_id,revision_id,revision_hash,status,approver_actor_id,reason,record_version,decision_json,canonical_json_hash,idempotency_scope,payload_hash,audit_event_id,outbox_event_id,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                workspace_id,
                decision.approval_id,
                decision.submission_id,
                decision.revision_id,
                decision.revision_hash,
                decision.status.value,
                decision.approver_actor_id,
                decision.reason,
                decision.record_version,
                payload,
                json_hash,
                scope_key,
                payload_hash,
                audit_id,
                outbox_id,
                decision.created_at,
            ),
        )

    @classmethod
    def _dependency_scope(
        cls, workspace_id: str, actor_id: str, command: str, path: str, idempotency_key: str
    ) -> IdempotencyScope:
        return IdempotencyScope(
            workspace_id,
            actor_id,
            command,
            path,
            idempotency_key_hash(idempotency_key),
        )

    @classmethod
    def _dependency_audit(
        cls,
        source: AuditEvent,
        scope: IdempotencyScope,
        payload_hash: str,
        aggregate_id: str,
        *,
        decision_id: str | None = None,
    ) -> AuditEvent:
        return replace(
            source,
            event_id=f"dependency-audit-{scope.scope_key}",
            actor_id=scope.actor_id,
            command=scope.command,
            row_id=aggregate_id,
            decision_id=decision_id,
            idempotency_key_hash=scope.key_hash,
            canonical_payload_hash=payload_hash,
        )

    @classmethod
    def _dependency_outbox(
        cls,
        source: OutboxEvent,
        scope: IdempotencyScope,
        payload: Mapping[str, object],
        aggregate_id: str,
        event_type: str,
    ) -> OutboxEvent:
        return OutboxEvent(
            event_id=f"dependency-outbox-{scope.scope_key}",
            workspace_id=scope.workspace_id,
            aggregate_type="fmea_governance",
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            payload_hash=outbox_payload_hash(payload),
            created_at=source.created_at,
            scope_key=scope.scope_key,
        )

    @classmethod
    def _persist_publication_dependencies(
        cls,
        connection: sqlite3.Connection,
        prepared: PreparedPublication,
        fail: Callable[[str], None],
    ) -> None:
        cls._validate_authoritative_analysis(connection, prepared.revision)
        revision_row = connection.execute(
            "SELECT revision_id FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
            (prepared.scope.workspace_id, prepared.revision.revision_id),
        ).fetchone()
        if revision_row is None:
            revision_key = str(uuid5(NAMESPACE_URL, f"revision:{prepared.publication.publication_id}"))
            revision_command = AssembleRevisionCommand(
                RevisionAssemblyRequest(
                    prepared.revision.analysis_id,
                    prepared.revision.parent_revision_id,
                    prepared.revision.analysis_record_version,
                    prepared.revision.parent_revision_hash,
                ),
                revision_key,
            )
            revision_scope = cls._dependency_scope(
                prepared.scope.workspace_id,
                prepared.scope.actor_id,
                "fmea.revision.assemble",
                f"/fmea/analyses/{prepared.revision.analysis_id}/revisions",
                revision_key,
            )
            revision_payload = canonical_governance_payload(
                "revision.assemble", revision_command, revision=prepared.revision
            )
            revision_payload_hash = governance_payload_hash(revision_payload)
            revision_audit = cls._dependency_audit(
                prepared.audit,
                revision_scope,
                revision_payload_hash,
                prepared.revision.revision_id,
            )
            revision_outbox = cls._dependency_outbox(
                prepared.outbox,
                revision_scope,
                revision_payload,
                prepared.revision.revision_id,
                "revision.assembled",
            )
            revision_meta = _PreparedMeta(
                "revision",
                prepared.scope.workspace_id,
                prepared.revision.revision_id,
                prepared.revision.revision_id,
                "revision",
                revision_scope.command,
                revision_payload,
            )
            cls._insert_idempotency(
                connection,
                revision_scope,
                revision_payload_hash,
                prepared.revision.created_at,
            )
            cls._insert_audit(
                connection,
                revision_audit,
                revision_scope,
                revision_payload_hash,
                revision_meta,
            )
            cls._ensure_revision(
                connection,
                prepared.revision,
                revision_audit.event_id,
                revision_outbox.event_id,
                revision_scope.scope_key,
                revision_payload_hash,
            )
            cls._insert_revision_analysis_binding(connection, prepared.revision)
            fail("publication.revision")
            cls._insert_outbox(
                connection,
                revision_outbox,
                revision_scope,
                revision_meta,
                "revision.assembled",
            )
            revision_result = RevisionResult(
                prepared.revision.revision_id,
                1,
                revision_audit.event_id,
                revision_outbox.event_id,
            )
            cls._insert_event_binding(connection, revision_meta, revision_result)
            cls._complete_idempotency(
                connection,
                revision_scope,
                revision_payload_hash,
                prepared.revision.revision_id,
                revision_result,
                prepared.revision.created_at,
            )
        else:
            persisted_revision = cls._revision_from_connection(
                connection,
                prepared.revision.revision_id,
                prepared.scope.workspace_id,
            )
            if persisted_revision != prepared.revision:
                _error(
                    "FMEA_IDEMPOTENCY_CONFLICT",
                    "Revision identity is already bound to a different payload.",
                )
            cls._verify_persisted_dependency_chain(
                connection,
                "revision",
                prepared.scope.workspace_id,
                prepared.revision.revision_id,
            )
        submission_row = connection.execute(
            "SELECT * FROM fmea_approval_submissions WHERE workspace_id=? AND submission_id=?",
            (prepared.scope.workspace_id, prepared.submission.submission_id),
        ).fetchone()
        if submission_row is None:
            command = __import__(
                "fmea_application.governance_contracts", fromlist=["SubmitApprovalCommand"]
            ).SubmitApprovalCommand(
                prepared.submission.revision_id,
                prepared.submission.revision_hash,
                prepared.revision_record_version,
                str(uuid5(NAMESPACE_URL, f"submission:{prepared.publication.publication_id}")),
            )
            scope = cls._dependency_scope(
                prepared.scope.workspace_id,
                prepared.submission.submitter_actor_id,
                "fmea.approval.submit",
                f"/fmea/revisions/{prepared.submission.revision_id}/approval-submissions",
                command.idempotency_key,
            )
            payload = canonical_governance_payload("approval.submit", command, submission=prepared.submission)
            payload_hash = governance_payload_hash(payload)
            audit = cls._dependency_audit(prepared.audit, scope, payload_hash, prepared.submission.submission_id)
            outbox = cls._dependency_outbox(
                prepared.outbox, scope, payload, prepared.submission.submission_id, "approval.submitted"
            )
            cls._insert_idempotency(connection, scope, payload_hash, prepared.submission.created_at)
            dependency_meta = _PreparedMeta(
                "approval_submission",
                prepared.scope.workspace_id,
                prepared.submission.submission_id,
                prepared.submission.revision_id,
                "approval",
                scope.command,
                payload,
            )
            cls._insert_audit(connection, audit, scope, payload_hash, dependency_meta)
            cls._insert_submission_row(
                connection, prepared.submission, payload_hash, scope.scope_key, audit.event_id, outbox.event_id
            )
            cls._insert_outbox(connection, outbox, scope, dependency_meta, "approval.submitted")
            cls._insert_event_binding(
                connection,
                dependency_meta,
                ApprovalSubmissionResult(
                    prepared.submission.submission_id,
                    prepared.submission.record_version,
                    audit.event_id,
                    outbox.event_id,
                ),
            )
            cls._complete_idempotency(
                connection,
                scope,
                payload_hash,
                prepared.submission.submission_id,
                ApprovalSubmissionResult(
                    prepared.submission.submission_id,
                    prepared.submission.record_version,
                    audit.event_id,
                    outbox.event_id,
                ),
                prepared.submission.created_at,
            )
        else:
            if _decode_submission(submission_row["submission_json"]) != prepared.submission:
                _error(
                    "FMEA_IDEMPOTENCY_CONFLICT", "Approval submission identity is already bound to a different payload."
                )
        approval_row = connection.execute(
            "SELECT * FROM fmea_approval_decisions WHERE workspace_id=? AND approval_id=?",
            (prepared.scope.workspace_id, prepared.approval.approval_id),
        ).fetchone()
        if approval_row is None:
            command_type = (
                ApprovalRejectionCommand if prepared.approval.status is ApprovalStatus.REJECTED else ApprovalCommand
            )
            command = command_type(
                prepared.approval.submission_id,
                prepared.approval.revision_id,
                prepared.approval.revision_hash,
                prepared.submission.record_version,
                prepared.approval.reason,
                str(uuid5(NAMESPACE_URL, f"approval:{prepared.publication.publication_id}")),
            )
            scope = cls._dependency_scope(
                prepared.scope.workspace_id,
                prepared.approval.approver_actor_id,
                "fmea.approval.decide",
                f"/fmea/approval-submissions/{prepared.approval.submission_id}/decision",
                command.idempotency_key,
            )
            payload = canonical_governance_payload(
                "approval.decide", command, submission=prepared.submission, decision=prepared.approval
            )
            payload_hash = governance_payload_hash(payload)
            audit = cls._dependency_audit(
                prepared.audit,
                scope,
                payload_hash,
                prepared.approval.approval_id,
                decision_id=prepared.approval.approval_id,
            )
            outbox = cls._dependency_outbox(
                prepared.outbox,
                scope,
                payload,
                prepared.approval.approval_id,
                "approval.approved" if prepared.approval.status is ApprovalStatus.APPROVED else "approval.rejected",
            )
            cls._insert_idempotency(connection, scope, payload_hash, prepared.approval.created_at)
            dependency_meta = _PreparedMeta(
                "approval",
                prepared.scope.workspace_id,
                prepared.approval.approval_id,
                prepared.approval.revision_id,
                "approval",
                scope.command,
                payload,
            )
            cls._insert_audit(connection, audit, scope, payload_hash, dependency_meta)
            cls._insert_approval_row(
                connection,
                prepared.scope.workspace_id,
                prepared.approval,
                payload_hash,
                scope.scope_key,
                audit.event_id,
                outbox.event_id,
            )
            fail("publication.decision")
            cls._insert_outbox(
                connection,
                outbox,
                scope,
                dependency_meta,
                "approval.approved" if prepared.approval.status is ApprovalStatus.APPROVED else "approval.rejected",
            )
            cls._insert_event_binding(
                connection,
                dependency_meta,
                ApprovalResult(
                    prepared.approval.approval_id, prepared.approval.record_version, audit.event_id, outbox.event_id
                ),
            )
            cls._complete_idempotency(
                connection,
                scope,
                payload_hash,
                prepared.approval.approval_id,
                ApprovalResult(
                    prepared.approval.approval_id, prepared.approval.record_version, audit.event_id, outbox.event_id
                ),
                prepared.approval.created_at,
            )
        elif _decode_approval(approval_row["decision_json"]) != prepared.approval:
            _error("FMEA_IDEMPOTENCY_CONFLICT", "Approval decision identity is already bound to a different payload.")

    @classmethod
    def _write_revision(
        cls,
        connection: sqlite3.Connection,
        prepared: PreparedRevision,
        meta: _PreparedMeta,
        fail: Callable[[str], None],
    ) -> None:
        cls._validate_authoritative_analysis(connection, prepared.revision)
        inserted = cls._ensure_revision(
            connection,
            prepared.revision,
            prepared.audit.event_id,
            prepared.outbox.event_id,
            prepared.scope.scope_key,
            prepared.payload_hash,
        )
        if inserted:
            cls._insert_revision_analysis_binding(connection, prepared.revision)
        else:
            cls._verify_revision_analysis_binding(connection, prepared.revision)
        fail("revision.record")

    @classmethod
    def _write_submission(
        cls,
        connection: sqlite3.Connection,
        prepared: PreparedApprovalSubmission,
        meta: _PreparedMeta,
        fail: Callable[[str], None],
    ) -> None:
        revision = cls._revision_from_connection(connection, prepared.submission.revision_id, meta.workspace_id)
        record_version = int(
            connection.execute(
                "SELECT record_version FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
                (meta.workspace_id, revision.revision_id),
            ).fetchone()[0]
        )
        if (
            revision.revision_hash != prepared.submission.revision_hash
            or record_version != prepared.revision_record_version
        ):
            _error("FMEA_VERSION_CONFLICT", "Approval submission revision binding is stale.")
        cls._insert_submission_row(
            connection,
            prepared.submission,
            prepared.payload_hash,
            prepared.scope.scope_key,
            prepared.audit.event_id,
            prepared.outbox.event_id,
        )
        fail("approval.submission")

    @classmethod
    def _write_approval(
        cls,
        connection: sqlite3.Connection,
        prepared: PreparedApproval,
        meta: _PreparedMeta,
        fail: Callable[[str], None],
    ) -> None:
        submission = cls._submission_from_connection(connection, prepared.submission.submission_id, meta.workspace_id)
        if submission != prepared.submission:
            _error("FMEA_VERSION_CONFLICT", "Approval submission binding is stale.")
        revision = cls._revision_from_connection(connection, submission.revision_id, meta.workspace_id)
        if revision.revision_hash != prepared.decision.revision_hash:
            _error("FMEA_VERSION_CONFLICT", "Approval revision binding is stale.")
        existing_decisions = connection.execute(
            "SELECT approval_id FROM fmea_approval_decisions WHERE workspace_id=? AND submission_id=?",
            (meta.workspace_id, prepared.submission.submission_id),
        ).fetchall()
        if existing_decisions:
            _error(
                "FMEA_GOVERNANCE_APPROVAL_STATE_INVALID",
                "Approval submission already has a terminal decision.",
            )
        cls._insert_approval_row(
            connection,
            meta.workspace_id,
            prepared.decision,
            prepared.payload_hash,
            prepared.scope.scope_key,
            prepared.audit.event_id,
            prepared.outbox.event_id,
        )
        fail("approval.decision")

    @classmethod
    def _write_approval_withdrawal(
        cls,
        connection: sqlite3.Connection,
        prepared: PreparedApprovalWithdrawal,
        meta: _PreparedMeta,
        fail: Callable[[str], None],
    ) -> None:
        approval = cls._approval_from_connection(connection, prepared.approval.approval_id, meta.workspace_id)
        if approval != prepared.approval or approval.status is not ApprovalStatus.APPROVED:
            _error("FMEA_VERSION_CONFLICT", "Approval withdrawal binding is stale.")
        existing_withdrawals = connection.execute(
            "SELECT withdrawal_id FROM fmea_approval_withdrawals WHERE workspace_id=? AND approval_id=?",
            (meta.workspace_id, prepared.approval.approval_id),
        ).fetchall()
        if existing_withdrawals:
            _error(
                "FMEA_GOVERNANCE_APPROVAL_STATE_INVALID",
                "Approval has already been withdrawn.",
            )
        connection.execute(
            "INSERT INTO fmea_approval_withdrawals "
            "(workspace_id,withdrawal_id,approval_id,revision_id,revision_hash,actor_id,reason,withdrawal_json,canonical_json_hash,idempotency_scope,payload_hash,audit_event_id,outbox_event_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                meta.workspace_id,
                prepared.withdrawal.withdrawal_id,
                prepared.withdrawal.approval_id,
                prepared.withdrawal.revision_id,
                prepared.withdrawal.revision_hash,
                prepared.withdrawal.actor_id,
                prepared.withdrawal.reason,
                _object_json(prepared.withdrawal)[0],
                _object_json(prepared.withdrawal)[1],
                prepared.scope.scope_key,
                prepared.payload_hash,
                prepared.audit.event_id,
                prepared.outbox.event_id,
                prepared.withdrawal.created_at,
            ),
        )
        fail("approval.withdrawal")

    @classmethod
    def _insert_manifest(cls, connection: sqlite3.Connection, manifest: PublicationManifest, workspace_id: str) -> None:
        payload, json_hash = _object_json(manifest)
        connection.execute(
            "INSERT INTO fmea_publication_manifests (workspace_id,manifest_id,revision_id,revision_hash,approval_id,snapshot_id,snapshot_hash,version_manifest_hash,previous_audit_chain_head,export_eligible,manifest_hash,manifest_json,canonical_json_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                workspace_id,
                manifest.manifest_id,
                manifest.revision_id,
                manifest.revision_hash,
                manifest.approval_id,
                manifest.snapshot_id,
                manifest.snapshot_hash,
                manifest.version_manifest_hash,
                manifest.previous_audit_chain_head,
                int(manifest.export_eligible),
                manifest.manifest_hash,
                payload,
                json_hash,
                manifest.created_at,
            ),
        )

    @classmethod
    def _write_publication(
        cls,
        connection: sqlite3.Connection,
        prepared: PreparedPublication,
        meta: _PreparedMeta,
        fail: Callable[[str], None],
    ) -> None:
        # Service-created publications carry the final audit-chain hash in both
        # the immutable publication and its audit event. Recompute that order
        # in the same transaction before any dependency or publication row is
        # inserted. Legacy prepared fixtures do not carry this marker and are
        # still validated by their existing immutable/canonical contracts.
        if prepared.audit.after_hash == prepared.publication.audit_chain_head:
            expected_manifest_hash = canonical_hash(
                {
                    "manifest_id": prepared.manifest.manifest_id,
                    "revision_id": prepared.manifest.revision_id,
                    "revision_hash": prepared.manifest.revision_hash,
                    "approval_id": prepared.manifest.approval_id,
                    "snapshot_id": prepared.manifest.snapshot_id,
                    "snapshot_hash": prepared.manifest.snapshot_hash,
                    "version_manifest_hash": prepared.manifest.version_manifest_hash,
                    "previous_audit_chain_head": prepared.manifest.previous_audit_chain_head,
                    "export_eligible": prepared.manifest.export_eligible,
                },
                prefixed=True,
            )
            expected_audit_chain_head = canonical_hash(
                {
                    "previous_audit_chain_head": prepared.manifest.previous_audit_chain_head,
                    "revision_hash": prepared.revision.revision_hash,
                    "approval_hash": canonical_hash(prepared.approval, prefixed=True),
                    "snapshot_hash": prepared.snapshot.snapshot_hash,
                    "manifest_hash": expected_manifest_hash,
                },
                prefixed=True,
            )
            if (
                prepared.manifest.manifest_hash != expected_manifest_hash
                or prepared.publication.audit_chain_head != expected_audit_chain_head
                or prepared.audit.after_hash != expected_audit_chain_head
            ):
                _error("FMEA_REVIEW_REQUEST_INVALID", "Publication hash chain is invalid.")
        cls._persist_publication_dependencies(connection, prepared, fail)
        validate_approval_binding(prepared.approval, prepared.revision)
        persisted_revision = cls._revision_from_connection(connection, prepared.revision.revision_id, meta.workspace_id)
        persisted_submission = cls._submission_from_connection(
            connection, prepared.submission.submission_id, meta.workspace_id
        )
        persisted_approval = cls._approval_from_connection(connection, prepared.approval.approval_id, meta.workspace_id)
        if (
            persisted_revision != prepared.revision
            or persisted_submission != prepared.submission
            or persisted_approval != prepared.approval
            or persisted_approval.status is not ApprovalStatus.APPROVED
        ):
            _error("FMEA_VERSION_CONFLICT", "Publication governance dependency is stale.")
        approval_withdrawal = connection.execute(
            "SELECT withdrawal_id FROM fmea_approval_withdrawals WHERE workspace_id=? AND approval_id=?",
            (meta.workspace_id, prepared.approval.approval_id),
        ).fetchone()
        if approval_withdrawal is not None:
            _error(
                "FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID",
                "Publication cannot use a withdrawn approval.",
            )
        revision_row = connection.execute(
            "SELECT revision_hash,record_version FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
            (meta.workspace_id, prepared.revision.revision_id),
        ).fetchone()
        if (
            revision_row is None
            or revision_row["revision_hash"] != prepared.revision.revision_hash
            or revision_row["record_version"] != prepared.revision_record_version
        ):
            _error("FMEA_VERSION_CONFLICT", "Publication revision binding is stale.")
        manifest_row = connection.execute(
            "SELECT * FROM fmea_publication_manifests WHERE workspace_id=? AND manifest_id=?",
            (meta.workspace_id, prepared.manifest.manifest_id),
        ).fetchone()
        if manifest_row is None:
            cls._insert_manifest(connection, prepared.manifest, meta.workspace_id)
            persisted_manifest = prepared.manifest
            fail("publication.manifest")
        else:
            persisted_manifest = cls._manifest_from_connection(
                connection, prepared.manifest.manifest_id, meta.workspace_id
            )
            if persisted_manifest != prepared.manifest:
                _error("FMEA_IDEMPOTENCY_CONFLICT", "Publication manifest identity is already bound differently.")
        if (
            persisted_manifest.revision_id != persisted_revision.revision_id
            or persisted_manifest.revision_hash != persisted_revision.revision_hash
            or persisted_manifest.approval_id != persisted_approval.approval_id
            or persisted_manifest.snapshot_id != prepared.snapshot.snapshot_id
            or persisted_manifest.snapshot_hash != prepared.snapshot.snapshot_hash
            or prepared.publication.revision_id != persisted_revision.revision_id
            or prepared.publication.revision_hash != persisted_revision.revision_hash
            or prepared.publication.analysis_id != persisted_revision.analysis_id
            or prepared.publication.approval_id != persisted_approval.approval_id
            or prepared.publication.manifest_id != persisted_manifest.manifest_id
            or prepared.publication.manifest_hash != persisted_manifest.manifest_hash
            or prepared.publication.snapshot_id != persisted_manifest.snapshot_id
            or prepared.publication.snapshot_hash != persisted_manifest.snapshot_hash
            or prepared.snapshot.revision_id != persisted_revision.revision_id
            or prepared.snapshot.revision_hash != persisted_revision.revision_hash
            or prepared.snapshot.analysis_id != persisted_revision.analysis_id
            or prepared.snapshot.manifest_id != persisted_manifest.manifest_id
            or prepared.snapshot.publication_id != prepared.publication.publication_id
        ):
            _error("FMEA_REVIEW_REQUEST_INVALID", "Publication manifest lineage binding is invalid.")
        snapshot_row = connection.execute(
            "SELECT * FROM fmea_normalized_snapshots WHERE workspace_id=? AND snapshot_id=?",
            (meta.workspace_id, prepared.snapshot.snapshot_id),
        ).fetchone()
        if snapshot_row is not None:
            snapshot_payload, snapshot_json_hash = _object_json(prepared.snapshot)
            if (
                snapshot_row["snapshot_json"] != snapshot_payload
                or snapshot_row["canonical_json_hash"] != snapshot_json_hash
                or snapshot_row["snapshot_hash"] != prepared.snapshot.snapshot_hash
                or snapshot_row["publication_id"] != prepared.publication.publication_id
                or snapshot_row["manifest_id"] != persisted_manifest.manifest_id
                or snapshot_row["revision_id"] != persisted_revision.revision_id
            ):
                _error("FMEA_IDEMPOTENCY_CONFLICT", "Normalized snapshot identity is already bound differently.")
        snapshot_payload, snapshot_json_hash = _object_json(prepared.snapshot)
        connection.execute(
            "INSERT INTO fmea_normalized_snapshots (workspace_id,snapshot_id,publication_id,manifest_id,revision_id,revision_hash,analysis_id,snapshot_hash,snapshot_json,canonical_json_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                meta.workspace_id,
                prepared.snapshot.snapshot_id,
                prepared.snapshot.publication_id,
                prepared.snapshot.manifest_id,
                prepared.snapshot.revision_id,
                prepared.snapshot.revision_hash,
                prepared.snapshot.analysis_id,
                prepared.snapshot.snapshot_hash,
                snapshot_payload,
                snapshot_json_hash,
                prepared.snapshot.created_at,
            ),
        )
        fail("publication.snapshot")
        publication_payload, publication_json_hash = _object_json(prepared.publication)
        connection.execute(
            "INSERT INTO fmea_publications (workspace_id,publication_id,analysis_id,revision_id,revision_hash,approval_id,manifest_id,manifest_hash,snapshot_id,snapshot_hash,audit_chain_head,publisher_actor_id,record_version,publication_json,canonical_json_hash,audit_event_id,outbox_event_id,idempotency_scope,payload_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                meta.workspace_id,
                prepared.publication.publication_id,
                prepared.publication.analysis_id,
                prepared.publication.revision_id,
                prepared.publication.revision_hash,
                prepared.publication.approval_id,
                prepared.publication.manifest_id,
                prepared.publication.manifest_hash,
                prepared.publication.snapshot_id,
                prepared.publication.snapshot_hash,
                prepared.publication.audit_chain_head,
                prepared.publication.publisher_actor_id,
                prepared.publication.record_version,
                publication_payload,
                publication_json_hash,
                prepared.audit.event_id,
                prepared.outbox.event_id,
                prepared.scope.scope_key,
                prepared.payload_hash,
                prepared.publication.created_at,
            ),
        )
        fail("publication.record")
        eligibility_json, eligibility_json_hash = _object_json(prepared.export_eligibility)
        source_hashes_json = _source_hashes_json(prepared.export_eligibility.source_hashes)
        connection.execute(
            "INSERT INTO fmea_export_eligibility (workspace_id,eligibility_id,publication_id,manifest_id,eligible,eligibility_hash,eligibility_json,source_hashes_json,canonical_json_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                meta.workspace_id,
                prepared.export_eligibility.eligibility_id,
                prepared.publication.publication_id,
                prepared.manifest.manifest_id,
                int(prepared.manifest.export_eligible),
                prepared.export_eligibility.eligibility_hash,
                eligibility_json,
                source_hashes_json,
                eligibility_json_hash,
                prepared.publication.created_at,
            ),
        )
        cls._insert_publication_lineage_binding(connection, prepared)

    @classmethod
    def _write_publication_withdrawal(
        cls,
        connection: sqlite3.Connection,
        prepared: PreparedPublicationWithdrawal,
        meta: _PreparedMeta,
        fail: Callable[[str], None],
    ) -> None:
        publication = cls._publication_from_connection(
            connection, prepared.publication.publication_id, meta.workspace_id
        )
        if (
            publication != prepared.publication
            or publication.record_version != prepared.command.expected_publication_version
        ):
            _error("FMEA_VERSION_CONFLICT", "Publication withdrawal binding is stale.")
        existing_withdrawals = connection.execute(
            "SELECT withdrawal_id FROM fmea_publication_withdrawals WHERE workspace_id=? AND publication_id=?",
            (meta.workspace_id, prepared.publication.publication_id),
        ).fetchall()
        if existing_withdrawals:
            _error(
                "FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID",
                "Publication has already been withdrawn.",
            )
        supersession = connection.execute(
            "SELECT supersession_id FROM fmea_supersessions WHERE workspace_id=? AND old_publication_id=?",
            (meta.workspace_id, prepared.publication.publication_id),
        ).fetchone()
        if supersession is not None:
            _error(
                "FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID",
                "Superseded publication cannot be withdrawn.",
            )
        withdrawal_payload, withdrawal_json_hash = _object_json(prepared.withdrawal)
        connection.execute(
            "INSERT INTO fmea_publication_withdrawals (workspace_id,withdrawal_id,publication_id,replacement_publication_id,actor_id,reason,withdrawal_json,canonical_json_hash,idempotency_scope,payload_hash,audit_event_id,outbox_event_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                meta.workspace_id,
                prepared.withdrawal.withdrawal_id,
                prepared.withdrawal.publication_id,
                prepared.withdrawal.replacement_publication_id,
                prepared.withdrawal.actor_id,
                prepared.withdrawal.reason,
                withdrawal_payload,
                withdrawal_json_hash,
                prepared.scope.scope_key,
                prepared.payload_hash,
                prepared.audit.event_id,
                prepared.outbox.event_id,
                prepared.withdrawal.created_at,
            ),
        )
        fail("publication.withdrawal")

    @classmethod
    def _would_cycle(cls, connection: sqlite3.Connection, workspace_id: str, old_id: str, new_id: str) -> bool:
        seen: set[str] = set()
        frontier = [new_id]
        while frontier:
            current = frontier.pop()
            if current == old_id:
                return True
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(
                str(row[0])
                for row in connection.execute(
                    "SELECT new_publication_id FROM fmea_supersessions WHERE workspace_id=? AND old_publication_id=?",
                    (workspace_id, current),
                ).fetchall()
            )
        return False

    @classmethod
    def _write_supersession(
        cls,
        connection: sqlite3.Connection,
        prepared: PreparedSupersession,
        meta: _PreparedMeta,
        fail: Callable[[str], None],
    ) -> None:
        old_revision = cls._revision_from_connection(connection, prepared.old_revision.revision_id, meta.workspace_id)
        replacement_revision = cls._revision_from_connection(
            connection, prepared.replacement_revision.revision_id, meta.workspace_id
        )
        if old_revision != prepared.old_revision or replacement_revision != prepared.replacement_revision:
            _error("FMEA_VERSION_CONFLICT", "Supersession revision binding is stale.")
        for publication in (prepared.old_publication, prepared.replacement_publication):
            row = connection.execute(
                "SELECT publication_json FROM fmea_publications WHERE workspace_id=? AND publication_id=?",
                (meta.workspace_id, publication.publication_id),
            ).fetchone()
            if row is None:
                _error("FMEA_VERSION_CONFLICT", "Supersession publication is missing.")
            if _decode_publication(row["publication_json"]) != publication:
                _error("FMEA_IDEMPOTENCY_CONFLICT", "Publication identity is already bound to a different payload.")
        validate_supersession_binding(
            prepared.supersession,
            old=prepared.old_publication,
            replacement=prepared.replacement_publication,
            old_revision=prepared.old_revision,
            replacement_revision=prepared.replacement_revision,
        )
        if cls._would_cycle(
            connection,
            meta.workspace_id,
            prepared.supersession.old_publication_id,
            prepared.supersession.new_publication_id,
        ):
            _error("FMEA_REVIEW_REQUEST_INVALID", "Publication supersession would create a cycle.")
        old_withdrawal = connection.execute(
            "SELECT withdrawal_id FROM fmea_publication_withdrawals WHERE workspace_id=? AND publication_id=?",
            (meta.workspace_id, prepared.old_publication.publication_id),
        ).fetchone()
        replacement_withdrawal = connection.execute(
            "SELECT withdrawal_id FROM fmea_publication_withdrawals WHERE workspace_id=? AND publication_id=?",
            (meta.workspace_id, prepared.replacement_publication.publication_id),
        ).fetchone()
        existing_outgoing = connection.execute(
            "SELECT supersession_id FROM fmea_supersessions WHERE workspace_id=? AND old_publication_id=?",
            (meta.workspace_id, prepared.old_publication.publication_id),
        ).fetchall()
        if old_withdrawal is not None or replacement_withdrawal is not None or existing_outgoing:
            _error(
                "FMEA_GOVERNANCE_SUPERSESSION_INVALID",
                "Publication supersession state is no longer current.",
            )
        payload, json_hash = _object_json(prepared.supersession)
        connection.execute(
            "INSERT INTO fmea_supersessions (workspace_id,supersession_id,old_publication_id,new_publication_id,actor_id,reason,supersession_json,canonical_json_hash,idempotency_scope,payload_hash,audit_event_id,outbox_event_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                meta.workspace_id,
                prepared.supersession.supersession_id,
                prepared.supersession.old_publication_id,
                prepared.supersession.new_publication_id,
                prepared.supersession.actor_id,
                prepared.supersession.reason,
                payload,
                json_hash,
                prepared.scope.scope_key,
                prepared.payload_hash,
                prepared.audit.event_id,
                prepared.outbox.event_id,
                prepared.supersession.created_at,
            ),
        )
        fail("supersession.record")

    @classmethod
    def _write_readiness(
        cls,
        connection: sqlite3.Connection,
        prepared: PreparedReadinessReport,
        meta: _PreparedMeta,
        fail: Callable[[str], None],
    ) -> ReadinessReportRecord:
        cls._validate_authoritative_analysis(connection, prepared.revision)
        persisted_revision = cls._revision_from_connection(connection, prepared.revision.revision_id, meta.workspace_id)
        revision_row = connection.execute(
            "SELECT record_version FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
            (meta.workspace_id, prepared.revision.revision_id),
        ).fetchone()
        if (
            persisted_revision != prepared.revision
            or revision_row is None
            or revision_row["record_version"] != prepared.revision_record_version
        ):
            _error("FMEA_VERSION_CONFLICT", "Readiness revision binding is stale.")
        source_hashes = dict(prepared.source_hashes)
        if (
            source_hashes.get("analysis") != prepared.revision.analysis_hash
            or source_hashes.get("revision") != prepared.revision.revision_hash
        ):
            _error("FMEA_REVIEW_REQUEST_INVALID", "Readiness source hash binding is invalid.")
        record = ReadinessReportRecord(
            readiness_id=prepared.readiness_id,
            report=prepared.report,
            source_hashes=prepared.source_hashes,
            report_hash=canonical_hash(prepared.report, prefixed=True),
            canonical_json_hash=canonical_hash(
                {
                    "readiness_id": prepared.readiness_id,
                    "report": prepared.report,
                    "source_hashes": prepared.source_hashes,
                },
                prefixed=True,
            ),
            created_at=prepared.audit.occurred_at_server,
        )
        report_json, _ = _object_json(record.report)
        connection.execute(
            "INSERT INTO fmea_revision_readiness_reports "
            "(workspace_id,readiness_id,revision_id,revision_hash,target_record_version,ready,blocking_codes_json,report_hash,report_json,created_at,source_hashes_json,canonical_json_hash,idempotency_scope,payload_hash,audit_event_id,outbox_event_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                meta.workspace_id,
                record.readiness_id,
                prepared.revision.revision_id,
                prepared.revision.revision_hash,
                prepared.report.target_record_version,
                int(prepared.report.ready),
                canonical_json(prepared.report.blocking_codes),
                record.report_hash,
                report_json,
                record.created_at,
                _source_hashes_json(record.source_hashes),
                record.canonical_json_hash,
                prepared.scope.scope_key,
                prepared.payload_hash,
                prepared.audit.event_id,
                prepared.outbox.event_id,
            ),
        )
        fail("revision.readiness")
        return record

    @classmethod
    def _writer(
        cls, connection: sqlite3.Connection, prepared: Any, meta: _PreparedMeta, fail: Callable[[str], None]
    ) -> object:
        if meta.kind == "readiness":
            cls._write_readiness(connection, prepared, meta, fail)
            return ReadinessResult(prepared.readiness_id, 1, prepared.audit.event_id, prepared.outbox.event_id)
        if meta.kind == "revision":
            cls._write_revision(connection, prepared, meta, fail)
            return RevisionResult(prepared.revision.revision_id, 1, prepared.audit.event_id, prepared.outbox.event_id)
        if meta.kind == "approval_submission":
            cls._write_submission(connection, prepared, meta, fail)
            return __import__(
                "fmea_application.governance_contracts", fromlist=["ApprovalSubmissionResult"]
            ).ApprovalSubmissionResult(
                prepared.submission.submission_id,
                prepared.submission.record_version,
                prepared.audit.event_id,
                prepared.outbox.event_id,
            )
        if meta.kind == "approval":
            cls._write_approval(connection, prepared, meta, fail)
            return __import__("fmea_application.governance_contracts", fromlist=["ApprovalResult"]).ApprovalResult(
                prepared.decision.approval_id,
                prepared.decision.record_version,
                prepared.audit.event_id,
                prepared.outbox.event_id,
            )
        if meta.kind == "approval_withdrawal":
            cls._write_approval_withdrawal(connection, prepared, meta, fail)
            return ApprovalWithdrawalResult(
                prepared.withdrawal.withdrawal_id,
                prepared.withdrawal.approval_id,
                prepared.audit.event_id,
                prepared.outbox.event_id,
            )
        if meta.kind == "publication":
            cls._write_publication(connection, prepared, meta, fail)
            return PublicationResult(
                prepared.publication.publication_id,
                prepared.manifest.manifest_id,
                prepared.snapshot.snapshot_id,
                prepared.publication.record_version,
                prepared.audit.event_id,
                prepared.outbox.event_id,
            )
        if meta.kind == "publication_withdrawal":
            cls._write_publication_withdrawal(connection, prepared, meta, fail)
            return PublicationWithdrawalResult(
                prepared.withdrawal.withdrawal_id,
                prepared.withdrawal.publication_id,
                prepared.audit.event_id,
                prepared.outbox.event_id,
            )
        cls._write_supersession(connection, prepared, meta, fail)
        return SupersessionResult(
            prepared.supersession.supersession_id,
            prepared.supersession.old_publication_id,
            prepared.supersession.new_publication_id,
            prepared.audit.event_id,
            prepared.outbox.event_id,
        )

    def _commit(self, kind: str, prepared: object) -> object:
        meta = self._meta(kind, prepared)
        value = cast(Any, prepared)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._check_existing(connection, meta, value)
            if replay is not None:
                connection.execute("COMMIT")
                return replay
            self._insert_idempotency(connection, value.scope, value.payload_hash, value.audit.occurred_at_server)
            self._fail("idempotency.reserve")
            self._insert_audit(connection, value.audit, value.scope, value.payload_hash, meta)
            self._fail("audit")
            result = self._writer(connection, value, meta, self._fail)
            self._insert_outbox(connection, value.outbox, value.scope, meta, self._lifecycle_event_type(kind, value))
            self._insert_event_binding(connection, meta, result)
            self._fail("outbox")
            self._complete_idempotency(
                connection, value.scope, value.payload_hash, meta.resource_id, result, value.audit.occurred_at_server
            )
            self._fail("idempotency.complete")
            connection.execute("COMMIT")
            return result
        except ReviewError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except sqlite3.IntegrityError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            _error("FMEA_REVIEW_REQUEST_INVALID", "Governance persistence constraints rejected the write.")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _replay(self, kind: str, scope: IdempotencyScope, payload_hash: str) -> object | None:
        if not isinstance(scope, IdempotencyScope):
            _error("FMEA_REVIEW_REQUEST_INVALID", "Governance idempotency scope is invalid.")
        _hash(payload_hash, "payload_hash")
        connection = self._connect()
        try:
            row = self._idempotency_row(connection, scope)
            if row is None:
                return None
            if row["payload_hash"] != payload_hash:
                _error("FMEA_IDEMPOTENCY_CONFLICT", "Idempotency key was already used with a different payload.")
            if row["state"] != "completed":
                return None
            result = self._decode_result(kind, row["response_json"])
            if kind == "revision":
                resource_id = result.revision_id
            elif kind == "readiness":
                resource_id = result.readiness_id
            elif kind == "approval_submission":
                resource_id = result.submission_id
            elif kind == "approval":
                resource_id = result.approval_id
            elif kind == "publication":
                resource_id = result.publication_id
            elif kind in {"approval_withdrawal", "publication_withdrawal"}:
                resource_id = result.withdrawal_id
            else:
                resource_id = result.supersession_id
            if row["resource_id"] != resource_id:
                raise ValueError("persisted governance response resource is invalid")
            self._verify_replay_chain(connection, kind, scope, payload_hash, result)
            return replace(result, replayed=True)
        finally:
            connection.close()

    def commit_revision(self, prepared: PreparedRevision) -> RevisionResult:
        return cast(RevisionResult, self._commit("revision", prepared))

    def replay_revision(self, scope: IdempotencyScope, payload_hash: str) -> RevisionResult | None:
        return cast(RevisionResult | None, self._replay("revision", scope, payload_hash))

    def commit_readiness(self, prepared: PreparedReadinessReport) -> ReadinessResult:
        return cast(ReadinessResult, self._commit("readiness", prepared))

    def replay_readiness(self, scope: IdempotencyScope, payload_hash: str) -> ReadinessResult | None:
        return cast(ReadinessResult | None, self._replay("readiness", scope, payload_hash))

    def commit_approval_submission(self, prepared: PreparedApprovalSubmission):
        return self._commit("approval_submission", prepared)

    def replay_approval_submission(self, scope: IdempotencyScope, payload_hash: str):
        return self._replay("approval_submission", scope, payload_hash)

    def commit_approval(self, prepared: PreparedApproval):
        return self._commit("approval", prepared)

    def replay_approval_decision(self, scope: IdempotencyScope, payload_hash: str):
        return self._replay("approval", scope, payload_hash)

    def commit_approval_withdrawal(self, prepared: PreparedApprovalWithdrawal):
        return self._commit("approval_withdrawal", prepared)

    def replay_approval_withdrawal(self, scope: IdempotencyScope, payload_hash: str):
        return self._replay("approval_withdrawal", scope, payload_hash)

    def commit_publication(self, prepared: PreparedPublication) -> PublicationResult:
        return cast(PublicationResult, self._commit("publication", prepared))

    def replay_publication(self, scope: IdempotencyScope, payload_hash: str) -> PublicationResult | None:
        return cast(PublicationResult | None, self._replay("publication", scope, payload_hash))

    def commit_publication_withdrawal(self, prepared: PreparedPublicationWithdrawal):
        return self._commit("publication_withdrawal", prepared)

    def replay_publication_withdrawal(self, scope: IdempotencyScope, payload_hash: str):
        return self._replay("publication_withdrawal", scope, payload_hash)

    def commit_supersession(self, prepared: PreparedSupersession):
        return self._commit("supersession", prepared)

    def replay_supersession(self, scope: IdempotencyScope, payload_hash: str):
        return self._replay("supersession", scope, payload_hash)

    def get_revision(self, revision_id: str, workspace_id: str) -> FmeaRevision | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT revision_id FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
                (_text(workspace_id, "workspace_id"), _text(revision_id, "revision_id")),
            ).fetchone()
            return None if row is None else self._revision_from_connection(connection, revision_id, workspace_id)
        finally:
            connection.close()

    def get_revision_record_version(self, revision_id: str, workspace_id: str) -> int | None:
        connection = self._connect()
        try:
            workspace = _text(workspace_id, "workspace_id")
            revision = _text(revision_id, "revision_id")
            row = connection.execute(
                "SELECT record_version FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
                (workspace, revision),
            ).fetchone()
            if row is None:
                return None
            self._revision_from_connection(connection, revision, workspace)
            return int(row["record_version"])
        finally:
            connection.close()

    @staticmethod
    def _single_row(
        connection: sqlite3.Connection,
        sql: str,
        parameters: tuple[object, ...],
        description: str,
    ) -> sqlite3.Row | None:
        rows = connection.execute(sql, parameters).fetchall()
        if len(rows) > 1:
            raise ValueError(f"persisted {description} has duplicate effective rows")
        return None if not rows else rows[0]

    @staticmethod
    def _verify_canonical_row(row: sqlite3.Row, json_column: str, value: object, description: str) -> None:
        payload = row[json_column]
        canonical_payload, canonical_hash_value = _object_json(value)
        if payload != canonical_payload or row["canonical_json_hash"] != canonical_hash_value:
            raise ValueError(f"persisted {description} is not canonical")

    def get_approval_submission(self, submission_id: str, workspace_id: str) -> ApprovalSubmission | None:
        connection = self._connect()
        try:
            workspace = _text(workspace_id, "workspace_id")
            submission = _text(submission_id, "submission_id")
            row = self._single_row(
                connection,
                "SELECT * FROM fmea_approval_submissions WHERE workspace_id=? AND submission_id=?",
                (workspace, submission),
                "approval submission",
            )
            if row is None:
                return None
            return self._submission_from_connection(connection, submission, workspace)
        finally:
            connection.close()

    def get_approval_decision(self, approval_id: str, workspace_id: str) -> ApprovalDecision | None:
        connection = self._connect()
        try:
            workspace = _text(workspace_id, "workspace_id")
            approval = _text(approval_id, "approval_id")
            row = self._single_row(
                connection,
                "SELECT * FROM fmea_approval_decisions WHERE workspace_id=? AND approval_id=?",
                (workspace, approval),
                "approval decision",
            )
            if row is None:
                return None
            return self._approval_from_connection(connection, approval, workspace)
        finally:
            connection.close()

    def get_approval_decision_for_submission(
        self, submission_id: str, workspace_id: str
    ) -> ApprovalDecision | None:
        connection = self._connect()
        try:
            workspace = _text(workspace_id, "workspace_id")
            submission = _text(submission_id, "submission_id")
            row = self._single_row(
                connection,
                "SELECT * FROM fmea_approval_decisions WHERE workspace_id=? AND submission_id=? "
                "ORDER BY created_at, approval_id",
                (workspace, submission),
                "approval decision",
            )
            if row is None:
                return None
            return self._approval_from_connection(connection, row["approval_id"], workspace)
        finally:
            connection.close()

    def get_approval_withdrawal(
        self, approval_id: str, workspace_id: str
    ) -> ApprovalWithdrawalRecord | None:
        connection = self._connect()
        try:
            workspace = _text(workspace_id, "workspace_id")
            approval = _text(approval_id, "approval_id")
            row = self._single_row(
                connection,
                "SELECT * FROM fmea_approval_withdrawals WHERE workspace_id=? AND approval_id=? "
                "ORDER BY created_at, withdrawal_id",
                (workspace, approval),
                "approval withdrawal",
            )
            if row is None:
                return None
            value = _decode_approval_withdrawal(row["withdrawal_json"])
            self._verify_canonical_row(row, "withdrawal_json", value, "approval withdrawal")
            if value.approval_id != approval or value.revision_id != row["revision_id"]:
                raise ValueError("persisted approval withdrawal binding is invalid")
            return value
        finally:
            connection.close()

    def get_publication(self, publication_id: str, workspace_id: str) -> PublishedRevision | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT publication_id FROM fmea_publications WHERE workspace_id=? AND publication_id=?",
                (_text(workspace_id, "workspace_id"), _text(publication_id, "publication_id")),
            ).fetchone()
            return None if row is None else self._publication_from_connection(connection, publication_id, workspace_id)
        finally:
            connection.close()

    def get_publication_lifecycle(self, publication_id: str, workspace_id: str) -> PublicationLifecycleView | None:
        connection = self._connect()
        try:
            workspace = _text(workspace_id, "workspace_id")
            publication_id = _text(publication_id, "publication_id")
            publication_row = self._single_row(
                connection,
                "SELECT * FROM fmea_publications WHERE workspace_id=? AND publication_id=?",
                (workspace, publication_id),
                "publication",
            )
            if publication_row is None:
                return None
            publication = self._publication_from_connection(connection, publication_id, workspace)

            withdrawal_row = self._single_row(
                connection,
                "SELECT * FROM fmea_publication_withdrawals WHERE workspace_id=? AND publication_id=? "
                "ORDER BY created_at, withdrawal_id",
                (workspace, publication_id),
                "publication withdrawal",
            )
            withdrawal = None
            if withdrawal_row is not None:
                withdrawal = _decode_publication_withdrawal(withdrawal_row["withdrawal_json"])
                self._verify_canonical_row(
                    withdrawal_row, "withdrawal_json", withdrawal, "publication withdrawal"
                )
                if withdrawal.publication_id != publication_id:
                    raise ValueError("persisted publication withdrawal binding is invalid")

            supersession_row = self._single_row(
                connection,
                "SELECT * FROM fmea_supersessions WHERE workspace_id=? AND old_publication_id=? "
                "ORDER BY created_at, supersession_id",
                (workspace, publication_id),
                "supersession",
            )
            supersession = None
            if supersession_row is not None:
                supersession = _decode_supersession(supersession_row["supersession_json"])
                self._verify_canonical_row(
                    supersession_row, "supersession_json", supersession, "supersession"
                )
                if supersession.old_publication_id != publication_id:
                    raise ValueError("persisted supersession binding is invalid")
            return project_publication_lifecycle(
                publication,
                withdrawal=withdrawal,
                supersession=supersession,
            )
        finally:
            connection.close()

    def get_snapshot(self, publication_id: str, workspace_id: str):
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM fmea_normalized_snapshots WHERE workspace_id=? AND (publication_id=? OR snapshot_id=?)",
                (_text(workspace_id, "workspace_id"), _text(publication_id, "publication_id"), publication_id),
            ).fetchone()
            if row is None:
                return None
            return self._snapshot_from_connection(connection, row["snapshot_id"], workspace_id)
        finally:
            connection.close()

    def get_readiness(self, readiness_id: str, workspace_id: str) -> ReadinessReportRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT readiness_id FROM fmea_revision_readiness_reports WHERE workspace_id=? AND readiness_id=?",
                (_text(workspace_id, "workspace_id"), _text(readiness_id, "readiness_id")),
            ).fetchone()
            return None if row is None else self._readiness_from_connection(connection, readiness_id, workspace_id)
        finally:
            connection.close()

    def get_export_eligibility(self, publication_id: str, workspace_id: str) -> ExportEligibilityRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT publication_id FROM fmea_export_eligibility WHERE workspace_id=? AND publication_id=?",
                (_text(workspace_id, "workspace_id"), _text(publication_id, "publication_id")),
            ).fetchone()
            return None if row is None else self._eligibility_from_connection(connection, publication_id, workspace_id)
        finally:
            connection.close()

    @staticmethod
    def _cursor(value: str | None) -> tuple[str, str] | None:
        if value is None:
            return None
        parts = value.split("|", 1)
        if len(parts) != 2 or not all(parts):
            raise ValueError("governance history cursor is invalid")
        return parts[0], parts[1]

    def _list_events(self, query: GovernanceHistoryQuery, expected_type: str) -> GovernanceHistoryPage:
        query_type = "revision" if expected_type == "approval" else "publication"
        if not isinstance(query, GovernanceHistoryQuery) or query.resource_type != query_type:
            raise ValueError("governance history query resource type is invalid")
        cursor = self._cursor(query.cursor)
        order = "DESC" if query.descending else "ASC"
        comparison = "<" if query.descending else ">"
        sql = "SELECT * FROM fmea_audit_events WHERE workspace_id=? AND resource_type=? AND resource_id=?"
        params: list[object] = [query.workspace_id, expected_type, query.resource_id]
        if cursor is not None:
            sql += f" AND (created_at,event_id) {comparison} (?,?)"
            params.extend(cursor)
        sql += f" ORDER BY created_at {order}, event_id {order} LIMIT ?"
        params.append(query.page_size + 1)
        connection = self._connect()
        try:
            rows = connection.execute(sql, params).fetchall()
            has_more = len(rows) > query.page_size
            rows = rows[: query.page_size]
            events: list[AuditEvent] = []
            for row in rows:
                event = decode_audit_event(row["event_json"])
                if (
                    event.workspace_id != query.workspace_id
                    or row["canonical_payload_hash"] != event.canonical_payload_hash
                ):
                    raise ValueError("persisted governance audit event is invalid")
                events.append(event)
            next_cursor = None if not has_more or not rows else f"{rows[-1]['created_at']}|{rows[-1]['event_id']}"
            return GovernanceHistoryPage(tuple(events), next_cursor)
        finally:
            connection.close()

    def list_approval_events(self, query: GovernanceHistoryQuery) -> GovernanceHistoryPage:
        return self._list_events(query, "approval")

    def list_publication_events(self, query: GovernanceHistoryQuery) -> GovernanceHistoryPage:
        return self._list_events(query, "publication")


__all__ = ["SqliteGovernanceRepository"]
