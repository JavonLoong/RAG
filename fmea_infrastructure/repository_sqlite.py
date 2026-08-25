"""Dedicated SQLite persistence for the review-only FMEA workflow."""

# Review persistence exposes stable ValueError failures for malformed stored data.
# ruff: noqa: TRY003, TRY004, TRY300, TRY301

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from typing import NoReturn, cast

from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.policies import validate_row_evidence
from core_domain.fmea.states import (
    ActorType,
    PublicationStatus,
    ReviewStatus,
)
from core_domain.fmea.value_objects import EvidencePack
from fmea_application.review_contracts import (
    ActorContext,
    ReviewCandidateBundle,
    ReviewDecisionRecord,
    ReviewSourceSnapshot,
    ReviewSuggestion,
    decode_review_decision_record,
    decode_review_source_snapshot,
    decode_review_suggestion,
    encode_review_json,
)
from fmea_application.review_errors import ReviewError

_MIGRATION_PATTERN = re.compile(r"^(\d+)_([a-z0-9_]+)\.sql$")
_MAX_BUSY_TIMEOUT_MS = 60_000
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
            "SELECT run_id, row_id, workspace_id, request_hash, idempotency_scope, request_id, trace_id "
            "FROM review_suggestion_runs WHERE status IN ('queued', 'running') ORDER BY run_id"
        ).fetchall()
        for row in rows:
            finished_at = _utc_now()
            event_id = "recovery-" + sha256(str(row["run_id"]).encode("utf-8")).hexdigest()
            event_json = encode_review_json(
                {
                    "event_id": event_id,
                    "command": "review.suggestion.fail",
                    "error_code": "FMEA_REVIEW_RUN_INTERRUPTED",
                    "idempotency_scope": str(row["idempotency_scope"]),
                    "request_hash": str(row["request_hash"]),
                    "request_id": str(row["request_id"]),
                    "run_id": str(row["run_id"]),
                    "trace_id": str(row["trace_id"]),
                }
            )
            connection.execute(
                "UPDATE review_suggestion_runs SET status = 'failed', error_code = ?, retryable = 1, finished_at = ? "
                "WHERE run_id = ?",
                ("FMEA_REVIEW_RUN_INTERRUPTED", finished_at, row["run_id"]),
            )
            connection.execute(
                "INSERT INTO audit_events "
                "(event_id, row_id, workspace_id, actor_id, actor_type, command, canonical_payload_hash, event_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    row["row_id"],
                    row["workspace_id"],
                    "system",
                    ActorType.SYSTEM.value,
                    "review.suggestion.fail",
                    row["request_hash"],
                    event_json,
                    finished_at,
                ),
            )

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
            validate_row_evidence(row, bundle.evidence_pack)
            final_row = replace(
                row,
                review_status=ReviewStatus.SUGGESTED,
                publication_status=PublicationStatus.UNPUBLISHED,
            )
            source = source_by_row.get(row.row_id)
            if source is None:
                raise ValueError(f"missing source snapshot for row {row.row_id}")
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


__all__ = ["SqliteFmeaRepository"]
