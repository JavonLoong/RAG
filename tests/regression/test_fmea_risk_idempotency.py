from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from fmea_application.review_errors import ReviewError
from fmea_application.risk_contracts import risk_proposal_payload_hash
from fmea_infrastructure.risk_repository_sqlite import SqliteRiskRepository
from tests.integration.test_fmea_risk_lifecycle_sqlite import (
    _confirmation,
    prepared_proposal,
    register_pack_snapshots,
)


@pytest.fixture
def risk_repository(seeded_review_repository) -> SqliteRiskRepository:
    repository = SqliteRiskRepository(seeded_review_repository.database_path)
    repository.initialize()
    register_pack_snapshots(repository)
    return repository


def _counts(repository: SqliteRiskRepository) -> tuple[int, int, int, int]:
    with sqlite3.connect(repository.database_path) as connection:
        return tuple(
            connection.execute(query).fetchone()[0]
            for query in (
                "SELECT COUNT(*) FROM fmea_risk_decisions",
                "SELECT COUNT(*) FROM fmea_outbox_events",
                "SELECT COUNT(*) FROM audit_events",
                "SELECT COUNT(*) FROM idempotency_records",
            )
        )


def test_completed_confirmation_replay_has_no_duplicate_side_effects(risk_repository) -> None:
    risk_repository.save_proposal(prepared_proposal())
    prepared = _confirmation()
    first = risk_repository.commit_confirmation(prepared)
    before = _counts(risk_repository)

    replay = risk_repository.commit_confirmation(prepared)

    assert replay == replace(first, replayed=True)
    assert _counts(risk_repository) == before


def test_same_proposal_scope_with_changed_payload_conflicts_without_writes(risk_repository) -> None:
    prepared = prepared_proposal()
    risk_repository.save_proposal(prepared)
    before = _counts(risk_repository)
    changed_proposal = replace(prepared.proposal, reason="changed proposal")
    changed_hash = risk_proposal_payload_hash(prepared.scope, changed_proposal, prepared.assessment)
    changed = replace(
        prepared,
        proposal=changed_proposal,
        payload_hash=changed_hash,
        audit=replace(prepared.audit, canonical_payload_hash=changed_hash),
    )

    with pytest.raises(ReviewError) as captured:
        risk_repository.save_proposal(changed)

    assert captured.value.code == "FMEA_IDEMPOTENCY_CONFLICT"
    assert _counts(risk_repository) == before
