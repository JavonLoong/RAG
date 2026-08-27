from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from hashlib import sha256

import pytest
from fmea_review_fixtures import make_review_decision_record, make_review_source, make_review_suggestion

from fmea_application.review_contracts import encode_review_json
from fmea_application.review_errors import ReviewError
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository


def test_initialize_sets_sqlite_pragmas(tmp_path) -> None:
    repository = SqliteFmeaRepository(tmp_path / "nested" / "fmea.sqlite3", busy_timeout_ms=4321)
    repository.initialize()

    connection = repository._connect()
    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 4321
    finally:
        connection.close()


def test_migrations_are_ordered_and_same_version_hash_replay_is_rejected(tmp_path) -> None:
    path = tmp_path / "fmea.sqlite3"
    SqliteFmeaRepository(path).initialize()

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall() == [(1,), (2,), (3,)]
        connection.execute(
            "UPDATE schema_migrations SET migration_hash = ? WHERE version = 1",
            ("sha256:" + "0" * 64,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="migration"):
        SqliteFmeaRepository(path).initialize()


def test_malformed_persisted_row_json_fails_closed(seeded_review_repository) -> None:
    connection = sqlite3.connect(seeded_review_repository.database_path)
    try:
        connection.execute("UPDATE fmea_rows SET row_json = ? WHERE row_id = ?", ("{not-json", "row-1"))
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="row JSON"):
        seeded_review_repository.get_row("row-1", "ws-1")


def test_evidence_pack_requires_a_workspace_matched_row(seeded_review_repository) -> None:
    connection = sqlite3.connect(seeded_review_repository.database_path)
    try:
        connection.execute("DELETE FROM fmea_rows WHERE row_id = ?", ("row-1",))
        connection.commit()
    finally:
        connection.close()

    assert seeded_review_repository.get_evidence_pack("pack-1", "ws-1") is None


def test_sqlite_history_pages_are_keyset_ordered_bounded_and_cursor_exclusive(seeded_review_repository) -> None:
    timestamp = "2026-08-23T00:00:00Z"
    connection = sqlite3.connect(seeded_review_repository.database_path)
    try:
        for record_version, suffix in enumerate(("b", "a", "c"), start=2):
            suggestion = make_review_suggestion(
                suggestion_id=f"suggestion-{suffix}",
                run_id=f"run-{suffix}",
                created_at=timestamp,
            )
            encoded = encode_review_json(suggestion)
            connection.execute(
                "INSERT INTO review_suggestion_runs "
                "(run_id, row_id, workspace_id, actor_id, source_record_version, status, request_hash, "
                "idempotency_scope, request_id, trace_id, created_at, suggestion_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    suggestion.run_id,
                    "row-1",
                    "ws-1",
                    "system-1",
                    1,
                    "succeeded",
                    "sha256:" + suffix * 64,
                    "scope-" + suffix,
                    "request-" + suffix,
                    "trace-" + suffix,
                    timestamp,
                    suggestion.suggestion_id,
                ),
            )
            connection.execute(
                "INSERT INTO review_suggestions "
                "(suggestion_id, run_id, row_id, workspace_id, source_record_version, stale, suggestion_json, suggestion_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    suggestion.suggestion_id,
                    suggestion.run_id,
                    "row-1",
                    "ws-1",
                    1,
                    0,
                    encoded,
                    "sha256:" + sha256(encoded.encode("utf-8")).hexdigest(),
                    timestamp,
                ),
            )
            decision = make_review_decision_record(
                decision_id=f"decision-{suffix}",
                previous_record_version=record_version - 1,
                record_version=record_version,
                created_at=timestamp,
            )
            decision_json = encode_review_json(decision)
            connection.execute(
                "INSERT INTO review_decisions "
                "(decision_id, row_id, workspace_id, previous_record_version, record_version, actor_id, action, reason_code, decision_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    decision.decision_id,
                    "row-1",
                    "ws-1",
                    decision.previous_record_version,
                    decision.record_version,
                    decision.actor_id,
                    decision.action.value,
                    decision.reason_code.value,
                    decision_json,
                    timestamp,
                ),
            )
        connection.commit()
    finally:
        connection.close()

    first_page = seeded_review_repository.page_suggestions("row-1", "ws-1", after=None, limit=2)
    assert [item.suggestion_id for item in first_page] == ["suggestion-a", "suggestion-b", "suggestion-c"]
    after = (first_page[1].created_at, first_page[1].suggestion_id)
    second_page = seeded_review_repository.page_suggestions("row-1", "ws-1", after=after, limit=2)
    assert [item.suggestion_id for item in second_page] == ["suggestion-c"]
    first_decisions = seeded_review_repository.page_decisions("row-1", "ws-1", after=None, limit=2)
    assert [item.decision_id for item in first_decisions] == ["decision-a", "decision-b", "decision-c"]
    decision_after = (first_decisions[1].created_at, first_decisions[1].decision_id)
    second_decisions = seeded_review_repository.page_decisions(
        "row-1", "ws-1", after=decision_after, limit=2
    )
    assert [item.decision_id for item in second_decisions] == ["decision-c"]


