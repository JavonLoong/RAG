from __future__ import annotations

import importlib

import pytest

from core_domain.fmea.states import ActorType
from fmea_application.assistance_contracts import AssistanceDecisionAction, AssistanceKind, AssistanceSuggestion
from fmea_application.review_contracts import ActorContext
from fmea_application.review_errors import ReviewError


def _types():
    module = importlib.import_module("fmea_application.assistance_service")
    return module.AssistanceDecisionService, module.DecideAssistanceCommand, module.AssistanceHandlerResult


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
        self.reservations = {}

    def get_suggestion(self, suggestion_id: str, workspace_id: str):
        if suggestion_id == self.suggestion.suggestion_id and workspace_id == self.suggestion.workspace_id:
            return self.suggestion
        return None

    def append_decision(self, prepared):
        assert self.reservations[prepared.scope.scope_key] == (
            prepared.reservation_hash,
            prepared.decision.decision_id,
        )
        self.decisions.append(prepared)
        return prepared.decision

    def get_decision(self, decision_id: str, workspace_id: str):
        for prepared in self.decisions:
            if prepared.decision.decision_id == decision_id and workspace_id == self.suggestion.workspace_id:
                return prepared.decision
        return None

    def reserve_decision(self, scope, reservation_hash, decision_id, created_at):
        assert created_at
        existing = self.reservations.get(scope.scope_key)
        if existing is not None and existing != (reservation_hash, decision_id):
            raise ReviewError("FMEA_IDEMPOTENCY_CONFLICT", "reservation key is already bound")
        self.reservations[scope.scope_key] = (reservation_hash, decision_id)
        return self.get_decision(decision_id, scope.workspace_id)

    def replay_decision(self, scope, payload_hash):
        for prepared in self.decisions:
            if prepared.scope == scope and prepared.payload_hash == payload_hash:
                return prepared.decision
        return None


class _FailOnceRepository(_Repository):
    def __init__(self, suggestion: AssistanceSuggestion[object]) -> None:
        super().__init__(suggestion)
        self.append_attempts = 0

    def append_decision(self, prepared):
        self.append_attempts += 1
        if self.append_attempts == 1:
            raise RuntimeError("transient append failure")  # noqa: TRY003
        return super().append_decision(prepared)


def _handlers(calls):
    result_type = importlib.import_module("fmea_application.assistance_service").AssistanceHandlerResult

    def handler(action):
        def invoke(request):
            calls.append((action, request.suggestion.suggestion_id))
            if action in {
                AssistanceDecisionAction.ADOPT,
                AssistanceDecisionAction.PARTIAL_ADOPT,
                AssistanceDecisionAction.EDIT_AND_ADOPT,
            }:
                return result_type(
                    target_type=request.suggestion.target_type,
                    target_id=request.suggestion.target_id,
                    idempotency_key=request.command.idempotency_key,
                    applied_record_version=4,
                )
            return None

        return invoke

    return {
        AssistanceDecisionAction.ADOPT: handler(AssistanceDecisionAction.ADOPT),
        AssistanceDecisionAction.PARTIAL_ADOPT: handler(AssistanceDecisionAction.PARTIAL_ADOPT),
        AssistanceDecisionAction.EDIT_AND_ADOPT: handler(AssistanceDecisionAction.EDIT_AND_ADOPT),
        AssistanceDecisionAction.REJECT: handler(AssistanceDecisionAction.REJECT),
        AssistanceDecisionAction.DEFER: handler(AssistanceDecisionAction.DEFER),
        AssistanceDecisionAction.REQUEST_EVIDENCE: handler(AssistanceDecisionAction.REQUEST_EVIDENCE),
    }


