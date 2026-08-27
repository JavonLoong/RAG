"""Atomic SQLite persistence for the FMEA risk lifecycle."""

# SQL fragments are constants and all values remain parameterized. Stored
# contract failures are normalized to stable ReviewError responses.
# ruff: noqa: C901, S608, TRY003, TRY004, TRY300, TRY301

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import NoReturn, cast

from core_domain.fmea.codec import decode_evidence_pack, decode_row, encode_json
from core_domain.fmea.domain_pack import DomainPackManifest
from core_domain.fmea.scoring import (
    RiskAssessment,
    RiskAssessmentRecord,
    RiskProposal,
    ScoreDimension,
    ScoringRulePack,
)
from core_domain.fmea.states import RiskStatus
from fmea_application.review_contracts import AuditEvent, IdempotencyScope, encode_review_json
from fmea_application.review_errors import ReviewError
from fmea_application.risk_contracts import (
    OutboxEvent,
    PreparedRiskConfirmation,
    PreparedRiskInvalidation,
    PreparedRiskProposal,
    PreparedRiskRejection,
    RiskConfirmationResult,
    canonical_json,
    outbox_payload_hash,
    risk_confirmation_payload_hash,
)

from .domain_pack_registry import (
    canonical_domain_pack_body,
    canonical_scoring_rule_body,
    domain_pack_content_hash,
    load_domain_pack_manifest,
    load_scoring_rule_pack,
    scoring_rule_content_hash,
)
from .repository_sqlite import SqliteFmeaRepository
from .sqlite_codec import decode_audit_event

_MAX_BUSY_TIMEOUT_MS = 60_000
_PROPOSAL_COLUMNS = (
    "proposal_id, workspace_id, row_id, source_record_version, evidence_pack_id, domain_pack_id, "
    "domain_pack_version, rule_pack_id, rule_pack_version, dimensions_json, reason, assistance_suggestion_id, "
    "uncertainty, status, proposal_hash, payload_hash, audit_event_id, idempotency_scope, created_at"
)
_ASSESSMENT_COLUMNS = (
    "assessment_id, workspace_id, row_id, source_record_version, evidence_pack_id, domain_pack_id, "
    "domain_pack_version, rule_pack_id, rule_pack_version, status, dimensions_json, derived_json, proposal_id, "
    "assistance_suggestion_id, confirmer_actor_id, invalidated_reason, record_version, assessment_hash, "
    "created_at, updated_at"
)
_OUTBOX_COLUMNS = (
    "event_id, workspace_id, aggregate_type, aggregate_id, event_type, status, payload_json, payload_hash, "
    "idempotency_scope, created_at"
)


def _safe_error(code: str, message: str, *, retryable: bool = False) -> ReviewError:
    return ReviewError(code, message, retryable)


def _storage_error() -> ReviewError:
    return _safe_error("FMEA_REVIEW_STORAGE_UNAVAILABLE", "Stored risk resource failed integrity validation.")


def _conflict() -> NoReturn:
    raise _safe_error("FMEA_IDEMPOTENCY_CONFLICT", "Idempotency key was already used with a different payload.")


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
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
        value = json.loads(payload, object_pairs_hook=_pairs, parse_constant=_reject_constant)
        if canonical_json(value) != payload:
            raise ValueError(f"noncanonical {label}")
        return value
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _storage_error() from exc


def _object_hash(value: object) -> str:
    return "sha256:" + sha256(_canonical(value).encode("utf-8")).hexdigest()


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    return value


def _canonical(value: object) -> str:
    return canonical_json(_json_value(value))


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, label)


def _optional_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer or null")
    return value


