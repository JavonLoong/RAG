from __future__ import annotations

import sqlite3

from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository

EXPECTED_TABLES = {
    "fmea_domain_packs",
    "fmea_scoring_rule_packs",
    "fmea_assistance_suggestions",
    "fmea_assistance_decisions",
    "fmea_risk_proposals",
    "fmea_risk_assessments",
    "fmea_risk_decisions",
    "fmea_outbox_events",
}

EXPECTED_TRIGGERS = {
    "fmea_domain_packs_no_update",
    "fmea_domain_packs_no_delete",
    "fmea_scoring_rule_packs_no_update",
    "fmea_scoring_rule_packs_no_delete",
    "fmea_assistance_suggestions_no_update",
    "fmea_assistance_suggestions_no_delete",
    "fmea_assistance_decisions_no_update",
    "fmea_assistance_decisions_no_delete",
    "fmea_risk_proposals_no_update",
    "fmea_risk_proposals_no_delete",
    "fmea_risk_assessments_confirmed_no_update",
    "fmea_risk_assessments_confirmed_no_delete",
    "fmea_risk_decisions_no_update",
    "fmea_risk_decisions_no_delete",
    "fmea_outbox_events_no_update",
    "fmea_outbox_events_no_delete",
}


def test_risk_migration_is_hash_managed_idempotent_and_has_required_schema(tmp_path) -> None:
    path = tmp_path / "fmea.sqlite3"
    repository = SqliteFmeaRepository(path)
    repository.initialize()
    repository.initialize()

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert tables >= EXPECTED_TABLES
        assert connection.execute(
            "SELECT filename FROM schema_migrations WHERE version = 3"
        ).fetchone() == ("003_fmea_risk_closure.sql",)
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 3"
        ).fetchone() == (1,)

        triggers = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
        }
        assert triggers >= EXPECTED_TRIGGERS

        schema_sql = "\n".join(
            row[0]
            for row in connection.execute(
                "SELECT sql FROM sqlite_master WHERE type IN ('table', 'index', 'trigger') AND sql IS NOT NULL"
            )
        )
        for fragment in (
            "workspace_id TEXT NOT NULL",
            "content_hash TEXT NOT NULL",
            "status TEXT NOT NULL",
            "record_version INTEGER NOT NULL",
            "payload_hash TEXT NOT NULL",
            "CHECK (actor_type = 'human')",
            "UNIQUE (workspace_id, suggestion_id, suggestion_record_version)",
            "UNIQUE (workspace_id, row_id, record_version)",
        ):
            assert fragment in schema_sql


def test_confirmed_assessment_trigger_does_not_block_proposed_transition(tmp_path) -> None:
    path = tmp_path / "fmea.sqlite3"
    SqliteFmeaRepository(path).initialize()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO fmea_risk_assessments "
            "(assessment_id, workspace_id, row_id, source_record_version, evidence_pack_id, "
            "domain_pack_id, domain_pack_version, rule_pack_id, rule_pack_version, status, "
            "dimensions_json, derived_json, proposal_id, assistance_suggestion_id, "
            "confirmer_actor_id, invalidated_reason, record_version, assessment_hash, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "assessment-1",
                "ws-1",
                "row-1",
                1,
                "pack-1",
                "fuel-combustion",
                "1.0.0",
                "fuel-sod-rpn",
                "1.0.0",
                "proposed",
                "[]",
                None,
                "proposal-1",
                None,
                None,
                None,
                1,
                "sha256:" + "a" * 64,
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        connection.execute(
            "UPDATE fmea_risk_assessments SET status = 'confirmed', derived_json = '{}', "
            "confirmer_actor_id = 'reviewer-1', record_version = 2 WHERE assessment_id = ?",
            ("assessment-1",),
        )
