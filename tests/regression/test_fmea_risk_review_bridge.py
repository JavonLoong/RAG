"""Real review version changes must not rewrite immutable generation provenance."""

from __future__ import annotations

import sqlite3
from dataclasses import fields, replace

import pytest

from fmea_application.review_contracts import ReviewSourceSnapshot, decode_review_source_snapshot, encode_review_json
from fmea_application.review_errors import ReviewError
from fmea_infrastructure.risk_repository_sqlite import SqliteRiskRepository
from scripts.run_fmea_full_acceptance import run_candidate_review_risk


def test_reviewed_row_can_be_scored_without_rewriting_origin_snapshot(tmp_path):
    result = run_candidate_review_risk(tmp_path)
    assert "blocked_step" not in result.evidence
    confirmed = result.evidence["risk_records"][-1]
    assert confirmed["status"] == "confirmed"
    assert confirmed["source_record_version"] == 2
    with sqlite3.connect(tmp_path / "fmea.sqlite3") as connection:
        source_version, current_version = connection.execute(
            "SELECT s.source_record_version, r.record_version FROM review_source_snapshots s "
            "JOIN fmea_rows r ON r.row_id=s.row_id AND r.workspace_id=s.workspace_id"
        ).fetchone()
    assert source_version == 1
    assert current_version == 2


@pytest.mark.parametrize("mutation", ["future_origin", "version_column", "hash_column"])
def test_origin_snapshot_remains_integrity_checked_after_review(tmp_path, mutation):
    result = run_candidate_review_risk(tmp_path)
    risk = result.evidence["risk_records"][-1]
    database = tmp_path / "fmea.sqlite3"
    repository = SqliteRiskRepository(database)
    proposal = repository.get_proposal(risk["proposal_id"], risk["workspace_id"])
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        # Corruption injection in this test-owned temporary database only.
        # Normal writes are already rejected by this immutability trigger.
        connection.execute("DROP TRIGGER review_source_snapshots_no_update")
        if mutation == "future_origin":
            stored = connection.execute("SELECT snapshot_json FROM review_source_snapshots").fetchone()[0]
            source = decode_review_source_snapshot(stored)
            body = {field.name: getattr(source, field.name) for field in fields(source) if field.name != "source_hash"}
            body["source_record_version"] = 3
            forged = ReviewSourceSnapshot.build(**body)
            connection.execute(
                "UPDATE review_source_snapshots SET source_record_version=?, source_hash=?, snapshot_json=?",
                (3, forged.source_hash, encode_review_json(forged)),
            )
        elif mutation == "version_column":
            connection.execute("UPDATE review_source_snapshots SET source_record_version=2")
        else:
            connection.execute("UPDATE review_source_snapshots SET source_hash=?", ("sha256:" + "0" * 64,))
        with pytest.raises(ReviewError, match="integrity"):
            repository._validate_sources(connection, proposal)


def test_historical_risk_read_cannot_reference_a_future_row_version(tmp_path):
    result = run_candidate_review_risk(tmp_path)
    risk = result.evidence["risk_records"][-1]
    repository = SqliteRiskRepository(tmp_path / "fmea.sqlite3")
    proposal = repository.get_proposal(risk["proposal_id"], risk["workspace_id"])
    future = replace(proposal, source_record_version=3, assistance_suggestion_id=None)
    with sqlite3.connect(tmp_path / "fmea.sqlite3") as connection:
        connection.row_factory = sqlite3.Row
        with pytest.raises(ReviewError) as failure:
            repository._validate_sources(connection, future, require_current_version=False)
        with pytest.raises(ReviewError) as foreign_failure:
            repository._validate_sources(connection, replace(proposal, workspace_id="foreign-workspace"), require_current_version=False)
    assert failure.value.code == "FMEA_RISK_VERSION_CONFLICT"
    assert foreign_failure.value.code == "FMEA_ROW_NOT_FOUND"