def _string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    result = tuple(_required_text(item, f"{label} item") for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must not contain duplicates")
    return result


def _decode_dimensions(value: object) -> tuple[ScoreDimension, ...]:
    if not isinstance(value, list):
        raise ValueError("dimensions must be an array")
    result: list[ScoreDimension] = []
    expected = {"name", "value", "evidence_ids", "reason", "uncertainty"}
    for item in value:
        if not isinstance(item, dict) or set(item) != expected or not isinstance(item["evidence_ids"], list):
            raise ValueError("invalid dimension")
        result.append(
            ScoreDimension(
                name=_required_text(item["name"], "dimension name"),
                value=_optional_int(item["value"], "dimension value"),
                evidence_ids=_string_list(item["evidence_ids"], "dimension evidence_ids"),
                reason=_required_text(item["reason"], "dimension reason"),
                uncertainty=_optional_text(item["uncertainty"], "dimension uncertainty"),
            )
        )
    return tuple(result)


def _decode_derived(value: object) -> RiskAssessment | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("invalid derived assessment")
    expected = {
        "severity_by_consequence_class",
        "decision_severity",
        "occurrence",
        "detection",
        "rpn",
        "decision_priority",
        "inherent_risk",
        "current_risk",
        "target_residual_risk",
        "verified_residual_risk",
        "uncertainty",
        "reason",
        "scoring_rule_pack_id",
        "scoring_rule_pack_version",
        "evidence_ids",
    }
    if set(value) != expected:
        raise ValueError("invalid derived assessment fields")
    severity = value["severity_by_consequence_class"]
    evidence = value["evidence_ids"]
    if not isinstance(severity, list):
        raise ValueError("invalid derived assessment arrays")
    severity_values: list[tuple[str, int | None]] = []
    for item in severity:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("invalid severity consequence pair")
        severity_values.append(
            (
                _required_text(item[0], "severity consequence class"),
                _optional_int(item[1], "severity consequence value"),
            )
        )
    return RiskAssessment(
        severity_by_consequence_class=tuple(severity_values),
        decision_severity=_optional_int(value["decision_severity"], "decision_severity"),
        occurrence=_optional_int(value["occurrence"], "occurrence"),
        detection=_optional_int(value["detection"], "detection"),
        rpn=_optional_int(value["rpn"], "rpn"),
        decision_priority=_required_text(value["decision_priority"], "decision_priority"),
        inherent_risk=_optional_int(value["inherent_risk"], "inherent_risk"),
        current_risk=_optional_int(value["current_risk"], "current_risk"),
        target_residual_risk=_optional_int(value["target_residual_risk"], "target_residual_risk"),
        verified_residual_risk=_optional_int(value["verified_residual_risk"], "verified_residual_risk"),
        uncertainty=_optional_text(value["uncertainty"], "risk uncertainty"),
        reason=_required_text(value["reason"], "risk reason"),
        scoring_rule_pack_id=_required_text(value["scoring_rule_pack_id"], "scoring_rule_pack_id"),
        scoring_rule_pack_version=_required_text(value["scoring_rule_pack_version"], "scoring_rule_pack_version"),
        evidence_ids=_string_list(evidence, "risk evidence_ids"),
    )


def _decode_assessment_value(value: object) -> RiskAssessmentRecord:
    if not isinstance(value, dict):
        raise ValueError("assessment must be an object")
    expected = {
        "assessment_id",
        "workspace_id",
        "row_id",
        "source_record_version",
        "evidence_pack_id",
        "domain_pack_id",
        "domain_pack_version",
        "rule_pack_id",
        "rule_pack_version",
        "status",
        "dimensions",
        "derived",
        "proposal_id",
        "assistance_suggestion_id",
        "confirmer_actor_id",
        "invalidated_reason",
        "record_version",
        "created_at",
        "updated_at",
    }
    if set(value) != expected:
        raise ValueError("invalid assessment fields")
    return RiskAssessmentRecord(
        assessment_id=cast(str, value["assessment_id"]),
        workspace_id=cast(str, value["workspace_id"]),
        row_id=cast(str, value["row_id"]),
        source_record_version=cast(int, value["source_record_version"]),
        evidence_pack_id=cast(str, value["evidence_pack_id"]),
        domain_pack_id=cast(str, value["domain_pack_id"]),
        domain_pack_version=cast(str, value["domain_pack_version"]),
        rule_pack_id=cast(str, value["rule_pack_id"]),
        rule_pack_version=cast(str, value["rule_pack_version"]),
        status=RiskStatus(cast(str, value["status"])),
        dimensions=_decode_dimensions(value["dimensions"]),
        derived=_decode_derived(value["derived"]),
        proposal_id=cast(str | None, value["proposal_id"]),
        assistance_suggestion_id=cast(str | None, value["assistance_suggestion_id"]),
        confirmer_actor_id=cast(str | None, value["confirmer_actor_id"]),
        invalidated_reason=cast(str | None, value["invalidated_reason"]),
        record_version=cast(int, value["record_version"]),
        created_at=cast(str, value["created_at"]),
        updated_at=cast(str, value["updated_at"]),
    )


def _audit_row_matches(row: sqlite3.Row, audit: AuditEvent) -> bool:
    return (
        row["event_id"] == audit.event_id
        and row["row_id"] == audit.row_id
        and row["workspace_id"] == audit.workspace_id
        and row["actor_id"] == audit.actor_id
        and row["actor_type"] == audit.actor_type.value
        and row["command"] == audit.command
        and row["action"] == (audit.action.value if audit.action is not None else None)
        and row["suggestion_id"] == audit.suggestion_id
        and row["decision_id"] == audit.decision_id
        and row["expected_record_version"] == audit.expected_record_version
        and row["applied_record_version"] == audit.applied_record_version
        and row["before_hash"] == audit.before_hash
        and row["after_hash"] == audit.after_hash
        and row["canonical_payload_hash"] == audit.canonical_payload_hash
        and row["event_json"] == encode_review_json(audit)
        and row["created_at"] == audit.occurred_at_server
    )


def _assessment_identity_matches(left: RiskAssessmentRecord, right: RiskAssessmentRecord) -> bool:
    return all(
        getattr(left, field_name) == getattr(right, field_name)
        for field_name in (
            "assessment_id",
            "workspace_id",
            "row_id",
            "source_record_version",
            "evidence_pack_id",
            "domain_pack_id",
            "domain_pack_version",
            "rule_pack_id",
            "rule_pack_version",
            "dimensions",
            "proposal_id",
            "assistance_suggestion_id",
            "created_at",
        )
    )


class SqliteRiskRepository:
    """Workspace-scoped risk persistence with atomic lifecycle transitions."""

    def __init__(self, database_path: str | Path, *, busy_timeout_ms: int = 5000) -> None:
        if isinstance(busy_timeout_ms, bool) or not isinstance(busy_timeout_ms, int):
            raise ValueError("busy_timeout_ms must be an integer")
        if not 1 <= busy_timeout_ms <= _MAX_BUSY_TIMEOUT_MS:
            raise ValueError(f"busy_timeout_ms must be between 1 and {_MAX_BUSY_TIMEOUT_MS}")
        self.database_path = Path(database_path).expanduser().resolve()
        self._busy_timeout_ms = busy_timeout_ms

    def initialize(self) -> None:
        SqliteFmeaRepository(self.database_path, busy_timeout_ms=self._busy_timeout_ms).initialize()

    def register_pack_snapshots(
        self,
        workspace_id: str,
        domain_pack: DomainPackManifest,
        domain_source: bytes,
        rule_pack: ScoringRulePack,
        rule_source: bytes,
        created_at: str,
    ) -> None:
        try:
            if (
                not isinstance(workspace_id, str)
                or not workspace_id.strip()
                or not isinstance(created_at, str)
                or not created_at.strip()
                or load_domain_pack_manifest(domain_source) != domain_pack
                or load_scoring_rule_pack(rule_source) != rule_pack
                or domain_pack_content_hash(domain_pack) != domain_pack.content_hash
                or (rule_pack.rule_pack_id, rule_pack.version) not in domain_pack.scoring_rule_identities
            ):
                raise ValueError("pack snapshot inputs are inconsistent")
        except Exception as exc:
            raise _safe_error("FMEA_REVIEW_REQUEST_INVALID", "Risk pack snapshots are invalid.") from exc
        domain_values = (
            workspace_id,
            domain_pack.pack_id,
            domain_pack.version,
            "registered",
            "sha256:" + domain_pack.content_hash,
            "sha256:" + sha256(domain_source).hexdigest(),
            canonical_domain_pack_body(domain_pack),
            created_at,
        )
        rule_values = (
            workspace_id,
            rule_pack.rule_pack_id,
            rule_pack.version,
            "registered",
            "sha256:" + scoring_rule_content_hash(rule_pack),
            "sha256:" + sha256(rule_source).hexdigest(),
            canonical_scoring_rule_body(rule_pack),
            created_at,
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            domain_row = connection.execute(
                "SELECT workspace_id, pack_id, version, status, content_hash, source_hash, manifest_json, created_at "
                "FROM fmea_domain_packs WHERE workspace_id=? AND pack_id=? AND version=?",
                domain_values[:3],
            ).fetchone()
            if domain_row is None:
                connection.execute(
                    "INSERT INTO fmea_domain_packs "
                    "(workspace_id, pack_id, version, status, content_hash, source_hash, manifest_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    domain_values,
                )
            elif tuple(domain_row)[:7] != domain_values[:7]:
                raise _safe_error("FMEA_REVIEW_ACTION_INVALID", "Domain pack snapshot conflicts with stored state.")
            rule_row = connection.execute(
                "SELECT workspace_id, rule_pack_id, version, status, rule_hash, source_hash, rule_json, created_at "
                "FROM fmea_scoring_rule_packs WHERE workspace_id=? AND rule_pack_id=? AND version=?",
                rule_values[:3],
            ).fetchone()
            if rule_row is None:
                connection.execute(
                    "INSERT INTO fmea_scoring_rule_packs "
                    "(workspace_id, rule_pack_id, version, status, rule_hash, source_hash, rule_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    rule_values,
                )
            elif tuple(rule_row)[:7] != rule_values[:7]:
                raise _safe_error("FMEA_REVIEW_ACTION_INVALID", "Scoring pack snapshot conflicts with stored state.")
            connection.execute("COMMIT")
        except ReviewError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise _safe_error("FMEA_REVIEW_ACTION_INVALID", "Risk pack snapshot conflicts with stored state.") from exc
        except sqlite3.Error as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise _safe_error("FMEA_REVIEW_STORAGE_UNAVAILABLE", "Risk storage is unavailable.", retryable=True) from exc
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.database_path), timeout=self._busy_timeout_ms / 1000, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @staticmethod
    def _idempotency_row(connection: sqlite3.Connection, scope_key: str) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT payload_hash, state, status_code, resource_id, response_json, completed_at "
            "FROM idempotency_records WHERE scope_key=?",
            (scope_key,),
        ).fetchone()

    @staticmethod
    def _replay_response(row: sqlite3.Row | None, payload_hash: str, resource_type: str) -> Mapping[str, object] | None:
        if row is None:
            return None
        if row["payload_hash"] != payload_hash:
            _conflict()
        if (
            row["state"] != "completed"
            or row["status_code"] != 201
            or row["resource_id"] is None
            or row["response_json"] is None
            or not isinstance(row["completed_at"], str)
            or not row["completed_at"]
        ):
            raise _storage_error()
        response = _strict_json(row["response_json"], "idempotency response")
        if not isinstance(response, dict) or response.get("resource_type") != resource_type:
            raise _storage_error()
        expected_fields = (
            {"assessment_id", "outbox_event_id", "resource_type"}
            if resource_type == "risk_proposal"
            else {"assessment_id", "audit_event_id", "decision_id", "outbox_event_id", "resource_type"}
        )
        if set(response) != expected_fields or response.get("assessment_id") != row["resource_id"]:
            raise _storage_error()
        return response

    @staticmethod
    def _reserve(connection: sqlite3.Connection, scope: IdempotencyScope, payload_hash: str, created_at: str) -> None:
        connection.execute(
            "INSERT INTO idempotency_records "
            "(scope_key, payload_hash, state, status_code, resource_id, response_json, created_at, completed_at) "
            "VALUES (?, ?, 'reserved', NULL, NULL, NULL, ?, NULL)",
            (scope.scope_key, payload_hash, created_at),
        )

    @staticmethod
    def _complete(
        connection: sqlite3.Connection,
        scope: IdempotencyScope,
        payload_hash: str,
        response: Mapping[str, object],
        resource_id: str,
        completed_at: str,
    ) -> None:
        response_json = canonical_json(response)
        cursor = connection.execute(
            "UPDATE idempotency_records SET state='completed', status_code=201, resource_id=?, response_json=?, "
            "completed_at=? WHERE scope_key=? AND payload_hash=? AND state='reserved'",
            (resource_id, response_json, completed_at, scope.scope_key, payload_hash),
        )
        if cursor.rowcount != 1:
            raise _storage_error()

    @staticmethod
    def _insert_audit(connection: sqlite3.Connection, audit: AuditEvent) -> None:
        connection.execute(
            "INSERT INTO audit_events "
            "(event_id, row_id, workspace_id, actor_id, actor_type, command, action, suggestion_id, decision_id, "
            "expected_record_version, applied_record_version, before_hash, after_hash, canonical_payload_hash, "
            "event_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                audit.event_id,
                audit.row_id,
                audit.workspace_id,
                audit.actor_id,
                audit.actor_type.value,
                audit.command,
                audit.action.value if audit.action is not None else None,
                audit.suggestion_id,
                audit.decision_id,
                audit.expected_record_version,
                audit.applied_record_version,
                audit.before_hash,
                audit.after_hash,
                audit.canonical_payload_hash,
                encode_review_json(audit),
                audit.occurred_at_server,
            ),
        )

    def get_row(self, row_id: str, workspace_id: str):
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT row_json, row_hash, record_version FROM fmea_rows WHERE row_id=? AND workspace_id=?",
                (row_id, workspace_id),
            ).fetchone()
            if row is None:
                return None
            value = decode_row(str(row["row_json"]))
            if encode_json(value) != row["row_json"] or value.record_version != row["record_version"]:
                raise _storage_error()
            return value
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc
        finally:
            connection.close()

    def get_evidence_pack(self, pack_id: str, workspace_id: str):
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT pack_json, pack_hash FROM evidence_packs WHERE pack_id=? AND workspace_id=?",
                (pack_id, workspace_id),
            ).fetchone()
            if row is None:
                return None
            value = decode_evidence_pack(str(row["pack_json"]))
            if encode_json(value) != row["pack_json"] or value.pack_hash != row["pack_hash"]:
                raise _storage_error()
            return value
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc
        finally:
            connection.close()

    @staticmethod
    def _decode_proposal(row: sqlite3.Row) -> RiskProposal:
        try:
            dimensions = _decode_dimensions(_strict_json(row["dimensions_json"], "risk dimensions"))
            proposal = RiskProposal(
                proposal_id=row["proposal_id"],
                workspace_id=row["workspace_id"],
                row_id=row["row_id"],
                source_record_version=row["source_record_version"],
                evidence_pack_id=row["evidence_pack_id"],
                dimensions=dimensions,
                domain_pack_id=row["domain_pack_id"],
                domain_pack_version=row["domain_pack_version"],
                rule_pack_id=row["rule_pack_id"],
                rule_pack_version=row["rule_pack_version"],
                reason=row["reason"],
                assistance_suggestion_id=row["assistance_suggestion_id"],
                uncertainty=row["uncertainty"],
                created_at=row["created_at"],
            )
            if row["status"] != "proposed" or _object_hash(proposal) != row["proposal_hash"]:
                raise ValueError("proposal integrity mismatch")
            return proposal
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc

    @staticmethod
    def _decode_assessment(row: sqlite3.Row) -> RiskAssessmentRecord:
        try:
            dimensions = _decode_dimensions(_strict_json(row["dimensions_json"], "risk dimensions"))
            derived = None if row["derived_json"] is None else _decode_derived(
                _strict_json(row["derived_json"], "derived assessment")
            )
            assessment = RiskAssessmentRecord(
                assessment_id=row["assessment_id"],
                workspace_id=row["workspace_id"],
                row_id=row["row_id"],
                source_record_version=row["source_record_version"],
                evidence_pack_id=row["evidence_pack_id"],
                domain_pack_id=row["domain_pack_id"],
                domain_pack_version=row["domain_pack_version"],
                rule_pack_id=row["rule_pack_id"],
                rule_pack_version=row["rule_pack_version"],
                status=RiskStatus(row["status"]),
                dimensions=dimensions,
                derived=derived,
                proposal_id=row["proposal_id"],
                assistance_suggestion_id=row["assistance_suggestion_id"],
                confirmer_actor_id=row["confirmer_actor_id"],
                invalidated_reason=row["invalidated_reason"],
                record_version=row["record_version"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            if _object_hash(assessment) != row["assessment_hash"]:
                raise ValueError("assessment integrity mismatch")
            return assessment
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc

    def _assessment_by_id(
        self, connection: sqlite3.Connection, assessment_id: str, workspace_id: str
    ) -> RiskAssessmentRecord | None:
        row = connection.execute(
            f"SELECT {_ASSESSMENT_COLUMNS} FROM fmea_risk_assessments WHERE assessment_id=? AND workspace_id=?",
            (assessment_id, workspace_id),
        ).fetchone()
        return None if row is None else self._decode_assessment(row)

    def _validate_proposal_replay(
        self,
        connection: sqlite3.Connection,
        prepared: PreparedRiskProposal,
        response: Mapping[str, object],
    ) -> None:
        proposal_row = connection.execute(
            f"SELECT {_PROPOSAL_COLUMNS} FROM fmea_risk_proposals WHERE proposal_id=? AND workspace_id=?",
            (prepared.proposal.proposal_id, prepared.proposal.workspace_id),
        ).fetchone()
        audit_row = connection.execute(
            "SELECT * FROM audit_events WHERE event_id=? AND workspace_id=?",
            (prepared.audit.event_id, prepared.proposal.workspace_id),
        ).fetchone()
        outbox_row = connection.execute(
            f"SELECT {_OUTBOX_COLUMNS} FROM fmea_outbox_events WHERE event_id=? AND workspace_id=?",
            (response.get("outbox_event_id"), prepared.proposal.workspace_id),
        ).fetchone()
        if proposal_row is None or audit_row is None or outbox_row is None:
            raise _storage_error()
        expected_outbox = self._make_proposal_outbox(prepared)
        if (
            self._decode_proposal(proposal_row) != prepared.proposal
            or proposal_row["payload_hash"] != prepared.payload_hash
            or proposal_row["audit_event_id"] != prepared.audit.event_id
            or proposal_row["idempotency_scope"] != prepared.scope.scope_key
            or decode_audit_event(audit_row["event_json"]) != prepared.audit
            or not _audit_row_matches(audit_row, prepared.audit)
            or self._decode_outbox(outbox_row) != expected_outbox
            or response.get("assessment_id") != prepared.assessment.assessment_id
            or response.get("outbox_event_id") != expected_outbox.event_id
        ):
            raise _storage_error()

    def get_current_assessment(self, row_id: str, workspace_id: str) -> RiskAssessmentRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                f"SELECT {_ASSESSMENT_COLUMNS} FROM fmea_risk_assessments WHERE row_id=? AND workspace_id=? "
                "ORDER BY record_version DESC LIMIT 1",
                (row_id, workspace_id),
            ).fetchone()
            if row is None:
                return None
            assessment = self._decode_assessment(row)
            if assessment.status is not RiskStatus.UNSCORED:
                if assessment.status is RiskStatus.PROPOSED:
                    outbox_row = connection.execute(
                        f"SELECT {_OUTBOX_COLUMNS} FROM fmea_outbox_events "
                        "WHERE aggregate_id=? AND workspace_id=? AND event_type='risk.proposed'",
                        (assessment.assessment_id, workspace_id),
                    ).fetchone()
                else:
                    outbox_row = connection.execute(
                        f"SELECT {', '.join('outbox.' + item.strip() for item in _OUTBOX_COLUMNS.split(','))} "
                        "FROM fmea_outbox_events AS outbox JOIN fmea_risk_decisions AS decision "
                        "ON decision.outbox_event_id=outbox.event_id AND decision.workspace_id=outbox.workspace_id "
                        "WHERE decision.resulting_assessment_id=? AND decision.workspace_id=? "
                        "AND decision.applied_assessment_version=?",
                        (assessment.assessment_id, workspace_id, assessment.record_version),
                    ).fetchone()
                if outbox_row is None:
                    raise _storage_error()
                self._validate_outbox_chain(connection, self._decode_outbox(outbox_row))
            return assessment
        except ReviewError:
            raise
        except sqlite3.Error as exc:
            raise _safe_error("FMEA_REVIEW_STORAGE_UNAVAILABLE", "Risk storage is unavailable.", retryable=True) from exc
        except Exception as exc:
            raise _storage_error() from exc
        finally:
            connection.close()

    def _validate_sources(self, connection: sqlite3.Connection, proposal: RiskProposal) -> None:
        row = connection.execute(
            "SELECT row_json, record_version FROM fmea_rows WHERE row_id=? AND workspace_id=?",
            (proposal.row_id, proposal.workspace_id),
        ).fetchone()
        if row is None:
            raise _safe_error("FMEA_ROW_NOT_FOUND", "FMEA row was not found.")
        if row["record_version"] != proposal.source_record_version:
            raise _safe_error("FMEA_RISK_VERSION_CONFLICT", "Risk source row version is stale.")
        pack_row = connection.execute(
            "SELECT pack_json, pack_hash FROM evidence_packs WHERE pack_id=? AND workspace_id=?",
            (proposal.evidence_pack_id, proposal.workspace_id),
        ).fetchone()
        if pack_row is None:
            raise _safe_error("FMEA_EVIDENCE_INVALID", "Risk evidence pack is invalid.")
        pack = decode_evidence_pack(str(pack_row["pack_json"]))
        if encode_json(pack) != pack_row["pack_json"] or pack.pack_hash != pack_row["pack_hash"]:
            raise _storage_error()
        available = {ref.evidence_id for ref in pack.refs}
        used = {evidence_id for dimension in proposal.dimensions for evidence_id in dimension.evidence_ids}
        if not used.issubset(available):
            raise _safe_error("FMEA_EVIDENCE_INVALID", "Risk evidence references are invalid.")
        domain_row = connection.execute(
            "SELECT status, content_hash, manifest_json FROM fmea_domain_packs "
            "WHERE workspace_id=? AND pack_id=? AND version=?",
            (proposal.workspace_id, proposal.domain_pack_id, proposal.domain_pack_version),
        ).fetchone()
        rule_row = connection.execute(
            "SELECT status, rule_hash, rule_json FROM fmea_scoring_rule_packs "
            "WHERE workspace_id=? AND rule_pack_id=? AND version=?",
            (proposal.workspace_id, proposal.rule_pack_id, proposal.rule_pack_version),
        ).fetchone()
        if (
            domain_row is None
            or domain_row["status"] != "registered"
            or domain_row["content_hash"]
            != "sha256:" + sha256(str(domain_row["manifest_json"]).encode("utf-8")).hexdigest()
            or rule_row is None
            or rule_row["status"] != "registered"
            or rule_row["rule_hash"]
            != "sha256:" + sha256(str(rule_row["rule_json"]).encode("utf-8")).hexdigest()
        ):
            raise _safe_error("FMEA_REVIEW_ACTION_INVALID", "Risk pack snapshots are unavailable or invalid.")
        if proposal.assistance_suggestion_id is not None:
            suggestion = connection.execute(
                "SELECT 1 FROM fmea_assistance_suggestions WHERE suggestion_id=? AND workspace_id=?",
                (proposal.assistance_suggestion_id, proposal.workspace_id),
            ).fetchone()
            if suggestion is None:
                raise _safe_error("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "Assistance suggestion was not found.")

    @staticmethod
    def _insert_proposal(
        connection: sqlite3.Connection, prepared: PreparedRiskProposal
    ) -> None:
        proposal = prepared.proposal
        connection.execute(
            "INSERT INTO fmea_risk_proposals (" + _PROPOSAL_COLUMNS + ") VALUES (" + ",".join("?" for _ in range(19)) + ")",
            (
                proposal.proposal_id,
                proposal.workspace_id,
                proposal.row_id,
                proposal.source_record_version,
                proposal.evidence_pack_id,
                proposal.domain_pack_id,
                proposal.domain_pack_version,
                proposal.rule_pack_id,
                proposal.rule_pack_version,
                _canonical(proposal.dimensions),
                proposal.reason,
                proposal.assistance_suggestion_id,
                proposal.uncertainty,
                "proposed",
                _object_hash(proposal),
                prepared.payload_hash,
                prepared.audit.event_id,
                prepared.scope.scope_key,
                proposal.created_at,
            ),
        )

    @staticmethod
    def _insert_assessment(connection: sqlite3.Connection, assessment: RiskAssessmentRecord) -> None:
        connection.execute(
            "INSERT INTO fmea_risk_assessments (" + _ASSESSMENT_COLUMNS + ") VALUES (" + ",".join("?" for _ in range(20)) + ")",
            SqliteRiskRepository._assessment_values(assessment),
        )

    @staticmethod
    def _assessment_values(assessment: RiskAssessmentRecord) -> tuple[object, ...]:
        return (
            assessment.assessment_id,
            assessment.workspace_id,
            assessment.row_id,
            assessment.source_record_version,
            assessment.evidence_pack_id,
            assessment.domain_pack_id,
            assessment.domain_pack_version,
            assessment.rule_pack_id,
            assessment.rule_pack_version,
            assessment.status.value,
            _canonical(assessment.dimensions),
            None if assessment.derived is None else _canonical(assessment.derived),
            assessment.proposal_id,
            assessment.assistance_suggestion_id,
            assessment.confirmer_actor_id,
            assessment.invalidated_reason,
            assessment.record_version,
            _object_hash(assessment),
            assessment.created_at,
            assessment.updated_at,
        )

    def save_proposal(self, prepared: PreparedRiskProposal) -> RiskAssessmentRecord:
        if not isinstance(prepared, PreparedRiskProposal):
            raise _safe_error("FMEA_REVIEW_REQUEST_INVALID", "Prepared risk proposal is invalid.")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            response = self._replay_response(
                self._idempotency_row(connection, prepared.scope.scope_key), prepared.payload_hash, "risk_proposal"
            )
            if response is not None:
                assessment = self._assessment_by_id(
                    connection, cast(str, response.get("assessment_id")), prepared.proposal.workspace_id
                )
                if assessment is None or assessment != prepared.assessment:
                    raise _storage_error()
                self._validate_proposal_replay(connection, prepared, response)
                connection.execute("COMMIT")
                return assessment
            self._validate_sources(connection, prepared.proposal)
            self._reserve(connection, prepared.scope, prepared.payload_hash, prepared.audit.occurred_at_server)
            self._insert_audit(connection, prepared.audit)
            self._insert_proposal(connection, prepared)
            self._insert_assessment(connection, prepared.assessment)
            outbox = self._make_proposal_outbox(prepared)
            self._insert_outbox(connection, outbox)
            self._complete(
                connection,
                prepared.scope,
                prepared.payload_hash,
                {
                    "assessment_id": prepared.assessment.assessment_id,
                    "outbox_event_id": outbox.event_id,
                    "resource_type": "risk_proposal",
                },
                prepared.assessment.assessment_id,
                prepared.audit.occurred_at_server,
            )
            connection.execute("COMMIT")
            return prepared.assessment
        except ReviewError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise _safe_error("FMEA_REVIEW_ACTION_INVALID", "Risk proposal conflicts with stored state.") from exc
        except sqlite3.Error as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise _safe_error("FMEA_REVIEW_STORAGE_UNAVAILABLE", "Risk storage is unavailable.", retryable=True) from exc
        except Exception as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise _storage_error() from exc
        finally:
            connection.close()

    @staticmethod
    def _decision_body(
        decision_type: str,
        decision_id: str,
        previous: RiskAssessmentRecord,
        assessment: RiskAssessmentRecord,
    ) -> Mapping[str, object]:
        return {
            "assessment": json.loads(_canonical(assessment)),
            "decision_id": decision_id,
            "decision_type": decision_type,
            "previous_assessment": json.loads(_canonical(previous)),
        }

    @staticmethod
    def _insert_decision(
        connection: sqlite3.Connection,
        *,
        decision_type: str,
        decision_id: str,
        previous: RiskAssessmentRecord,
        assessment: RiskAssessmentRecord,
        proposal_id: str | None,
        audit: AuditEvent,
        scope: IdempotencyScope,
        payload_hash: str,
    ) -> None:
        connection.execute(
            "INSERT INTO fmea_risk_decisions "
            "(decision_id, workspace_id, row_id, previous_assessment_id, resulting_assessment_id, proposal_id, "
            "audit_event_id, outbox_event_id, decision_type, "
            "from_status, to_status, expected_assessment_version, applied_assessment_version, actor_id, actor_type, "
            "decision_json, idempotency_scope, payload_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                decision_id,
                assessment.workspace_id,
                assessment.row_id,
                previous.assessment_id,
                assessment.assessment_id,
                proposal_id,
                audit.event_id,
                f"outbox-{decision_id}",
                decision_type,
                previous.status.value,
                assessment.status.value,
                previous.record_version,
                assessment.record_version,
                audit.actor_id,
                audit.actor_type.value,
                canonical_json(SqliteRiskRepository._decision_body(decision_type, decision_id, previous, assessment)),
                scope.scope_key,
                payload_hash,
                audit.occurred_at_server,
            ),
        )

    @staticmethod
    def _update_assessment(connection: sqlite3.Connection, assessment: RiskAssessmentRecord, expected: int) -> None:
        values = SqliteRiskRepository._assessment_values(assessment)
        cursor = connection.execute(
            "UPDATE fmea_risk_assessments SET source_record_version=?, evidence_pack_id=?, domain_pack_id=?, "
            "domain_pack_version=?, rule_pack_id=?, rule_pack_version=?, status=?, dimensions_json=?, derived_json=?, "
            "proposal_id=?, assistance_suggestion_id=?, confirmer_actor_id=?, invalidated_reason=?, record_version=?, "
            "assessment_hash=?, created_at=?, updated_at=? WHERE assessment_id=? AND workspace_id=? AND record_version=?",
            (*values[3:20], assessment.assessment_id, assessment.workspace_id, expected),
        )
        if cursor.rowcount != 1:
            raise _safe_error("FMEA_RISK_VERSION_CONFLICT", "Risk assessment version is stale.")

    @staticmethod
    def _make_outbox(
        event_type: str,
        decision_id: str,
        audit: AuditEvent,
        assessment: RiskAssessmentRecord,
        scope: IdempotencyScope,
    ) -> OutboxEvent:
        payload = {
            "assessment": json.loads(_canonical(assessment)),
            "audit_event_id": audit.event_id,
            "decision_id": decision_id,
        }
        return OutboxEvent(
            event_id=f"outbox-{decision_id}",
            workspace_id=assessment.workspace_id,
            aggregate_type="risk_assessment",
            aggregate_id=assessment.assessment_id,
            event_type=event_type,
            payload=payload,
            payload_hash=outbox_payload_hash(payload),
            created_at=audit.occurred_at_server,
            scope_key=scope.scope_key,
        )

    @staticmethod
    def _insert_outbox(connection: sqlite3.Connection, event: OutboxEvent) -> None:
        connection.execute(
            "INSERT INTO fmea_outbox_events (" + _OUTBOX_COLUMNS + ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.workspace_id,
                event.aggregate_type,
                event.aggregate_id,
                event.event_type,
                "pending",
                canonical_json(event.payload),
                event.payload_hash,
                event.scope_key,
                event.created_at,
            ),
        )

    @staticmethod
    def _make_proposal_outbox(prepared: PreparedRiskProposal) -> OutboxEvent:
        payload = {
            "assessment": json.loads(_canonical(prepared.assessment)),
            "audit_event_id": prepared.audit.event_id,
            "proposal": json.loads(_canonical(prepared.proposal)),
        }
        return OutboxEvent(
            event_id=f"outbox-proposal-{prepared.proposal.proposal_id}",
            workspace_id=prepared.proposal.workspace_id,
            aggregate_type="risk_assessment",
            aggregate_id=prepared.assessment.assessment_id,
            event_type="risk.proposed",
            payload=payload,
            payload_hash=outbox_payload_hash(payload),
            created_at=prepared.audit.occurred_at_server,
            scope_key=prepared.scope.scope_key,
        )

    def _authoritative_transition(
        self,
        connection: sqlite3.Connection,
        previous: RiskAssessmentRecord,
        proposal_value: RiskProposal | None,
    ) -> RiskAssessmentRecord:
        current_row = connection.execute(
            f"SELECT {_ASSESSMENT_COLUMNS} FROM fmea_risk_assessments WHERE row_id=? AND workspace_id=? "
            "ORDER BY record_version DESC LIMIT 1",
            (previous.row_id, previous.workspace_id),
        ).fetchone()
        if current_row is None:
            raise _safe_error("FMEA_REVIEW_ACTION_INVALID", "Risk assessment was not found.")
        current = self._decode_assessment(current_row)
        if current.record_version != previous.record_version:
            raise _safe_error("FMEA_RISK_VERSION_CONFLICT", "Risk assessment version is stale.")
        if current != previous:
            raise _storage_error()
        if proposal_value is not None:
            proposal_row = connection.execute(
                f"SELECT {_PROPOSAL_COLUMNS} FROM fmea_risk_proposals WHERE proposal_id=? AND workspace_id=?",
                (proposal_value.proposal_id, proposal_value.workspace_id),
            ).fetchone()
            if proposal_row is None or self._decode_proposal(proposal_row) != proposal_value:
                raise _storage_error()
        return current

    def _validate_transition_replay(
        self,
        connection: sqlite3.Connection,
        prepared: PreparedRiskConfirmation | PreparedRiskRejection | PreparedRiskInvalidation,
        decision_type: str,
        event_type: str,
        response: Mapping[str, object],
    ) -> None:
        decision = connection.execute(
            "SELECT * FROM fmea_risk_decisions WHERE decision_id=? AND workspace_id=?",
            (response.get("decision_id"), prepared.assessment.workspace_id),
        ).fetchone()
        audit = connection.execute(
            "SELECT * FROM audit_events WHERE event_id=? AND workspace_id=?",
            (response.get("audit_event_id"), prepared.assessment.workspace_id),
        ).fetchone()
        outbox = connection.execute(
            f"SELECT {_OUTBOX_COLUMNS} FROM fmea_outbox_events WHERE event_id=? AND workspace_id=?",
            (response.get("outbox_event_id"), prepared.assessment.workspace_id),
        ).fetchone()
        if decision is None or audit is None or outbox is None:
            raise _storage_error()
        expected_body = canonical_json(
            self._decision_body(decision_type, prepared.decision_id, prepared.previous_assessment, prepared.assessment)
        )
        expected_outbox = self._make_outbox(
            event_type, prepared.decision_id, prepared.audit, prepared.assessment, prepared.scope
        )
        if (
            decision["decision_json"] != expected_body
            or decision["decision_id"] != prepared.decision_id
            or decision["previous_assessment_id"] != prepared.previous_assessment.assessment_id
            or decision["resulting_assessment_id"] != prepared.assessment.assessment_id
            or decision["proposal_id"] != prepared.assessment.proposal_id
            or decision["audit_event_id"] != prepared.audit.event_id
            or decision["outbox_event_id"] != expected_outbox.event_id
            or decision["decision_type"] != decision_type
            or decision["from_status"] != prepared.previous_assessment.status.value
            or decision["to_status"] != prepared.assessment.status.value
            or decision["expected_assessment_version"] != prepared.expected_assessment_version
            or decision["applied_assessment_version"] != prepared.assessment.record_version
            or decision["actor_id"] != prepared.audit.actor_id
            or decision["actor_type"] != prepared.audit.actor_type.value
            or decision["idempotency_scope"] != prepared.scope.scope_key
            or decision["payload_hash"] != prepared.payload_hash
            or decode_audit_event(audit["event_json"]) != prepared.audit
            or not _audit_row_matches(audit, prepared.audit)
            or self._decode_outbox(outbox) != expected_outbox
        ):
            raise _storage_error()

    def _transition(
        self,
        *,
        prepared: PreparedRiskConfirmation | PreparedRiskRejection | PreparedRiskInvalidation,
        decision_type: str,
        event_type: str,
        resource_type: str,
    ) -> RiskConfirmationResult | RiskAssessmentRecord:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            response = self._replay_response(
                self._idempotency_row(connection, prepared.scope.scope_key), prepared.payload_hash, resource_type
            )
            if response is not None:
                assessment = self._assessment_by_id(
                    connection, cast(str, response.get("assessment_id")), prepared.assessment.workspace_id
                )
                if assessment is None or assessment != prepared.assessment:
                    raise _storage_error()
                self._validate_transition_replay(connection, prepared, decision_type, event_type, response)
                connection.execute("COMMIT")
                if decision_type == "confirm":
                    return RiskConfirmationResult(
                        assessment=assessment,
                        decision_id=cast(str, response.get("decision_id")),
                        audit_event_id=cast(str, response.get("audit_event_id")),
                        outbox_event_id=cast(str, response.get("outbox_event_id")),
                        replayed=True,
                    )
                return assessment
            proposal_value = prepared.proposal if isinstance(
                prepared, PreparedRiskConfirmation | PreparedRiskRejection
            ) else None
            self._authoritative_transition(connection, prepared.previous_assessment, proposal_value)
            if prepared.expected_assessment_version != prepared.previous_assessment.record_version:
                raise _safe_error("FMEA_RISK_VERSION_CONFLICT", "Risk assessment version is stale.")
            self._reserve(connection, prepared.scope, prepared.payload_hash, prepared.audit.occurred_at_server)
            self._insert_audit(connection, prepared.audit)
            if prepared.assessment.assessment_id == prepared.previous_assessment.assessment_id:
                self._insert_decision(
                    connection,
                    decision_type=decision_type,
                    decision_id=prepared.decision_id,
                    previous=prepared.previous_assessment,
                    assessment=prepared.assessment,
                    proposal_id=prepared.assessment.proposal_id,
                    audit=prepared.audit,
                    scope=prepared.scope,
                    payload_hash=prepared.payload_hash,
                )
                self._update_assessment(connection, prepared.assessment, prepared.expected_assessment_version)
            else:
                self._insert_decision(
                    connection,
                    decision_type=decision_type,
                    decision_id=prepared.decision_id,
                    previous=prepared.previous_assessment,
                    assessment=prepared.assessment,
                    proposal_id=prepared.assessment.proposal_id,
                    audit=prepared.audit,
                    scope=prepared.scope,
                    payload_hash=prepared.payload_hash,
                )
                self._insert_assessment(connection, prepared.assessment)
            outbox = self._make_outbox(
                event_type, prepared.decision_id, prepared.audit, prepared.assessment, prepared.scope
            )
            self._insert_outbox(connection, outbox)
            response_body = {
                "assessment_id": prepared.assessment.assessment_id,
                "audit_event_id": prepared.audit.event_id,
                "decision_id": prepared.decision_id,
                "outbox_event_id": outbox.event_id,
                "resource_type": resource_type,
            }
            self._complete(
                connection,
                prepared.scope,
                prepared.payload_hash,
                response_body,
                prepared.assessment.assessment_id,
                prepared.audit.occurred_at_server,
            )
            connection.execute("COMMIT")
            if decision_type == "confirm":
                return RiskConfirmationResult(
                    assessment=prepared.assessment,
                    decision_id=prepared.decision_id,
                    audit_event_id=prepared.audit.event_id,
                    outbox_event_id=outbox.event_id,
                )
            return prepared.assessment
        except ReviewError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise _safe_error("FMEA_REVIEW_ACTION_INVALID", "Risk transition conflicts with stored state.") from exc
        except sqlite3.Error as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise _safe_error("FMEA_REVIEW_STORAGE_UNAVAILABLE", "Risk storage is unavailable.", retryable=True) from exc
        except Exception as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise _storage_error() from exc
        finally:
            connection.close()

    def commit_confirmation(self, prepared: PreparedRiskConfirmation) -> RiskConfirmationResult:
        if not isinstance(prepared, PreparedRiskConfirmation):
            raise _safe_error("FMEA_REVIEW_REQUEST_INVALID", "Prepared risk confirmation is invalid.")
        return cast(
            RiskConfirmationResult,
            self._transition(
                prepared=prepared,
                decision_type="confirm",
                event_type="risk.confirmed",
                resource_type="risk_confirmation",
            ),
        )

    def reject(self, prepared: PreparedRiskRejection) -> RiskAssessmentRecord:
        if not isinstance(prepared, PreparedRiskRejection):
            raise _safe_error("FMEA_REVIEW_REQUEST_INVALID", "Prepared risk rejection is invalid.")
        return cast(
            RiskAssessmentRecord,
            self._transition(
                prepared=prepared,
                decision_type="reject",
                event_type="risk.rejected",
                resource_type="risk_rejection",
            ),
        )

    def invalidate(self, prepared: PreparedRiskInvalidation) -> RiskAssessmentRecord:
        if not isinstance(prepared, PreparedRiskInvalidation):
            raise _safe_error("FMEA_REVIEW_REQUEST_INVALID", "Prepared risk invalidation is invalid.")
        return cast(
            RiskAssessmentRecord,
            self._transition(
                prepared=prepared,
                decision_type="invalidate",
                event_type="risk.invalidated",
                resource_type="risk_invalidation",
            ),
        )

    def replay_confirmation(self, scope: IdempotencyScope, payload_hash: str) -> RiskConfirmationResult | None:
        connection = self._connect()
        try:
            response = self._replay_response(
                self._idempotency_row(connection, scope.scope_key), payload_hash, "risk_confirmation"
            )
            if response is None:
                return None
            assessment = self._assessment_by_id(
                connection, cast(str, response.get("assessment_id")), scope.workspace_id
            )
            if assessment is None:
                raise _storage_error()
            decision = connection.execute(
                "SELECT * FROM fmea_risk_decisions "
                "WHERE decision_id=? AND workspace_id=?",
                (response.get("decision_id"), scope.workspace_id),
            ).fetchone()
            audit = connection.execute(
                "SELECT * FROM audit_events WHERE event_id=? AND workspace_id=?",
                (response.get("audit_event_id"), scope.workspace_id),
            ).fetchone()
            outbox = connection.execute(
                f"SELECT {_OUTBOX_COLUMNS} FROM fmea_outbox_events WHERE event_id=? AND workspace_id=?",
                (response.get("outbox_event_id"), scope.workspace_id),
            ).fetchone()
            if decision is None or audit is None or outbox is None:
                raise _storage_error()
            audit_value = decode_audit_event(audit["event_json"])
            decision_body = _strict_json(decision["decision_json"], "risk decision")
            if not isinstance(decision_body, dict) or set(decision_body) != {
                "assessment",
                "decision_id",
                "decision_type",
                "previous_assessment",
            }:
                raise _storage_error()
            previous = _decode_assessment_value(decision_body["previous_assessment"])
            decision_assessment = _decode_assessment_value(decision_body["assessment"])
            proposal_row = connection.execute(
                f"SELECT {_PROPOSAL_COLUMNS} FROM fmea_risk_proposals WHERE proposal_id=? AND workspace_id=?",
                (assessment.proposal_id, scope.workspace_id),
            ).fetchone()
            if proposal_row is None:
                raise _storage_error()
            proposal = self._decode_proposal(proposal_row)
            decision_id = cast(str, decision_body["decision_id"])
            expected_hash = risk_confirmation_payload_hash(
                scope,
                proposal,
                previous,
                decision_assessment,
                previous.record_version,
                decision_id,
            )
            prepared = PreparedRiskConfirmation(
                scope=scope,
                payload_hash=expected_hash,
                proposal=proposal,
                previous_assessment=previous,
                assessment=decision_assessment,
                expected_assessment_version=previous.record_version,
                decision_id=decision_id,
                audit=audit_value,
            )
            self._validate_transition_replay(connection, prepared, "confirm", "risk.confirmed", response)
            if (
                decision_body["decision_type"] != "confirm"
                or decision_assessment != assessment
                or expected_hash != payload_hash
            ):
                raise _storage_error()
            return RiskConfirmationResult(
                assessment=assessment,
                decision_id=cast(str, response.get("decision_id")),
                audit_event_id=cast(str, response.get("audit_event_id")),
                outbox_event_id=cast(str, response.get("outbox_event_id")),
                replayed=True,
            )
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc
        finally:
            connection.close()

    @staticmethod
    def _decode_outbox(row: sqlite3.Row) -> OutboxEvent:
        payload = _strict_json(row["payload_json"], "outbox payload")
        if not isinstance(payload, dict) or row["status"] != "pending":
            raise _storage_error()
        event = OutboxEvent(
            event_id=row["event_id"],
            workspace_id=row["workspace_id"],
            aggregate_type=row["aggregate_type"],
            aggregate_id=row["aggregate_id"],
            event_type=row["event_type"],
            payload=payload,
            payload_hash=row["payload_hash"],
            scope_key=row["idempotency_scope"],
            created_at=row["created_at"],
        )
        if canonical_json(event.payload) != row["payload_json"]:
            raise _storage_error()
        return event

    def _validate_outbox_chain(self, connection: sqlite3.Connection, event: OutboxEvent) -> None:
        if event.aggregate_type != "risk_assessment":
            raise _storage_error()
        if event.event_type == "risk.proposed":
            if set(event.payload) != {"assessment", "audit_event_id", "proposal"}:
                raise _storage_error()
            assessment = _decode_assessment_value(_json_value(event.payload["assessment"]))
            proposal_value = _json_value(event.payload["proposal"])
            if not isinstance(proposal_value, dict):
                raise _storage_error()
            proposal_id = proposal_value.get("proposal_id")
            proposal_row = connection.execute(
                f"SELECT {_PROPOSAL_COLUMNS} FROM fmea_risk_proposals WHERE proposal_id=? AND workspace_id=?",
                (proposal_id, event.workspace_id),
            ).fetchone()
            stored_assessment = self._assessment_by_id(connection, assessment.assessment_id, event.workspace_id)
            audit_row = connection.execute(
                "SELECT * FROM audit_events WHERE event_id=? AND workspace_id=?",
                (event.payload["audit_event_id"], event.workspace_id),
            ).fetchone()
            if proposal_row is None or stored_assessment is None or audit_row is None:
                raise _storage_error()
            proposal = self._decode_proposal(proposal_row)
            audit = decode_audit_event(audit_row["event_json"])
            response = self._replay_response(
                self._idempotency_row(connection, event.scope_key), proposal_row["payload_hash"], "risk_proposal"
            )
            if (
                response is None
                or response["assessment_id"] != assessment.assessment_id
                or response["outbox_event_id"] != event.event_id
                or event.aggregate_id != assessment.assessment_id
                or event.created_at != audit.occurred_at_server
                or assessment.status is not RiskStatus.PROPOSED
                or assessment.record_version != 1
                or assessment.updated_at != assessment.created_at
                or assessment.derived is not None
                or assessment.confirmer_actor_id is not None
                or assessment.invalidated_reason is not None
                or not _assessment_identity_matches(stored_assessment, assessment)
                or stored_assessment.record_version < assessment.record_version
                or proposal_value != _json_value(proposal)
                or assessment.proposal_id != proposal.proposal_id
                or event.payload["audit_event_id"] != proposal_row["audit_event_id"]
                or proposal_row["idempotency_scope"] != event.scope_key
                or not _audit_row_matches(audit_row, audit)
            ):
                raise _storage_error()
            return

        transition_types = {
            "risk.confirmed": ("confirm", "risk_confirmation"),
            "risk.rejected": ("reject", "risk_rejection"),
            "risk.invalidated": ("invalidate", "risk_invalidation"),
        }
        transition = transition_types.get(event.event_type)
        if transition is None or set(event.payload) != {"assessment", "audit_event_id", "decision_id"}:
            raise _storage_error()
        decision_type, resource_type = transition
        decision = connection.execute(
            "SELECT * FROM fmea_risk_decisions WHERE decision_id=? AND workspace_id=?",
            (event.payload["decision_id"], event.workspace_id),
        ).fetchone()
        audit_row = connection.execute(
            "SELECT * FROM audit_events WHERE event_id=? AND workspace_id=?",
            (event.payload["audit_event_id"], event.workspace_id),
        ).fetchone()
        if decision is None or audit_row is None:
            raise _storage_error()
        decision_body = _strict_json(decision["decision_json"], "risk decision")
        if not isinstance(decision_body, dict) or set(decision_body) != {
            "assessment",
            "decision_id",
            "decision_type",
            "previous_assessment",
        }:
            raise _storage_error()
        previous = _decode_assessment_value(decision_body["previous_assessment"])
        assessment = _decode_assessment_value(decision_body["assessment"])
        stored_previous = self._assessment_by_id(connection, previous.assessment_id, event.workspace_id)
        stored_assessment = self._assessment_by_id(connection, assessment.assessment_id, event.workspace_id)
        audit = decode_audit_event(audit_row["event_json"])
        response = self._replay_response(
            self._idempotency_row(connection, event.scope_key), decision["payload_hash"], resource_type
        )
        expected_payload = {
            "assessment": _json_value(assessment),
            "audit_event_id": audit.event_id,
            "decision_id": decision["decision_id"],
        }
        previous_is_historical = previous.assessment_id != assessment.assessment_id
        stored_result_matches = stored_assessment == assessment or (
            stored_assessment is not None
            and stored_assessment.record_version > assessment.record_version
            and _assessment_identity_matches(stored_assessment, assessment)
        )
        if (
            response is None
            or stored_previous is None
            or stored_assessment is None
            or (previous_is_historical and stored_previous != previous)
            or not stored_result_matches
            or _json_value(event.payload) != expected_payload
            or event.aggregate_id != assessment.assessment_id
            or event.created_at != audit.occurred_at_server
            or decision["decision_type"] != decision_type
            or decision["previous_assessment_id"] != previous.assessment_id
            or decision["resulting_assessment_id"] != assessment.assessment_id
            or decision["row_id"] != assessment.row_id
            or decision["proposal_id"] != assessment.proposal_id
            or decision["audit_event_id"] != audit.event_id
            or decision["outbox_event_id"] != event.event_id
            or decision["idempotency_scope"] != event.scope_key
            or decision["from_status"] != previous.status.value
            or decision["to_status"] != assessment.status.value
            or decision["expected_assessment_version"] != previous.record_version
            or decision["applied_assessment_version"] != assessment.record_version
            or decision["actor_id"] != audit.actor_id
            or decision["actor_type"] != audit.actor_type.value
            or response["assessment_id"] != assessment.assessment_id
            or response["audit_event_id"] != audit.event_id
            or response["decision_id"] != decision["decision_id"]
            or response["outbox_event_id"] != event.event_id
            or not _audit_row_matches(audit_row, audit)
        ):
            raise _storage_error()

    def list_outbox_events(self, aggregate_id: str, workspace_id: str) -> tuple[OutboxEvent, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT {_OUTBOX_COLUMNS} FROM fmea_outbox_events WHERE aggregate_id=? AND workspace_id=? "
                "ORDER BY created_at, event_id",
                (aggregate_id, workspace_id),
            ).fetchall()
            events = tuple(self._decode_outbox(row) for row in rows)
            for event in events:
                self._validate_outbox_chain(connection, event)
            return events
        except ReviewError:
            raise
        except Exception as exc:
            raise _storage_error() from exc
        finally:
            connection.close()


__all__ = ["SqliteRiskRepository"]
