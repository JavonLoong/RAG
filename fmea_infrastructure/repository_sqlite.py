"""Dedicated SQLite persistence for the review-only FMEA workflow."""

# Review persistence exposes stable ValueError failures for malformed stored data.
# ruff: noqa: TRY003, TRY004, TRY300, TRY301

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import fields, replace
from datetime import datetime, timezone
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from typing import Any, NoReturn, cast

from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.policies import validate_row_evidence
from core_domain.fmea.states import (
    FMEA_SCHEMA_ID,
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
    RunStatus,
)
from core_domain.fmea.value_objects import EvidencePack, VersionSet
from fmea_application.review_contracts import (
    EDITABLE_REVIEW_FIELDS,
    ActorContext,
    AuditEvent,
    EvidenceRequestItem,
    IdempotencyScope,
    PreparedReviewDecision,
    PreparedSuggestionRun,
    ReviewAction,
    ReviewCandidateBundle,
    ReviewDecisionRecord,
    ReviewDecisionResult,
    ReviewModelManifest,
    ReviewPriority,
    ReviewReasonCode,
    ReviewSourceSnapshot,
    ReviewSuggestion,
    ReviewSuggestionRun,
    SuggestionRunReservation,
    canonical_payload_hash,
    decode_review_decision_record,
    decode_review_source_snapshot,
    decode_review_suggestion,
    encode_review_json,
    idempotency_key_hash,
)
from fmea_application.review_errors import REVIEW_ERROR_CODES, ReviewError

_MIGRATION_PATTERN = re.compile(r"^(\d+)_([a-z0-9_]+)\.sql$")
_MAX_BUSY_TIMEOUT_MS = 60_000
_SUGGESTION_START_COMMAND = "review.suggestion.start"
_SUGGESTION_CREATE_COMMAND = "review.suggestion.create"
_SUGGESTION_COMPLETE_COMMAND = "review.suggestion.complete"
_SUGGESTION_FAIL_COMMAND = "review.suggestion.fail"
_DECISION_COMMAND = "review.decision"
_DECISION_REVIEW_STATUS = {
    ReviewAction.ACCEPT: ReviewStatus.ACCEPTED,
    ReviewAction.MODIFY_AND_ACCEPT: ReviewStatus.ACCEPTED,
    ReviewAction.REJECT: ReviewStatus.REJECTED,
    ReviewAction.REQUEST_EVIDENCE: ReviewStatus.IN_REVIEW,
    ReviewAction.DEFER: ReviewStatus.IN_REVIEW,
}
_CLAIM_PRIORITY = {
    ClaimStatus.KNOWN: 0,
    ClaimStatus.NOT_APPLICABLE: 1,
    ClaimStatus.UNKNOWN: 2,
    ClaimStatus.INSUFFICIENT_EVIDENCE: 3,
    ClaimStatus.CONFLICT: 4,
}
_FMEA_CODEC = import_module("core_domain.fmea.codec")
encode_json = cast(Callable[[object], str], _FMEA_CODEC.encode_json)
decode_analysis = cast(Callable[[str], object], _FMEA_CODEC.decode_analysis)
decode_evidence_pack = cast(Callable[[str], object], _FMEA_CODEC.decode_evidence_pack)
decode_row = cast(Callable[[str], object], _FMEA_CODEC.decode_row)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _json_hash(payload: str) -> str:
    return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


def _strict_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"invalid JSON constant: {value}")


def _load_strict_json(payload: object, kind: str) -> dict[str, object]:
    if not isinstance(payload, str):
        raise ValueError(f"{kind} JSON must be text")
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid persisted {kind} JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"persisted {kind} JSON must be an object")
    return value


def _decision_result_json(result: ReviewDecisionResult) -> str:
    return encode_review_json(result)


def _strict_string_tuple(value: object, kind: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"persisted {kind} must be a string array")
    return tuple(value)


