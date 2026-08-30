from __future__ import annotations

import pytest
from fmea_governance_fixtures import make_blocked_readiness_report, make_governance_actor

from core_domain.fmea.states import ActorType


def _implementation():
    try:
        from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
        from fmea_application.governance_assistance_service import GovernanceAssistanceService
    except ModuleNotFoundError as exc:
        pytest.fail(f"Task 2 production implementation is missing: {exc}")
    return AssistanceKind, AssistanceSuggestion, GovernanceAssistanceService


def test_model_readiness_checklist_cannot_clear_a_blocker():
    AssistanceKind, AssistanceSuggestion, GovernanceAssistanceService = _implementation()
    report = make_blocked_readiness_report()
    actor = make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset())
    suggestion = GovernanceAssistanceService().suggest_readiness_checklist(report, actor)
    assert isinstance(suggestion, AssistanceSuggestion)
    assert suggestion.kind is AssistanceKind.APPROVAL_READINESS_CHECKLIST
    assert suggestion.applied is False
    assert suggestion.payload["ready"] is False
    assert report["ready"] is False


def test_readiness_assistance_is_offline_and_immutable_by_default():
    _, _, GovernanceAssistanceService = _implementation()
    report = make_blocked_readiness_report()
    actor = make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset())
    suggestion = GovernanceAssistanceService().suggest_readiness_checklist(report, actor)
    assert suggestion.model_hash == suggestion.model_hash.lower()
    assert len(suggestion.model_hash) == 64
    assert len(suggestion.prompt_hash) == 64
    with pytest.raises((AttributeError, TypeError)):
        suggestion.applied = True  # type: ignore[misc]


def test_human_actor_cannot_be_used_as_model_readiness_assistance():
    _, _, GovernanceAssistanceService = _implementation()
    human = make_governance_actor(actor_type=ActorType.HUMAN)
    with pytest.raises(ValueError, match="model actor"):
        GovernanceAssistanceService().suggest_readiness_checklist(make_blocked_readiness_report(), human)
