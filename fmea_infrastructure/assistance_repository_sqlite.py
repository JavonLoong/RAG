"""Atomic SQLite persistence for immutable FMEA assistance records."""

# Internal codec sentinel errors are normalized to safe ReviewError values at
# the repository boundary. SQL fragments are module constants; all data values
# remain parameterized.
# ruff: noqa: S608, TRY003, TRY004, TRY300, TRY301

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import NoReturn, cast

from core_domain.fmea.codec import decode_evidence_pack, decode_row, encode_json
from core_domain.fmea.states import ActorType
from fmea_application.assistance_contracts import (
    AssistanceDecision,
    AssistanceDecisionAction,
    AssistanceHandlerCheckpoint,
    AssistanceKind,
    AssistanceSuggestion,
)
from fmea_application.review_contracts import (
    AuditEvent,
    IdempotencyScope,
    encode_review_json,
    idempotency_key_hash,
)
from fmea_application.review_errors import ReviewError
from fmea_application.risk_contracts import (
    PreparedAssistanceDecision,
    PreparedAssistanceSuggestion,
    assistance_decision_payload_hash,
    assistance_suggestion_payload_hash,
    canonical_json,
)

from .repository_sqlite import SqliteFmeaRepository
from .sqlite_codec import decode_audit_event

_MAX_BUSY_TIMEOUT_MS = 60_000
_SUGGESTION_COLUMNS = (
    "suggestion_id, workspace_id, kind, target_type, target_id, target_record_version, "
    "evidence_pack_ids_json, payload_json, evidence_ids_json, conflict_ids_json, uncertainty, "
    "model_hash, prompt_hash, run_id, trace_id, domain_pack_id, domain_pack_version, template_id, "
    "template_version, rule_pack_id, rule_pack_version, suggestion_record_version, status, applied, "
    "suggestion_hash, payload_hash, audit_event_id, created_at"
)
_DECISION_COLUMNS = (
    "decision_id, workspace_id, suggestion_id, suggestion_hash, suggestion_record_version, "
    "target_record_version, action, actor_id, actor_type, edits_json, decision_json, reason, "
    "idempotency_scope, payload_hash, audit_event_id, resulting_resource_type, resulting_resource_id, created_at"
)


def _safe_error(code: str, message: str, *, retryable: bool = False) -> ReviewError:
    return ReviewError(code, message, retryable)


def _storage_error() -> ReviewError:
    return _safe_error("FMEA_REVIEW_STORAGE_UNAVAILABLE", "Stored assistance resource failed integrity validation.")


def _conflict(message: str = "Idempotency key was already used with a different payload.") -> NoReturn:
    raise _safe_error("FMEA_IDEMPOTENCY_CONFLICT", message)


def _json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> NoReturn:
    raise ValueError("non-finite JSON number")


def _strict_json(payload: object, label: str) -> object:
    if not isinstance(payload, str):
        raise _storage_error()
    try:
        value = json.loads(payload, object_pairs_hook=_json_pairs, parse_constant=_reject_constant)
        if canonical_json(value) != payload:
            raise ValueError(f"noncanonical {label}")
        return value
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _storage_error() from exc


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    return value


def _decision_body(decision: AssistanceDecision) -> dict[str, object]:
    return {
        "decision_id": decision.decision_id,
        "suggestion_id": decision.suggestion_id,
        "suggestion_hash": decision.suggestion_hash,
        "suggestion_record_version": decision.suggestion_record_version,
        "target_record_version": decision.target_record_version,
        "action": decision.action.value,
        "actor_id": decision.actor_id,
        "actor_type": decision.actor_type.value,
        "edits": [[field, _plain(value)] for field, value in decision.edits],
        "reason": decision.reason,
        "idempotency_key": decision.idempotency_key,
        "resulting_resource_identity": (
            list(decision.resulting_resource_identity) if decision.resulting_resource_identity is not None else None
        ),
        "created_at": decision.created_at,
    }


