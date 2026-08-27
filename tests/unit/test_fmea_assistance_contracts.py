from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from core_domain.fmea.states import ActorType
from fmea_application.assistance_contracts import (
    AssistanceDecision,
    AssistanceDecisionAction,
    AssistanceKind,
    AssistanceRequest,
    AssistanceSuggestion,
)


def _suggestion(*, applied: bool = False) -> AssistanceSuggestion[dict[str, object]]:
    return AssistanceSuggestion(
        suggestion_id="suggestion-1",
        kind=AssistanceKind.SCORE_RECOMMENDATION,
        workspace_id="ws-1",
        target_type="fmea_row",
        target_id="row-1",
        target_record_version=3,
        evidence_pack_ids=("pack-1",),
        payload={"severity": 7},
        evidence_ids=("ev-1",),
        conflict_ids=(),
        uncertainty="low",
        model_hash="a" * 64,
        prompt_hash="b" * 64,
        run_id="run-1",
        trace_id="trace-1",
        applied=applied,
    )


def test_assistance_is_immutable_unapplied_and_version_bound() -> None:
    suggestion = _suggestion()
    assert suggestion.applied is False
    assert suggestion.target_record_version == 3
    assert suggestion.evidence_pack_ids == ("pack-1",)
    with pytest.raises(FrozenInstanceError):
        suggestion.applied = True


def test_assistance_suggestion_cannot_be_created_as_applied() -> None:
    with pytest.raises(ValueError, match="applied"):
        _suggestion(applied=True)


def test_assistance_decision_is_human_and_binds_exact_suggestion() -> None:
    suggestion = _suggestion()
    decision = AssistanceDecision(
        decision_id="decision-1",
        suggestion_id=suggestion.suggestion_id,
        suggestion_hash=suggestion.suggestion_hash,
        suggestion_record_version=suggestion.record_version,
        target_record_version=suggestion.target_record_version,
        action=AssistanceDecisionAction.ADOPT,
        actor_id="reviewer-1",
        actor_type=ActorType.HUMAN,
        edits=(),
        reason="accepted after review",
        idempotency_key="idempotency-1",
        resulting_resource_identity=("fmea_row", "row-1"),
    )
    assert decision.action is AssistanceDecisionAction.ADOPT
    assert decision.actor_type is ActorType.HUMAN

    with pytest.raises(ValueError, match="human actor"):
        AssistanceDecision(
            decision_id="decision-2",
            suggestion_id=suggestion.suggestion_id,
            suggestion_hash=suggestion.suggestion_hash,
            suggestion_record_version=suggestion.record_version,
            target_record_version=suggestion.target_record_version,
            action=AssistanceDecisionAction.ADOPT,
            actor_id="model-1",
            actor_type=ActorType.MODEL,
            edits=(),
            reason="model cannot adopt",
            idempotency_key="idempotency-2",
            resulting_resource_identity=None,
        )


def test_assistance_request_normalizes_version_bound_identities() -> None:
    request = AssistanceRequest(
        request_id="request-1",
        kind=AssistanceKind.REVIEW_SUMMARY,
        workspace_id="ws-1",
        target_type="fmea_row",
        target_id="row-1",
        target_record_version=3,
        evidence_pack_ids=["pack-1"],
        payload={"focus": "missing evidence"},
    )
    assert request.evidence_pack_ids == ("pack-1",)
