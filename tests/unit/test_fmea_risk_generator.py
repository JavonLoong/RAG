from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from core_domain.structured_generation import GenerationRunStatus, GenerationStage, StructuredGenerationError
from fmea_application.assistance_contracts import AssistanceKind
from fmea_application.review_errors import ReviewError
from fmea_application.risk_contracts import RiskModelRequest
from fmea_infrastructure.risk_generator import RiskSuggestionGenerator
from tests.unit.test_fmea_risk_service import _domain_pack, _rule_pack


class _Service:
    def __init__(
        self,
        payload: dict[str, object],
        *,
        status: GenerationRunStatus = GenerationRunStatus.SUCCEEDED,
        repair_count: int = 0,
    ) -> None:
        self.payload = payload
        self.status = status
        self.repair_count = repair_count
        self.calls: list[dict[str, object]] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            status=self.status,
            repair_count=self.repair_count,
            batch=SimpleNamespace(
                template_id="fmea-risk-proposal",
                template_version="1.0.0",
                evidence_pack_id=kwargs["evidence_pack"].pack_id,
                candidates=(SimpleNamespace(candidate_id="risk-suggestion-1", payload=self.payload),),
            ),
            traces=(
                SimpleNamespace(
                    stage=GenerationStage.REPAIR if self.repair_count else GenerationStage.CRITIC,
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
    anchors = tuple(
        (name, tuple((score, f"{name}-{score}") for score in range(1, 11)))
        for name in ("severity", "occurrence", "detection")
    )
    return RiskModelRequest(
        run_id="risk-run-1",
        context=fixture_review_context,
        evidence_pack=fixture_pack,
        domain_pack=_domain_pack(),
        rule_pack=replace(_rule_pack(), dimension_anchors=anchors),
        template_id="fuel-combustion-fmea",
        template_version="1.0.0",
    )


def _request_with_hidden_evidence(fixture_pack, fixture_review_context) -> RiskModelRequest:
    hidden = replace(
        fixture_pack.refs[0],
        evidence_id="ev-hidden",
        evidence_hash="2" * 64,
        quote="secret raw quote that must not reach the model",
    )
    source_pack = type(fixture_pack).build(
        pack_id=fixture_pack.pack_id,
        workspace_id=fixture_pack.workspace_id,
        acl_scope=fixture_pack.acl_scope,
        versions=fixture_pack.versions,
        refs=(*fixture_pack.refs, hidden),
        created_at=fixture_pack.created_at,
        expires_at=fixture_pack.expires_at,
    )
    projected = replace(
        fixture_review_context.evidence,
        pack_hash="sha256:" + source_pack.pack_hash.removeprefix("sha256:"),
    )
    return replace(
        _request(source_pack, replace(fixture_review_context, evidence=projected)),
        evidence_pack=source_pack,
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
    assert set(suggestion.payload) == {"dimensions", "reason", "uncertainty", "binding"}
    assert "rpn" not in suggestion.payload
    assert service.calls[0]["template_id"] == "fmea-risk-proposal"
    assert tuple(ref.evidence_id for ref in service.calls[0]["evidence_pack"].refs) == ("ev-1",)


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


def test_risk_generator_fails_closed_without_complete_scoring_anchors(
    fixture_pack, fixture_review_context
) -> None:
    request = replace(_request(fixture_pack, fixture_review_context), rule_pack=_rule_pack())

    with pytest.raises(ReviewError) as captured:
        RiskSuggestionGenerator(_Service(_payload())).generate(request)

    assert captured.value.code == "FMEA_MODEL_SUGGESTION_INVALID"


def test_repaired_candidate_remains_an_unapplied_human_review_proposal(
    fixture_pack, fixture_review_context
) -> None:
    service = _Service(_payload(), status=GenerationRunStatus.NEEDS_REVIEW, repair_count=1)

    suggestion = RiskSuggestionGenerator(service).generate(_request(fixture_pack, fixture_review_context))

    assert suggestion.applied is False
    assert suggestion.kind is AssistanceKind.SCORE_RECOMMENDATION


def test_risk_generator_never_passes_hidden_raw_evidence_to_the_model(
    fixture_pack, fixture_review_context
) -> None:
    service = _Service(_payload())
    request = _request_with_hidden_evidence(fixture_pack, fixture_review_context)

    RiskSuggestionGenerator(service).generate(request)

    model_pack = service.calls[0]["evidence_pack"]
    assert tuple(ref.evidence_id for ref in model_pack.refs) == ("ev-1",)
    assert all("secret raw quote" not in ref.quote for ref in model_pack.refs)


def test_risk_generator_rejects_payload_references_to_hidden_evidence(
    fixture_pack, fixture_review_context
) -> None:
    payload = _payload()
    payload["dimensions"][0]["evidence_ids"] = ["ev-hidden"]

    with pytest.raises(ReviewError) as captured:
        RiskSuggestionGenerator(_Service(payload)).generate(
            _request_with_hidden_evidence(fixture_pack, fixture_review_context)
        )

    assert captured.value.code == "FMEA_MODEL_SUGGESTION_INVALID"