@pytest.mark.parametrize("history_kind", ("suggestion", "decision"))
def test_history_rejects_valid_but_noncanonical_json(
    seeded_review_repository, history_kind: str
) -> None:
    suggestion = make_review_suggestion()
    decision = make_review_decision_record()
    value = suggestion if history_kind == "suggestion" else decision
    canonical_json = encode_review_json(value)
    noncanonical_json = json.dumps(json.loads(canonical_json), ensure_ascii=False, indent=2)

    connection = sqlite3.connect(seeded_review_repository.database_path)
    try:
        if history_kind == "suggestion":
            connection.execute(
                "INSERT INTO review_suggestion_runs "
                "(run_id, row_id, workspace_id, actor_id, source_record_version, status, request_hash, "
                "idempotency_scope, request_id, trace_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "run-1",
                    "row-1",
                    "ws-1",
                    "system-1",
                    1,
                    "queued",
                    "sha256:" + "a" * 64,
                    "scope-1",
                    "request-1",
                    "trace-1",
                    "2026-08-23T00:00:00Z",
                ),
            )
            connection.execute(
                "INSERT INTO review_suggestions "
                "(suggestion_id, run_id, row_id, workspace_id, source_record_version, stale, suggestion_json, suggestion_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    suggestion.suggestion_id,
                    suggestion.run_id,
                    suggestion.row_id,
                    "ws-1",
                    suggestion.source_record_version,
                    int(suggestion.stale),
                    noncanonical_json,
                    "sha256:" + sha256(canonical_json.encode("utf-8")).hexdigest(),
                    suggestion.created_at,
                ),
            )
        else:
            connection.execute(
                "INSERT INTO review_decisions "
                "(decision_id, row_id, workspace_id, previous_record_version, record_version, actor_id, action, reason_code, decision_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    decision.decision_id,
                    decision.row_id,
                    "ws-1",
                    decision.previous_record_version,
                    decision.record_version,
                    decision.actor_id,
                    decision.action.value,
                    decision.reason_code.value,
                    noncanonical_json,
                    decision.created_at,
                ),
            )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="canonical"):
        if history_kind == "suggestion":
            seeded_review_repository.list_suggestions("row-1", "ws-1")
        else:
            seeded_review_repository.list_decisions("row-1", "ws-1")


def test_candidate_validation_has_no_partial_writes(
    tmp_path, fixture_review_bundle, fixture_review_row, fixture_system_actor
) -> None:
    repository = SqliteFmeaRepository(tmp_path / "fmea.sqlite3")
    repository.initialize()
    second_row = replace(fixture_review_row, row_id="row-2", analysis_id="wrong-analysis")
    second_source = make_review_source(row_id="row-2")
    bundle = replace(
        fixture_review_bundle,
        rows=(fixture_review_row, second_row),
        source_snapshots=(fixture_review_bundle.source_snapshots[0], second_source),
    )

    with pytest.raises(ValueError, match="analysis_id"):
        repository.save_review_candidate_bundle(
            bundle,
            actor=fixture_system_actor,
        )

    connection = sqlite3.connect(repository.database_path)
    try:
        counts = connection.execute(
            "SELECT (SELECT count(*) FROM fmea_analyses), "
            "(SELECT count(*) FROM evidence_packs), "
            "(SELECT count(*) FROM fmea_rows), "
            "(SELECT count(*) FROM review_source_snapshots)"
        ).fetchone()
    finally:
        connection.close()
    assert counts == (0, 0, 0, 0)

