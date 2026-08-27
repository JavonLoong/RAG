from __future__ import annotations

from types import SimpleNamespace

import pytest

from core_domain.structured_generation import GenerationRunStatus, GenerationStage, StructuredGenerationError
from fmea_application.assistance_contracts import AssistanceKind
from fmea_application.review_errors import ReviewError
from fmea_application.risk_contracts import RiskModelRequest
from fmea_infrastructure.risk_generator import RiskSuggestionGenerator
from tests.unit.test_fmea_risk_service import _domain_pack, _rule_pack


class _Service:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            status=GenerationRunStatus.SUCCEEDED,
            repair_count=0,
            batch=SimpleNamespace(
                template_id="fmea-risk-proposal",
                template_version="1.0.0",
                evidence_pack_id=kwargs["evidence_pack"].pack_id,
                candidates=(SimpleNamespace(candidate_id="risk-suggestion-1", payload=self.payload),),
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


def _payload() -> dict[str, object]:
    return {
        "dimensions": [
            {"name": "severity", "value": 9, "evidence_ids": ["ev-1"], "reason": "severe", "uncertainty": None},
            {"name": "occurrence", "value": 3, "evidence_ids": ["ev-1"], "reason": "occasional", "uncertainty": None},
            {"name": "detection", "value": 4, "evidence_ids": ["ev-1"], "reason": "detectable", "uncertainty": None},
        ],
        "reason": "bounded evidence proposal",
        "uncertainty": None,
    }


def _request(fixture_pack, fixture_review_context) -> RiskModelRequest:
    return RiskModelRequest(
        run_id="risk-run-1",
        context=fixture_review_context,
        evidence_pack=fixture_pack,
        domain_pack=_domain_pack(),
        rule_pack=_rule_pack(),
        template_id="fuel-combustion-fmea",
        template_version="1.0.0",
    )


def test_risk_generator_returns_only_bound_unapplied_score_suggestion(
    fixture_pack, fixture_review_context
) -> None:
    service = _Service(_payload())
    generator = RiskSuggestionGenerator(service, clock=lambda: "2026-08-28T00:00:00Z")

    suggestion = generator.generate(_request(fixture_pack, fixture_review_context))

    assert suggestion.kind is AssistanceKind.SCORE_RECOMMENDATION
    assert suggestion.applied is False
    assert suggestion.target_id == "row-1"
    assert suggestion.evidence_ids == ("ev-1",)
    assert set(suggestion.payload) == {"dimensions", "reason", "uncertainty"}
    assert "rpn" not in suggestion.payload
    assert service.calls[0]["template_id"] == "fmea-risk-proposal"


def test_risk_generator_rejects_model_derived_authority_fields(fixture_pack, fixture_review_context) -> None:
    payload = _payload()
    payload["rpn"] = 108
    generator = RiskSuggestionGenerator(_Service(payload), clock=lambda: "2026-08-28T00:00:00Z")

    with pytest.raises(ReviewError) as captured:
        generator.generate(_request(fixture_pack, fixture_review_context))

    assert captured.value.code == "FMEA_MODEL_SUGGESTION_INVALID"


def test_risk_generator_maps_provider_timeout_to_retryable_safe_error(fixture_pack, fixture_review_context) -> None:
    class _TimeoutService:
        def run(self, **_kwargs):
            raise StructuredGenerationError("MODEL_TIMEOUT", "secret upstream detail")

    with pytest.raises(ReviewError) as captured:
        RiskSuggestionGenerator(_TimeoutService()).generate(_request(fixture_pack, fixture_review_context))

    assert captured.value.code == "FMEA_MODEL_SUGGESTION_UNAVAILABLE"
    assert captured.value.retryable is True
    assert "secret upstream detail" not in str(captured.value)
