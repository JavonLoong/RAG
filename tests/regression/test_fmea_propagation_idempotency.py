from __future__ import annotations

import sqlite3

import pytest

from core_domain.fmea.states import ActorType
from fmea_application.propagation_service import (
    InvalidatePropagationCommand,
    PropagationReviewService,
)
from fmea_application.review_contracts import ActorContext
from fmea_application.review_errors import ReviewError
from tests.fmea_propagation_fixtures import _rule_pack


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
