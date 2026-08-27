from __future__ import annotations

import importlib

import pytest

from core_domain.fmea.states import ActorType
from fmea_application.assistance_contracts import AssistanceDecisionAction, AssistanceKind, AssistanceSuggestion
from fmea_application.review_contracts import ActorContext


def _types():
    module = importlib.import_module("fmea_application.assistance_service")
    return module.AssistanceDecisionService, module.DecideAssistanceCommand


def _suggestion() -> AssistanceSuggestion[object]:
    return AssistanceSuggestion(
        suggestion_id="scope-suggestion-1",
        kind=AssistanceKind.ANALYSIS_SCOPE_DRAFT,
        workspace_id="ws-1",
        target_type="fmea_analysis",
        target_id="analysis-1",
        target_record_version=3,
        evidence_pack_ids=("pack-1",),
        payload={"scope": "bounded"},
        evidence_ids=("ev-1",),
        model_hash="a" * 64,
        prompt_hash="b" * 64,
        run_id="scope-run-1",
        trace_id="scope-trace-1",
        created_at="2026-08-28T00:00:00Z",
    )


class _Repository:
    def __init__(self, suggestion: AssistanceSuggestion[object]) -> None:
        self.suggestion = suggestion
        self.decisions = []

    def get_suggestion(self, suggestion_id: str, workspace_id: str):
        if suggestion_id == self.suggestion.suggestion_id and workspace_id == self.suggestion.workspace_id:
            return self.suggestion
        return None

    def append_decision(self, prepared):
        self.decisions.append(prepared)
        return prepared.decision

    def get_decision(self, decision_id: str, workspace_id: str):
        for prepared in self.decisions:
            if prepared.decision.decision_id == decision_id and workspace_id == self.suggestion.workspace_id:
                return prepared.decision
        return None

    def replay_decision(self, scope, payload_hash):
        for prepared in self.decisions:
            if prepared.scope == scope and prepared.payload_hash == payload_hash:
                return prepared.decision
        return None


def _handlers(calls):
    def handler(action, result):
        def invoke(request):
            calls.append((action, request.suggestion.suggestion_id))
            return result

        return invoke

    return {
        AssistanceDecisionAction.ADOPT: handler(AssistanceDecisionAction.ADOPT, ("fmea_analysis", "analysis-1")),
        AssistanceDecisionAction.PARTIAL_ADOPT: handler(
            AssistanceDecisionAction.PARTIAL_ADOPT, ("fmea_analysis", "analysis-1")
        ),
        AssistanceDecisionAction.EDIT_AND_ADOPT: handler(
            AssistanceDecisionAction.EDIT_AND_ADOPT, ("fmea_analysis", "analysis-1")
        ),
        AssistanceDecisionAction.REJECT: handler(AssistanceDecisionAction.REJECT, None),
        AssistanceDecisionAction.DEFER: handler(AssistanceDecisionAction.DEFER, None),
        AssistanceDecisionAction.REQUEST_EVIDENCE: handler(AssistanceDecisionAction.REQUEST_EVIDENCE, None),
    }


def test_human_assistance_decision_is_version_checked_and_allowlisted() -> None:
    service_type, command_type = _types()
    suggestion = _suggestion()
    repository = _Repository(suggestion)
    service = service_type(
        repository,
        handlers={
            AssistanceDecisionAction.ADOPT: lambda _request: ("fmea_analysis", "analysis-1"),
            AssistanceDecisionAction.PARTIAL_ADOPT: lambda _request: ("fmea_analysis", "analysis-1"),
            AssistanceDecisionAction.EDIT_AND_ADOPT: lambda _request: ("fmea_analysis", "analysis-1"),
            AssistanceDecisionAction.REJECT: lambda _request: None,
            AssistanceDecisionAction.DEFER: lambda _request: None,
            AssistanceDecisionAction.REQUEST_EVIDENCE: lambda _request: None,
        },
        clock=lambda: "2026-08-28T00:00:01Z",
        id_factory=lambda prefix: f"{prefix}-1",
    )
    command = command_type(
        suggestion_id=suggestion.suggestion_id,
        expected_suggestion_version=suggestion.record_version,
        expected_target_record_version=suggestion.target_record_version,
        action=AssistanceDecisionAction.ADOPT,
        idempotency_key="00000000-0000-4000-8000-000000000001",
        reason="human adopted the bounded scope",
        edits=(),
    )

    decision = service.decide(
        command,
        ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1"),
    )

    assert decision.action is AssistanceDecisionAction.ADOPT
    assert decision.actor_type is ActorType.HUMAN
    assert len(repository.decisions) == 1


def test_all_six_actions_use_only_their_typed_allowlisted_handler() -> None:
    service_type, command_type = _types()
    suggestion = _suggestion()
    repository = _Repository(suggestion)
    calls = []
    service = service_type(repository, handlers=_handlers(calls))

    for index, action in enumerate(AssistanceDecisionAction, start=10):
        edits = (("scope", "edited"),) if action in {
            AssistanceDecisionAction.PARTIAL_ADOPT,
            AssistanceDecisionAction.EDIT_AND_ADOPT,
        } else ()
        command = command_type(
            suggestion_id=suggestion.suggestion_id,
            expected_suggestion_version=suggestion.record_version,
            expected_target_record_version=suggestion.target_record_version,
            action=action,
            idempotency_key=f"00000000-0000-4000-8000-0000000000{index:02d}",
            reason=f"human decision {action.value}",
            edits=edits,
        )
        decision = service.decide(
            command,
            ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1"),
        )
        assert decision.action is action

    assert [action for action, _ in calls] == list(AssistanceDecisionAction)


def test_replayed_assistance_decision_does_not_run_handler_again() -> None:
    service_type, command_type = _types()
    suggestion = _suggestion()
    repository = _Repository(suggestion)
    calls = []
    service = service_type(repository, handlers=_handlers(calls))
    command = command_type(
        suggestion_id=suggestion.suggestion_id,
        expected_suggestion_version=suggestion.record_version,
        expected_target_record_version=suggestion.target_record_version,
        action=AssistanceDecisionAction.ADOPT,
        idempotency_key="00000000-0000-4000-8000-000000000099",
        reason="adopt once",
        edits=(),
    )
    actor = ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1")

    first = service.decide(command, actor)
    replay = service.decide(command, actor)

    assert replay == first
    assert len(calls) == 1


def test_assistance_decision_requires_human_reviewer_and_exact_versions() -> None:
    service_type, command_type = _types()
    suggestion = _suggestion()
    service = service_type(_Repository(suggestion), handlers=_handlers([]))
    command = command_type(
        suggestion_id=suggestion.suggestion_id,
        expected_suggestion_version=2,
        expected_target_record_version=suggestion.target_record_version,
        action=AssistanceDecisionAction.ADOPT,
        idempotency_key="00000000-0000-4000-8000-000000000098",
        reason="stale adoption",
        edits=(),
    )

    with pytest.raises(Exception) as model_error:
        service.decide(command, ActorContext("model-1", ActorType.MODEL, frozenset(), "ws-1"))
    assert getattr(model_error.value, "code", None) == "FMEA_REVIEW_FORBIDDEN"

    with pytest.raises(Exception) as stale_error:
        service.decide(
            command,
            ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1"),
        )
    assert getattr(stale_error.value, "code", None) == "FMEA_REVIEW_SUGGESTION_STALE"
