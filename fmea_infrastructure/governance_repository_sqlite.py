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
    PublicationManifest,
    PublicationWithdrawalRecord,
    PublishedRevision,
    ReadinessIssue,
    RetrievalProvenanceSnapshot,
    SupersessionRecord,
    canonical_json_bytes,
    validate_approval_binding,
    validate_supersession_binding,
)
from fmea_application.governance_contracts import (
    ApprovalCommand,
    ApprovalRejectionCommand,
    ApprovalResult,
    ApprovalSubmissionResult,
    GovernanceHistoryQuery,
    PreparedApproval,
    PreparedApprovalSubmission,
    PreparedApprovalWithdrawal,
    PreparedPublication,
    PreparedPublicationWithdrawal,
    PreparedRevision,
    PreparedSupersession,
    PublicationResult,
    PublicationWithdrawalResult,
    RevisionResult,
    SupersessionResult,
    canonical_governance_payload,
    governance_payload_hash,
)
from fmea_application.ports import ApprovalWithdrawalResult, GovernanceHistoryPage
from fmea_application.review_contracts import AuditEvent, IdempotencyScope, encode_review_json, idempotency_key_hash
from fmea_application.review_errors import ReviewError
from fmea_application.risk_contracts import OutboxEvent, canonical_json, outbox_payload_hash

from .repository_sqlite import SqliteFmeaRepository
from .sqlite_codec import decode_audit_event, load_strict_json

