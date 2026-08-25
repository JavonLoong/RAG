from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from fmea_application.review_errors import ReviewError


@pytest.fixture
def sqlite_review_counts():
    allowed_tables = {"review_decisions", "audit_events"}
    count_queries = {
        "review_decisions": "SELECT COUNT(*) FROM review_decisions WHERE row_id = ?",
        "audit_events": "SELECT COUNT(*) FROM audit_events WHERE row_id = ?",
    }

    def count(repository, table: str, row_id: str, command: str | None = None) -> int:
        if table not in allowed_tables:
            raise ValueError("unsupported review count table")  # noqa: TRY003
        connection = sqlite3.connect(f"file:{repository.database_path}?mode=ro", uri=True)
        try:
            sql = count_queries[table]
            parameters: list[str] = [row_id]
            if command is not None:
                sql += " AND command = ?"
                parameters.append(command)
            return int(connection.execute(sql, tuple(parameters)).fetchone()[0])
        finally:
            connection.close()

    return count


def test_completed_replay_returns_original_result_after_version_increment(
    sqlite_review_service,
    seeded_review_repository,
    sqlite_review_counts,
    fixture_human_reviewer,
    fixture_decision_command,
) -> None:
    first = sqlite_review_service.submit_decision(fixture_decision_command, fixture_human_reviewer)
    replay = sqlite_review_service.submit_decision(fixture_decision_command, fixture_human_reviewer)

    assert replay == first
    assert seeded_review_repository.get_row("row-1", "ws-1").record_version == 2
    assert sqlite_review_counts(seeded_review_repository, "review_decisions", "row-1") == 1
    assert sqlite_review_counts(seeded_review_repository, "audit_events", "row-1", command="review.decision") == 1


def test_same_key_different_payload_is_conflict_without_writes(
    sqlite_review_service,
    seeded_review_repository,
    sqlite_review_counts,
    fixture_human_reviewer,
    fixture_decision_command,
) -> None:
    first_row = seeded_review_repository.get_row("row-1", "ws-1")
    sqlite_review_service.submit_decision(fixture_decision_command, fixture_human_reviewer)
    changed = replace(fixture_decision_command, reason="different payload")

    with pytest.raises(ReviewError) as captured:
        sqlite_review_service.submit_decision(changed, fixture_human_reviewer)

    assert captured.value.code == "FMEA_IDEMPOTENCY_CONFLICT"
    assert seeded_review_repository.get_row("row-1", "ws-1").record_version == 2
    assert sqlite_review_counts(seeded_review_repository, "review_decisions", "row-1") == 1
    assert sqlite_review_counts(seeded_review_repository, "audit_events", "row-1", command="review.decision") == 1
    assert first_row is not None


def test_decision_transaction_rolls_back_all_mutable_effects_on_audit_failure(
    sqlite_review_service,
    seeded_review_repository,
    sqlite_review_counts,
    fixture_human_reviewer,
    fixture_decision_command,
    monkeypatch,
) -> None:
    import fmea_infrastructure.repository_sqlite as repository_module

    original_insert_audit = repository_module.SqliteFmeaRepository._insert_audit

    def fail_audit(connection, audit, extra=None):
        raise sqlite3.IntegrityError("injected audit failure")  # noqa: TRY003

    monkeypatch.setattr(repository_module.SqliteFmeaRepository, "_insert_audit", staticmethod(fail_audit))
    with pytest.raises(sqlite3.IntegrityError):
        sqlite_review_service.submit_decision(fixture_decision_command, fixture_human_reviewer)
    monkeypatch.setattr(repository_module.SqliteFmeaRepository, "_insert_audit", original_insert_audit)

    row = seeded_review_repository.get_row("row-1", "ws-1")
    assert row is not None
    assert row.record_version == 1
    assert sqlite_review_counts(seeded_review_repository, "review_decisions", "row-1") == 0
    assert sqlite_review_counts(seeded_review_repository, "audit_events", "row-1", command="review.decision") == 0
