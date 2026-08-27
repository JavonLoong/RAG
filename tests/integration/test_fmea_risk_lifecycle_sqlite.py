from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from core_domain.fmea.states import ActorType, RiskStatus
from fmea_application.review_errors import ReviewError
from fmea_application.risk_contracts import (
    PreparedRiskConfirmation,
    PreparedRiskInvalidation,
    PreparedRiskProposal,
    PreparedRiskRejection,
    canonical_json,
    outbox_payload_hash,
    risk_confirmation_payload_hash,
    risk_invalidation_payload_hash,
    risk_proposal_payload_hash,
    risk_rejection_payload_hash,
)
from fmea_infrastructure.domain_pack_registry import load_domain_pack_manifest, load_scoring_rule_pack
from fmea_infrastructure.risk_repository_sqlite import SqliteRiskRepository
from tests.unit.test_fmea_risk_repository_contract import (
    assessment as _base_assessment,
)
from tests.unit.test_fmea_risk_repository_contract import audit, scope
from tests.unit.test_fmea_risk_repository_contract import proposal as _base_proposal

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOMAIN_SOURCE = (_REPO_ROOT / "domain_packs" / "fuel-combustion" / "manifest.yaml").read_bytes()
_RULE_SOURCE = (
    _REPO_ROOT / "domain_packs" / "fuel-combustion" / "scoring" / "sod-rpn-1.0.0.yaml"
).read_bytes()


def proposal():
    value = _base_proposal()
    return replace(
        value,
        dimensions=tuple(replace(dimension, evidence_ids=("ev-1",)) for dimension in value.dimensions),
    )


def assessment(status: RiskStatus, **overrides: object):
    value = _base_assessment(status, **overrides)
    dimensions = tuple(replace(dimension, evidence_ids=("ev-1",)) for dimension in value.dimensions)
    derived = None if value.derived is None else replace(value.derived, evidence_ids=("ev-1",))
    return replace(value, dimensions=dimensions, derived=derived)


def prepared_proposal():
    proposal_value = proposal()
    assessment_value = assessment(RiskStatus.PROPOSED)
    prepared_scope = scope("model-1")
    payload_hash = risk_proposal_payload_hash(prepared_scope, proposal_value, assessment_value)
    return PreparedRiskProposal(
        scope=prepared_scope,
        payload_hash=payload_hash,
        proposal=proposal_value,
        assessment=assessment_value,
        audit=replace(
            audit(actor_id="model-1", actor_type=ActorType.MODEL, canonical_hash=payload_hash),
            evidence_ids=("ev-1",),
        ),
    )


def _confirmation() -> PreparedRiskConfirmation:
    previous = assessment(RiskStatus.PROPOSED)
    confirmed = assessment(RiskStatus.CONFIRMED, version=2)
    decision_id = "risk-decision-confirm-1"
    prepared_scope = scope("reviewer-1")
    payload_hash = risk_confirmation_payload_hash(
        prepared_scope, proposal(), previous, confirmed, 1, decision_id
    )
    return PreparedRiskConfirmation(
        scope=prepared_scope,
        payload_hash=payload_hash,
        proposal=proposal(),
        previous_assessment=previous,
        assessment=confirmed,
        expected_assessment_version=1,
        decision_id=decision_id,
        audit=replace(
            audit(
                actor_id="reviewer-1",
                actor_type=ActorType.HUMAN,
                decision_id=decision_id,
                canonical_hash=payload_hash,
            ),
            event_id="audit-confirm-1",
        ),
    )


def _rejection(actor_id: str = "reviewer-1") -> PreparedRiskRejection:
    previous = assessment(RiskStatus.PROPOSED)
    reviewed = assessment(RiskStatus.REVIEWED, version=2)
    decision_id = "risk-decision-reject-1"
    prepared_scope = scope(actor_id)
    payload_hash = risk_rejection_payload_hash(
        prepared_scope, proposal(), previous, reviewed, 1, decision_id
    )
    return PreparedRiskRejection(
        scope=prepared_scope,
        payload_hash=payload_hash,
        proposal=proposal(),
        previous_assessment=previous,
        assessment=reviewed,
        expected_assessment_version=1,
        decision_id=decision_id,
        audit=replace(
            audit(
                actor_id=actor_id,
                actor_type=ActorType.HUMAN,
                decision_id=decision_id,
                canonical_hash=payload_hash,
            ),
            event_id="audit-reject-1",
        ),
    )


