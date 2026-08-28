from __future__ import annotations

import json
import sqlite3
from dataclasses import replace

import pytest

from core_domain.fmea.states import ActorType, ReviewStatus
from fmea_application.propagation_service import (
    InvalidatePropagationCommand,
    PropagationReviewService,
    propagation_invalidation_payload_hash,
    propagation_review_payload_hash,
)
from fmea_application.review_contracts import ActorContext, encode_review_json
from fmea_application.review_errors import ReviewError
from fmea_application.risk_contracts import canonical_json, outbox_payload_hash
from tests.fmea_propagation_fixtures import _foreign_pack, _graph, _rule_pack, _topology


def _system_propagation_service(repository) -> PropagationReviewService:
    return PropagationReviewService(
        repository,
        assistance_repository=object(),
        topology_port=object(),
        domain_pack_registry=object(),
        propagation_rule_registry=type("Registry", (), {"get": lambda _self, _id, _version: _rule_pack()})(),
        generator=object(),
        clock=lambda: "2026-08-28T00:00:02Z",
    )


def test_graph_review_same_key_replays_exactly_after_repository_restart(tmp_path, prepared_graph_confirmation) -> None:
    from fmea_infrastructure.propagation_repository_sqlite import SqlitePropagationRepository

    path = tmp_path / "fmea.sqlite3"
    repository = SqlitePropagationRepository(path)
    repository.initialize()
    prepared = prepared_graph_confirmation(repository=repository)
    first = repository.commit_graph_review(prepared)

    restarted = SqlitePropagationRepository(path)
    restarted.initialize()

    replayed = restarted.replay_graph_review(prepared.scope, prepared.payload_hash)
    assert replayed is not None
    assert replayed.replayed is True
    assert replayed.graph == first.graph
    assert replayed.decision_id == first.decision_id
    assert replayed.audit_event_id == first.audit_event_id
    assert replayed.outbox_event_id == first.outbox_event_id


def test_graph_review_same_key_different_payload_conflicts_without_writes(
    repository, prepared_graph_confirmation
) -> None:
    prepared = prepared_graph_confirmation(repository=repository)
    repository.commit_graph_review(prepared)
    conflicting = prepared_graph_confirmation(
        repository=repository,
        idempotency_key=prepared.command.idempotency_key,
        reason="different human decision",
    )
    before = repository.count_propagation_records("ws-1")

    with pytest.raises(ReviewError, match="different payload"):
        repository.commit_graph_review(conflicting)

    assert repository.count_propagation_records("ws-1") == before


def test_graph_review_rollback_leaves_no_partial_decision_audit_or_outbox(
    repository, prepared_graph_confirmation, monkeypatch
) -> None:
    prepared = prepared_graph_confirmation(repository=repository)
    monkeypatch.setattr(
        repository, "_insert_outbox", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    with pytest.raises(RuntimeError, match="boom"):
        repository.commit_graph_review(prepared)

    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_propagation_graph_decisions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM fmea_propagation_edge_decisions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM fmea_outbox_events").fetchone()[0] == 0


def test_graph_review_rejects_foreign_workspace_without_writes(repository, prepared_graph_confirmation) -> None:
    prepared = prepared_graph_confirmation(repository=repository, workspace_id="other-workspace")

    with pytest.raises(ReviewError):
        repository.commit_graph_review(prepared)

    assert repository.count_propagation_records("ws-1") == 0


def test_invalidation_replays_before_dependency_reload(repository, prepared_graph_confirmation, monkeypatch) -> None:
    prepared = prepared_graph_confirmation(repository=repository)
    confirmed = repository.commit_graph_review(prepared)
    command = InvalidatePropagationCommand(
        graph_revision_id=confirmed.graph.graph_revision_id,
        expected_graph_record_version=confirmed.graph.record_version,
        changed_evidence_hash="sha256:" + "9" * 64,
        reason="evidence superseded",
        idempotency_key="00000000-0000-4000-8000-000000000402",
    )
    actor = ActorContext("system", ActorType.SYSTEM, frozenset(), "ws-1")
    service = _system_propagation_service(repository)

    first = service.invalidate(command, actor)
    monkeypatch.setattr(
        repository, "get_topology_snapshot", lambda *_args: (_ for _ in ()).throw(RuntimeError("must not reload"))
    )
    replayed = service.invalidate(command, actor)

    assert replayed == first
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_propagation_graph_decisions").fetchone()[0] == 2


def test_sql_constraints_reject_cross_graph_edge_decision(repository, prepared_graph_confirmation) -> None:
    prepared = prepared_graph_confirmation(repository=repository)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO fmea_propagation_edge_decisions "
                "(workspace_id, edge_decision_id, graph_revision_id, decision_id, edge_id, action, actor_id, actor_type, reason, decision_json, idempotency_scope, payload_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "ws-1",
                    "sql-edge-decision",
                    prepared.previous_graph.graph_revision_id,
                    "sql-decision",
                    "not-an-edge-in-this-graph",
                    "accept",
                    "reviewer-1",
                    "human",
                    "crafted",
                    '{"action":"accept","edge_id":"not-an-edge-in-this-graph","reason":"crafted"}',
                    prepared.scope.scope_key,
                    prepared.payload_hash,
                    prepared.audit.occurred_at_server,
                ),
            )


