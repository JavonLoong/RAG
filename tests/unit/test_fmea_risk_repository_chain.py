from __future__ import annotations

import json
import sqlite3
from dataclasses import replace

import pytest

from core_domain.fmea.states import RiskStatus
from fmea_application.review_errors import ReviewError
from fmea_application.risk_contracts import (
    PreparedRiskConfirmation,
    PreparedRiskProposal,
    risk_confirmation_payload_hash,
    risk_proposal_payload_hash,
)
from fmea_infrastructure.assistance_repository_sqlite import SqliteAssistanceRepository
from fmea_infrastructure.risk_repository_sqlite import SqliteRiskRepository, _object_hash
from tests.integration.test_fmea_assistance_sqlite import _prepared_suggestion, _suggestion
from tests.integration.test_fmea_risk_lifecycle_sqlite import (
    _confirmation,
    _rejection,
    assessment,
    prepared_proposal,
    register_pack_snapshots,
)


@pytest.fixture
def risk_repository(seeded_review_repository) -> SqliteRiskRepository:
    repository = SqliteRiskRepository(seeded_review_repository.database_path)
    repository.initialize()
    register_pack_snapshots(repository)
    return repository


def _service_confirmation() -> PreparedRiskConfirmation:
    base = _confirmation()
    scope = replace(
        base.scope,
        command="fmea.risk.confirm",
        resource_path="/fmea/rows/row-1/risk-confirmations",
    )
    payload_hash = risk_confirmation_payload_hash(
        scope,
        base.proposal,
        base.previous_assessment,
        base.assessment,
        base.expected_assessment_version,
        base.decision_id,
    )
    return replace(
        base,
        scope=scope,
        payload_hash=payload_hash,
        audit=replace(base.audit, command=scope.command, canonical_payload_hash=payload_hash),
    )


@pytest.mark.parametrize("target", ["assessment", "audit", "idempotency", "outbox"])
def test_get_proposal_validates_every_persisted_lifecycle_link(
    risk_repository: SqliteRiskRepository, target: str
) -> None:
    prepared = prepared_proposal()
    risk_repository.save_proposal(prepared)

    with sqlite3.connect(risk_repository.database_path) as connection:
        if target == "assessment":
            connection.execute("DROP TRIGGER fmea_risk_assessments_transition_guard")
            connection.execute("DROP TRIGGER fmea_risk_assessments_requires_decision")
            connection.execute(
                "UPDATE fmea_risk_assessments SET assessment_hash=? WHERE assessment_id=?",
                ("sha256:" + "c" * 64, prepared.assessment.assessment_id),
            )
        elif target == "audit":
            connection.execute("DROP TRIGGER audit_events_no_update")
            connection.execute(
                "UPDATE audit_events SET canonical_payload_hash=? WHERE event_id=?",
                ("sha256:" + "c" * 64, prepared.audit.event_id),
            )
        elif target == "idempotency":
            connection.execute(
                "UPDATE idempotency_records SET response_json='{}' WHERE scope_key=?",
                (prepared.scope.scope_key,),
            )
        else:
            connection.execute("DROP TRIGGER fmea_outbox_events_no_update")
            connection.execute(
                "UPDATE fmea_outbox_events SET payload_json='{}' WHERE event_id=?",
                (f"outbox-proposal-{prepared.proposal.proposal_id}",),
            )

    with pytest.raises(ReviewError):
        risk_repository.get_proposal(prepared.proposal.proposal_id, prepared.proposal.workspace_id)


