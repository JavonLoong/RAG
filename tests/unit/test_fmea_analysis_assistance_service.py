from __future__ import annotations

import importlib
from dataclasses import replace

import pytest

from core_domain.fmea.states import ActorType
from fmea_application.assistance_contracts import AssistanceKind, AssistanceRequest, AssistanceSuggestion
from fmea_application.review_contracts import ActorContext


def _service_type():
    module = importlib.import_module("fmea_application.analysis_assistance_service")
    return module.AnalysisAssistanceService


class _SuggestionGenerator:
    def __init__(self) -> None:
        self.request = None

    def generate(self, request):
        self.request = request
        return AssistanceSuggestion(
            suggestion_id="scope-suggestion-1",
            kind=AssistanceKind.ANALYSIS_SCOPE_DRAFT,
            workspace_id=request.workspace_id,
            target_type=request.target_type,
            target_id=request.target_id,
            target_record_version=request.target_record_version,
            evidence_pack_ids=request.evidence_pack_ids,
            payload={
                "scope": "fuel delivery to combustor interface",
                "system_boundary": "fuel skid to burner manifold",
                "exclusions": ["plant electrical distribution"],
                "operating_modes": ["startup", "steady_state"],
                "assumptions": ["pressure transmitter is calibrated"],
                "limitations": ["no transient test data"],
            },
            evidence_ids=("ev-1",),
            model_hash="a" * 64,
            prompt_hash="b" * 64,
            run_id="scope-run-1",
            trace_id="scope-trace-1",
            created_at="2026-08-28T00:00:00Z",
        )


class _AssistanceRepository:
    def __init__(self) -> None:
        self.saved = []

    def save_suggestion(self, prepared):
        self.saved.append(prepared)
        return prepared.suggestion

    def get_suggestion(self, suggestion_id: str, workspace_id: str):
        for prepared in self.saved:
            if prepared.suggestion.suggestion_id == suggestion_id and prepared.suggestion.workspace_id == workspace_id:
                return prepared.suggestion
        return None


class _MismatchingSuggestionGenerator(_SuggestionGenerator):
    def generate(self, request):
        suggestion = super().generate(request)
        return replace(suggestion, target_record_version=request.target_record_version + 1)


class _ExtraScopeFieldGenerator(_SuggestionGenerator):
    def generate(self, request):
        return AssistanceSuggestion(
            suggestion_id="scope-suggestion-1",
            kind=AssistanceKind.ANALYSIS_SCOPE_DRAFT,
            workspace_id=request.workspace_id,
            target_type=request.target_type,
            target_id=request.target_id,
            target_record_version=request.target_record_version,
            evidence_pack_ids=request.evidence_pack_ids,
            payload={"scope": "bounded", "derived_risk": 108},
            evidence_ids=("ev-1",),
            model_hash="a" * 64,
            prompt_hash="b" * 64,
            run_id="scope-run-1",
            trace_id="scope-trace-1",
            created_at="2026-08-28T00:00:00Z",
        )


def _request() -> AssistanceRequest[object]:
    return AssistanceRequest(
        request_id="scope-request-1",
        kind=AssistanceKind.ANALYSIS_SCOPE_DRAFT,
        workspace_id="ws-1",
        target_type="fmea_analysis",
        target_id="analysis-1",
        target_record_version=1,
        evidence_pack_ids=("pack-1",),
        payload={"analysis_type": "design_fmea", "lifecycle_stage": "draft"},
        idempotency_key="00000000-0000-4000-8000-000000000004",
    )


def _model_actor() -> ActorContext:
    return ActorContext("model-1", ActorType.MODEL, frozenset(), "ws-1")


def test_scope_suggestion_is_unapplied_and_never_creates_canonical_analysis() -> None:
    service = _service_type()(
        _SuggestionGenerator(),
        _AssistanceRepository(),
        clock=lambda: "2026-08-28T00:00:00Z",
        id_factory=lambda prefix: f"{prefix}-1",
    )
    request = _request()
    actor = _model_actor()

    suggestion = service.suggest_scope(request, actor)

    assert suggestion.kind is AssistanceKind.ANALYSIS_SCOPE_DRAFT
    assert suggestion.applied is False


def test_scope_suggestion_rejects_changed_target_version() -> None:
    service = _service_type()(_MismatchingSuggestionGenerator(), _AssistanceRepository())

    with pytest.raises(Exception) as captured:
        service.suggest_scope(_request(), _model_actor())

    assert getattr(captured.value, "code", None) == "FMEA_MODEL_SUGGESTION_INVALID"


def test_scope_suggestion_rejects_derived_risk_fields() -> None:
    service = _service_type()(_ExtraScopeFieldGenerator(), _AssistanceRepository())

    with pytest.raises(Exception) as captured:
        service.suggest_scope(_request(), _model_actor())

    assert getattr(captured.value, "code", None) == "FMEA_MODEL_SUGGESTION_INVALID"


def test_authenticated_workspace_can_read_persisted_scope_suggestion() -> None:
    repository = _AssistanceRepository()
    service = _service_type()(_SuggestionGenerator(), repository)
    suggestion = service.suggest_scope(_request(), _model_actor())
    human = ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1")

    assert service.get(suggestion.suggestion_id, human) is suggestion
    with pytest.raises(Exception) as captured:
        service.get(suggestion.suggestion_id, ActorContext("other", ActorType.HUMAN, frozenset(), "ws-2"))
    assert getattr(captured.value, "code", None) == "FMEA_REVIEW_SUGGESTION_NOT_FOUND"