def test_sql_constraints_reject_illegal_graph_transition(repository, prepared_graph_confirmation) -> None:
    prepared = prepared_graph_confirmation(repository=repository)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO fmea_propagation_graph_decisions "
                "(workspace_id, decision_id, previous_graph_revision_id, resulting_graph_revision_id, decision_type, from_status, to_status, expected_graph_version, applied_graph_version, actor_id, actor_type, acknowledged_issue_codes_json, decision_json, idempotency_scope, payload_hash, audit_event_id, outbox_event_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "ws-1",
                    "sql-illegal-transition",
                    prepared.previous_graph.graph_revision_id,
                    prepared.previous_graph.graph_revision_id,
                    "confirm",
                    "confirmed",
                    "proposed",
                    1,
                    2,
                    "reviewer-1",
                    "human",
                    "[]",
                    "{}",
                    prepared.scope.scope_key,
                    prepared.payload_hash,
                    "missing-audit",
                    "missing-outbox",
                    prepared.audit.occurred_at_server,
                ),
            )


def test_sql_constraints_reject_outbox_from_another_workspace(repository, prepared_graph_confirmation) -> None:
    prepared = prepared_graph_confirmation(repository=repository)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO fmea_outbox_events "
            "(event_id, workspace_id, aggregate_type, aggregate_id, event_type, status, payload_json, payload_hash, idempotency_scope, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "sql-foreign-outbox",
                "ws-2",
                "propagation_graph",
                "graph-foreign",
                "propagation.confirmed",
                "pending",
                "{}",
                "sha256:" + "1" * 64,
                prepared.scope.scope_key,
                prepared.audit.occurred_at_server,
            ),
        )
        row_id = connection.execute("SELECT row_id FROM fmea_rows LIMIT 1").fetchone()[0]
        connection.execute(
            "INSERT INTO audit_events "
            "(event_id, row_id, workspace_id, actor_id, actor_type, command, action, suggestion_id, decision_id, expected_record_version, applied_record_version, before_hash, after_hash, canonical_payload_hash, event_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "sql-audit",
                row_id,
                "ws-1",
                "reviewer-1",
                "human",
                "fmea.propagation.review",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                "sha256:" + "1" * 64,
                "{}",
                prepared.audit.occurred_at_server,
            ),
        )
        audit_id = "sql-audit"
        connection.execute(
            "INSERT INTO fmea_propagation_graph_decisions "
            "(workspace_id, decision_id, previous_graph_revision_id, resulting_graph_revision_id, decision_type, from_status, to_status, expected_graph_version, applied_graph_version, actor_id, actor_type, acknowledged_issue_codes_json, decision_json, idempotency_scope, payload_hash, audit_event_id, outbox_event_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ws-1",
                "sql-foreign-outbox-decision",
                prepared.previous_graph.graph_revision_id,
                prepared.previous_graph.graph_revision_id,
                "confirm",
                "proposed",
                "confirmed",
                1,
                2,
                "reviewer-1",
                "human",
                "[]",
                "{}",
                prepared.scope.scope_key,
                prepared.payload_hash,
                audit_id,
                "sql-foreign-outbox",
                prepared.audit.occurred_at_server,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.commit()
        connection.rollback()


def test_repository_rejects_crafted_review_child_even_when_caller_rebinds_hashes(
    repository, prepared_graph_confirmation
) -> None:
    prepared = prepared_graph_confirmation(repository=repository)
    crafted_graph = replace(prepared.graph, paths=())
    object.__setattr__(prepared, "graph", crafted_graph)
    crafted_hash = propagation_review_payload_hash(
        prepared.scope, prepared.command, prepared.previous_graph, crafted_graph, prepared.edge_decisions
    )
    object.__setattr__(prepared, "payload_hash", crafted_hash)
    object.__setattr__(prepared, "audit", replace(prepared.audit, canonical_payload_hash=crafted_hash))
    payload = {
        "graph": json.loads(encode_review_json(crafted_graph)),
        "audit_event_id": prepared.audit.event_id,
        "decision_id": prepared.decision_id,
        "edge_decisions": json.loads(encode_review_json(prepared.edge_decisions)),
    }
    object.__setattr__(
        prepared,
        "outbox",
        replace(prepared.outbox, payload=payload, payload_hash=outbox_payload_hash(payload)),
    )

    with pytest.raises(ReviewError, match="child|graph"):
        repository.commit_graph_review(prepared)


def test_repository_rejects_crafted_invalidation_dependency_even_when_hashes_rebound(
    repository, prepared_graph_invalidation
) -> None:
    prepared = prepared_graph_invalidation
    crafted_graph = replace(prepared.graph, topology_hash="sha256:" + "f" * 64)
    object.__setattr__(prepared, "graph", crafted_graph)
    crafted_hash = propagation_invalidation_payload_hash(
        prepared.scope, prepared.command, prepared.previous_graph, crafted_graph
    )
    object.__setattr__(prepared, "payload_hash", crafted_hash)
    object.__setattr__(prepared, "audit", replace(prepared.audit, canonical_payload_hash=crafted_hash))
    payload = {
        "graph": json.loads(encode_review_json(crafted_graph)),
        "audit_event_id": prepared.audit.event_id,
        "decision_id": prepared.decision_id,
        "edge_decisions": [],
    }
    object.__setattr__(
        prepared,
        "outbox",
        replace(prepared.outbox, payload=payload, payload_hash=outbox_payload_hash(payload)),
    )

    with pytest.raises(ReviewError, match="child|dependency|graph"):
        repository.invalidate(prepared)


def test_repository_rejects_live_rule_and_evidence_drift_against_persisted_snapshots(
    repository, prepared_graph_confirmation, fixture_pack
) -> None:
    prepared = prepared_graph_confirmation(repository=repository)
    object.__setattr__(prepared, "rule_pack", replace(prepared.rule_pack, directions=("drifted",)))
    with pytest.raises(ReviewError, match="snapshot|dependency"):
        repository.commit_graph_review(prepared)

    prepared = prepared_graph_confirmation(
        repository=repository, idempotency_key="00000000-0000-4000-8000-000000000406"
    )
    object.__setattr__(prepared, "evidence_packs", (replace(fixture_pack, acl_scope=("drifted",)),))
    with pytest.raises(ReviewError, match="snapshot|evidence|dependency"):
        repository.commit_graph_review(prepared)


@pytest.mark.parametrize(
    ("table", "trigger", "column", "value"),
    (
        (
            "fmea_propagation_rule_snapshots",
            "fmea_propagation_rule_snapshots_no_update",
            "rule_json",
            "{}",
        ),
        (
            "fmea_propagation_evidence_snapshots",
            "fmea_propagation_evidence_snapshots_no_update",
            "pack_json",
            "{}",
        ),
    ),
)
def test_snapshot_tamper_is_rejected_on_restart_replay(
    repository, prepared_graph_confirmation, table, trigger, column, value
) -> None:
    prepared = prepared_graph_confirmation(repository=repository)
    first = repository.commit_graph_review(prepared)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(f"DROP TRIGGER {trigger}")
        if table.endswith("rule_snapshots"):
            connection.execute(
                f"UPDATE {table} SET {column} = ? WHERE workspace_id = ? AND rule_pack_id = ?",  # noqa: S608
                (value, "ws-1", prepared.rule_pack.rule_pack_id),
            )
        else:
            connection.execute(
                f"UPDATE {table} SET {column} = ? WHERE workspace_id = ? AND pack_id = ?",  # noqa: S608
                (value, "ws-1", prepared.evidence_packs[0].pack_id),
            )
        connection.commit()

    restarted = type(repository)(repository.database_path)
    with pytest.raises(ReviewError, match="storage|snapshot"):
        restarted.replay_graph_review(prepared.scope, prepared.payload_hash)
    assert first.graph.graph_revision_id == prepared.graph.graph_revision_id


def test_same_uuid_is_scoped_independently_across_workspaces(
    tmp_path, repository, fixture_review_bundle, fixture_system_actor, fixture_pack, prepared_graph_confirmation
) -> None:
    from fmea_infrastructure.propagation_repository_sqlite import SqlitePropagationRepository

    workspace_two = "ws-2"
    repository_two = SqlitePropagationRepository(tmp_path / "workspace-two.sqlite3")
    repository_two.initialize()
    bundle_two = replace(
        fixture_review_bundle,
        evidence_pack=_foreign_pack(fixture_pack, workspace_two),
    )
    repository_two.save_review_candidate_bundle(
        bundle_two,
        replace(fixture_system_actor, workspace_id=workspace_two),
    )
    parent_two = _graph(workspace_two)
    topology_two = _topology(workspace_two)
    connection = repository_two._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        repository_two._insert_topology(connection, topology_two)
        repository_two._insert_evidence_snapshot(connection, bundle_two.evidence_pack)
        repository_two._insert_rule_snapshot(connection, _rule_pack(), workspace_two, parent_two.created_at)
        repository_two._insert_graph(connection, parent_two, ("row-1",))
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()

    key = "00000000-0000-4000-8000-000000000407"
    first_prepared = prepared_graph_confirmation(repository=repository, idempotency_key=key)
    first = repository.commit_graph_review(first_prepared)
    second_prepared = prepared_graph_confirmation(
        repository=repository_two, workspace_id=workspace_two, idempotency_key=key
    )
    second = repository_two.commit_graph_review(second_prepared)

    assert first.decision_id != second.decision_id
    assert first.graph.graph_revision_id != second.graph.graph_revision_id
    assert first.audit_event_id != second.audit_event_id
    assert first.outbox_event_id != second.outbox_event_id
    first_replay = repository.replay_graph_review(first_prepared.scope, first_prepared.payload_hash)
    second_replay = repository_two.replay_graph_review(second_prepared.scope, second_prepared.payload_hash)
    assert first_replay is not None and first_replay.replayed is True
    assert second_replay is not None and second_replay.replayed is True
    assert first_replay.graph == first.graph
    assert second_replay.graph == second.graph


def test_review_replay_rejects_corrupted_edge_decision_chain(repository, prepared_graph_confirmation) -> None:
    prepared = prepared_graph_confirmation(repository=repository)
    repository.commit_graph_review(prepared)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("DROP TRIGGER fmea_propagation_edge_decisions_no_update")
        connection.execute(
            "UPDATE fmea_propagation_edge_decisions SET actor_id = ? WHERE workspace_id = ? AND decision_id = ?",
            ("tampered-actor", "ws-1", prepared.decision_id),
        )
        connection.commit()

    with pytest.raises(ReviewError, match="storage"):
        repository.replay_graph_review(prepared.scope, prepared.payload_hash)


def test_review_replay_rejects_corrupted_idempotency_response_chain(repository, prepared_graph_confirmation) -> None:
    prepared = prepared_graph_confirmation(repository=repository)
    repository.commit_graph_review(prepared)
    with sqlite3.connect(repository.database_path) as connection:
        row = connection.execute(
            "SELECT response_json FROM idempotency_records WHERE scope_key = ?",
            (prepared.scope.scope_key,),
        ).fetchone()
        assert row is not None
        response = json.loads(row[0])
        response["workspace_id"] = "tampered-workspace"
        connection.execute(
            "UPDATE idempotency_records SET response_json = ? WHERE scope_key = ?",
            (canonical_json(response), prepared.scope.scope_key),
        )
        connection.commit()

    with pytest.raises(ReviewError, match="storage"):
        repository.replay_graph_review(prepared.scope, prepared.payload_hash)


def test_propagation_proposal_rolls_back_assistance_graph_audit_outbox_and_idempotency(
    repository, fixture_analysis, fixture_row, fixture_pack, monkeypatch
) -> None:
    from fmea_infrastructure.assistance_repository_sqlite import SqliteAssistanceRepository
    from tests.unit.test_fmea_propagation_service import (
        _actor,
        _command,
        _domain_pack,
        _Generator,
        _Registry,
        _suggestion,
        _Topology,
        _topology,
    )
    from tests.unit.test_fmea_propagation_service import (
        _rule_pack as unit_rule_pack,
    )

    analysis = replace(fixture_analysis, analysis_type="fuel_system")
    row = replace(
        fixture_row, analysis_id=analysis.analysis_id, item_id="fuel_pump", review_status=ReviewStatus.ACCEPTED
    )
    service = __import__(
        "fmea_application.propagation_service", fromlist=["PropagationAnalysisService"]
    ).PropagationAnalysisService(
        repository,
        assistance_repository=SqliteAssistanceRepository(repository.database_path),
        topology_port=_Topology(_topology()),
        domain_pack_registry=_Registry(_domain_pack()),
        propagation_rule_registry=_Registry(unit_rule_pack()),
        generator=_Generator(lambda request: _suggestion(request)),
        clock=lambda: "2026-08-28T00:00:01Z",
    )
    monkeypatch.setattr(repository, "get_row", lambda *_args: row)
    monkeypatch.setattr(
        repository, "_insert_outbox", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("outbox failed"))
    )

    with pytest.raises(RuntimeError, match="outbox failed"):
        service.start_analysis(_command(), _actor())

    with sqlite3.connect(repository.database_path) as connection:
        for table in (
            "fmea_assistance_suggestions",
            "fmea_assistance_audit_events",
            "fmea_propagation_runs",
            "fmea_propagation_graph_revisions",
            "fmea_propagation_graph_decisions",
            "audit_events",
            "fmea_outbox_events",
            "idempotency_records",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table  # noqa: S608


def test_propagation_proposal_replays_after_restart_without_generator_or_dependency_reads(
    repository, fixture_analysis, fixture_row, fixture_pack, monkeypatch
) -> None:
    from fmea_application.propagation_service import PropagationAnalysisService
    from fmea_infrastructure.assistance_repository_sqlite import SqliteAssistanceRepository
    from tests.unit.test_fmea_propagation_service import (
        _actor,
        _command,
        _domain_pack,
        _Generator,
        _Registry,
        _suggestion,
        _Topology,
        _topology,
    )
    from tests.unit.test_fmea_propagation_service import (
        _rule_pack as unit_rule_pack,
    )

    row = replace(
        fixture_row, analysis_id=fixture_analysis.analysis_id, item_id="fuel_pump", review_status=ReviewStatus.ACCEPTED
    )
    monkeypatch.setattr(repository, "get_row", lambda *_args: row)

    generator = _Generator(lambda request: _suggestion(request))
    service = PropagationAnalysisService(
        repository,
        assistance_repository=SqliteAssistanceRepository(repository.database_path),
        topology_port=_Topology(_topology()),
        domain_pack_registry=_Registry(_domain_pack()),
        propagation_rule_registry=_Registry(unit_rule_pack()),
        generator=generator,
        clock=lambda: "2026-08-28T00:00:01Z",
    )
    first = service.start_analysis(_command(), _actor())
    assert first.status.value == "succeeded", (
        f"{first.error_code}: {first.error_message}; requests={generator.requests}"
    )

    class _Exploding:
        def generate(self, *_args):
            raise AssertionError("generator invoked on replay")  # noqa: TRY003

        def load_snapshot(self, *_args):
            raise AssertionError("topology loaded on replay")  # noqa: TRY003

    restarted = PropagationAnalysisService(
        repository,
        assistance_repository=object(),
        topology_port=_Exploding(),
        domain_pack_registry=_Exploding(),
        propagation_rule_registry=_Exploding(),
        generator=_Exploding(),
    )
    replayed = restarted.start_analysis(_command(), _actor())
    assert replayed == first

    with pytest.raises(ReviewError, match="different payload"):
        restarted.start_analysis(_command(max_edges=39), _actor())