class SqliteAssistanceRepository:
    """Workspace-scoped, append-only assistance persistence adapter."""

    def __init__(self, database_path: str | Path, *, busy_timeout_ms: int = 5000) -> None:
        if isinstance(busy_timeout_ms, bool) or not isinstance(busy_timeout_ms, int):
            raise ValueError("busy_timeout_ms must be an integer")
        if not 1 <= busy_timeout_ms <= _MAX_BUSY_TIMEOUT_MS:
            raise ValueError(f"busy_timeout_ms must be between 1 and {_MAX_BUSY_TIMEOUT_MS}")
        self.database_path = Path(database_path).expanduser().resolve()
        self._busy_timeout_ms = busy_timeout_ms

    def initialize(self) -> None:
        SqliteFmeaRepository(self.database_path, busy_timeout_ms=self._busy_timeout_ms).initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.database_path),
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @staticmethod
    def _insert_audit(
        connection: sqlite3.Connection,
        audit: AuditEvent,
        *,
        target_type: str,
        target_id: str,
        scope: IdempotencyScope,
    ) -> None:
        event_json = encode_review_json(audit)
        event_hash = "sha256:" + sha256(event_json.encode("utf-8")).hexdigest()
        connection.execute(
            "INSERT INTO fmea_assistance_audit_events "
            "(event_id, workspace_id, target_type, target_id, actor_id, actor_type, command, suggestion_id, "
            "decision_id, idempotency_scope, resource_path, canonical_payload_hash, event_hash, event_json, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                audit.event_id,
                audit.workspace_id,
                target_type,
                target_id,
                audit.actor_id,
                audit.actor_type.value,
                audit.command,
                audit.suggestion_id,
                audit.decision_id,
                scope.scope_key,
                scope.resource_path,
                audit.canonical_payload_hash,
                event_hash,
                event_json,
                audit.occurred_at_server,
            ),
        )

    @staticmethod
    def _idempotency_row(connection: sqlite3.Connection, scope: IdempotencyScope) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT payload_hash, state, resource_id, response_json FROM idempotency_records WHERE scope_key=?",
            (scope.scope_key,),
        ).fetchone()

    @staticmethod
    def _check_replay_row(row: sqlite3.Row | None, payload_hash: str, resource_type: str) -> str | None:
        if row is None:
            return None
        if str(row["payload_hash"]) != payload_hash:
            _conflict()
        if row["state"] != "completed" or row["resource_id"] is None or row["response_json"] is None:
            raise _storage_error()
        response = _strict_json(row["response_json"], "idempotency response")
        if not isinstance(response, dict) or response != {
            "resource_id": str(row["resource_id"]),
            "resource_type": resource_type,
        }:
            raise _storage_error()
        return str(row["resource_id"])

    @classmethod
    def _validate_completed_idempotency(
        cls,
        connection: sqlite3.Connection,
        *,
        scope_key: str,
        payload_hash: str,
        resource_type: str,
        resource_id: str,
    ) -> None:
        row = connection.execute(
            "SELECT payload_hash, state, resource_id, response_json FROM idempotency_records WHERE scope_key=?",
            (scope_key,),
        ).fetchone()
        if cls._check_replay_row(row, payload_hash, resource_type) != resource_id:
            raise _storage_error()

    @staticmethod
    def _validate_assistance_audit(
        connection: sqlite3.Connection,
        *,
        event_id: str,
        workspace_id: str,
        target_type: str,
        target_id: str,
        suggestion_id: str,
        decision_id: str | None,
        actor_id: str | None,
        actor_type: str | None,
        payload_hash: str | None = None,
        idempotency_key_hash_value: str | None = None,
    ) -> tuple[IdempotencyScope, str]:
        audit = connection.execute(
            "SELECT event_id, workspace_id, target_type, target_id, actor_id, actor_type, command, "
            "suggestion_id, decision_id, idempotency_scope, resource_path, canonical_payload_hash, event_hash, "
            "event_json, created_at "
            "FROM fmea_assistance_audit_events WHERE event_id=? AND workspace_id=?",
            (event_id, workspace_id),
        ).fetchone()
        if audit is None:
            raise _storage_error()
        try:
            event = decode_audit_event(audit["event_json"])
        except (TypeError, ValueError) as exc:
            raise _storage_error() from exc
        if encode_review_json(event) != audit["event_json"]:
            raise _storage_error()
        expected_hash = "sha256:" + sha256(str(audit["event_json"]).encode("utf-8")).hexdigest()
        if audit["event_hash"] != expected_hash:
            raise _storage_error()
        expected_actor_id = str(audit["actor_id"]) if actor_id is None else actor_id
        expected_actor_type = str(audit["actor_type"]) if actor_type is None else actor_type
        event_key_hash = event.idempotency_key_hash
        if idempotency_key_hash_value is not None and event_key_hash != idempotency_key_hash_value:
            raise _storage_error()
        reconstructed_scope = IdempotencyScope(
            workspace_id,
            expected_actor_id,
            str(audit["command"]),
            str(audit["resource_path"]),
            event_key_hash,
        )
        if reconstructed_scope.scope_key != audit["idempotency_scope"]:
            raise _storage_error()
        checks = (
            event.event_id == event_id,
            event.workspace_id == workspace_id,
            event.actor_id == expected_actor_id,
            event.actor_type.value == expected_actor_type,
            event.command == audit["command"],
            event.row_id == target_id,
            event.suggestion_id == suggestion_id,
            event.decision_id == decision_id,
            event.canonical_payload_hash == audit["canonical_payload_hash"],
            event.occurred_at_server == audit["created_at"],
            event.action is None,
            audit["event_id"] == event_id,
            audit["workspace_id"] == workspace_id,
            audit["target_type"] == target_type,
            audit["target_id"] == target_id,
            audit["actor_id"] == expected_actor_id,
            audit["actor_type"] == expected_actor_type,
            audit["suggestion_id"] == suggestion_id,
            audit["decision_id"] == decision_id,
            payload_hash is None or audit["canonical_payload_hash"] == payload_hash,
        )
        if not all(checks):
            raise _storage_error()
        return reconstructed_scope, str(audit["canonical_payload_hash"])

    @staticmethod
    def _reserve_idempotency(
        connection: sqlite3.Connection,
        scope: IdempotencyScope,
        payload_hash: str,
        created_at: str,
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
        resource_type: str,
        resource_id: str,
        completed_at: str,
    ) -> None:
        response_json = canonical_json({"resource_id": resource_id, "resource_type": resource_type})
        cursor = connection.execute(
            "UPDATE idempotency_records SET state='completed', status_code=201, resource_id=?, response_json=?, "
            "completed_at=? WHERE scope_key=? AND payload_hash=? AND state='reserved'",
            (resource_id, response_json, completed_at, scope.scope_key, payload_hash),
        )
        if cursor.rowcount != 1:
            raise _storage_error()

    @staticmethod
    def _authoritative_row(connection: sqlite3.Connection, row_id: str, workspace_id: str):
        row = connection.execute(
            "SELECT row_json, row_hash, record_version FROM fmea_rows WHERE row_id=? AND workspace_id=?",
            (row_id, workspace_id),
        ).fetchone()
        if row is None:
            raise _safe_error("FMEA_ROW_NOT_FOUND", "FMEA row was not found.")
        try:
            domain_row = decode_row(str(row["row_json"]))
            if encode_json(domain_row) != row["row_json"] or domain_row.record_version != int(row["record_version"]):
                raise ValueError("row mismatch")
        except Exception as exc:
            raise _storage_error() from exc
        return domain_row

    @staticmethod
    def _authoritative_evidence(connection: sqlite3.Connection, pack_id: str, workspace_id: str):
        row = connection.execute(
            "SELECT pack_json, pack_hash FROM evidence_packs WHERE pack_id=? AND workspace_id=?",
            (pack_id, workspace_id),
        ).fetchone()
        if row is None:
            raise _safe_error("FMEA_EVIDENCE_INVALID", "Evidence pack is invalid.")
        try:
            pack = decode_evidence_pack(str(row["pack_json"]))
            if encode_json(pack) != row["pack_json"] or pack.pack_hash != row["pack_hash"]:
                raise ValueError("evidence mismatch")
        except Exception as exc:
            raise _storage_error() from exc
        return pack

    @staticmethod
    def _validate_suggestion_source(
        connection: sqlite3.Connection,
        suggestion: AssistanceSuggestion[object],
    ) -> None:
        if suggestion.target_type == "fmea_row":
            row = SqliteAssistanceRepository._authoritative_row(
                connection, suggestion.target_id, suggestion.workspace_id
            )
            if row.record_version != suggestion.target_record_version:
                raise _safe_error("FMEA_REVIEW_SUGGESTION_STALE", "Assistance suggestion is stale.")
        available: set[str] = set()
        for pack_id in suggestion.evidence_pack_ids:
            pack = SqliteAssistanceRepository._authoritative_evidence(connection, pack_id, suggestion.workspace_id)
            available.update(ref.evidence_id for ref in pack.refs)
        if not set(suggestion.evidence_ids).issubset(available):
            raise _safe_error("FMEA_EVIDENCE_INVALID", "Assistance evidence is invalid.")

    @staticmethod
    def _insert_suggestion(
        connection: sqlite3.Connection,
        suggestion: AssistanceSuggestion[object],
        payload_hash: str,
        audit_event_id: str,
    ) -> None:
        connection.execute(
            "INSERT INTO fmea_assistance_suggestions ("
            + _SUGGESTION_COLUMNS
            + ") VALUES ("
            + ",".join("?" for _ in range(28))
            + ")",
            (
                suggestion.suggestion_id,
                suggestion.workspace_id,
                suggestion.kind.value,
                suggestion.target_type,
                suggestion.target_id,
                suggestion.target_record_version,
                canonical_json(list(suggestion.evidence_pack_ids)),
                canonical_json(_plain(suggestion.payload)),
                canonical_json(list(suggestion.evidence_ids)),
                canonical_json(list(suggestion.conflict_ids)),
                suggestion.uncertainty,
                suggestion.model_hash,
                suggestion.prompt_hash,
                suggestion.run_id,
                suggestion.trace_id,
                suggestion.domain_pack_id,
                suggestion.domain_pack_version,
                suggestion.template_id,
                suggestion.template_version,
                suggestion.rule_pack_id,
                suggestion.rule_pack_version,
                suggestion.record_version,
                "proposed",
                0,
                suggestion.suggestion_hash,
                payload_hash,
                audit_event_id,
                suggestion.created_at,
            ),
        )

    @staticmethod
    def _decode_suggestion(row: sqlite3.Row, connection: sqlite3.Connection) -> AssistanceSuggestion[object]:
        try:
            evidence_pack_ids = _strict_json(row["evidence_pack_ids_json"], "evidence packs")
            payload = _strict_json(row["payload_json"], "suggestion payload")
            evidence_ids = _strict_json(row["evidence_ids_json"], "evidence IDs")
            conflict_ids = _strict_json(row["conflict_ids_json"], "conflict IDs")
            if not all(isinstance(value, list) for value in (evidence_pack_ids, evidence_ids, conflict_ids)):
                raise ValueError("invalid ID arrays")
            suggestion = AssistanceSuggestion(
                suggestion_id=row["suggestion_id"],
                kind=AssistanceKind(row["kind"]),
                workspace_id=row["workspace_id"],
                target_type=row["target_type"],
                target_id=row["target_id"],
                target_record_version=row["target_record_version"],
                evidence_pack_ids=tuple(cast(list[str], evidence_pack_ids)),
                payload=payload,
                evidence_ids=tuple(cast(list[str], evidence_ids)),
                conflict_ids=tuple(cast(list[str], conflict_ids)),
                uncertainty=row["uncertainty"],
                model_hash=row["model_hash"],
                prompt_hash=row["prompt_hash"],
                run_id=row["run_id"],
                trace_id=row["trace_id"],
                domain_pack_id=row["domain_pack_id"],
                domain_pack_version=row["domain_pack_version"],
                template_id=row["template_id"],
                template_version=row["template_version"],
                rule_pack_id=row["rule_pack_id"],
                rule_pack_version=row["rule_pack_version"],
                record_version=row["suggestion_record_version"],
                created_at=row["created_at"],
                applied=bool(row["applied"]),
                suggestion_hash=row["suggestion_hash"],
            )
            if row["status"] != "proposed" or int(row["applied"]) != 0:
                raise ValueError("invalid suggestion state")
            scope, payload_hash = SqliteAssistanceRepository._validate_assistance_audit(
                connection,
                event_id=str(row["audit_event_id"]),
                workspace_id=suggestion.workspace_id,
                target_type=suggestion.target_type,
                target_id=suggestion.target_id,
                suggestion_id=suggestion.suggestion_id,
                decision_id=None,
                actor_id=None,
                actor_type=None,
                payload_hash=str(row["payload_hash"]),
            )
            SqliteAssistanceRepository._validate_completed_idempotency(
                connection,
                scope_key=scope.scope_key,
                payload_hash=payload_hash,
                resource_type="assistance_suggestion",
                resource_id=suggestion.suggestion_id,
            )
            if assistance_suggestion_payload_hash(scope, suggestion) != payload_hash:
                raise ValueError("suggestion payload hash mismatch")
            return suggestion
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc

    def get_suggestion(self, suggestion_id: str, workspace_id: str) -> AssistanceSuggestion[object] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                f"SELECT {_SUGGESTION_COLUMNS} FROM fmea_assistance_suggestions "
                "WHERE suggestion_id=? AND workspace_id=?",
                (suggestion_id, workspace_id),
            ).fetchone()
            return None if row is None else self._decode_suggestion(row, connection)
        finally:
            connection.close()

    def save_suggestion(  # noqa: C901
        self, prepared: PreparedAssistanceSuggestion
    ) -> AssistanceSuggestion[object]:
        if not isinstance(prepared, PreparedAssistanceSuggestion):
            raise _safe_error("FMEA_REVIEW_REQUEST_INVALID", "Prepared assistance suggestion is invalid.")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay_id = self._check_replay_row(
                self._idempotency_row(connection, prepared.scope), prepared.payload_hash, "assistance_suggestion"
            )
            if replay_id is not None:
                row = connection.execute(
                    f"SELECT {_SUGGESTION_COLUMNS} FROM fmea_assistance_suggestions "
                    "WHERE suggestion_id=? AND workspace_id=?",
                    (replay_id, prepared.suggestion.workspace_id),
                ).fetchone()
                if row is None:
                    raise _storage_error()
                result = self._decode_suggestion(row, connection)
                if assistance_suggestion_payload_hash(prepared.scope, result) != prepared.payload_hash:
                    raise _storage_error()
                connection.execute("COMMIT")
                return result
            self._validate_suggestion_source(connection, prepared.suggestion)
            self._reserve_idempotency(
                connection, prepared.scope, prepared.payload_hash, prepared.audit.occurred_at_server
            )
            self._insert_audit(
                connection,
                prepared.audit,
                target_type=prepared.suggestion.target_type,
                target_id=prepared.suggestion.target_id,
                scope=prepared.scope,
            )
            self._insert_suggestion(
                connection,
                prepared.suggestion,
                prepared.payload_hash,
                prepared.audit.event_id,
            )
            self._complete_idempotency(
                connection,
                prepared.scope,
                prepared.payload_hash,
                "assistance_suggestion",
                prepared.suggestion.suggestion_id,
                prepared.audit.occurred_at_server,
            )
            connection.execute("COMMIT")
            return prepared.suggestion
        except ReviewError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise _safe_error(
                "FMEA_MODEL_SUGGESTION_INVALID", "Assistance suggestion conflicts with stored state."
            ) from exc
        except sqlite3.Error as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise _safe_error(
                "FMEA_REVIEW_STORAGE_UNAVAILABLE", "Assistance storage is unavailable.", retryable=True
            ) from exc
        finally:
            connection.close()

    @staticmethod
    def _insert_decision(
        connection: sqlite3.Connection,
        prepared: PreparedAssistanceDecision,
    ) -> None:
        decision = prepared.decision
        identity = decision.resulting_resource_identity
        connection.execute(
            "INSERT INTO fmea_assistance_decisions ("
            + _DECISION_COLUMNS
            + ") VALUES ("
            + ",".join("?" for _ in range(18))
            + ")",
            (
                decision.decision_id,
                prepared.suggestion.workspace_id,
                decision.suggestion_id,
                decision.suggestion_hash,
                decision.suggestion_record_version,
                decision.target_record_version,
                decision.action.value,
                decision.actor_id,
                decision.actor_type.value,
                canonical_json([[field, _plain(value)] for field, value in decision.edits]),
                canonical_json(_decision_body(decision)),
                decision.reason,
                prepared.scope.scope_key,
                prepared.payload_hash,
                prepared.audit.event_id,
                identity[0] if identity is not None else None,
                identity[1] if identity is not None else None,
                decision.created_at,
            ),
        )

    @staticmethod
    def _decode_decision(row: sqlite3.Row, connection: sqlite3.Connection) -> AssistanceDecision:
        try:
            body = _strict_json(row["decision_json"], "assistance decision")
            edits = _strict_json(row["edits_json"], "assistance edits")
            expected_keys = {
                "decision_id",
                "suggestion_id",
                "suggestion_hash",
                "suggestion_record_version",
                "target_record_version",
                "action",
                "actor_id",
                "actor_type",
                "edits",
                "reason",
                "idempotency_key",
                "resulting_resource_identity",
                "created_at",
            }
            if not isinstance(body, dict) or set(body) != expected_keys or body["edits"] != edits:
                raise ValueError("invalid decision body")
            identity = body["resulting_resource_identity"]
            decision = AssistanceDecision(
                decision_id=cast(str, body["decision_id"]),
                suggestion_id=cast(str, body["suggestion_id"]),
                suggestion_hash=cast(str, body["suggestion_hash"]),
                suggestion_record_version=cast(int, body["suggestion_record_version"]),
                target_record_version=cast(int, body["target_record_version"]),
                action=AssistanceDecisionAction(cast(str, body["action"])),
                actor_id=cast(str, body["actor_id"]),
                actor_type=ActorType(cast(str, body["actor_type"])),
                edits=tuple((cast(str, item[0]), item[1]) for item in cast(list[list[object]], edits)),
                reason=cast(str, body["reason"]),
                idempotency_key=cast(str, body["idempotency_key"]),
                resulting_resource_identity=(
                    None if identity is None else (cast(list[str], identity)[0], cast(list[str], identity)[1])
                ),
                created_at=cast(str, body["created_at"]),
            )
            checks = (
                decision.decision_id == row["decision_id"],
                decision.suggestion_id == row["suggestion_id"],
                decision.suggestion_hash == row["suggestion_hash"],
                decision.suggestion_record_version == row["suggestion_record_version"],
                decision.target_record_version == row["target_record_version"],
                decision.action.value == row["action"],
                decision.actor_id == row["actor_id"],
                decision.actor_type.value == row["actor_type"],
                decision.reason == row["reason"],
                decision.created_at == row["created_at"],
                (
                    decision.resulting_resource_identity
                    == (
                        None
                        if row["resulting_resource_type"] is None and row["resulting_resource_id"] is None
                        else (row["resulting_resource_type"], row["resulting_resource_id"])
                    )
                ),
                canonical_json(_decision_body(decision)) == row["decision_json"],
            )
            if not all(checks):
                raise ValueError("decision columns mismatch")
            suggestion_row = connection.execute(
                f"SELECT {_SUGGESTION_COLUMNS} FROM fmea_assistance_suggestions "
                "WHERE suggestion_id=? AND workspace_id=?",
                (decision.suggestion_id, row["workspace_id"]),
            ).fetchone()
            if suggestion_row is None:
                raise ValueError("decision suggestion missing")
            suggestion = SqliteAssistanceRepository._decode_suggestion(suggestion_row, connection)
            if (
                decision.suggestion_hash != suggestion.suggestion_hash
                or decision.suggestion_record_version != suggestion.record_version
                or decision.target_record_version != suggestion.target_record_version
            ):
                raise ValueError("decision suggestion binding mismatch")
            scope, _ = SqliteAssistanceRepository._validate_assistance_audit(
                connection,
                event_id=str(row["audit_event_id"]),
                workspace_id=str(row["workspace_id"]),
                target_type=suggestion.target_type,
                target_id=suggestion.target_id,
                suggestion_id=decision.suggestion_id,
                decision_id=decision.decision_id,
                actor_id=decision.actor_id,
                actor_type=decision.actor_type.value,
                payload_hash=str(row["payload_hash"]),
                idempotency_key_hash_value=idempotency_key_hash(decision.idempotency_key),
            )
            if scope.scope_key != row["idempotency_scope"]:
                raise ValueError("decision idempotency scope mismatch")
            if assistance_decision_payload_hash(scope, suggestion, decision) != row["payload_hash"]:
                raise ValueError("decision payload hash mismatch")
            SqliteAssistanceRepository._validate_completed_idempotency(
                connection,
                scope_key=scope.scope_key,
                payload_hash=str(row["payload_hash"]),
                resource_type="assistance_decision",
                resource_id=decision.decision_id,
            )
            return decision
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc

    def get_decision(self, decision_id: str, workspace_id: str) -> AssistanceDecision | None:
        connection = self._connect()
        try:
            row = connection.execute(
                f"SELECT {_DECISION_COLUMNS} FROM fmea_assistance_decisions WHERE decision_id=? AND workspace_id=?",
                (decision_id, workspace_id),
            ).fetchone()
            return None if row is None else self._decode_decision(row, connection)
        finally:
            connection.close()

    def replay_decision(self, scope: IdempotencyScope, payload_hash: str) -> AssistanceDecision | None:
        connection = self._connect()
        try:
            resource_id = self._check_replay_row(
                self._idempotency_row(connection, scope), payload_hash, "assistance_decision"
            )
            if resource_id is None:
                return None
            row = connection.execute(
                f"SELECT {_DECISION_COLUMNS} FROM fmea_assistance_decisions WHERE decision_id=? AND workspace_id=?",
                (resource_id, scope.workspace_id),
            ).fetchone()
            if row is None:
                raise _storage_error()
            decision = self._decode_decision(row, connection)
            suggestion_row = connection.execute(
                f"SELECT {_SUGGESTION_COLUMNS} FROM fmea_assistance_suggestions "
                "WHERE suggestion_id=? AND workspace_id=?",
                (decision.suggestion_id, scope.workspace_id),
            ).fetchone()
            if suggestion_row is None:
                raise _storage_error()
            suggestion = self._decode_suggestion(suggestion_row, connection)
            if assistance_decision_payload_hash(scope, suggestion, decision) != payload_hash:
                raise _storage_error()
            return decision
        finally:
            connection.close()

    def reserve_decision(
        self,
        scope: IdempotencyScope,
        reservation_hash: str,
        decision_id: str,
        created_at: str,
    ) -> AssistanceDecision | None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._idempotency_row(connection, scope)
            if row is None:
                connection.execute(
                    "INSERT INTO idempotency_records "
                    "(scope_key, payload_hash, state, status_code, resource_id, response_json, created_at, completed_at) "
                    "VALUES (?, ?, 'reserved', NULL, ?, NULL, ?, NULL)",
                    (scope.scope_key, reservation_hash, decision_id, created_at),
                )
                connection.execute("COMMIT")
                return None
            if row["state"] == "completed":
                stored_id = str(row["resource_id"])
                decision_row = connection.execute(
                    f"SELECT {_DECISION_COLUMNS} FROM fmea_assistance_decisions WHERE decision_id=? AND workspace_id=?",
                    (stored_id, scope.workspace_id),
                ).fetchone()
                if stored_id != decision_id or decision_row is None:
                    raise _storage_error()
                decision = self._decode_decision(decision_row, connection)
                connection.execute("COMMIT")
                return decision
            if (
                row["state"] != "reserved"
                or row["payload_hash"] != reservation_hash
                or row["resource_id"] != decision_id
            ):
                _conflict()
            self._decode_handler_checkpoint(row, reservation_hash, decision_id)
            connection.execute("COMMIT")
            return None
        except ReviewError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except sqlite3.Error as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise _safe_error(
                "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                "Assistance storage is unavailable.",
                retryable=True,
            ) from exc
        finally:
            connection.close()

    @staticmethod
    def _decode_handler_checkpoint(
        row: sqlite3.Row,
        reservation_hash: str,
        decision_id: str,
    ) -> AssistanceHandlerCheckpoint | None:
        if row["state"] != "reserved" or row["payload_hash"] != reservation_hash or row["resource_id"] != decision_id:
            raise _storage_error()
        if row["response_json"] is None:
            return None
        payload = _strict_json(row["response_json"], "assistance handler checkpoint")
        if payload == {"handler_state": "started"}:
            return None
        if not isinstance(payload, dict) or set(payload) != {
            "applied_record_version",
            "decision_id",
            "handler_state",
            "reservation_hash",
            "resulting_resource_identity",
        }:
            raise _storage_error()
        identity = payload["resulting_resource_identity"]
        if identity is not None:
            if not isinstance(identity, list) or len(identity) != 2:
                raise _storage_error()
            identity = (identity[0], identity[1])
        if payload["handler_state"] != "completed":
            raise _storage_error()
        try:
            return AssistanceHandlerCheckpoint(
                decision_id=payload["decision_id"],
                reservation_hash=payload["reservation_hash"],
                resulting_resource_identity=identity,
                applied_record_version=payload["applied_record_version"],
            )
        except (TypeError, ValueError) as exc:
            raise _storage_error() from exc

    def get_decision_handler_checkpoint(
        self,
        scope: IdempotencyScope,
        reservation_hash: str,
        decision_id: str,
    ) -> AssistanceHandlerCheckpoint | None:
        connection = self._connect()
        try:
            row = self._idempotency_row(connection, scope)
            if row is None:
                raise _storage_error()
            return self._decode_handler_checkpoint(row, reservation_hash, decision_id)
        finally:
            connection.close()

    def claim_decision_handler(
        self,
        scope: IdempotencyScope,
        reservation_hash: str,
        decision_id: str,
    ) -> bool:
        connection = self._connect()
        started = canonical_json({"handler_state": "started"})
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE idempotency_records SET response_json=? WHERE scope_key=? AND payload_hash=? "
                "AND state='reserved' AND resource_id=? AND response_json IS NULL",
                (started, scope.scope_key, reservation_hash, decision_id),
            )
            if cursor.rowcount == 1:
                connection.execute("COMMIT")
                return True
            row = self._idempotency_row(connection, scope)
            if row is None:
                raise _storage_error()
            self._decode_handler_checkpoint(row, reservation_hash, decision_id)
            connection.execute("COMMIT")
            return False
        except ReviewError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def save_decision_handler_checkpoint(
        self,
        scope: IdempotencyScope,
        checkpoint: AssistanceHandlerCheckpoint,
    ) -> None:
        identity = checkpoint.resulting_resource_identity
        completed = canonical_json({
            "applied_record_version": checkpoint.applied_record_version,
            "decision_id": checkpoint.decision_id,
            "handler_state": "completed",
            "reservation_hash": checkpoint.reservation_hash,
            "resulting_resource_identity": None if identity is None else list(identity),
        })
        started = canonical_json({"handler_state": "started"})
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE idempotency_records SET response_json=? WHERE scope_key=? AND payload_hash=? "
                "AND state='reserved' AND resource_id=? AND response_json=?",
                (
                    completed,
                    scope.scope_key,
                    checkpoint.reservation_hash,
                    checkpoint.decision_id,
                    started,
                ),
            )
            if cursor.rowcount != 1:
                raise _storage_error()
            connection.execute("COMMIT")
        except ReviewError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def append_decision(self, prepared: PreparedAssistanceDecision) -> AssistanceDecision:  # noqa: C901
        if not isinstance(prepared, PreparedAssistanceDecision):
            raise _safe_error("FMEA_REVIEW_REQUEST_INVALID", "Prepared assistance decision is invalid.")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            idempotency_row = self._idempotency_row(connection, prepared.scope)
            if prepared.reservation_hash is None or (
                idempotency_row is not None and idempotency_row["state"] == "completed"
            ):
                replay_id = self._check_replay_row(idempotency_row, prepared.payload_hash, "assistance_decision")
            else:
                if idempotency_row is None:
                    raise _storage_error()
                checkpoint = self._decode_handler_checkpoint(
                    idempotency_row,
                    prepared.reservation_hash,
                    prepared.decision.decision_id,
                )
                if (
                    checkpoint is None
                    or checkpoint.resulting_resource_identity != prepared.decision.resulting_resource_identity
                    or checkpoint.applied_record_version != prepared.audit.applied_record_version
                ):
                    raise _storage_error()
                replay_id = None
            if replay_id is not None:
                row = connection.execute(
                    f"SELECT {_DECISION_COLUMNS} FROM fmea_assistance_decisions WHERE decision_id=? AND workspace_id=?",
                    (replay_id, prepared.suggestion.workspace_id),
                ).fetchone()
                if row is None:
                    raise _storage_error()
                result = self._decode_decision(row, connection)
                if (
                    assistance_decision_payload_hash(prepared.scope, prepared.suggestion, result)
                    != prepared.payload_hash
                ):
                    raise _storage_error()
                connection.execute("COMMIT")
                return result
            source = connection.execute(
                f"SELECT {_SUGGESTION_COLUMNS} FROM fmea_assistance_suggestions "
                "WHERE suggestion_id=? AND workspace_id=?",
                (prepared.suggestion.suggestion_id, prepared.suggestion.workspace_id),
            ).fetchone()
            if source is None:
                raise _safe_error("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "Assistance suggestion was not found.")
            authoritative = self._decode_suggestion(source, connection)
            if authoritative != prepared.suggestion:
                raise _safe_error("FMEA_MODEL_SUGGESTION_INVALID", "Assistance suggestion binding is invalid.")
            self._validate_suggestion_source(connection, authoritative)
            if prepared.decision.actor_type is not ActorType.HUMAN:
                raise _safe_error("FMEA_REVIEW_FORBIDDEN", "A human actor is required.")
            if prepared.reservation_hash is None:
                self._reserve_idempotency(
                    connection, prepared.scope, prepared.payload_hash, prepared.audit.occurred_at_server
                )
            else:
                rebound = connection.execute(
                    "UPDATE idempotency_records SET payload_hash=? WHERE scope_key=? AND payload_hash=? "
                    "AND state='reserved' AND resource_id=?",
                    (
                        prepared.payload_hash,
                        prepared.scope.scope_key,
                        prepared.reservation_hash,
                        prepared.decision.decision_id,
                    ),
                )
                if rebound.rowcount != 1:
                    raise _storage_error()
            # The decision has an FK to its immutable audit row, so the audit is inserted first.
            self._insert_audit(
                connection,
                prepared.audit,
                target_type=prepared.suggestion.target_type,
                target_id=prepared.suggestion.target_id,
                scope=prepared.scope,
            )
            self._insert_decision(connection, prepared)
            if prepared.reservation_hash is None:
                self._complete_idempotency(
                    connection,
                    prepared.scope,
                    prepared.payload_hash,
                    "assistance_decision",
                    prepared.decision.decision_id,
                    prepared.audit.occurred_at_server,
                )
            else:
                response_json = canonical_json({
                    "resource_id": prepared.decision.decision_id,
                    "resource_type": "assistance_decision",
                })
                cursor = connection.execute(
                    "UPDATE idempotency_records SET state='completed', status_code=201, "
                    "response_json=?, completed_at=? WHERE scope_key=? AND payload_hash=? AND state='reserved' "
                    "AND resource_id=?",
                    (
                        response_json,
                        prepared.audit.occurred_at_server,
                        prepared.scope.scope_key,
                        prepared.payload_hash,
                        prepared.decision.decision_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise _storage_error()
            connection.execute("COMMIT")
            return prepared.decision
        except ReviewError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise _safe_error("FMEA_REVIEW_ACTION_INVALID", "Assistance decision conflicts with stored state.") from exc
        except sqlite3.Error as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise _safe_error(
                "FMEA_REVIEW_STORAGE_UNAVAILABLE", "Assistance storage is unavailable.", retryable=True
            ) from exc
        finally:
            connection.close()


__all__ = ["SqliteAssistanceRepository"]