def test_get_proposal_validates_linked_assistance_suggestion_chain(
    risk_repository: SqliteRiskRepository, seeded_review_repository
) -> None:
    assistance = SqliteAssistanceRepository(seeded_review_repository.database_path)
    pack = risk_repository.get_evidence_pack("pack-1", "ws-1")
    assert pack is not None
    suggestion_prepared = _prepared_suggestion(
        _suggestion(
            payload={
                "dimensions": [],
                "reason": "bounded risk proposal",
                "uncertainty": None,
                "binding": {
                    "operating_context_hash": "a" * 64,
                    "evidence_pack_hash": pack.pack_hash.removeprefix("sha256:"),
                    "model_template_id": "fmea-risk-proposal",
                    "model_template_version": "1.0.0",
                },
            }
        )
    )
    suggestion = assistance.save_suggestion(suggestion_prepared)
    base = prepared_proposal()
    proposal = replace(base.proposal, assistance_suggestion_id=suggestion.suggestion_id)
    assessment_value = replace(base.assessment, assistance_suggestion_id=suggestion.suggestion_id)
    payload_hash = risk_proposal_payload_hash(base.scope, proposal, assessment_value)
    prepared = PreparedRiskProposal(
        scope=base.scope,
        payload_hash=payload_hash,
        proposal=proposal,
        assessment=assessment_value,
        audit=replace(base.audit, canonical_payload_hash=payload_hash, suggestion_id=suggestion.suggestion_id),
    )
    risk_repository.save_proposal(prepared)

    with sqlite3.connect(risk_repository.database_path) as connection:
        connection.execute("DROP TRIGGER fmea_assistance_audit_events_no_update")
        connection.execute(
            "UPDATE fmea_assistance_audit_events SET canonical_payload_hash=? WHERE event_id=?",
            ("sha256:" + "c" * 64, suggestion_prepared.audit.event_id),
        )

    with pytest.raises(ReviewError):
        risk_repository.get_proposal(proposal.proposal_id, proposal.workspace_id)


def test_get_proposal_rejects_a_rehashed_assessment_without_a_decision_chain(
    risk_repository: SqliteRiskRepository,
) -> None:
    prepared = prepared_proposal()
    risk_repository.save_proposal(prepared)
    forged = replace(
        prepared.assessment,
        status=RiskStatus.REVIEWED,
        record_version=2,
        updated_at="2026-01-01T00:00:01Z",
    )
    with sqlite3.connect(risk_repository.database_path) as connection:
        connection.execute("DROP TRIGGER fmea_risk_assessments_transition_guard")
        connection.execute("DROP TRIGGER fmea_risk_assessments_requires_decision")
        connection.execute(
            "UPDATE fmea_risk_assessments SET status=?, record_version=?, updated_at=?, assessment_hash=? "
            "WHERE assessment_id=?",
            (
                forged.status.value,
                forged.record_version,
                forged.updated_at,
                _object_hash(forged),
                forged.assessment_id,
            ),
        )

    with pytest.raises(ReviewError):
        risk_repository.get_proposal(prepared.proposal.proposal_id, prepared.proposal.workspace_id)


def test_replay_rejection_returns_typed_assessment_and_validates_transition_chain(
    risk_repository: SqliteRiskRepository,
) -> None:
    risk_repository.save_proposal(prepared_proposal())
    prepared = _rejection()
    saved = risk_repository.reject(prepared)

    replayed = risk_repository.replay_rejection(prepared.scope, prepared.payload_hash)

    assert replayed == saved

    with sqlite3.connect(risk_repository.database_path) as connection:
        connection.execute("DROP TRIGGER fmea_risk_decisions_no_update")
        connection.execute(
            "UPDATE fmea_risk_decisions SET decision_json=? WHERE decision_id=?",
            (json.dumps({}, separators=(",", ":")), prepared.decision_id),
        )

    with pytest.raises(ReviewError):
        risk_repository.replay_rejection(prepared.scope, prepared.payload_hash)


def test_get_assessment_version_reconstructs_and_validates_historical_assessment(
    risk_repository: SqliteRiskRepository,
) -> None:
    risk_repository.save_proposal(prepared_proposal())
    risk_repository.commit_confirmation(_service_confirmation())

    historical = risk_repository.get_assessment_version("row-1", "ws-1", 1)

    assert historical == assessment(RiskStatus.PROPOSED)
    assert historical != risk_repository.get_current_assessment("row-1", "ws-1")


def test_get_assessment_version_fails_closed_when_historical_transition_is_tampered(
    risk_repository: SqliteRiskRepository,
) -> None:
    risk_repository.save_proposal(prepared_proposal())
    prepared = _service_confirmation()
    risk_repository.commit_confirmation(prepared)
    with sqlite3.connect(risk_repository.database_path) as connection:
        connection.execute("DROP TRIGGER fmea_risk_decisions_no_update")
        connection.execute(
            "UPDATE fmea_risk_decisions SET actor_id=? WHERE decision_id=?",
            ("attacker", prepared.decision_id),
        )

    with pytest.raises(ReviewError):
        risk_repository.get_assessment_version("row-1", "ws-1", 1)