def _confirmed_invalidation() -> PreparedRiskInvalidation:
    previous = assessment(RiskStatus.CONFIRMED, version=2)
    invalidated = assessment(
        RiskStatus.INVALIDATED,
        assessment_id="assessment-2",
        version=3,
        source_version=1,
    )
    decision_id = "risk-decision-invalidate-1"
    prepared_scope = scope("risk-system")
    payload_hash = risk_invalidation_payload_hash(
        prepared_scope, previous, invalidated, 2, decision_id
    )
    return PreparedRiskInvalidation(
        scope=prepared_scope,
        payload_hash=payload_hash,
        previous_assessment=previous,
        assessment=invalidated,
        expected_assessment_version=2,
        decision_id=decision_id,
        audit=replace(
            audit(
                actor_id="risk-system",
                actor_type=ActorType.SYSTEM,
                decision_id=decision_id,
                canonical_hash=payload_hash,
            ),
            event_id="audit-invalidate-1",
        ),
    )


def register_pack_snapshots(repository: SqliteRiskRepository) -> None:
    repository.register_pack_snapshots(
        "ws-1",
        load_domain_pack_manifest(_DOMAIN_SOURCE),
        _DOMAIN_SOURCE,
        load_scoring_rule_pack(_RULE_SOURCE),
        _RULE_SOURCE,
        "2026-01-01T00:00:00Z",
    )


@pytest.fixture
def risk_repository(seeded_review_repository) -> SqliteRiskRepository:
    repository = SqliteRiskRepository(seeded_review_repository.database_path)
    repository.initialize()
    register_pack_snapshots(repository)
    return repository


def test_proposal_and_proposed_assessment_save_atomically_and_replay(risk_repository) -> None:
    prepared = prepared_proposal()

    saved = risk_repository.save_proposal(prepared)
    replayed = risk_repository.save_proposal(prepared)

    assert saved == prepared.assessment == replayed
    assert risk_repository.get_current_assessment("row-1", "ws-1") == saved
    assert risk_repository.get_current_assessment("row-1", "ws-2") is None
    assert risk_repository.list_outbox_events("assessment-1", "ws-1")[0].event_type == "risk.proposed"
    with sqlite3.connect(risk_repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_risk_proposals").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM fmea_risk_assessments").fetchone() == (1,)


def test_proposal_requires_registered_pack_snapshots(seeded_review_repository) -> None:
    repository = SqliteRiskRepository(seeded_review_repository.database_path)
    repository.initialize()

    with pytest.raises(ReviewError) as captured:
        repository.save_proposal(prepared_proposal())

    assert captured.value.code == "FMEA_REVIEW_ACTION_INVALID"


def test_proposal_outbox_rejects_a_self_consistent_forged_initial_assessment(risk_repository) -> None:
    prepared = prepared_proposal()
    risk_repository.save_proposal(prepared)
    event_id = f"outbox-proposal-{prepared.proposal.proposal_id}"
    with sqlite3.connect(risk_repository.database_path) as connection:
        payload = json.loads(
            connection.execute(
                "SELECT payload_json FROM fmea_outbox_events WHERE event_id=?",
                (event_id,),
            ).fetchone()[0]
        )
        payload["assessment"]["updated_at"] = "2026-01-01T00:00:01Z"
        connection.execute("DROP TRIGGER fmea_outbox_events_no_update")
        connection.execute(
            "UPDATE fmea_outbox_events SET payload_json=?, payload_hash=? WHERE event_id=?",
            (canonical_json(payload), outbox_payload_hash(payload), event_id),
        )

    with pytest.raises(ReviewError):
        risk_repository.list_outbox_events(prepared.assessment.assessment_id, prepared.assessment.workspace_id)


def test_confirmation_commits_audit_decision_outbox_and_replays(risk_repository) -> None:
    risk_repository.save_proposal(prepared_proposal())
    prepared = _confirmation()

    result = risk_repository.commit_confirmation(prepared)
    replay = risk_repository.replay_confirmation(prepared.scope, prepared.payload_hash)

    assert result.assessment == prepared.assessment
    assert replay == replace(result, replayed=True)
    assert risk_repository.get_current_assessment("row-1", "ws-1") == prepared.assessment
    events = risk_repository.list_outbox_events("assessment-1", "ws-1")
    assert tuple(event.event_type for event in events) == ("risk.proposed", "risk.confirmed")


