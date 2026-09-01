from __future__ import annotations

import sqlite3
from pathlib import Path

from fmea_infrastructure.propagation_repository_sqlite import SqlitePropagationRepository


def test_propagation_migration_is_additive_and_creates_required_schema(tmp_path: Path) -> None:
    repository = SqlitePropagationRepository(tmp_path / "fmea.sqlite3")
    repository.initialize()

    connection = sqlite3.connect(repository.database_path)
    try:
        versions = connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'fmea_propagation_%'"
            )
        }
    finally:
        connection.close()

        assert [row[0] for row in versions] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert {
        "fmea_propagation_topology_snapshots",
        "fmea_propagation_runs",
        "fmea_propagation_graph_revisions",
        "fmea_propagation_edges",
        "fmea_propagation_paths",
        "fmea_propagation_edge_decisions",
        "fmea_propagation_graph_decisions",
        "fmea_propagation_issues",
    }.issubset(tables)


def test_confirm_graph_commits_decisions_revision_audit_and_outbox(repository, prepared_graph_confirmation) -> None:
    prepared = prepared_graph_confirmation(
        edge_actions=(
            ("edge-1", "accept"),
            ("edge-2", "reject"),
        )
    )

    result = repository.commit_graph_review(prepared)

    assert result.graph.status.value == "confirmed"
    assert [edge.edge_id for edge in result.graph.edges] == ["edge-1"]
    replayed = repository.replay_graph_review(prepared.scope, prepared.payload_hash)
    assert replayed is not None
    assert replayed.replayed is True
    assert replayed.graph == result.graph
    assert replayed.decision_id == result.decision_id
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_propagation_edge_decisions").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM fmea_propagation_graph_decisions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] >= 1
        assert connection.execute("SELECT COUNT(*) FROM fmea_outbox_events").fetchone()[0] == 1