def test_immutable_workflow_and_source_rows_reject_update_or_delete(seeded_review_repository) -> None:
    connection = sqlite3.connect(seeded_review_repository.database_path)
    try:
        connection.execute(
            "INSERT INTO review_suggestion_runs "
            "(run_id, row_id, workspace_id, actor_id, source_record_version, status, request_hash, "
            "idempotency_scope, request_id, trace_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "run-1",
                "row-1",
                "ws-1",
                "system-1",
                1,
                "queued",
                "sha256:" + "a" * 64,
                "scope-1",
                "request-1",
                "trace-1",
                "2026-08-23T00:00:00Z",
            ),
        )
        connection.execute(
            "INSERT INTO review_suggestions "
            "(suggestion_id, run_id, row_id, workspace_id, source_record_version, stale, suggestion_json, suggestion_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("suggestion-1", "run-1", "row-1", "ws-1", 1, 0, "{}", "sha256:" + "b" * 64, "2026-08-23T00:00:00Z"),
        )
        connection.execute(
            "INSERT INTO review_decisions "
            "(decision_id, row_id, workspace_id, previous_record_version, record_version, actor_id, action, reason_code, decision_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "decision-1",
                "row-1",
                "ws-1",
                1,
                2,
                "reviewer-1",
                "accept",
                "ACCEPT_AS_IS",
                "{}",
                "2026-08-23T00:00:00Z",
            ),
        )
        connection.execute(
            "INSERT INTO audit_events "
            "(event_id, row_id, workspace_id, actor_id, actor_type, command, canonical_payload_hash, event_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "event-1",
                "row-1",
                "ws-1",
                "system-1",
                "system",
                "review.test",
                "sha256:" + "c" * 64,
                "{}",
                "2026-08-23T00:00:00Z",
            ),
        )
        connection.commit()
        for statement, value in (
            ("UPDATE evidence_packs SET created_at = created_at WHERE pack_id = ?", "pack-1"),
            ("DELETE FROM evidence_packs WHERE pack_id = ?", "pack-1"),
            ("UPDATE review_source_snapshots SET created_at = created_at WHERE row_id = ?", "row-1"),
            ("DELETE FROM review_source_snapshots WHERE row_id = ?", "row-1"),
            ("UPDATE review_suggestions SET created_at = created_at WHERE suggestion_id = ?", "suggestion-1"),
            ("DELETE FROM review_suggestions WHERE suggestion_id = ?", "suggestion-1"),
            ("UPDATE review_decisions SET created_at = created_at WHERE decision_id = ?", "decision-1"),
            ("DELETE FROM review_decisions WHERE decision_id = ?", "decision-1"),
            ("UPDATE audit_events SET created_at = created_at WHERE event_id = ?", "event-1"),
            ("DELETE FROM audit_events WHERE event_id = ?", "event-1"),
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(statement, (value,))
    finally:
        connection.close()


def test_identical_candidate_replay_is_idempotent_and_hash_conflict_is_rejected(
    seeded_review_repository, fixture_review_bundle, fixture_system_actor
) -> None:
    replayed = seeded_review_repository.save_review_candidate_bundle(fixture_review_bundle, fixture_system_actor)
    assert replayed[0].row_id == "row-1"

    changed = replace(fixture_review_bundle.rows[0], failure_mode="different failure")
    with pytest.raises(ReviewError) as error:
        seeded_review_repository.save_review_candidate_bundle(
            replace(fixture_review_bundle, rows=(changed,)), fixture_system_actor
        )
    assert error.value.code == "FMEA_IDEMPOTENCY_CONFLICT"
