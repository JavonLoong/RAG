from __future__ import annotations

from types import SimpleNamespace

import pytest

from core_domain.structured_generation import GenerationRunStatus, GenerationStage, StructuredGenerationError
from fmea_application.assistance_contracts import AssistanceKind, AssistanceRequest
from fmea_application.review_errors import ReviewError
from fmea_infrastructure.analysis_assistance_generator import AnalysisAssistanceGenerator


class _Service:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def run(self, **kwargs):
        return SimpleNamespace(
            status=GenerationRunStatus.SUCCEEDED,
            repair_count=0,
            batch=SimpleNamespace(
                template_id="fmea-analysis-scope",
                template_version="1.0.0",
                evidence_pack_id=kwargs["evidence_pack"].pack_id,
                candidates=(SimpleNamespace(candidate_id="scope-suggestion-1", payload=self.payload),),
            ),
            traces=(
                SimpleNamespace(
                    stage=GenerationStage.CRITIC,
                    model_id="deepseek-v4-pro",
                    prompt_hash="b" * 64,
                    response_hash="a" * 64,
                    error_code=None,
                ),
            ),
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
        payload={"analysis_type": "design_fmea"},
        idempotency_key="00000000-0000-4000-8000-000000000005",
    )


def _payload() -> dict[str, object]:
    return {
        "scope": "fuel delivery",
        "system_boundary": "skid to manifold",
        "exclusions": ["electrical distribution"],
        "operating_modes": ["startup", "steady_state"],
        "assumptions": ["calibrated sensors"],
        "limitations": ["no transient data"],
    }


def test_analysis_generator_returns_scope_only_unapplied_suggestion(fixture_pack) -> None:
    generator = AnalysisAssistanceGenerator(
        _Service(_payload()),
        evidence_loader=lambda pack_id, workspace_id: fixture_pack,
        clock=lambda: "2026-08-28T00:00:00Z",
    )

    suggestion = generator.generate(_request())

    assert suggestion.kind is AssistanceKind.ANALYSIS_SCOPE_DRAFT
    assert suggestion.applied is False
    assert set(suggestion.payload) == set(_payload())


def test_analysis_generator_rejects_non_scope_fields(fixture_pack) -> None:
    payload = _payload()
    payload["risk_status"] = "confirmed"
    generator = AnalysisAssistanceGenerator(
        _Service(payload),
        evidence_loader=lambda pack_id, workspace_id: fixture_pack,
    )

    with pytest.raises(ReviewError) as captured:
        generator.generate(_request())

    assert captured.value.code == "FMEA_MODEL_SUGGESTION_INVALID"


def test_analysis_generator_maps_provider_timeout_to_retryable_safe_error(fixture_pack) -> None:
    class _TimeoutService:
        def run(self, **_kwargs):
            raise StructuredGenerationError("MODEL_TIMEOUT", "secret upstream detail")

    generator = AnalysisAssistanceGenerator(
        _TimeoutService(),
        evidence_loader=lambda pack_id, workspace_id: fixture_pack,
    )

    with pytest.raises(ReviewError) as captured:
        generator.generate(_request())

    assert captured.value.code == "FMEA_MODEL_SUGGESTION_UNAVAILABLE"
    assert captured.value.retryable is True
    assert "secret upstream detail" not in str(captured.value)
