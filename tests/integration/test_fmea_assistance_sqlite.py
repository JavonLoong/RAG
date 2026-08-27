from __future__ import annotations

import json
import sqlite3
from dataclasses import replace

import pytest

from core_domain.fmea.codec import encode_json
from core_domain.fmea.states import ActorType
from fmea_application.assistance_contracts import (
    AssistanceDecision,
    AssistanceDecisionAction,
    AssistanceKind,
    AssistanceSuggestion,
)
from fmea_application.review_contracts import AuditEvent, IdempotencyScope, idempotency_key_hash
from fmea_application.review_errors import ReviewError
from fmea_application.risk_contracts import (
    PreparedAssistanceDecision,
    PreparedAssistanceSuggestion,
    assistance_decision_payload_hash,
    assistance_suggestion_payload_hash,
    canonical_json,
)
from fmea_infrastructure.assistance_repository_sqlite import SqliteAssistanceRepository

HASH = "sha256:" + "a" * 64
UUID_KEY = "00000000-0000-4000-8000-000000000001"


def _scope(actor_id: str, *, key_hash: str = HASH) -> IdempotencyScope:
    return IdempotencyScope("ws-1", actor_id, "fmea.assistance", "/fmea/rows/row-1", key_hash)


def _suggestion(**overrides: object) -> AssistanceSuggestion[object]:
    value = AssistanceSuggestion(
        suggestion_id="suggestion-1",
        kind=AssistanceKind.SCORE_RECOMMENDATION,
        workspace_id="ws-1",
        target_type="fmea_row",
        target_id="row-1",
        target_record_version=1,
        evidence_pack_ids=("pack-1",),
        payload={"score": 9},
        evidence_ids=("ev-1",),
        conflict_ids=(),
        uncertainty=None,
        model_hash=HASH,
        prompt_hash=HASH,
        run_id="run-1",
        trace_id="trace-1",
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        template_id="fuel-combustion-fmea",
        template_version="1.0.0",
        rule_pack_id="fuel-sod-rpn",
        rule_pack_version="1.0.0",
        created_at="2026-01-01T00:00:00Z",
    )
    return replace(value, suggestion_hash=None, **overrides) if overrides else value


def _decision(suggestion: AssistanceSuggestion[object], **overrides: object) -> AssistanceDecision:
    value = AssistanceDecision(
        decision_id="decision-1",
        suggestion_id=suggestion.suggestion_id,
        suggestion_hash=suggestion.suggestion_hash,
        suggestion_record_version=suggestion.record_version,
        target_record_version=suggestion.target_record_version,
        action=AssistanceDecisionAction.ADOPT,
        actor_id="reviewer-1",
        actor_type=ActorType.HUMAN,
        edits=(),
        reason="reviewed",
        idempotency_key=UUID_KEY,
        resulting_resource_identity=("fmea_row", "row-1"),
        created_at="2026-01-01T00:00:00Z",
    )
    return replace(value, **overrides) if overrides else value


def _audit(
    *,
    actor_id: str,
    actor_type: ActorType,
    payload_hash: str,
    decision_id: str | None = None,
    idempotency_key_hash: str = HASH,
    suggestion_id: str = "suggestion-1",
    target_id: str = "row-1",
) -> AuditEvent:
    from core_domain.fmea.value_objects import VersionSet

    return AuditEvent(
        event_id="audit-decision-1" if decision_id else "audit-suggestion-1",
        occurred_at_server="2026-01-01T00:00:00Z",
        workspace_id="ws-1",
        actor_id=actor_id,
        actor_type=actor_type,
        actor_roles=("reviewer",) if actor_type is ActorType.HUMAN else (),
        command="fmea.assistance",
        action=None,
        reason_code=None,
        reason="assistance persistence",
        analysis_id="analysis-1",
        row_id=target_id,
        suggestion_id=suggestion_id,
        decision_id=decision_id,
        expected_record_version=1,
        applied_record_version=None,
        before_hash=None,
        after_hash=None,
        changed_fields=(),
        evidence_ids=("ev-1",),
        evidence_request_targets=(),
        idempotency_key_hash=idempotency_key_hash,
        canonical_payload_hash=payload_hash,
        versions=VersionSet(
            "graphrag.fmea.v1",
            "1.0.0",
            "1.0.0",
            "1.0.0",
            "1.0.0",
            "1.0.0",
            "1.0.0",
            "1.0.0",
            "1.0.0",
            HASH,
        ),
        template_id="fuel-combustion-fmea",
        template_version="1.0.0",
        profile_id="combined",
        profile_version="1.0.0",
        model_manifest=None,
        request_id="request-1",
        trace_id="trace-1",
        retrieval_trace_id="retrieval-1",
    )