def test_human_assistance_decision_is_version_checked_and_allowlisted() -> None:
    service_type, command_type, _ = _types()
    suggestion = _suggestion()
    repository = _Repository(suggestion)
    service = service_type(
        repository,
        handlers={
            AssistanceDecisionAction.ADOPT: _handlers([])[AssistanceDecisionAction.ADOPT],
            AssistanceDecisionAction.PARTIAL_ADOPT: _handlers([])[AssistanceDecisionAction.PARTIAL_ADOPT],
            AssistanceDecisionAction.EDIT_AND_ADOPT: _handlers([])[AssistanceDecisionAction.EDIT_AND_ADOPT],
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
    service_type, command_type, result_type = _types()
    suggestion = _suggestion()
    repository = _Repository(suggestion)
    calls = []

    def handlers_with_typed_results():
        handlers = _handlers(calls)
        for action in (
            AssistanceDecisionAction.ADOPT,
            AssistanceDecisionAction.PARTIAL_ADOPT,
            AssistanceDecisionAction.EDIT_AND_ADOPT,
        ):
            def invoke(request, action=action):
                calls.append((action, request.suggestion.suggestion_id))
                return result_type(
                    target_type=request.suggestion.target_type,
                    target_id=request.suggestion.target_id,
                    idempotency_key=request.command.idempotency_key,
                    applied_record_version=4,
                )

            handlers[action] = invoke
        return handlers

    service = service_type(repository, handlers=handlers_with_typed_results())

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
    service_type, command_type, result_type = _types()
    suggestion = _suggestion()
    repository = _Repository(suggestion)
    calls = []
    service = service_type(
        repository,
        handlers={
            **_handlers(calls),
            AssistanceDecisionAction.ADOPT: lambda request: (
                calls.append((AssistanceDecisionAction.ADOPT, request.suggestion.suggestion_id))
                or result_type(
                    target_type=request.suggestion.target_type,
                    target_id=request.suggestion.target_id,
                    idempotency_key=request.command.idempotency_key,
                    applied_record_version=4,
                )
            ),
        },
    )
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
    service_type, command_type, result_type = _types()
    suggestion = _suggestion()
    service = service_type(
        _Repository(suggestion),
        handlers={
            **_handlers([]),
            AssistanceDecisionAction.ADOPT: lambda request: result_type(
                target_type=request.suggestion.target_type,
                target_id=request.suggestion.target_id,
                idempotency_key=request.command.idempotency_key,
                applied_record_version=4,
            ),
        },
    )
    command = command_type(
        suggestion_id=suggestion.suggestion_id,
        expected_suggestion_version=2,
        expected_target_record_version=suggestion.target_record_version,
        action=AssistanceDecisionAction.ADOPT,
        idempotency_key="00000000-0000-4000-8000-000000000098",
        reason="stale adoption",
        edits=(),
    )

    with pytest.raises(ReviewError) as model_error:
        service.decide(command, ActorContext("model-1", ActorType.MODEL, frozenset(), "ws-1"))
    assert getattr(model_error.value, "code", None) == "FMEA_REVIEW_FORBIDDEN"

    with pytest.raises(ReviewError) as stale_error:
        service.decide(
            command,
            ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1"),
        )
    assert getattr(stale_error.value, "code", None) == "FMEA_REVIEW_SUGGESTION_STALE"


def test_adopt_handlers_return_typed_target_and_record_applied_version() -> None:
    service_type, command_type, result_type = _types()
    suggestion = _suggestion()
    repository = _Repository(suggestion)
    seen = []

    def handler(request):
        seen.append(request.command.idempotency_key)
        return result_type(
            target_type=request.suggestion.target_type,
            target_id=request.suggestion.target_id,
            idempotency_key=request.command.idempotency_key,
            applied_record_version=7,
        )

    service = service_type(
        repository,
        handlers={
            AssistanceDecisionAction.ADOPT: handler,
            AssistanceDecisionAction.PARTIAL_ADOPT: handler,
            AssistanceDecisionAction.EDIT_AND_ADOPT: handler,
            AssistanceDecisionAction.REJECT: lambda _request: None,
            AssistanceDecisionAction.DEFER: lambda _request: None,
            AssistanceDecisionAction.REQUEST_EVIDENCE: lambda _request: None,
        },
        clock=lambda: "2026-08-28T00:00:01Z",
    )
    command = command_type(
        suggestion_id=suggestion.suggestion_id,
        expected_suggestion_version=suggestion.record_version,
        expected_target_record_version=suggestion.target_record_version,
        action=AssistanceDecisionAction.ADOPT,
        idempotency_key="00000000-0000-4000-8000-000000000201",
        reason="adopt with typed result",
    )

    decision = service.decide(command, ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1"))

    assert decision.resulting_resource_identity == (suggestion.target_type, suggestion.target_id)
    assert repository.decisions[-1].audit.applied_record_version == 7
    assert seen == [command.idempotency_key]


@pytest.mark.parametrize(
    ("target_type", "target_id", "idempotency_key"),
    [
        ("wrong_type", "analysis-1", "00000000-0000-4000-8000-000000000202"),
        ("fmea_analysis", "wrong-id", "00000000-0000-4000-8000-000000000203"),
        ("fmea_analysis", "analysis-1", "00000000-0000-4000-8000-000000000204"),
    ],
)
def test_adopt_handler_result_must_bind_target_and_command_uuid(
    target_type: str, target_id: str, idempotency_key: str
) -> None:
    service_type, command_type, result_type = _types()
    suggestion = _suggestion()
    repository = _Repository(suggestion)
    command = command_type(
        suggestion_id=suggestion.suggestion_id,
        expected_suggestion_version=suggestion.record_version,
        expected_target_record_version=suggestion.target_record_version,
        action=AssistanceDecisionAction.ADOPT,
        idempotency_key="00000000-0000-4000-8000-000000000205",
        reason="reject mismatched handler result",
    )

    def handler(_request):
        return result_type(
            target_type=target_type,
            target_id=target_id,
            idempotency_key=idempotency_key,
            applied_record_version=4,
        )

    service = service_type(
        repository,
        handlers={
            AssistanceDecisionAction.ADOPT: handler,
            AssistanceDecisionAction.PARTIAL_ADOPT: handler,
            AssistanceDecisionAction.EDIT_AND_ADOPT: handler,
            AssistanceDecisionAction.REJECT: lambda _request: None,
            AssistanceDecisionAction.DEFER: lambda _request: None,
            AssistanceDecisionAction.REQUEST_EVIDENCE: lambda _request: None,
        },
    )

    with pytest.raises(ReviewError) as error:
        service.decide(command, ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1"))
    assert getattr(error.value, "code", None) == "FMEA_REVIEW_ACTION_INVALID"
    assert repository.decisions == []


@pytest.mark.parametrize(
    "action",
    [
        AssistanceDecisionAction.REJECT,
        AssistanceDecisionAction.DEFER,
        AssistanceDecisionAction.REQUEST_EVIDENCE,
    ],
)
def test_non_adopt_handlers_cannot_return_canonical_resources(action: AssistanceDecisionAction) -> None:
    service_type, command_type, result_type = _types()
    suggestion = _suggestion()
    repository = _Repository(suggestion)
    command = command_type(
        suggestion_id=suggestion.suggestion_id,
        expected_suggestion_version=suggestion.record_version,
        expected_target_record_version=suggestion.target_record_version,
        action=action,
        idempotency_key=f"00000000-0000-4000-8000-0000000002{10 + list(AssistanceDecisionAction).index(action)}",
        reason=f"{action.value} without resource",
    )
    resource_handler = lambda request: result_type(
        target_type=request.suggestion.target_type,
        target_id=request.suggestion.target_id,
        idempotency_key=request.command.idempotency_key,
        applied_record_version=4,
    )
    service = service_type(
        repository,
        handlers={
            AssistanceDecisionAction.ADOPT: resource_handler,
            AssistanceDecisionAction.PARTIAL_ADOPT: resource_handler,
            AssistanceDecisionAction.EDIT_AND_ADOPT: resource_handler,
            AssistanceDecisionAction.REJECT: resource_handler,
            AssistanceDecisionAction.DEFER: resource_handler,
            AssistanceDecisionAction.REQUEST_EVIDENCE: resource_handler,
        },
    )

    with pytest.raises(ReviewError) as error:
        service.decide(command, ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1"))
    assert getattr(error.value, "code", None) == "FMEA_REVIEW_ACTION_INVALID"
    assert repository.decisions == []


def test_retry_after_append_failure_reuses_the_same_handler_idempotency_uuid() -> None:
    service_type, command_type, result_type = _types()
    suggestion = _suggestion()
    repository = _FailOnceRepository(suggestion)
    handler_keys = []
    canonical_resources = set()

    def handler(request):
        handler_keys.append(request.command.idempotency_key)
        canonical_resources.add(request.command.idempotency_key)
        return result_type(
            target_type=request.suggestion.target_type,
            target_id=request.suggestion.target_id,
            idempotency_key=request.command.idempotency_key,
            applied_record_version=4,
        )

    service = service_type(
        repository,
        handlers={
            AssistanceDecisionAction.ADOPT: handler,
            AssistanceDecisionAction.PARTIAL_ADOPT: handler,
            AssistanceDecisionAction.EDIT_AND_ADOPT: handler,
            AssistanceDecisionAction.REJECT: lambda _request: None,
            AssistanceDecisionAction.DEFER: lambda _request: None,
            AssistanceDecisionAction.REQUEST_EVIDENCE: lambda _request: None,
        },
        clock=lambda: "2026-08-28T00:00:01Z",
    )
    command = command_type(
        suggestion_id=suggestion.suggestion_id,
        expected_suggestion_version=suggestion.record_version,
        expected_target_record_version=suggestion.target_record_version,
        action=AssistanceDecisionAction.ADOPT,
        idempotency_key="00000000-0000-4000-8000-000000000299",
        reason="retry after transient append failure",
    )
    actor = ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1")

    with pytest.raises(RuntimeError, match="transient append failure"):
        service.decide(command, actor)
    decision = service.decide(command, actor)

    assert handler_keys == [command.idempotency_key, command.idempotency_key]
    assert canonical_resources == {command.idempotency_key}
    assert decision.resulting_resource_identity == (suggestion.target_type, suggestion.target_id)
    assert len(repository.decisions) == 1


def test_decision_reservation_is_durable_before_the_adoption_handler_runs() -> None:
    service_type, command_type, result_type = _types()
    suggestion = _suggestion()
    repository = _Repository(suggestion)
    command = command_type(
        suggestion_id=suggestion.suggestion_id,
        expected_suggestion_version=suggestion.record_version,
        expected_target_record_version=suggestion.target_record_version,
        action=AssistanceDecisionAction.ADOPT,
        idempotency_key="00000000-0000-4000-8000-000000000298",
        reason="reserve before canonical write",
    )

    def handler(request):
        assert repository.reservations
        return result_type(
            target_type=request.suggestion.target_type,
            target_id=request.suggestion.target_id,
            idempotency_key=request.command.idempotency_key,
            applied_record_version=4,
        )

    service = service_type(
        repository,
        handlers={
            AssistanceDecisionAction.ADOPT: handler,
            AssistanceDecisionAction.PARTIAL_ADOPT: handler,
            AssistanceDecisionAction.EDIT_AND_ADOPT: handler,
            AssistanceDecisionAction.REJECT: lambda _request: None,
            AssistanceDecisionAction.DEFER: lambda _request: None,
            AssistanceDecisionAction.REQUEST_EVIDENCE: lambda _request: None,
        },
    )

    service.decide(command, ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1"))

    assert len(repository.reservations) == 1