def test_confirmed_assessment_rejects_a_late_proposed_outbox_event(risk_repository) -> None:
    proposal_prepared = prepared_proposal()
    risk_repository.save_proposal(proposal_prepared)
    risk_repository.commit_confirmation(_confirmation())

    with sqlite3.connect(risk_repository.database_path) as connection, pytest.raises(
        sqlite3.IntegrityError, match="matching lifecycle chain"
    ):
        connection.execute(
            "INSERT INTO fmea_outbox_events "
            "(event_id, workspace_id, aggregate_type, aggregate_id, event_type, status, payload_json, "
            "payload_hash, idempotency_scope, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "outbox-late-proposal",
                "ws-1",
                "risk_assessment",
                proposal_prepared.assessment.assessment_id,
                "risk.proposed",
                "pending",
                "{}",
                "sha256:" + "a" * 64,
                proposal_prepared.scope.scope_key,
                "2026-01-01T00:00:01Z",
            ),
        )


def test_stale_confirmation_rolls_back_decision_audit_outbox_and_idempotency(risk_repository) -> None:
    risk_repository.save_proposal(prepared_proposal())
    prepared = _confirmation()
    risk_repository.reject(_rejection("reviewer-2"))
    with sqlite3.connect(risk_repository.database_path) as connection:
        before = (
            connection.execute("SELECT COUNT(*) FROM fmea_risk_decisions").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM fmea_outbox_events").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0],
        )

    with pytest.raises(ReviewError) as captured:
        risk_repository.commit_confirmation(prepared)

    assert captured.value.code == "FMEA_RISK_VERSION_CONFLICT"
    with sqlite3.connect(risk_repository.database_path) as connection:
        after = (
            connection.execute("SELECT COUNT(*) FROM fmea_risk_decisions").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM fmea_outbox_events").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0],
        )
        assert after == before
        assert connection.execute(
            "SELECT COUNT(*) FROM idempotency_records WHERE scope_key=?",
            (prepared.scope.scope_key,),
        ).fetchone() == (0,)


def test_rejection_and_confirmed_invalidation_emit_events_without_rewriting_history(risk_repository) -> None:
    second_path = risk_repository.database_path.with_name("confirmed-invalidation.sqlite3")
    with sqlite3.connect(risk_repository.database_path) as source, sqlite3.connect(second_path) as target:
        source.backup(target)

    risk_repository.save_proposal(prepared_proposal())
    rejected = risk_repository.reject(_rejection())
    assert rejected.status is RiskStatus.REVIEWED
    assert risk_repository.list_outbox_events("assessment-1", "ws-1")[-1].event_type == "risk.rejected"

    second = SqliteRiskRepository(second_path)
    second.initialize()
    second.save_proposal(prepared_proposal())
    confirmed = second.commit_confirmation(_confirmation())
    invalidated = second.invalidate(_confirmed_invalidation())

    assert confirmed.assessment.status is RiskStatus.CONFIRMED
    assert invalidated.status is RiskStatus.INVALIDATED
    with sqlite3.connect(second_path) as connection:
        assert connection.execute(
            "SELECT status FROM fmea_risk_assessments WHERE assessment_id='assessment-1'"
        ).fetchone() == ("confirmed",)
        assert connection.execute(
            "SELECT status FROM fmea_risk_assessments WHERE assessment_id='assessment-2'"
        ).fetchone() == ("invalidated",)


def test_reviewed_assessment_can_be_rejected_again_with_a_new_version(risk_repository) -> None:
    risk_repository.save_proposal(prepared_proposal())
    first = risk_repository.reject(_rejection())
    second_assessment = assessment(RiskStatus.REVIEWED, version=3)
    decision_id = "risk-decision-reject-2"
    prepared_scope = scope("reviewer-1")
    prepared_scope = replace(prepared_scope, key_hash="sha256:" + "c" * 64)
    payload_hash = risk_rejection_payload_hash(
        prepared_scope, proposal(), first, second_assessment, 2, decision_id
    )
    prepared = PreparedRiskRejection(
        scope=prepared_scope,
        payload_hash=payload_hash,
        proposal=proposal(),
        previous_assessment=first,
        assessment=second_assessment,
        expected_assessment_version=2,
        decision_id=decision_id,
        audit=replace(
            audit(
                actor_id="reviewer-1",
                actor_type=ActorType.HUMAN,
                decision_id=decision_id,
                canonical_hash=payload_hash,
            ),
            event_id="audit-reject-2",
            expected_record_version=2,
            applied_record_version=3,
            idempotency_key_hash=prepared_scope.key_hash,
        ),
    )

    assert risk_repository.reject(prepared) == second_assessment
    assert risk_repository.get_current_assessment("row-1", "ws-1") == second_assessment
    assert tuple(
        event.event_type for event in risk_repository.list_outbox_events("assessment-1", "ws-1")
    ) == ("risk.proposed", "risk.rejected", "risk.rejected")