def _prepared_suggestion(
    suggestion: AssistanceSuggestion[object] | None = None,
    *,
    scope_value: IdempotencyScope | None = None,
) -> PreparedAssistanceSuggestion:
    value = suggestion or _suggestion()
    scope = scope_value or _scope("model-1")
    payload_hash = assistance_suggestion_payload_hash(scope, value)
    return PreparedAssistanceSuggestion(
        scope=scope,
        payload_hash=payload_hash,
        suggestion=value,
        audit=_audit(
            actor_id="model-1",
            actor_type=ActorType.MODEL,
            payload_hash=payload_hash,
            suggestion_id=value.suggestion_id,
            idempotency_key_hash=scope.key_hash,
            target_id=value.target_id,
        ),
    )


def _prepared_decision(suggestion: AssistanceSuggestion[object]) -> PreparedAssistanceDecision:
    decision = _decision(suggestion)
    scope = _scope("reviewer-1", key_hash=idempotency_key_hash(UUID_KEY))
    payload_hash = assistance_decision_payload_hash(scope, suggestion, decision)
    return PreparedAssistanceDecision(
        scope=scope,
        payload_hash=payload_hash,
        suggestion=suggestion,
        decision=decision,
        audit=_audit(
            actor_id="reviewer-1",
            actor_type=ActorType.HUMAN,
            payload_hash=payload_hash,
            decision_id=decision.decision_id,
            idempotency_key_hash=scope.key_hash,
        ),
    )


@pytest.fixture
def assistance_repository(seeded_review_repository) -> SqliteAssistanceRepository:
    repository = SqliteAssistanceRepository(seeded_review_repository.database_path)
    repository.initialize()
    return repository


def test_suggestion_round_trips_canonically_and_replays_once(assistance_repository) -> None:
    prepared = _prepared_suggestion()
    saved = assistance_repository.save_suggestion(prepared)
    replayed = assistance_repository.save_suggestion(prepared)

    assert saved == prepared.suggestion == replayed
    assert assistance_repository.get_suggestion("suggestion-1", "ws-1") == saved
    assert assistance_repository.get_suggestion("suggestion-1", "ws-2") is None
    with sqlite3.connect(assistance_repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_assistance_suggestions").fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_assistance_audit_events WHERE event_id='audit-suggestion-1'"
        ).fetchone() == (1,)