_MAX_BUSY_TIMEOUT_MS = 60_000
_KIND_TYPES: dict[str, type[object]] = {
    "revision": PreparedRevision,
    "approval_submission": PreparedApprovalSubmission,
    "approval": PreparedApproval,
    "approval_withdrawal": PreparedApprovalWithdrawal,
    "publication": PreparedPublication,
    "publication_withdrawal": PreparedPublicationWithdrawal,
    "supersession": PreparedSupersession,
}
_RESULT_FIELDS: dict[str, set[str]] = {
    "revision": {"revision_id", "record_version", "audit_event_id", "outbox_event_id", "replayed"},
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
        if kind == "revision":
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
            or audit.canonical_payload_hash != prepared.payload_hash
            or audit_row["resource_id"] != meta.history_id
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
            or outbox_row["workspace_id"] != meta.workspace_id
            or outbox_row["aggregate_type"] != "fmea_governance"
            or outbox_row["aggregate_id"] != meta.resource_id
            or outbox_row["event_type"] != cls._lifecycle_event_type(meta.kind, prepared)
        ):
            raise ValueError("persisted governance outbox is not canonical")
        if (
            outbox_row["payload_hash"] != outbox_payload_hash(outbox_payload)
            or outbox_row["idempotency_scope"] != prepared.scope.scope_key
        ):
            raise ValueError("persisted governance outbox binding is invalid")
        if meta.kind == "revision":
            cls._revision_from_connection(connection, meta.resource_id, meta.workspace_id)
        elif meta.kind == "approval_submission":
            cls._submission_from_connection(connection, meta.resource_id, meta.workspace_id)
        elif meta.kind == "approval":
            cls._approval_from_connection(connection, meta.resource_id, meta.workspace_id)
        elif meta.kind == "publication":
            cls._publication_from_connection(connection, meta.resource_id, meta.workspace_id)
            if (
                connection.execute(
                    "SELECT 1 FROM fmea_publication_manifests WHERE workspace_id=? AND manifest_id=?",
                    (meta.workspace_id, result.manifest_id),
                ).fetchone()
                is None
            ):
                raise ValueError("persisted publication manifest is missing")
            if (
                connection.execute(
                    "SELECT 1 FROM fmea_normalized_snapshots WHERE workspace_id=? AND snapshot_id=?",
                    (meta.workspace_id, result.snapshot_id),
                ).fetchone()
                is None
            ):
                raise ValueError("persisted normalized snapshot is missing")
        elif meta.kind == "approval_withdrawal":
            if (
                connection.execute(
                    "SELECT 1 FROM fmea_approval_withdrawals WHERE workspace_id=? AND withdrawal_id=?",
                    (meta.workspace_id, meta.resource_id),
                ).fetchone()
                is None
            ):
                raise ValueError("persisted approval withdrawal is missing")
        elif meta.kind == "publication_withdrawal":
            if (
                connection.execute(
                    "SELECT 1 FROM fmea_publication_withdrawals WHERE workspace_id=? AND withdrawal_id=?",
                    (meta.workspace_id, meta.resource_id),
                ).fetchone()
                is None
            ):
                raise ValueError("persisted publication withdrawal is missing")
        elif (
            connection.execute(
                "SELECT 1 FROM fmea_supersessions WHERE workspace_id=? AND supersession_id=?",
                (meta.workspace_id, meta.resource_id),
            ).fetchone()
            is None
        ):
            raise ValueError("persisted supersession is missing")

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
            table = "fmea_revisions"
            identifier = "revision_id"
        elif kind == "approval_submission":
            resource_id = result.submission_id
            table = "fmea_approval_submissions"
            identifier = "submission_id"
        elif kind == "approval":
            resource_id = result.approval_id
            table = "fmea_approval_decisions"
            identifier = "approval_id"
        elif kind == "approval_withdrawal":
            resource_id = result.withdrawal_id
            table = "fmea_approval_withdrawals"
            identifier = "withdrawal_id"
        elif kind == "publication":
            resource_id = result.publication_id
            table = "fmea_publications"
            identifier = "publication_id"
        elif kind == "publication_withdrawal":
            resource_id = result.withdrawal_id
            table = "fmea_publication_withdrawals"
            identifier = "withdrawal_id"
        else:
            resource_id = result.supersession_id
            table = "fmea_supersessions"
            identifier = "supersession_id"
        audit_row = connection.execute(
            "SELECT * FROM fmea_audit_events WHERE workspace_id=? AND event_id=?",
            (scope.workspace_id, result.audit_event_id),
        ).fetchone()
        if audit_row is None:
            raise ValueError("persisted governance audit event is missing")
        audit = decode_audit_event(audit_row["event_json"])
        if (
            audit.workspace_id != scope.workspace_id
            or audit.command != scope.command
            or audit.row_id != resource_id
            or audit.idempotency_key_hash != scope.key_hash
            or audit.canonical_payload_hash != payload_hash
            or audit_row["idempotency_scope"] != scope.scope_key
            or _object_json(audit)[0] != audit_row["event_json"]
        ):
            raise ValueError("persisted governance audit binding is invalid")
        authority_row = connection.execute(
            f"SELECT * FROM {table} WHERE workspace_id=? AND {identifier}=?",
            (scope.workspace_id, resource_id),
        ).fetchone()
        if authority_row is None:
            raise ValueError(f"persisted {kind} is missing")
        if kind not in {"revision", "publication"} and (
            authority_row["idempotency_scope"] != scope.scope_key or authority_row["payload_hash"] != payload_hash
        ):
            raise ValueError(f"persisted {kind} idempotency binding is invalid")
        outbox_row = connection.execute(
            "SELECT * FROM fmea_outbox_events WHERE workspace_id=? AND event_id=?",
            (scope.workspace_id, result.outbox_event_id),
        ).fetchone()
        if outbox_row is None:
            raise ValueError("persisted governance outbox event is missing")
        outbox_payload = load_strict_json(outbox_row["payload_json"], "governance outbox")
        expected_event_type = {
            "revision": "revision.assembled",
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
            or outbox_row["aggregate_type"] != "fmea_governance"
            or outbox_row["aggregate_id"] != resource_id
            or outbox_row["event_type"] != expected_event_type
            or outbox_row["idempotency_scope"] != scope.scope_key
            or outbox_row["payload_hash"] != outbox_payload_hash(outbox_payload)
        ):
            raise ValueError("persisted governance outbox binding is invalid")
        if kind == "revision":
            cls._revision_from_connection(connection, resource_id, scope.workspace_id)
        elif kind == "approval_submission":
            cls._submission_from_connection(connection, resource_id, scope.workspace_id)
        elif kind == "approval":
            cls._approval_from_connection(connection, resource_id, scope.workspace_id)
        elif kind == "publication":
            cls._publication_from_connection(connection, resource_id, scope.workspace_id)
            cls._manifest_from_connection(connection, result.manifest_id, scope.workspace_id)
            snapshot_row = connection.execute(
                "SELECT snapshot_id FROM fmea_normalized_snapshots WHERE workspace_id=? AND snapshot_id=? AND publication_id=?",
                (scope.workspace_id, result.snapshot_id, resource_id),
            ).fetchone()
            if snapshot_row is None:
                raise ValueError("persisted normalized snapshot is missing")
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
            or value.revision_hash != row["revision_hash"]
            or row["canonical_json_hash"] != _json_hash(payload)
            or value.analysis_record_version != row["analysis_record_version"]
            or row["record_version"] < 1
        ):
            raise ValueError("persisted revision identity or hash is invalid")
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
            or value.revision_hash != row["revision_hash"]
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
            or value.revision_hash != row["revision_hash"]
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
            or value.revision_hash != row["revision_hash"]
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
            or row["canonical_json_hash"] != _json_hash(payload)
        ):
            raise ValueError("persisted publication identity or hash is invalid")
        return value

    @classmethod
    def _insert_revision_row(cls, connection: sqlite3.Connection, revision: FmeaRevision) -> None:
        payload, payload_hash = _object_json(revision)
        connection.execute(
            "INSERT INTO fmea_revisions "
            "(workspace_id,revision_id,analysis_id,analysis_record_version,parent_revision_id,parent_revision_hash,revision_hash,revision_json,record_version,canonical_json_hash,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
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
                revision.created_at,
            ),
        )

    @classmethod
    def _ensure_revision(cls, connection: sqlite3.Connection, revision: FmeaRevision) -> None:
        row = connection.execute(
            "SELECT revision_json FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
            (revision.workspace_id, revision.revision_id),
        ).fetchone()
        if row is None:
            if revision.parent_revision_id is not None:
                parent = cls._revision_from_connection(connection, revision.parent_revision_id, revision.workspace_id)
                if parent.revision_hash != revision.parent_revision_hash:
                    _error("FMEA_REVIEW_REQUEST_INVALID", "Parent revision binding is invalid.")
            cls._insert_revision_row(connection, revision)
            return
        if _decode_revision(row["revision_json"]) != revision:
            _error("FMEA_IDEMPOTENCY_CONFLICT", "Revision identity is already bound to a different payload.")

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
        cls, workspace_id: str, actor_id: str, command: str, path: str, seed: str
    ) -> IdempotencyScope:
        key = str(uuid5(NAMESPACE_URL, f"fmea-governance:{seed}"))
        return IdempotencyScope(workspace_id, actor_id, command, path, idempotency_key_hash(key))

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
    def _persist_publication_dependencies(cls, connection: sqlite3.Connection, prepared: PreparedPublication) -> None:
        cls._ensure_revision(connection, prepared.revision)
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
            cls._insert_outbox(
                connection,
                outbox,
                scope,
                dependency_meta,
                "approval.approved" if prepared.approval.status is ApprovalStatus.APPROVED else "approval.rejected",
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
    def _write_revision(cls, connection: sqlite3.Connection, prepared: PreparedRevision, meta: _PreparedMeta) -> None:
        cls._ensure_revision(connection, prepared.revision)

    @classmethod
    def _write_submission(
        cls, connection: sqlite3.Connection, prepared: PreparedApprovalSubmission, meta: _PreparedMeta
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

    @classmethod
    def _write_approval(cls, connection: sqlite3.Connection, prepared: PreparedApproval, meta: _PreparedMeta) -> None:
        submission = cls._submission_from_connection(connection, prepared.submission.submission_id, meta.workspace_id)
        if submission != prepared.submission:
            _error("FMEA_VERSION_CONFLICT", "Approval submission binding is stale.")
        revision = cls._revision_from_connection(connection, submission.revision_id, meta.workspace_id)
        if revision.revision_hash != prepared.decision.revision_hash:
            _error("FMEA_VERSION_CONFLICT", "Approval revision binding is stale.")
        cls._insert_approval_row(
            connection,
            meta.workspace_id,
            prepared.decision,
            prepared.payload_hash,
            prepared.scope.scope_key,
            prepared.audit.event_id,
            prepared.outbox.event_id,
        )

    @classmethod
    def _write_approval_withdrawal(
        cls, connection: sqlite3.Connection, prepared: PreparedApprovalWithdrawal, meta: _PreparedMeta
    ) -> None:
        approval = cls._approval_from_connection(connection, prepared.approval.approval_id, meta.workspace_id)
        if approval != prepared.approval or approval.status is not ApprovalStatus.APPROVED:
            _error("FMEA_VERSION_CONFLICT", "Approval withdrawal binding is stale.")
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
        cls, connection: sqlite3.Connection, prepared: PreparedPublication, meta: _PreparedMeta
    ) -> None:
        cls._persist_publication_dependencies(connection, prepared)
        validate_approval_binding(prepared.approval, prepared.revision)
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
        cls._manifest_from_connection(
            connection, prepared.manifest.manifest_id, meta.workspace_id
        ) if connection.execute(
            "SELECT 1 FROM fmea_publication_manifests WHERE workspace_id=? AND manifest_id=?",
            (meta.workspace_id, prepared.manifest.manifest_id),
        ).fetchone() is not None else cls._insert_manifest(connection, prepared.manifest, meta.workspace_id)
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
        publication_payload, publication_json_hash = _object_json(prepared.publication)
        connection.execute(
            "INSERT INTO fmea_publications (workspace_id,publication_id,analysis_id,revision_id,revision_hash,approval_id,manifest_id,manifest_hash,snapshot_id,snapshot_hash,audit_chain_head,publisher_actor_id,record_version,publication_json,canonical_json_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                prepared.publication.created_at,
            ),
        )
        eligibility = {
            "eligible": prepared.manifest.export_eligible,
            "manifest_id": prepared.manifest.manifest_id,
            "publication_id": prepared.publication.publication_id,
        }
        eligibility_json = canonical_json(eligibility)
        connection.execute(
            "INSERT INTO fmea_export_eligibility (workspace_id,eligibility_id,publication_id,manifest_id,eligible,eligibility_hash,eligibility_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                meta.workspace_id,
                f"eligibility:{prepared.publication.publication_id}",
                prepared.publication.publication_id,
                prepared.manifest.manifest_id,
                int(prepared.manifest.export_eligible),
                _json_hash(eligibility_json),
                eligibility_json,
                prepared.publication.created_at,
            ),
        )

    @classmethod
    def _write_publication_withdrawal(
        cls, connection: sqlite3.Connection, prepared: PreparedPublicationWithdrawal, meta: _PreparedMeta
    ) -> None:
        publication = cls._publication_from_connection(
            connection, prepared.publication.publication_id, meta.workspace_id
        )
        if (
            publication != prepared.publication
            or publication.record_version != prepared.command.expected_publication_version
        ):
            _error("FMEA_VERSION_CONFLICT", "Publication withdrawal binding is stale.")
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
        cls, connection: sqlite3.Connection, prepared: PreparedSupersession, meta: _PreparedMeta
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

    @classmethod
    def _writer(cls, connection: sqlite3.Connection, prepared: Any, meta: _PreparedMeta) -> object:
        if meta.kind == "revision":
            cls._write_revision(connection, prepared, meta)
            return RevisionResult(prepared.revision.revision_id, 1, prepared.audit.event_id, prepared.outbox.event_id)
        if meta.kind == "approval_submission":
            cls._write_submission(connection, prepared, meta)
            return __import__(
                "fmea_application.governance_contracts", fromlist=["ApprovalSubmissionResult"]
            ).ApprovalSubmissionResult(
                prepared.submission.submission_id,
                prepared.submission.record_version,
                prepared.audit.event_id,
                prepared.outbox.event_id,
            )
        if meta.kind == "approval":
            cls._write_approval(connection, prepared, meta)
            return __import__("fmea_application.governance_contracts", fromlist=["ApprovalResult"]).ApprovalResult(
                prepared.decision.approval_id,
                prepared.decision.record_version,
                prepared.audit.event_id,
                prepared.outbox.event_id,
            )
        if meta.kind == "approval_withdrawal":
            cls._write_approval_withdrawal(connection, prepared, meta)
            return ApprovalWithdrawalResult(
                prepared.withdrawal.withdrawal_id,
                prepared.withdrawal.approval_id,
                prepared.audit.event_id,
                prepared.outbox.event_id,
            )
        if meta.kind == "publication":
            cls._write_publication(connection, prepared, meta)
            return PublicationResult(
                prepared.publication.publication_id,
                prepared.manifest.manifest_id,
                prepared.snapshot.snapshot_id,
                prepared.publication.record_version,
                prepared.audit.event_id,
                prepared.outbox.event_id,
            )
        if meta.kind == "publication_withdrawal":
            cls._write_publication_withdrawal(connection, prepared, meta)
            return PublicationWithdrawalResult(
                prepared.withdrawal.withdrawal_id,
                prepared.withdrawal.publication_id,
                prepared.audit.event_id,
                prepared.outbox.event_id,
            )
        cls._write_supersession(connection, prepared, meta)
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
            result = self._writer(connection, value, meta)
            for step in {
                "revision": ("revision.record",),
                "approval_submission": ("approval.submission",),
                "approval": ("approval.decision",),
                "approval_withdrawal": ("approval.withdrawal",),
                "publication": (
                    "publication.revision",
                    "publication.decision",
                    "publication.manifest",
                    "publication.snapshot",
                    "publication.record",
                ),
                "publication_withdrawal": ("publication.withdrawal",),
                "supersession": ("supersession.record",),
            }[kind]:
                self._fail(step)
            self._fail(f"{kind}.record")
            self._insert_outbox(connection, value.outbox, value.scope, meta, self._lifecycle_event_type(kind, value))
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

    def get_snapshot(self, publication_id: str, workspace_id: str):
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM fmea_normalized_snapshots WHERE workspace_id=? AND (publication_id=? OR snapshot_id=?)",
                (_text(workspace_id, "workspace_id"), _text(publication_id, "publication_id"), publication_id),
            ).fetchone()
            if row is None:
                return None
            from fmea_application.snapshot_contracts import NormalizedFmeaSnapshot

            data = _strict_object(
                row["snapshot_json"], "normalized snapshot", {field.name for field in fields(NormalizedFmeaSnapshot)}
            )
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
            if (
                value.workspace_id != workspace_id
                or value.snapshot_id != row["snapshot_id"]
                or value.publication_id != row["publication_id"]
                or value.revision_hash != row["revision_hash"]
                or value.snapshot_hash != row["snapshot_hash"]
                or row["canonical_json_hash"] != _json_hash(row["snapshot_json"])
                or _object_json(value)[0] != row["snapshot_json"]
            ):
                raise ValueError("persisted normalized snapshot is not canonical")
            return value
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