def test_same_scope_changed_proposal_is_an_idempotency_conflict(risk_repository) -> None:
    prepared = prepared_proposal()
    risk_repository.save_proposal(prepared)
    changed_proposal = replace(prepared.proposal, reason="changed proposal body")
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


@pytest.mark.parametrize(
    "target",
    ["decision", "decision_column", "outbox", "outbox_chain", "idempotency", "idempotency_metadata"],
)
def test_confirmation_replay_and_outbox_reads_fail_closed_on_tamper(risk_repository, target: str) -> None:
    risk_repository.save_proposal(prepared_proposal())
    prepared = _confirmation()
    risk_repository.commit_confirmation(prepared)
    with sqlite3.connect(risk_repository.database_path) as connection:
        if target == "decision":
            connection.execute("DROP TRIGGER fmea_risk_decisions_no_update")
            connection.execute(
                "UPDATE fmea_risk_decisions SET decision_json='{}' WHERE decision_id=?",
                (prepared.decision_id,),
            )
        elif target == "decision_column":
            connection.execute("DROP TRIGGER fmea_risk_decisions_no_update")
            connection.execute(
                "UPDATE fmea_risk_decisions SET actor_id='attacker' WHERE decision_id=?",
                (prepared.decision_id,),
            )
        elif target in {"outbox", "outbox_chain"}:
            connection.execute("DROP TRIGGER fmea_outbox_events_no_update")
            if target == "outbox":
                connection.execute(
                    "UPDATE fmea_outbox_events SET payload_json='{}' WHERE event_id=?",
                    (f"outbox-{prepared.decision_id}",),
                )
            else:
                payload = json.loads(
                    connection.execute(
                        "SELECT payload_json FROM fmea_outbox_events WHERE event_id=?",
                        (f"outbox-{prepared.decision_id}",),
                    ).fetchone()[0]
                )
                payload["assessment"]["updated_at"] = "2026-01-01T00:00:01Z"
                connection.execute(
                    "UPDATE fmea_outbox_events SET payload_json=?, payload_hash=? WHERE event_id=?",
                    (
                        canonical_json(payload),
                        outbox_payload_hash(payload),
                        f"outbox-{prepared.decision_id}",
                    ),
                )
        elif target == "idempotency":
            connection.execute(
                "UPDATE idempotency_records SET response_json='{}' WHERE scope_key=?",
                (prepared.scope.scope_key,),
            )
        else:
            connection.execute(
                "UPDATE idempotency_records SET status_code=200 WHERE scope_key=?",
                (prepared.scope.scope_key,),
            )

    with pytest.raises(ReviewError):
        if target in {"decision", "decision_column", "idempotency", "idempotency_metadata"}:
            risk_repository.replay_confirmation(prepared.scope, prepared.payload_hash)
        else:
            risk_repository.list_outbox_events("assessment-1", "ws-1")


def test_malformed_derived_json_fails_closed_even_with_matching_assessment_hash(risk_repository) -> None:
    risk_repository.save_proposal(prepared_proposal())
    prepared = _confirmation()
    risk_repository.commit_confirmation(prepared)
    with sqlite3.connect(risk_repository.database_path) as connection:
        decision_body = json.loads(
            connection.execute(
                "SELECT decision_json FROM fmea_risk_decisions WHERE decision_id=?",
                (prepared.decision_id,),
            ).fetchone()[0]
        )
        assessment_body = decision_body["assessment"]
        assessment_body["derived"]["occurrence"] = "not-an-integer"
        connection.execute("DROP TRIGGER fmea_risk_assessments_confirmed_no_update")
        connection.execute("DROP TRIGGER fmea_risk_assessments_transition_guard")
        connection.execute("DROP TRIGGER fmea_risk_assessments_requires_decision")
        connection.execute(
            "UPDATE fmea_risk_assessments SET derived_json=?, assessment_hash=? WHERE assessment_id=?",
            (
                canonical_json(assessment_body["derived"]),
                "sha256:" + sha256(canonical_json(assessment_body).encode("utf-8")).hexdigest(),
                prepared.assessment.assessment_id,
            ),
        )

    with pytest.raises(ReviewError):
        risk_repository.get_current_assessment("row-1", "ws-1")