def test_non_row_scope_suggestion_persists_without_borrowing_an_fmea_row(tmp_path, fixture_pack) -> None:
    assistance_repository = SqliteAssistanceRepository(tmp_path / "scope-only.sqlite3")
    assistance_repository.initialize()
    with sqlite3.connect(assistance_repository.database_path) as connection:
        connection.execute(
            "INSERT INTO evidence_packs(pack_id, workspace_id, pack_hash, pack_json, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                fixture_pack.pack_id,
                fixture_pack.workspace_id,
                fixture_pack.pack_hash,
                encode_json(fixture_pack),
                fixture_pack.created_at,
                fixture_pack.expires_at,
            ),
        )
    suggestion = _suggestion(
        suggestion_id="scope-draft-1",
        kind=AssistanceKind.ANALYSIS_SCOPE_DRAFT,
        target_type="fmea_analysis",
        target_id="analysis-draft-1",
        payload={"system_boundary": "fuel and combustion system"},
    )
    scope = IdempotencyScope(
        "ws-1",
        "model-1",
        "fmea.assistance",
        "/fmea/analyses/analysis-draft-1",
        "sha256:" + "c" * 64,
    )
    with sqlite3.connect(assistance_repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_rows").fetchone() == (0,)

    saved = assistance_repository.save_suggestion(_prepared_suggestion(suggestion, scope_value=scope))

    assert saved == suggestion
    with sqlite3.connect(assistance_repository.database_path) as connection:
        assert connection.execute(
            "SELECT target_type, target_id FROM fmea_assistance_audit_events WHERE event_id='audit-suggestion-1'"
        ).fetchone() == ("fmea_analysis", "analysis-draft-1")


def test_suggestion_rejects_unknown_evidence_and_same_scope_changed_body(assistance_repository) -> None:
    prepared = _prepared_suggestion()
    assistance_repository.save_suggestion(prepared)

    bad_evidence = _suggestion(suggestion_id="suggestion-2", evidence_ids=("missing",))
    with pytest.raises(ReviewError, match="evidence"):
        assistance_repository.save_suggestion(
            _prepared_suggestion(bad_evidence, scope_value=_scope("model-1", key_hash="sha256:" + "c" * 64))
        )

    changed = _suggestion(suggestion_id="suggestion-2", payload={"score": 8})
    changed_scope = prepared.scope
    changed_prepared = _prepared_suggestion(changed, scope_value=changed_scope)
    with pytest.raises(ReviewError) as captured:
        assistance_repository.save_suggestion(changed_prepared)
    assert captured.value.code == "FMEA_IDEMPOTENCY_CONFLICT"


def test_human_decision_round_trips_replays_and_keeps_suggestion_unapplied(assistance_repository) -> None:
    suggestion = assistance_repository.save_suggestion(_prepared_suggestion())
    prepared = _prepared_decision(suggestion)

    saved = assistance_repository.append_decision(prepared)
    replayed = assistance_repository.append_decision(prepared)

    assert saved == prepared.decision == replayed
    assert assistance_repository.get_decision("decision-1", "ws-1") == saved
    assert assistance_repository.get_decision("decision-1", "ws-2") is None
    assert assistance_repository.replay_decision(prepared.scope, prepared.payload_hash) == saved
    assert assistance_repository.get_suggestion("suggestion-1", "ws-1").applied is False


def test_decision_rejects_stale_target_and_rolls_back_if_audit_insert_fails(
    assistance_repository, seeded_review_repository, monkeypatch
) -> None:
    suggestion = assistance_repository.save_suggestion(_prepared_suggestion())
    with sqlite3.connect(assistance_repository.database_path) as connection:
        connection.execute("UPDATE fmea_rows SET record_version=2 WHERE row_id='row-1'")
    with pytest.raises(ReviewError):
        assistance_repository.append_decision(_prepared_decision(suggestion))

    # Restore a fresh database state for the transaction rollback injection.
    monkeypatch.setattr(
        assistance_repository,
        "_insert_audit",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("injected")),
    )
    with sqlite3.connect(assistance_repository.database_path) as connection:
        connection.execute("UPDATE fmea_rows SET record_version=1 WHERE row_id='row-1'")
    with pytest.raises(ReviewError):
        assistance_repository.append_decision(_prepared_decision(suggestion))
    with sqlite3.connect(assistance_repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_assistance_decisions").fetchone() == (0,)


def test_tampered_noncanonical_suggestion_fails_closed(assistance_repository) -> None:
    assistance_repository.save_suggestion(_prepared_suggestion())
    with sqlite3.connect(assistance_repository.database_path) as connection:
        connection.execute("DROP TRIGGER fmea_assistance_suggestions_no_update")
        connection.execute(
            "UPDATE fmea_assistance_suggestions SET payload_json=? WHERE suggestion_id='suggestion-1'",
            ('{\"score\": 9}',),
        )
    with pytest.raises(ReviewError):
        assistance_repository.get_suggestion("suggestion-1", "ws-1")


def test_ordinary_decision_read_rejects_tampered_result_identity(assistance_repository) -> None:
    suggestion = assistance_repository.save_suggestion(_prepared_suggestion())
    assistance_repository.append_decision(_prepared_decision(suggestion))
    with sqlite3.connect(assistance_repository.database_path) as connection:
        connection.execute("DROP TRIGGER fmea_assistance_decisions_no_update")
        connection.execute(
            "UPDATE fmea_assistance_decisions SET resulting_resource_id='row-2' WHERE decision_id='decision-1'"
        )

    with pytest.raises(ReviewError):
        assistance_repository.get_decision("decision-1", "ws-1")


def test_ordinary_decision_read_rejects_tampered_audit_json(assistance_repository) -> None:
    suggestion = assistance_repository.save_suggestion(_prepared_suggestion())
    assistance_repository.append_decision(_prepared_decision(suggestion))
    with sqlite3.connect(assistance_repository.database_path) as connection:
        connection.execute("DROP TRIGGER fmea_assistance_audit_events_no_update")
        event_json = connection.execute(
            "SELECT event_json FROM fmea_assistance_audit_events WHERE event_id='audit-decision-1'"
        ).fetchone()[0]
        event = json.loads(event_json)
        event["reason"] = "tampered but still valid"
        connection.execute(
            "UPDATE fmea_assistance_audit_events SET event_json=? WHERE event_id='audit-decision-1'",
            (canonical_json(event),),
        )

    with pytest.raises(ReviewError):
        assistance_repository.get_decision("decision-1", "ws-1")


def test_ordinary_decision_read_recomputes_business_payload_hash(assistance_repository) -> None:
    suggestion = assistance_repository.save_suggestion(_prepared_suggestion())
    assistance_repository.append_decision(_prepared_decision(suggestion))
    with sqlite3.connect(assistance_repository.database_path) as connection:
        connection.execute("DROP TRIGGER fmea_assistance_decisions_no_update")
        body_json = connection.execute(
            "SELECT decision_json FROM fmea_assistance_decisions WHERE decision_id='decision-1'"
        ).fetchone()[0]
        body = json.loads(body_json)
        body["reason"] = "tampered but still valid"
        connection.execute(
            "UPDATE fmea_assistance_decisions SET reason=?, decision_json=? WHERE decision_id='decision-1'",
            (body["reason"], canonical_json(body)),
        )

    with pytest.raises(ReviewError):
        assistance_repository.get_decision("decision-1", "ws-1")


def test_ordinary_decision_read_requires_completed_idempotency_record(assistance_repository) -> None:
    suggestion = assistance_repository.save_suggestion(_prepared_suggestion())
    prepared = _prepared_decision(suggestion)
    assistance_repository.append_decision(prepared)
    with sqlite3.connect(assistance_repository.database_path) as connection:
        connection.execute("DELETE FROM idempotency_records WHERE scope_key=?", (prepared.scope.scope_key,))

    with pytest.raises(ReviewError):
        assistance_repository.get_decision("decision-1", "ws-1")