def _decode_decision_result(payload: object) -> ReviewDecisionResult:  # noqa: C901
    data = _load_strict_json(payload, "review decision response")
    expected = {
        "decision_id",
        "row",
        "previous_record_version",
        "record_version",
        "review_status",
        "publication_status",
        "audit_event_id",
        "suggestion_id",
        "evidence_requests",
        "persisted",
        "request_id",
        "trace_id",
    }
    if set(data) != expected:
        raise ValueError("persisted review decision response fields are invalid")
    row_data = data["row"]
    if not isinstance(row_data, dict):
        raise ValueError("persisted review decision response row is invalid")
    row_payload = encode_json(row_data)
    row = cast(FmeaRow, _decode_fmea_json(row_payload, decode_row, "row"))
    raw_requests = data["evidence_requests"]
    if not isinstance(raw_requests, list):
        raise ValueError("persisted review decision response requests are invalid")
    evidence_requests_list: list[EvidenceRequestItem] = []
    request_keys = {field.name for field in fields(EvidenceRequestItem)}
    for item in raw_requests:
        if not isinstance(item, dict):
            raise ValueError("persisted review decision response requests are invalid")
        if set(item) != request_keys:
            raise ValueError("persisted review decision response request fields are invalid")
        raw_types = item.get("preferred_source_types")
        if not isinstance(raw_types, list) or not all(isinstance(value, str) for value in raw_types):
            raise ValueError("persisted review decision response requests are invalid")
        evidence_requests_list.append(
            EvidenceRequestItem(
                target_field=cast(str, item["target_field"]),
                question=cast(str, item["question"]),
                preferred_source_types=tuple(raw_types),
                priority=ReviewPriority(cast(str, item["priority"])),
            )
        )
    evidence_requests = tuple(evidence_requests_list)
    try:
        result = ReviewDecisionResult(
            decision_id=cast(str, data["decision_id"]),
            row=row,
            previous_record_version=cast(int, data["previous_record_version"]),
            record_version=cast(int, data["record_version"]),
            review_status=ReviewStatus(cast(str, data["review_status"])),
            publication_status=PublicationStatus(cast(str, data["publication_status"])),
            audit_event_id=cast(str, data["audit_event_id"]),
            suggestion_id=None if data["suggestion_id"] is None else cast(str, data["suggestion_id"]),
            evidence_requests=evidence_requests,
            persisted=cast(bool, data["persisted"]),
            request_id=cast(str, data["request_id"]),
            trace_id=cast(str, data["trace_id"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("persisted review decision response values are invalid") from exc
    if not result.persisted:
        raise ValueError("persisted review decision response must be persisted")
    if encode_review_json(result) != payload:
        raise ValueError("persisted review decision response is not canonical")
    return result


def _decode_audit_event(payload: object) -> AuditEvent:
    data = _load_strict_json(payload, "audit event")
    expected = {field.name for field in fields(AuditEvent)}
    if set(data) != expected:
        raise ValueError("persisted audit event fields are invalid")
    raw_versions = data["versions"]
    if (
        not isinstance(raw_versions, dict)
        or set(raw_versions) != {field.name for field in fields(VersionSet)}
        or not all(isinstance(value, str) for value in raw_versions.values())
    ):
        raise ValueError("persisted audit event versions are invalid")
    raw_manifest = data["model_manifest"]
    if raw_manifest is not None and (
        not isinstance(raw_manifest, dict)
        or set(raw_manifest) != {field.name for field in fields(ReviewModelManifest)}
    ):
        raise ValueError("persisted audit event model manifest is invalid")
    try:
        versions = VersionSet(**cast(dict[str, Any], raw_versions))
        manifest = None if raw_manifest is None else ReviewModelManifest(**cast(dict[str, Any], raw_manifest))
        result = AuditEvent(
            event_id=cast(str, data["event_id"]),
            occurred_at_server=cast(str, data["occurred_at_server"]),
            workspace_id=cast(str, data["workspace_id"]),
            actor_id=cast(str, data["actor_id"]),
            actor_type=ActorType(cast(str, data["actor_type"])),
            actor_roles=_strict_string_tuple(data["actor_roles"], "audit actor_roles"),
            command=cast(str, data["command"]),
            action=None if data["action"] is None else ReviewAction(cast(str, data["action"])),
            reason_code=None if data["reason_code"] is None else ReviewReasonCode(cast(str, data["reason_code"])),
            reason=cast(str, data["reason"]),
            analysis_id=cast(str, data["analysis_id"]),
            row_id=cast(str, data["row_id"]),
            suggestion_id=None if data["suggestion_id"] is None else cast(str, data["suggestion_id"]),
            decision_id=None if data["decision_id"] is None else cast(str, data["decision_id"]),
            expected_record_version=None
            if data["expected_record_version"] is None
            else cast(int, data["expected_record_version"]),
            applied_record_version=None
            if data["applied_record_version"] is None
            else cast(int, data["applied_record_version"]),
            before_hash=None if data["before_hash"] is None else cast(str, data["before_hash"]),
            after_hash=None if data["after_hash"] is None else cast(str, data["after_hash"]),
            changed_fields=_strict_string_tuple(data["changed_fields"], "audit changed_fields"),
            evidence_ids=_strict_string_tuple(data["evidence_ids"], "audit evidence_ids"),
            evidence_request_targets=_strict_string_tuple(
                data["evidence_request_targets"], "audit evidence_request_targets"
            ),
            idempotency_key_hash=cast(str, data["idempotency_key_hash"]),
            canonical_payload_hash=cast(str, data["canonical_payload_hash"]),
            versions=versions,
            template_id=cast(str, data["template_id"]),
            template_version=cast(str, data["template_version"]),
            profile_id=cast(str, data["profile_id"]),
            profile_version=cast(str, data["profile_version"]),
            model_manifest=manifest,
            request_id=cast(str, data["request_id"]),
            trace_id=cast(str, data["trace_id"]),
            retrieval_trace_id=cast(str, data["retrieval_trace_id"]),
            run_id=None if data["run_id"] is None else cast(str, data["run_id"]),
            request_hash=None if data["request_hash"] is None else cast(str, data["request_hash"]),
            error_code=None if data["error_code"] is None else cast(str, data["error_code"]),
            retryable=cast(bool, data["retryable"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("persisted audit event values are invalid") from exc
    if encode_review_json(result) != payload:
        raise ValueError("persisted audit event is not canonical")
    return result


def _decode_fmea_json(payload: object, decoder: Callable[[str], object], kind: str) -> object:
    if not isinstance(payload, str):
        raise ValueError(f"{kind} JSON must be text")
    _load_strict_json(payload, kind)
    try:
        result = decoder(payload)
        if encode_json(result) != payload:
            raise ValueError(f"persisted {kind} JSON is not canonical")
        return result
    except Exception as exc:
        raise ValueError(f"invalid persisted {kind} JSON") from exc


class SqliteFmeaRepository:
    """A dedicated, migration-managed SQLite repository for review candidates."""

    def __init__(self, database_path: Path, *, busy_timeout_ms: int = 5000) -> None:
        if isinstance(busy_timeout_ms, bool) or not isinstance(busy_timeout_ms, int):
            raise ValueError("busy_timeout_ms must be an integer")
        if not 1 <= busy_timeout_ms <= _MAX_BUSY_TIMEOUT_MS:
            raise ValueError(f"busy_timeout_ms must be between 1 and {_MAX_BUSY_TIMEOUT_MS}")
        self.database_path = Path(database_path).expanduser().resolve()
        self._busy_timeout_ms = busy_timeout_ms
        self._migrations_path = Path(__file__).resolve().parent / "migrations"

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
    def _iter_migration_statements(sql: str) -> Iterator[str]:
        buffer = ""
        for line in sql.splitlines(keepends=True):
            buffer += line
            if sqlite3.complete_statement(buffer):
                statement = buffer.strip()
                if statement:
                    yield statement
                buffer = ""
        if buffer.strip():
            raise ValueError("migration contains an incomplete SQL statement")

    def _migration_files(self) -> tuple[tuple[int, Path], ...]:
        discovered: list[tuple[int, Path]] = []
        versions: set[int] = set()
        for path in self._migrations_path.glob("*.sql"):
            match = _MIGRATION_PATTERN.fullmatch(path.name)
            if match is None:
                continue
            version = int(match.group(1))
            if version in versions:
                raise ValueError(f"duplicate migration version: {version}")
            versions.add(version)
            discovered.append((version, path))
        return tuple(sorted(discovered, key=lambda item: (item[0], item[1].name)))

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    def _apply_migrations(self, connection: sqlite3.Connection) -> None:
        applied: dict[int, tuple[str, str]] = {}
        if self._table_exists(connection, "schema_migrations"):
            applied = {
                int(row["version"]): (str(row["filename"]), str(row["migration_hash"]))
                for row in connection.execute(
                    "SELECT version, filename, migration_hash FROM schema_migrations ORDER BY version"
                ).fetchall()
            }
        for version, path in self._migration_files():
            filename = path.name
            migration_hash = "sha256:" + sha256(path.read_bytes()).hexdigest()
            existing = applied.get(version)
            if existing is not None:
                if existing != (filename, migration_hash):
                    raise ValueError(f"migration version {version} hash or filename mismatch")
                continue
            for statement in self._iter_migration_statements(path.read_text(encoding="utf-8")):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, filename, migration_hash, applied_at) VALUES (?, ?, ?, ?)",
                (version, filename, migration_hash, _utc_now()),
            )

    def _recover_interrupted_runs(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT r.run_id, r.row_id, r.workspace_id, r.request_hash, r.idempotency_scope, r.request_id, "
            "r.trace_id, r.source_record_version, f.analysis_id "
            "FROM review_suggestion_runs AS r "
            "JOIN fmea_rows AS f ON f.row_id = r.row_id AND f.workspace_id = r.workspace_id "
            "WHERE r.status IN ('queued', 'running') ORDER BY r.run_id"
        ).fetchall()
        for row in rows:
            finished_at = _utc_now()
            event_id = "recovery-" + sha256(str(row["run_id"]).encode("utf-8")).hexdigest()
            request_hash = str(row["request_hash"])
            recovery_audit = AuditEvent(
                event_id=event_id,
                occurred_at_server=finished_at,
                workspace_id=str(row["workspace_id"]),
                actor_id="review-system",
                actor_type=ActorType.SYSTEM,
                actor_roles=(),
                command=_SUGGESTION_FAIL_COMMAND,
                action=None,
                reason_code=None,
                reason="FMEA_REVIEW_RUN_INTERRUPTED",
                analysis_id=str(row["analysis_id"]),
                row_id=str(row["row_id"]),
                suggestion_id=None,
                decision_id=None,
                expected_record_version=int(row["source_record_version"]),
                applied_record_version=None,
                before_hash=None,
                after_hash=None,
                changed_fields=(),
                evidence_ids=(),
                evidence_request_targets=(),
                idempotency_key_hash=_json_hash(str(row["idempotency_scope"])),
                canonical_payload_hash=request_hash,
                versions=VersionSet(
                    schema_id=FMEA_SCHEMA_ID,
                    data_version="review-v1",
                    graph_version="review-v1",
                    evidence_pack_version="review-v1",
                    profile_version="review-v1",
                    template_version="1.0.0",
                    scoring_version="review-v1",
                    prompt_version="review-v1",
                    model_version="review-v1",
                    input_snapshot_hash=request_hash,
                ),
                template_id="fmea-row-review",
                template_version="1.0.0",
                profile_id="fmea-review",
                profile_version="1.0.0",
                model_manifest=None,
                request_id=str(row["request_id"]),
                trace_id=str(row["trace_id"]),
                retrieval_trace_id=str(row["trace_id"]),
                run_id=str(row["run_id"]),
                request_hash=request_hash,
                error_code="FMEA_REVIEW_RUN_INTERRUPTED",
                retryable=True,
            )
            connection.execute(
                "UPDATE review_suggestion_runs SET status = 'failed', error_code = ?, retryable = 1, finished_at = ? "
                "WHERE run_id = ?",
                ("FMEA_REVIEW_RUN_INTERRUPTED", finished_at, row["run_id"]),
            )
            self._insert_audit(connection, recovery_audit)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute("BEGIN EXCLUSIVE")
            self._apply_migrations(connection)
            self._recover_interrupted_runs(connection)
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    @staticmethod
    def _workspace(workspace_id: str) -> str:
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ValueError("workspace_id must not be empty")
        return workspace_id

    @staticmethod
    def _conflict(message: str) -> NoReturn:
        raise ReviewError("FMEA_IDEMPOTENCY_CONFLICT", message)

    @staticmethod
    def _row_json(row: FmeaRow) -> tuple[str, str]:
        payload = encode_json(row)
        if cast(FmeaRow, _decode_fmea_json(payload, decode_row, "row")) != row:
            raise ValueError("row JSON does not round-trip through the FMEA codec")
        return payload, _json_hash(payload)

    @staticmethod
    def _analysis_json(analysis: FmeaAnalysis) -> tuple[str, str]:
        payload = encode_json(analysis)
        if cast(FmeaAnalysis, _decode_fmea_json(payload, decode_analysis, "analysis")) != analysis:
            raise ValueError("analysis JSON does not round-trip through the FMEA codec")
        return payload, _json_hash(payload)

    @staticmethod
    def _source_json(source: ReviewSourceSnapshot) -> tuple[str, str]:
        payload = encode_review_json(source)
        decoded = decode_review_source_snapshot(payload)
        return payload, decoded.source_hash

    def _validate_bundle(  # noqa: C901
        self, bundle: ReviewCandidateBundle, actor_workspace_id: str
    ) -> tuple[str, str, str, str, tuple[tuple[FmeaRow, str, str, ReviewSourceSnapshot, str], ...]]:
        if bundle.evidence_pack.workspace_id != actor_workspace_id:
            raise ValueError("evidence pack workspace_id does not match actor workspace")
        if len(bundle.rows) != len(bundle.source_snapshots):
            raise ValueError("each review row must have exactly one source snapshot")
        if len({row.row_id for row in bundle.rows}) != len(bundle.rows):
            raise ValueError("review row IDs must be unique")
        if len({source.row_id for source in bundle.source_snapshots}) != len(bundle.source_snapshots):
            raise ValueError("source snapshot row IDs must be unique")

        source_by_row = {source.row_id: source for source in bundle.source_snapshots}
        analysis_json, analysis_hash = self._analysis_json(bundle.analysis)
        pack_json = encode_json(bundle.evidence_pack)
        _decode_fmea_json(pack_json, decode_evidence_pack, "evidence pack")
        values: list[tuple[FmeaRow, str, str, ReviewSourceSnapshot, str]] = []
        for row in bundle.rows:
            if row.analysis_id != bundle.analysis.analysis_id:
                raise ValueError("row analysis_id does not match analysis")
            if row.evidence_pack_id != bundle.evidence_pack.pack_id:
                raise ValueError("row evidence_pack_id does not match evidence pack")
            source = source_by_row.get(row.row_id)
            if source is None:
                raise ValueError(f"missing source snapshot for row {row.row_id}")
            validate_row_evidence(
                row,
                bundle.evidence_pack,
                resolved_profile=source.resolved_evidence_profile,
                evidence_types=source.evidence_types,
                retrieval_incomplete=source.retrieval_incomplete,
            )
            final_row = replace(
                row,
                review_status=ReviewStatus.SUGGESTED,
                publication_status=PublicationStatus.UNPUBLISHED,
            )
            if source.source_record_version != final_row.record_version:
                raise ValueError(f"source record version does not match row {row.row_id}")
            source_json, _ = self._source_json(source)
            row_json, row_hash = self._row_json(final_row)
            values.append((final_row, row_json, row_hash, source, source_json))
        if len(values) != len(source_by_row):
            raise ValueError("each source snapshot must belong to one review row")
        return analysis_json, analysis_hash, pack_json, bundle.evidence_pack.pack_hash, tuple(values)

    def save_review_candidate_bundle(  # noqa: C901
        self, bundle: ReviewCandidateBundle, actor: ActorContext
    ) -> tuple[FmeaRow, ...]:
        actor_workspace_id = self._workspace(actor.workspace_id)
        analysis_json, analysis_hash, pack_json, pack_hash, values = self._validate_bundle(bundle, actor_workspace_id)
        created_at = _utc_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing_analysis = connection.execute(
                "SELECT analysis_hash, analysis_json FROM fmea_analyses WHERE analysis_id = ?",
                (bundle.analysis.analysis_id,),
            ).fetchone()
            if existing_analysis is not None and (
                existing_analysis["analysis_hash"] != analysis_hash or existing_analysis["analysis_json"] != analysis_json
            ):
                self._conflict("analysis ID already contains a different canonical payload")

            existing_pack = connection.execute(
                "SELECT workspace_id, pack_hash, pack_json FROM evidence_packs WHERE pack_id = ?",
                (bundle.evidence_pack.pack_id,),
            ).fetchone()
            if existing_pack is not None and (
                existing_pack["workspace_id"] != actor_workspace_id
                or existing_pack["pack_hash"] != pack_hash
                or existing_pack["pack_json"] != pack_json
            ):
                self._conflict("evidence pack ID already contains a different canonical payload")

            for final_row, row_json, row_hash, source, source_json in values:
                existing_row = connection.execute(
                    "SELECT workspace_id, analysis_id, evidence_pack_id, review_status, publication_status, "
                    "record_version, row_hash, row_json FROM fmea_rows WHERE row_id = ?",
                    (final_row.row_id,),
                ).fetchone()
                if existing_row is not None and (
                    existing_row["workspace_id"] != actor_workspace_id
                    or existing_row["analysis_id"] != final_row.analysis_id
                    or existing_row["evidence_pack_id"] != final_row.evidence_pack_id
                    or existing_row["review_status"] != final_row.review_status.value
                    or existing_row["publication_status"] != final_row.publication_status.value
                    or existing_row["record_version"] != final_row.record_version
                    or existing_row["row_hash"] != row_hash
                    or existing_row["row_json"] != row_json
                ):
                    self._conflict("row ID already contains a different canonical payload")
                existing_source = connection.execute(
                    "SELECT workspace_id, source_record_version, source_hash, snapshot_json "
                    "FROM review_source_snapshots WHERE row_id = ?",
                    (source.row_id,),
                ).fetchone()
                if existing_source is not None and (
                    existing_source["workspace_id"] != actor_workspace_id
                    or existing_source["source_record_version"] != source.source_record_version
                    or existing_source["source_hash"] != source.source_hash
                    or existing_source["snapshot_json"] != source_json
                ):
                    self._conflict("source snapshot already contains a different canonical payload")
                conflicting_source = connection.execute(
                    "SELECT row_id FROM review_source_snapshots WHERE source_hash = ?",
                    (source.source_hash,),
                ).fetchone()
                if conflicting_source is not None and conflicting_source["row_id"] != source.row_id:
                    self._conflict("source hash is already bound to another row")

            if existing_analysis is None:
                connection.execute(
                    "INSERT INTO fmea_analyses(analysis_id, analysis_hash, analysis_json, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (bundle.analysis.analysis_id, analysis_hash, analysis_json, created_at, created_at),
                )
            if existing_pack is None:
                connection.execute(
                    "INSERT INTO evidence_packs(pack_id, workspace_id, pack_hash, pack_json, created_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        bundle.evidence_pack.pack_id,
                        actor_workspace_id,
                        pack_hash,
                        pack_json,
                        bundle.evidence_pack.created_at,
                        bundle.evidence_pack.expires_at,
                    ),
                )
            for final_row, row_json, row_hash, source, source_json in values:
                if connection.execute("SELECT 1 FROM fmea_rows WHERE row_id = ?", (final_row.row_id,)).fetchone() is None:
                    connection.execute(
                        "INSERT INTO fmea_rows "
                        "(row_id, workspace_id, analysis_id, evidence_pack_id, review_status, publication_status, "
                        "record_version, row_hash, row_json, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            final_row.row_id,
                            actor_workspace_id,
                            final_row.analysis_id,
                            final_row.evidence_pack_id,
                            final_row.review_status.value,
                            final_row.publication_status.value,
                            final_row.record_version,
                            row_hash,
                            row_json,
                            created_at,
                            created_at,
                        ),
                    )
                if connection.execute(
                    "SELECT 1 FROM review_source_snapshots WHERE row_id = ?", (source.row_id,)
                ).fetchone() is None:
                    connection.execute(
                        "INSERT INTO review_source_snapshots "
                        "(row_id, workspace_id, source_record_version, source_hash, snapshot_json, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (source.row_id, actor_workspace_id, source.source_record_version, source.source_hash, source_json, created_at),
                    )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return tuple(item[0] for item in values)

    @staticmethod
    def _decode_row_record(row: sqlite3.Row) -> FmeaRow:
        decoded = cast(FmeaRow, _decode_fmea_json(row["row_json"], decode_row, "row"))
        if decoded.row_id != row["row_id"] or decoded.record_version != row["record_version"]:
            raise ValueError("persisted row identity does not match its columns")
        if row["row_hash"] != _json_hash(cast(str, row["row_json"])):
            raise ValueError("persisted row hash does not match its JSON")
        return decoded

    @staticmethod
    def _decode_analysis_record(row: sqlite3.Row) -> FmeaAnalysis:
        decoded = cast(FmeaAnalysis, _decode_fmea_json(row["analysis_json"], decode_analysis, "analysis"))
        if decoded.analysis_id != row["analysis_id"] or row["analysis_hash"] != _json_hash(cast(str, row["analysis_json"])):
            raise ValueError("persisted analysis hash or identity does not match its JSON")
        return decoded

    @staticmethod
    def _decode_pack_record(row: sqlite3.Row) -> EvidencePack:
        decoded = cast(EvidencePack, _decode_fmea_json(row["pack_json"], decode_evidence_pack, "evidence pack"))
        if decoded.pack_id != row["pack_id"] or decoded.workspace_id != row["workspace_id"]:
            raise ValueError("persisted evidence pack identity does not match its columns")
        if decoded.pack_hash != row["pack_hash"]:
            raise ValueError("persisted evidence pack hash does not match its columns")
        return decoded

    def get_row(self, row_id: str, workspace_id: str) -> FmeaRow | None:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT r.* FROM fmea_rows AS r "
                "JOIN evidence_packs AS p ON p.pack_id = r.evidence_pack_id AND p.workspace_id = r.workspace_id "
                "WHERE r.row_id = ? AND r.workspace_id = ? AND p.workspace_id = ?",
                (row_id, workspace, workspace),
            ).fetchone()
            return None if row is None else self._decode_row_record(row)
        finally:
            connection.close()

    def get_review_source(self, row_id: str, workspace_id: str) -> ReviewSourceSnapshot | None:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT s.* FROM review_source_snapshots AS s "
                "JOIN fmea_rows AS r ON r.row_id = s.row_id AND r.workspace_id = s.workspace_id "
                "JOIN evidence_packs AS p ON p.pack_id = r.evidence_pack_id AND p.workspace_id = r.workspace_id "
                "WHERE s.row_id = ? AND s.workspace_id = ? AND r.workspace_id = ? AND p.workspace_id = ?",
                (row_id, workspace, workspace, workspace),
            ).fetchone()
            if row is None:
                return None
            result = decode_review_source_snapshot(cast(str, row["snapshot_json"]))
            if result.row_id != row["row_id"] or result.source_record_version != row["source_record_version"]:
                raise ValueError("persisted source snapshot identity does not match its columns")
            if result.source_hash != row["source_hash"]:
                raise ValueError("persisted source snapshot hash does not match its columns")
            return result
        finally:
            connection.close()

    def get_evidence_pack(self, pack_id: str, workspace_id: str) -> EvidencePack | None:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT p.* FROM evidence_packs AS p "
                "JOIN fmea_rows AS r ON r.evidence_pack_id = p.pack_id AND r.workspace_id = p.workspace_id "
                "WHERE p.pack_id = ? AND p.workspace_id = ? AND r.workspace_id = ?",
                (pack_id, workspace, workspace),
            ).fetchone()
            return None if row is None else self._decode_pack_record(row)
        finally:
            connection.close()

    @staticmethod
    def _decode_suggestion_run(row: sqlite3.Row) -> ReviewSuggestionRun:
        try:
            status = RunStatus(str(row["status"]))
        except ValueError as exc:
            raise ValueError("persisted suggestion run status is invalid") from exc
        return ReviewSuggestionRun(
            run_id=str(row["run_id"]),
            row_id=str(row["row_id"]),
            source_record_version=int(row["source_record_version"]),
            status=status,
            suggestion_id=None if row["suggestion_id"] is None else str(row["suggestion_id"]),
            error_code=None if row["error_code"] is None else str(row["error_code"]),
            retryable=bool(row["retryable"]),
            request_id=str(row["request_id"]),
            trace_id=str(row["trace_id"]),
            created_at=str(row["created_at"]),
            started_at=None if row["started_at"] is None else str(row["started_at"]),
            finished_at=None if row["finished_at"] is None else str(row["finished_at"]),
        )

    @staticmethod
    def _run_response_json(run: ReviewSuggestionRun) -> str:
        return encode_review_json(
            {
                "run_id": run.run_id,
                "row_id": run.row_id,
                "source_record_version": run.source_record_version,
                "status": run.status.value,
                "suggestion_id": run.suggestion_id,
                "error_code": run.error_code,
                "retryable": run.retryable,
                "request_id": run.request_id,
                "trace_id": run.trace_id,
                "created_at": run.created_at,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            }
        )

    @staticmethod
    def _decode_run_response_json(payload: object) -> ReviewSuggestionRun:
        data = _load_strict_json(payload, "review run response")
        expected = {
            "run_id",
            "row_id",
            "source_record_version",
            "status",
            "suggestion_id",
            "error_code",
            "retryable",
            "request_id",
            "trace_id",
            "created_at",
            "started_at",
            "finished_at",
        }
        if set(data) != expected:
            raise ValueError("persisted review run response fields are invalid")
        run_id = data["run_id"]
        row_id = data["row_id"]
        source_record_version = data["source_record_version"]
        raw_status = data["status"]
        suggestion_id = data["suggestion_id"]
        error_code = data["error_code"]
        retryable = data["retryable"]
        request_id = data["request_id"]
        trace_id = data["trace_id"]
        created_at = data["created_at"]
        started_at = data["started_at"]
        finished_at = data["finished_at"]
        if (
            not isinstance(run_id, str)
            or not isinstance(row_id, str)
            or isinstance(source_record_version, bool)
            or not isinstance(source_record_version, int)
            or not isinstance(raw_status, str)
            or (suggestion_id is not None and not isinstance(suggestion_id, str))
            or (error_code is not None and not isinstance(error_code, str))
            or type(retryable) is not bool
            or not isinstance(request_id, str)
            or not isinstance(trace_id, str)
            or not isinstance(created_at, str)
            or (started_at is not None and not isinstance(started_at, str))
            or (finished_at is not None and not isinstance(finished_at, str))
        ):
            raise ValueError("persisted review run response values are invalid")
        try:
            status = RunStatus(raw_status)
        except ValueError as exc:
            raise ValueError("persisted review run response status is invalid") from exc
        return ReviewSuggestionRun(
            run_id=run_id,
            row_id=row_id,
            source_record_version=source_record_version,
            status=status,
            suggestion_id=suggestion_id,
            error_code=error_code,
            retryable=retryable,
            request_id=request_id,
            trace_id=trace_id,
            created_at=created_at,
            started_at=started_at,
            finished_at=finished_at,
        )

    @staticmethod
    def _insert_audit(
        connection: sqlite3.Connection,
        audit: AuditEvent,
    ) -> None:
        connection.execute(
            "INSERT INTO audit_events "
            "(event_id, row_id, workspace_id, actor_id, actor_type, command, action, suggestion_id, decision_id, "
            "expected_record_version, applied_record_version, before_hash, after_hash, canonical_payload_hash, event_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                audit.event_id,
                audit.row_id,
                audit.workspace_id,
                audit.actor_id,
                audit.actor_type.value,
                audit.command,
                None if audit.action is None else audit.action.value,
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

    @staticmethod
    def _reservation_row(connection: sqlite3.Connection, scope: IdempotencyScope) -> sqlite3.Row | None:
        row = connection.execute(
            "SELECT * FROM idempotency_records WHERE scope_key = ?",
            (scope.scope_key,),
        ).fetchone()
        return cast(sqlite3.Row | None, row)

    @staticmethod
    def _mutation_row(
        connection: sqlite3.Connection,
        run_id: str,
        workspace_id: str,
    ) -> sqlite3.Row | None:
        row = connection.execute(
            "SELECT r.*, f.analysis_id AS analysis_id "
            "FROM review_suggestion_runs AS r "
            "JOIN fmea_rows AS f ON f.row_id = r.row_id AND f.workspace_id = r.workspace_id "
            "JOIN evidence_packs AS p ON p.pack_id = f.evidence_pack_id AND p.workspace_id = f.workspace_id "
            "WHERE r.run_id = ? AND r.workspace_id = ? AND f.workspace_id = ? AND p.workspace_id = ?",
            (run_id, workspace_id, workspace_id, workspace_id),
        ).fetchone()
        return cast(sqlite3.Row | None, row)

    @staticmethod
    def _binding_error(message: str) -> NoReturn:
        raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", message)

    @staticmethod
    def _transition_error(message: str) -> NoReturn:
        raise ReviewError("FMEA_REVIEW_TERMINAL", message)

    @classmethod
    def _validate_prepared_binding(cls, prepared: PreparedSuggestionRun) -> None:
        command = prepared.command
        actor = prepared.actor
        scope = prepared.scope
        run = prepared.run
        audit = prepared.audit
        expected_key_hash = idempotency_key_hash(command.idempotency_key)
        if (
            scope.workspace_id != actor.workspace_id
            or scope.actor_id != actor.actor_id
            or scope.command != _SUGGESTION_START_COMMAND
            or scope.resource_path != f"/rows/{command.row_id}"
            or scope.key_hash != expected_key_hash
        ):
            cls._binding_error("review suggestion reservation binding is invalid")
        expected_payload_hash = canonical_payload_hash(command)
        if (
            prepared.payload_hash != expected_payload_hash
            or run.row_id != command.row_id
            or run.source_record_version != command.expected_record_version
            or run.status is not RunStatus.QUEUED
            or not run.request_id
            or not run.trace_id
        ):
            cls._binding_error("review suggestion reservation binding is invalid")
        if (
            audit.workspace_id != actor.workspace_id
            or audit.actor_id != actor.actor_id
            or audit.actor_type is not actor.actor_type
            or audit.actor_roles != tuple(sorted(actor.roles))
            or audit.row_id != command.row_id
            or audit.command != _SUGGESTION_CREATE_COMMAND
            or audit.suggestion_id is not None
            or audit.decision_id is not None
            or audit.expected_record_version != command.expected_record_version
            or audit.applied_record_version is not None
            or audit.request_id != run.request_id
            or audit.trace_id != run.trace_id
            or audit.retrieval_trace_id != run.trace_id
            or audit.run_id != run.run_id
            or audit.request_hash != prepared.payload_hash
            or audit.idempotency_key_hash != expected_key_hash
            or audit.canonical_payload_hash != prepared.payload_hash
        ):
            cls._binding_error("review suggestion audit binding is invalid")

    @classmethod
    def _validate_complete_binding(
        cls,
        run: ReviewSuggestionRun,
        run_row: sqlite3.Row,
        workspace_id: str,
        suggestion: ReviewSuggestion,
        audit: AuditEvent,
    ) -> None:
        if (
            suggestion.run_id != run.run_id
            or suggestion.row_id != run.row_id
            or suggestion.source_record_version != run.source_record_version
            or audit.workspace_id != workspace_id
            or audit.row_id != run.row_id
            or audit.request_id != run.request_id
            or audit.trace_id != run.trace_id
            or audit.canonical_payload_hash != str(run_row["request_hash"])
            or getattr(audit, "run_id", None) != run.run_id
            or getattr(audit, "request_hash", None) != str(run_row["request_hash"])
            or audit.expected_record_version != run.source_record_version
            or audit.command != _SUGGESTION_COMPLETE_COMMAND
            or audit.suggestion_id != suggestion.suggestion_id
            or audit.model_manifest != suggestion.model_manifest
            or audit.action != suggestion.recommended_action
            or audit.actor_type is not ActorType.MODEL
            or audit.actor_id != "review-model"
            or audit.decision_id is not None
        ):
            cls._binding_error("review suggestion completion binding is invalid")

    @classmethod
    def _validate_fail_binding(
        cls,
        run: ReviewSuggestionRun,
        run_row: sqlite3.Row,
        workspace_id: str,
        error_code: str,
        retryable: bool,
        audit: AuditEvent,
    ) -> None:
        if (
            error_code not in REVIEW_ERROR_CODES
            or not isinstance(retryable, bool)
            or audit.workspace_id != workspace_id
            or audit.row_id != run.row_id
            or audit.request_id != run.request_id
            or audit.trace_id != run.trace_id
            or audit.canonical_payload_hash != str(run_row["request_hash"])
            or getattr(audit, "run_id", None) != run.run_id
            or getattr(audit, "request_hash", None) != str(run_row["request_hash"])
            or audit.expected_record_version != run.source_record_version
            or audit.command != _SUGGESTION_FAIL_COMMAND
            or audit.reason != error_code
            or audit.error_code != error_code
            or audit.retryable is not retryable
            or run.suggestion_id is not None
            or audit.suggestion_id is not None
            or audit.decision_id is not None
            or audit.actor_type is not ActorType.SYSTEM
            or audit.actor_id != "review-system"
        ):
            cls._binding_error("review suggestion failure binding is invalid")

    @staticmethod
    def _load_reservation_run(connection: sqlite3.Connection, run_id: str, workspace_id: str) -> ReviewSuggestionRun:
        row = connection.execute(
            "SELECT * FROM review_suggestion_runs WHERE run_id = ? AND workspace_id = ?",
            (run_id, workspace_id),
        ).fetchone()
        if row is None:
            raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "review run could not be loaded", retryable=True)
        return SqliteFmeaRepository._decode_suggestion_run(row)

    @staticmethod
    def _derive_next_row(previous: FmeaRow, decision: ReviewDecisionRecord) -> FmeaRow:  # noqa: C901
        try:
            expected_status = _DECISION_REVIEW_STATUS[decision.action]
        except (KeyError, TypeError) as exc:
            raise ValueError("review decision action is invalid") from exc
        if decision.action is ReviewAction.MODIFY_AND_ACCEPT and not decision.edits:
            raise ValueError("modify_and_accept decision must contain edits")
        if decision.action is not ReviewAction.MODIFY_AND_ACCEPT and decision.edits:
            raise ValueError("non-modify decision must not contain edits")
        if decision.action is ReviewAction.REQUEST_EVIDENCE and not decision.evidence_requests:
            raise ValueError("request_evidence decision must contain requests")
        if decision.action is not ReviewAction.REQUEST_EVIDENCE and decision.evidence_requests:
            raise ValueError("non-request decision must not contain requests")

        values = {field: getattr(previous, field) for field in EDITABLE_REVIEW_FIELDS}
        field_evidence = dict(previous.field_evidence)
        field_support = dict(previous.field_support)
        statuses = [previous.claim_status, *(item.claim_status for item in decision.unresolved_acknowledgements)]
        seen_fields: set[str] = set()
        for edit in decision.edits:
            if edit.target_field not in EDITABLE_REVIEW_FIELDS or edit.target_field in seen_fields:
                raise ValueError("review decision edit fields are invalid")
            if edit.target_field == "failure_mode":
                if not isinstance(edit.value, str):
                    raise ValueError("failure_mode edit value is invalid")
            elif not isinstance(edit.value, tuple) or not all(isinstance(item, str) for item in edit.value):
                raise ValueError("review edit value is invalid")
            if not isinstance(edit.claim_status, ClaimStatus) or not isinstance(edit.support_status, EvidenceSupportStatus):
                raise ValueError("review edit statuses are invalid")
            if edit.target_field not in field_evidence or edit.target_field not in field_support:
                raise ValueError("review edit field is not present on the row")
            seen_fields.add(edit.target_field)
            values[edit.target_field] = edit.value
            field_evidence[edit.target_field] = edit.evidence_ids
            field_support[edit.target_field] = edit.support_status
            statuses.append(edit.claim_status)

        claim_status = max(statuses, key=lambda status: _CLAIM_PRIORITY[status])
        return replace(
            previous,
            **values,
            field_evidence=tuple((field, field_evidence[field]) for field, _ in previous.field_evidence),
            field_support=tuple((field, field_support[field]) for field, _ in previous.field_support),
            claim_status=claim_status,
            review_status=expected_status,
            record_version=previous.record_version + 1,
        )

    def _validate_prepared_decision(self, prepared: PreparedReviewDecision) -> None:
        decision = prepared.decision
        previous = prepared.previous_row
        next_row = prepared.next_row
        audit = prepared.audit
        scope = prepared.scope
        try:
            expected_status = _DECISION_REVIEW_STATUS[decision.action]
            expected_next = self._derive_next_row(previous, decision)
        except (KeyError, TypeError, ValueError, AttributeError):
            self._binding_error("review decision next row derivation is invalid")
        if (
            scope.workspace_id != audit.workspace_id
            or scope.actor_id != decision.actor_id
            or scope.command != _DECISION_COMMAND
            or scope.resource_path != f"/rows/{decision.row_id}"
            or scope.key_hash != audit.idempotency_key_hash
            or prepared.payload_hash != audit.canonical_payload_hash
            or prepared.expected_record_version != previous.record_version
            or decision.row_id != previous.row_id
            or decision.row_id != next_row.row_id
            or decision.previous_record_version != previous.record_version
            or decision.record_version != next_row.record_version
            or next_row.record_version != previous.record_version + 1
            or next_row.review_status is not expected_status
            or next_row.publication_status is not previous.publication_status
            or audit.workspace_id != scope.workspace_id
            or audit.row_id != decision.row_id
            or audit.actor_id != decision.actor_id
            or audit.actor_type is not ActorType.HUMAN
            or audit.command != _DECISION_COMMAND
            or audit.action is not decision.action
            or audit.reason_code is not decision.reason_code
            or audit.suggestion_id != decision.suggestion_id
            or audit.decision_id != decision.decision_id
            or audit.expected_record_version != previous.record_version
            or audit.applied_record_version != next_row.record_version
            or audit.analysis_id != previous.analysis_id
            or audit.request_id == ""
            or audit.trace_id == ""
            or audit.retrieval_trace_id != audit.trace_id
            or next_row != expected_next
        ):
            self._binding_error("review decision binding is invalid")
        if audit.before_hash != self._row_json(previous)[1] or audit.after_hash != self._row_json(next_row)[1]:
            self._binding_error("review decision row hash binding is invalid")
        expected_changed_fields = tuple(sorted(edit.target_field for edit in decision.edits))
        expected_evidence_ids = tuple(sorted({evidence_id for edit in decision.edits for evidence_id in edit.evidence_ids}))
        expected_request_targets = tuple(sorted(item.target_field for item in decision.evidence_requests))
        if (
            audit.changed_fields != expected_changed_fields
            or audit.evidence_ids != expected_evidence_ids
            or audit.evidence_request_targets != expected_request_targets
        ):
            self._binding_error("review decision audit binding is invalid")
        if decision.action is ReviewAction.MODIFY_AND_ACCEPT and not decision.edits:
            self._binding_error("modify_and_accept decision binding is invalid")
        if decision.action is not ReviewAction.MODIFY_AND_ACCEPT and decision.edits:
            self._binding_error("review decision action binding is invalid")
        if decision.action is ReviewAction.REQUEST_EVIDENCE and not decision.evidence_requests:
            self._binding_error("request_evidence decision binding is invalid")
        if decision.action is not ReviewAction.REQUEST_EVIDENCE and decision.evidence_requests:
            self._binding_error("review decision action binding is invalid")

    @staticmethod
    def _validate_decision_replay_binding(
        *,
        existing: sqlite3.Row,
        decision_row: sqlite3.Row,
        audit_row: sqlite3.Row,
        result: ReviewDecisionResult,
        decision: ReviewDecisionRecord,
        audit: AuditEvent,
        scope: IdempotencyScope,
        payload_hash: str,
    ) -> None:
        try:
            expected_status = _DECISION_REVIEW_STATUS[decision.action]
        except (KeyError, TypeError) as exc:
            raise ValueError("persisted review decision action is invalid") from exc
        row_hash = _json_hash(encode_json(result.row))
        expected_changed_fields = tuple(sorted(edit.target_field for edit in decision.edits))
        expected_evidence_ids = tuple(sorted({evidence_id for edit in decision.edits for evidence_id in edit.evidence_ids}))
        expected_request_targets = tuple(sorted(item.target_field for item in decision.evidence_requests))
        if (
            existing["payload_hash"] != payload_hash
            or existing["resource_id"] != result.decision_id
            or existing["state"] != "completed"
            or existing["status_code"] != 200
            or decision_row["decision_id"] != decision.decision_id
            or decision_row["workspace_id"] != scope.workspace_id
            or decision_row["row_id"] != result.row.row_id
            or decision_row["previous_record_version"] != decision.previous_record_version
            or decision_row["record_version"] != decision.record_version
            or decision_row["actor_id"] != decision.actor_id
            or decision_row["action"] != decision.action.value
            or decision_row["reason_code"] != decision.reason_code.value
            or decision_row["created_at"] != decision.created_at
            or cast(str, decision_row["decision_json"]) != encode_review_json(decision)
            or decision.decision_id != result.decision_id
            or decision.row_id != result.row.row_id
            or decision.previous_record_version != result.previous_record_version
            or decision.record_version != result.record_version
            or decision.record_version != decision.previous_record_version + 1
            or decision.suggestion_id != result.suggestion_id
            or decision.evidence_requests != result.evidence_requests
            or result.row.record_version != result.record_version
            or result.row.review_status is not result.review_status
            or result.row.publication_status is not result.publication_status
            or result.review_status is not expected_status
            or audit_row["event_id"] != result.audit_event_id
            or audit_row["row_id"] != result.row.row_id
            or audit_row["workspace_id"] != scope.workspace_id
            or audit_row["actor_id"] != scope.actor_id
            or audit_row["actor_type"] != audit.actor_type.value
            or audit_row["command"] != _DECISION_COMMAND
            or audit.action is None
            or audit_row["action"] != audit.action.value
            or audit_row["suggestion_id"] != audit.suggestion_id
            or audit_row["decision_id"] != result.decision_id
            or audit_row["expected_record_version"] != audit.expected_record_version
            or audit_row["applied_record_version"] != audit.applied_record_version
            or audit_row["before_hash"] != audit.before_hash
            or audit_row["after_hash"] != audit.after_hash
            or audit_row["canonical_payload_hash"] != audit.canonical_payload_hash
            or audit_row["created_at"] != audit.occurred_at_server
            or cast(str, audit_row["event_json"]) != encode_review_json(audit)
            or audit.event_id != result.audit_event_id
            or audit.workspace_id != scope.workspace_id
            or audit.actor_id != scope.actor_id
            or audit.actor_type is not ActorType.HUMAN
            or audit.command != _DECISION_COMMAND
            or audit.action is not decision.action
            or audit.reason_code is not decision.reason_code
            or audit.suggestion_id != decision.suggestion_id
            or audit.decision_id != result.decision_id
            or audit.analysis_id != result.row.analysis_id
            or audit.row_id != result.row.row_id
            or audit.expected_record_version != result.previous_record_version
            or audit.applied_record_version != result.record_version
            or audit.after_hash != row_hash
            or audit.before_hash is None
            or audit.idempotency_key_hash != scope.key_hash
            or audit.canonical_payload_hash != payload_hash
            or audit.changed_fields != expected_changed_fields
            or audit.evidence_ids != expected_evidence_ids
            or audit.evidence_request_targets != expected_request_targets
            or audit.request_id != result.request_id
            or audit.trace_id != result.trace_id
            or audit.retrieval_trace_id != result.trace_id
        ):
            raise ValueError("persisted review decision replay binding is invalid")

    @classmethod
    def _decision_replay(
        cls,
        connection: sqlite3.Connection,
        scope: IdempotencyScope,
        payload_hash: str,
    ) -> ReviewDecisionResult | None:
        existing = cls._reservation_row(connection, scope)
        if existing is None:
            return None
        if existing["payload_hash"] != payload_hash:
            cls._conflict("idempotency key already has a different payload")
        if existing["state"] != "completed" or not isinstance(existing["response_json"], str):
            raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "review decision replay is unavailable", retryable=True)
        try:
            result = _decode_decision_result(existing["response_json"])
            decision_row = connection.execute(
                "SELECT * FROM review_decisions WHERE decision_id = ? AND workspace_id = ?",
                (result.decision_id, scope.workspace_id),
            ).fetchone()
            audit_row = connection.execute(
                "SELECT * FROM audit_events WHERE event_id = ? AND workspace_id = ?",
                (result.audit_event_id, scope.workspace_id),
            ).fetchone()
            if decision_row is None or audit_row is None:
                raise ValueError("persisted review decision replay records are missing")
            decision = decode_review_decision_record(cast(str, decision_row["decision_json"]))
            audit = _decode_audit_event(audit_row["event_json"])
            cls._validate_decision_replay_binding(
                existing=existing,
                decision_row=decision_row,
                audit_row=audit_row,
                result=result,
                decision=decision,
                audit=audit,
                scope=scope,
                payload_hash=payload_hash,
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "review decision replay is unavailable", retryable=True) from exc
        return result

    def replay_decision(self, scope: IdempotencyScope, payload_hash: str) -> ReviewDecisionResult | None:
        if scope.command != _DECISION_COMMAND:
            self._binding_error("review decision scope is invalid")
        connection = self._connect()
        try:
            return self._decision_replay(connection, scope, payload_hash)
        finally:
            connection.close()

    def commit_review_decision(self, prepared: PreparedReviewDecision) -> ReviewDecisionResult:  # noqa: C901
        self._validate_prepared_decision(prepared)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._decision_replay(connection, prepared.scope, prepared.payload_hash)
            if replay is not None:
                connection.execute("COMMIT")
                return replay

            created_at = prepared.audit.occurred_at_server
            connection.execute(
                "INSERT INTO idempotency_records "
                "(scope_key, payload_hash, state, status_code, resource_id, response_json, created_at, completed_at) "
                "VALUES (?, ?, 'reserved', ?, ?, NULL, ?, NULL)",
                (
                    prepared.scope.scope_key,
                    prepared.payload_hash,
                    prepared.response_status,
                    prepared.decision.decision_id,
                    created_at,
                ),
            )
            current = connection.execute(
                "SELECT r.* FROM fmea_rows AS r "
                "JOIN evidence_packs AS p ON p.pack_id = r.evidence_pack_id AND p.workspace_id = r.workspace_id "
                "WHERE r.row_id = ? AND r.workspace_id = ? AND p.workspace_id = ?",
                (prepared.previous_row.row_id, prepared.scope.workspace_id, prepared.scope.workspace_id),
            ).fetchone()
            if current is None:
                raise ReviewError("FMEA_ROW_NOT_FOUND", "review row was not found")
            current_row = self._decode_row_record(current)
            if current_row.record_version != prepared.expected_record_version:
                raise ReviewError("FMEA_VERSION_CONFLICT", "review row version does not match the request")
            if current_row != prepared.previous_row:
                raise ReviewError("FMEA_VERSION_CONFLICT", "review row changed before the decision was committed")
            pack_record = connection.execute(
                "SELECT * FROM evidence_packs WHERE pack_id = ? AND workspace_id = ?",
                (current_row.evidence_pack_id, prepared.scope.workspace_id),
            ).fetchone()
            if pack_record is None:
                raise ReviewError("FMEA_ROW_NOT_FOUND", "review row was not found")
            authoritative_pack = self._decode_pack_record(pack_record)
            source_record = connection.execute(
                "SELECT snapshot_json FROM review_source_snapshots "
                "WHERE row_id = ? AND workspace_id = ?",
                (current_row.row_id, prepared.scope.workspace_id),
            ).fetchone()
            authoritative_source = (
                None
                if source_record is None
                else decode_review_source_snapshot(cast(str, source_record["snapshot_json"]))
            )
            try:
                validate_row_evidence(
                    prepared.next_row,
                    authoritative_pack,
                    resolved_profile=None
                    if authoritative_source is None
                    else authoritative_source.resolved_evidence_profile,
                    evidence_types=None
                    if authoritative_source is None
                    else authoritative_source.evidence_types,
                    retrieval_incomplete=False
                    if authoritative_source is None
                    else authoritative_source.retrieval_incomplete,
                )
            except (FmeaDomainError, ValueError):
                self._binding_error("review decision next row evidence binding is invalid")
            if current_row.review_status in {ReviewStatus.ACCEPTED, ReviewStatus.REJECTED, ReviewStatus.SUPERSEDED}:
                raise ReviewError("FMEA_REVIEW_TERMINAL", "review row is already terminal")
            if current_row.review_status not in {ReviewStatus.SUGGESTED, ReviewStatus.IN_REVIEW}:
                raise ReviewError("FMEA_PRECONDITION_REQUIRED", "review row is not available for human review")
            if current_row.publication_status is not PublicationStatus.UNPUBLISHED:
                raise ReviewError("FMEA_PRECONDITION_REQUIRED", "published rows cannot receive review decisions")

            decision_json = encode_review_json(prepared.decision)
            if decode_review_decision_record(decision_json) != prepared.decision:
                self._binding_error("review decision JSON is not canonical")
            connection.execute(
                "INSERT INTO review_decisions "
                "(decision_id, row_id, workspace_id, previous_record_version, record_version, actor_id, action, "
                "reason_code, decision_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    prepared.decision.decision_id,
                    prepared.decision.row_id,
                    prepared.scope.workspace_id,
                    prepared.decision.previous_record_version,
                    prepared.decision.record_version,
                    prepared.decision.actor_id,
                    prepared.decision.action.value,
                    prepared.decision.reason_code.value,
                    decision_json,
                    prepared.decision.created_at,
                ),
            )
            row_json, row_hash = self._row_json(prepared.next_row)
            updated = connection.execute(
                "UPDATE fmea_rows SET review_status=?, publication_status=?, record_version=?, row_hash=?, row_json=?, updated_at=? "
                "WHERE row_id=? AND workspace_id=? AND record_version=?",
                (
                    prepared.next_row.review_status.value,
                    prepared.next_row.publication_status.value,
                    prepared.next_row.record_version,
                    row_hash,
                    row_json,
                    _utc_now(),
                    prepared.next_row.row_id,
                    prepared.scope.workspace_id,
                    prepared.expected_record_version,
                ),
            )
            if updated.rowcount != 1:
                raise ReviewError("FMEA_VERSION_CONFLICT", "review row changed before the decision was committed")
            authoritative_audit = replace(prepared.audit, analysis_id=current_row.analysis_id)
            self._insert_audit(connection, authoritative_audit)
            result = ReviewDecisionResult(
                decision_id=prepared.decision.decision_id,
                row=prepared.next_row,
                previous_record_version=prepared.previous_row.record_version,
                record_version=prepared.next_row.record_version,
                review_status=prepared.next_row.review_status,
                publication_status=prepared.next_row.publication_status,
                audit_event_id=authoritative_audit.event_id,
                suggestion_id=prepared.decision.suggestion_id,
                evidence_requests=prepared.decision.evidence_requests,
                persisted=True,
                request_id=authoritative_audit.request_id,
                trace_id=authoritative_audit.trace_id,
            )
            response_json = _decision_result_json(result)
            completed = connection.execute(
                "UPDATE idempotency_records SET state='completed', status_code=?, resource_id=?, response_json=?, completed_at=? "
                "WHERE scope_key=? AND payload_hash=? AND state='reserved'",
                (
                    prepared.response_status,
                    result.decision_id,
                    response_json,
                    _utc_now(),
                    prepared.scope.scope_key,
                    prepared.payload_hash,
                ),
            )
            if completed.rowcount != 1:
                raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "review decision idempotency could not be completed", retryable=True)
            connection.execute("COMMIT")
            return result
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def reserve_suggestion_run(self, prepared: PreparedSuggestionRun) -> SuggestionRunReservation:  # noqa: C901
        self._validate_prepared_binding(prepared)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._reservation_row(connection, prepared.scope)
            if existing is not None:
                if existing["payload_hash"] != prepared.payload_hash:
                    self._conflict("idempotency key already has a different payload")
                run_id = existing["resource_id"]
                if not isinstance(run_id, str) or not run_id:
                    raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "review replay is unavailable", retryable=True)
                response_json = existing["response_json"]
                run = self._decode_run_response_json(response_json)
                if (
                    run.run_id != run_id
                    or run.row_id != prepared.command.row_id
                    or run.source_record_version != prepared.command.expected_record_version
                    or run.status is not RunStatus.QUEUED
                ):
                    raise ValueError("persisted review replay resource does not match its run")
                connection.execute("COMMIT")
                return SuggestionRunReservation(run=run, replayed=True)

            row = connection.execute(
                "SELECT r.row_id, r.workspace_id, r.analysis_id, r.evidence_pack_id, r.review_status, "
                "r.publication_status, r.record_version, s.source_record_version, p.workspace_id AS pack_workspace_id "
                "FROM fmea_rows AS r "
                "LEFT JOIN review_source_snapshots AS s ON s.row_id = r.row_id AND s.workspace_id = r.workspace_id "
                "LEFT JOIN evidence_packs AS p ON p.pack_id = r.evidence_pack_id AND p.workspace_id = r.workspace_id "
                "WHERE r.row_id = ? AND r.workspace_id = ?",
                (prepared.command.row_id, prepared.actor.workspace_id),
            ).fetchone()
            if row is None or row["pack_workspace_id"] != prepared.actor.workspace_id:
                raise ReviewError("FMEA_ROW_NOT_FOUND", "review row was not found")
            if row["review_status"] not in {ReviewStatus.SUGGESTED.value, ReviewStatus.IN_REVIEW.value}:
                raise ReviewError("FMEA_PRECONDITION_REQUIRED", "review row is not available for model suggestions")
            if row["publication_status"] != PublicationStatus.UNPUBLISHED.value:
                raise ReviewError("FMEA_PRECONDITION_REQUIRED", "published rows cannot receive model suggestions")
            if row["record_version"] != prepared.command.expected_record_version:
                raise ReviewError("FMEA_VERSION_CONFLICT", "review row version does not match the request")
            if row["source_record_version"] is None:
                raise ReviewError("FMEA_REVIEW_SOURCE_MISSING", "review source snapshot was not found")
            if row["analysis_id"] is None:
                raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "review row analysis binding is unavailable", retryable=True)

            workspace_active = connection.execute(
                "SELECT COUNT(*) AS count FROM review_suggestion_runs "
                "WHERE workspace_id = ? AND status IN ('queued', 'running')",
                (prepared.actor.workspace_id,),
            ).fetchone()
            actor_active = connection.execute(
                "SELECT COUNT(*) AS count FROM review_suggestion_runs "
                "WHERE workspace_id = ? AND actor_id = ? AND status IN ('queued', 'running')",
                (prepared.actor.workspace_id, prepared.actor.actor_id),
            ).fetchone()
            if int(workspace_active["count"]) >= 16 or int(actor_active["count"]) >= 4:
                raise ReviewError("FMEA_REVIEW_RATE_LIMITED", "too many active review runs", retryable=True)

            run = prepared.run
            connection.execute(
                "INSERT INTO idempotency_records "
                "(scope_key, payload_hash, state, status_code, resource_id, response_json, created_at, completed_at) "
                "VALUES (?, ?, 'completed', ?, ?, ?, ?, ?)",
                (
                    prepared.scope.scope_key,
                    prepared.payload_hash,
                    prepared.response_status,
                    run.run_id,
                    self._run_response_json(run),
                    run.created_at,
                    run.created_at,
                ),
            )
            connection.execute(
                "INSERT INTO review_suggestion_runs "
                "(run_id, row_id, workspace_id, actor_id, source_record_version, status, request_hash, idempotency_scope, "
                "request_id, trace_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run.run_id,
                    run.row_id,
                    prepared.actor.workspace_id,
                    prepared.actor.actor_id,
                    run.source_record_version,
                    run.status.value,
                    prepared.payload_hash,
                    prepared.scope.scope_key,
                    run.request_id,
                    run.trace_id,
                    run.created_at,
                ),
            )
            self._insert_audit(connection, replace(prepared.audit, analysis_id=str(row["analysis_id"])))
            connection.execute("COMMIT")
            return SuggestionRunReservation(run=run, replayed=False)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_suggestion_run(self, run_id: str, workspace_id: str) -> ReviewSuggestionRun | None:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            row = self._mutation_row(connection, run_id, workspace)
            return None if row is None else self._decode_suggestion_run(row)
        finally:
            connection.close()

    def mark_suggestion_run_running(self, run_id: str, workspace_id: str) -> ReviewSuggestionRun:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = self._mutation_row(connection, run_id, workspace)
            if current is None:
                raise ReviewError("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "review run was not found")
            run = self._decode_suggestion_run(current)
            if run.status is not RunStatus.QUEUED:
                self._transition_error("review run is not queued")
            connection.execute(
                "UPDATE review_suggestion_runs SET status = 'running', started_at = ? "
                "WHERE run_id = ? AND workspace_id = ? AND status = 'queued'",
                (_utc_now(), run_id, workspace),
            )
            result_row = self._mutation_row(connection, run_id, workspace)
            if result_row is None:
                raise ReviewError("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "review run was not found")
            result = self._decode_suggestion_run(result_row)
            connection.execute("COMMIT")
            return result
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def complete_suggestion_run(  # noqa: C901
        self,
        run_id: str,
        workspace_id: str,
        suggestion: ReviewSuggestion,
        audit: AuditEvent,
    ) -> ReviewSuggestionRun:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            run_row = self._mutation_row(connection, run_id, workspace)
            if run_row is None:
                raise ReviewError("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "review run was not found")
            run = self._decode_suggestion_run(run_row)
            if run.status is RunStatus.SUCCEEDED:
                self._validate_complete_binding(run, run_row, workspace, suggestion, audit)
                if run.suggestion_id != suggestion.suggestion_id:
                    self._binding_error("persisted review run suggestion binding is invalid")
                stored_row = connection.execute(
                    "SELECT suggestion_json FROM review_suggestions "
                    "WHERE run_id = ? AND workspace_id = ?",
                    (run_id, workspace),
                ).fetchone()
                if stored_row is None:
                    self._binding_error("persisted review suggestion binding is invalid")
                stored = decode_review_suggestion(str(stored_row["suggestion_json"]))
                if stored != replace(suggestion, stale=stored.stale):
                    self._binding_error("persisted review suggestion binding is invalid")
                connection.execute("COMMIT")
                return run
            if run.status is RunStatus.FAILED:
                self._transition_error("failed review run cannot complete")
            if run.status is not RunStatus.RUNNING:
                self._transition_error("review run is not running")
            self._validate_complete_binding(run, run_row, workspace, suggestion, audit)
            row = connection.execute(
                "SELECT record_version, workspace_id, analysis_id FROM fmea_rows "
                "WHERE row_id = ? AND workspace_id = ?",
                (run.row_id, workspace),
            ).fetchone()
            if row is None:
                raise ReviewError("FMEA_ROW_NOT_FOUND", "review row was not found")
            stale = int(row["record_version"]) != suggestion.source_record_version
            stored_suggestion = replace(suggestion, stale=stale)
            suggestion_json = encode_review_json(stored_suggestion)
            suggestion_hash = _json_hash(suggestion_json)
            connection.execute(
                "INSERT INTO review_suggestions "
                "(suggestion_id, run_id, row_id, workspace_id, source_record_version, stale, suggestion_json, suggestion_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    stored_suggestion.suggestion_id,
                    stored_suggestion.run_id,
                    stored_suggestion.row_id,
                    audit.workspace_id,
                    stored_suggestion.source_record_version,
                    int(stale),
                    suggestion_json,
                    suggestion_hash,
                    stored_suggestion.created_at,
                ),
            )
            self._insert_audit(connection, replace(audit, analysis_id=str(row["analysis_id"])))
            finished_at = _utc_now()
            connection.execute(
                "UPDATE review_suggestion_runs SET status = 'succeeded', suggestion_id = ?, finished_at = ? "
                "WHERE run_id = ? AND workspace_id = ? AND status = 'running'",
                (stored_suggestion.suggestion_id, finished_at, run_id, workspace),
            )
            result_row = self._mutation_row(connection, run_id, workspace)
            if result_row is None:
                raise ReviewError("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "review run was not found")
            result = self._decode_suggestion_run(result_row)
            connection.execute("COMMIT")
            return result
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def fail_suggestion_run(
        self,
        run_id: str,
        workspace_id: str,
        error_code: str,
        retryable: bool,
        audit: AuditEvent,
    ) -> ReviewSuggestionRun:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = self._mutation_row(connection, run_id, workspace)
            if current is None:
                raise ReviewError("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "review run was not found")
            run = self._decode_suggestion_run(current)
            if run.status is RunStatus.SUCCEEDED:
                self._transition_error("succeeded review run cannot fail")
            if run.status is RunStatus.FAILED:
                self._validate_fail_binding(run, current, workspace, error_code, retryable, audit)
                if run.error_code != error_code or run.retryable is not retryable:
                    self._binding_error("persisted review failure binding is invalid")
                connection.execute("COMMIT")
                return run
            if run.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
                self._transition_error("review run cannot fail from this state")
            self._validate_fail_binding(run, current, workspace, error_code, retryable, audit)
            row = connection.execute(
                "SELECT analysis_id FROM fmea_rows WHERE row_id = ? AND workspace_id = ?",
                (run.row_id, workspace),
            ).fetchone()
            if row is None:
                raise ReviewError("FMEA_ROW_NOT_FOUND", "review row was not found")
            finished_at = _utc_now()
            connection.execute(
                "UPDATE review_suggestion_runs SET status = 'failed', error_code = ?, retryable = ?, finished_at = ? "
                "WHERE run_id = ? AND workspace_id = ? AND status IN ('queued', 'running')",
                (error_code, int(retryable), finished_at, run_id, workspace),
            )
            self._insert_audit(
                connection,
                replace(audit, analysis_id=str(row["analysis_id"])),
            )
            result_row = self._mutation_row(connection, run_id, workspace)
            if result_row is None:
                raise ReviewError("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "review run was not found")
            result = self._decode_suggestion_run(result_row)
            connection.execute("COMMIT")
            return result
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def list_suggestions(self, row_id: str, workspace_id: str) -> tuple[ReviewSuggestion, ...]:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT s.* FROM review_suggestions AS s "
                "JOIN fmea_rows AS r ON r.row_id = s.row_id AND r.workspace_id = s.workspace_id "
                "JOIN evidence_packs AS p ON p.pack_id = r.evidence_pack_id AND p.workspace_id = r.workspace_id "
                "WHERE s.row_id = ? AND s.workspace_id = ? AND r.workspace_id = ? AND p.workspace_id = ? "
                "ORDER BY s.created_at, s.suggestion_id",
                (row_id, workspace, workspace, workspace),
            ).fetchall()
            result: list[ReviewSuggestion] = []
            for row in rows:
                suggestion = decode_review_suggestion(
                    cast(str, row["suggestion_json"]),
                    expected_hash=cast(str, row["suggestion_hash"]),
                )
                if (
                    suggestion.suggestion_id != row["suggestion_id"]
                    or suggestion.run_id != row["run_id"]
                    or suggestion.row_id != row["row_id"]
                    or suggestion.source_record_version != row["source_record_version"]
                    or suggestion.stale != bool(row["stale"])
                ):
                    raise ValueError("persisted suggestion identity or hash does not match its columns")
                result.append(suggestion)
            return tuple(result)
        finally:
            connection.close()

    def page_suggestions(
        self,
        row_id: str,
        workspace_id: str,
        *,
        after: tuple[str, str] | None = None,
        limit: int = 50,
    ) -> tuple[ReviewSuggestion, ...]:
        if limit < 1:
            raise ValueError("history page limit must be positive")
        workspace = self._workspace(workspace_id)
        cursor_parameters = (None, None, None, None) if after is None else (
            after[0],
            after[0],
            after[0],
            after[1],
        )
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT s.* FROM review_suggestions AS s "
                "JOIN fmea_rows AS r ON r.row_id = s.row_id AND r.workspace_id = s.workspace_id "
                "JOIN evidence_packs AS p ON p.pack_id = r.evidence_pack_id AND p.workspace_id = r.workspace_id "
                "WHERE s.row_id = ? AND s.workspace_id = ? AND r.workspace_id = ? AND p.workspace_id = ? "
                "AND (? IS NULL OR s.created_at > ? OR (s.created_at = ? AND s.suggestion_id > ?)) "
                "ORDER BY s.created_at, s.suggestion_id LIMIT ?",
                (row_id, workspace, workspace, workspace, *cursor_parameters, limit + 1),
            ).fetchall()
            result: list[ReviewSuggestion] = []
            for row in rows:
                suggestion = decode_review_suggestion(
                    cast(str, row["suggestion_json"]),
                    expected_hash=cast(str, row["suggestion_hash"]),
                )
                if (
                    suggestion.suggestion_id != row["suggestion_id"]
                    or suggestion.run_id != row["run_id"]
                    or suggestion.row_id != row["row_id"]
                    or suggestion.source_record_version != row["source_record_version"]
                    or suggestion.stale != bool(row["stale"])
                ):
                    raise ValueError("persisted suggestion identity or hash does not match its columns")
                result.append(suggestion)
            return tuple(result)
        finally:
            connection.close()

    def list_decisions(self, row_id: str, workspace_id: str) -> tuple[ReviewDecisionRecord, ...]:
        workspace = self._workspace(workspace_id)
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT d.* FROM review_decisions AS d "
                "JOIN fmea_rows AS r ON r.row_id = d.row_id AND r.workspace_id = d.workspace_id "
                "JOIN evidence_packs AS p ON p.pack_id = r.evidence_pack_id AND p.workspace_id = r.workspace_id "
                "WHERE d.row_id = ? AND d.workspace_id = ? AND r.workspace_id = ? AND p.workspace_id = ? "
                "ORDER BY d.record_version, d.created_at, d.decision_id",
                (row_id, workspace, workspace, workspace),
            ).fetchall()
            result: list[ReviewDecisionRecord] = []
            for row in rows:
                decision = decode_review_decision_record(cast(str, row["decision_json"]))
                if (
                    decision.decision_id != row["decision_id"]
                    or decision.row_id != row["row_id"]
                    or decision.previous_record_version != row["previous_record_version"]
                    or decision.record_version != row["record_version"]
                    or decision.actor_id != row["actor_id"]
                    or decision.action.value != row["action"]
                    or decision.reason_code.value != row["reason_code"]
                ):
                    raise ValueError("persisted decision identity does not match its columns")
                result.append(decision)
            return tuple(result)
        finally:
            connection.close()

    def page_decisions(
        self,
        row_id: str,
        workspace_id: str,
        *,
        after: tuple[str, str] | None = None,
        limit: int = 50,
    ) -> tuple[ReviewDecisionRecord, ...]:
        if limit < 1:
            raise ValueError("history page limit must be positive")
        workspace = self._workspace(workspace_id)
        cursor_parameters = (None, None, None, None) if after is None else (
            after[0],
            after[0],
            after[0],
            after[1],
        )
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT d.* FROM review_decisions AS d "
                "JOIN fmea_rows AS r ON r.row_id = d.row_id AND r.workspace_id = d.workspace_id "
                "JOIN evidence_packs AS p ON p.pack_id = r.evidence_pack_id AND p.workspace_id = r.workspace_id "
                "WHERE d.row_id = ? AND d.workspace_id = ? AND r.workspace_id = ? AND p.workspace_id = ? "
                "AND (? IS NULL OR d.created_at > ? OR (d.created_at = ? AND d.decision_id > ?)) "
                "ORDER BY d.created_at, d.decision_id LIMIT ?",
                (row_id, workspace, workspace, workspace, *cursor_parameters, limit + 1),
            ).fetchall()
            result: list[ReviewDecisionRecord] = []
            for row in rows:
                decision = decode_review_decision_record(cast(str, row["decision_json"]))
                if (
                    decision.decision_id != row["decision_id"]
                    or decision.row_id != row["row_id"]
                    or decision.previous_record_version != row["previous_record_version"]
                    or decision.record_version != row["record_version"]
                    or decision.actor_id != row["actor_id"]
                    or decision.action.value != row["action"]
                    or decision.reason_code.value != row["reason_code"]
                ):
                    raise ValueError("persisted decision identity does not match its columns")
                result.append(decision)
            return tuple(result)
        finally:
            connection.close()


__all__ = ["SqliteFmeaRepository"]
