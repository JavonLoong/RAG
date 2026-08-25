from __future__ import annotations

from dataclasses import replace

import pytest

from core_domain.structured_output import CandidateClaim, ClaimState
from fmea_application.review_contracts import ReviewAction
from fmea_application.review_errors import ReviewError
from fmea_application.review_template_adapter import ReviewTemplateAdapter
from tests.fmea_review_fixtures import _valid_review_payload, make_review_generation_result


def test_adapter_builds_bounded_canonical_model_input(
    fixture_review_context, fixture_pack
) -> None:
    adapter = ReviewTemplateAdapter()
    request = adapter.build_request(
        fixture_review_context,
        fixture_pack,
        "review-run-1",
        review_policy="default",
        focus_fields=("controls",),
    )

    rendered = adapter.render_task(request)
    assert request.template_id == "fmea-row-review"
    assert request.template_version == "1.0.0"
    assert len(rendered.encode("utf-8")) <= 4_000
    assert "C:/" not in rendered
    assert "acl_scope" not in rendered


def test_modify_suggestion_requires_one_valid_edit_and_exact_claim_evidence(
    fixture_review_context, valid_review_generation_result
) -> None:
    draft = ReviewTemplateAdapter().decode_draft(valid_review_generation_result, fixture_review_context)

    assert draft.recommended_action is ReviewAction.MODIFY_AND_ACCEPT
    assert draft.proposed_edits[0].target_field == "controls"


@pytest.mark.parametrize(
    "remove_actor_type",
    [False, True],
    ids=["root-server-field", "external-pack-evidence"],
)
def test_adapter_rejects_server_owned_fields_and_pack_external_evidence(
    fixture_review_context,
    review_result_with_extra_actor_and_external_evidence,
    remove_actor_type: bool,
) -> None:
    result = review_result_with_extra_actor_and_external_evidence
    if remove_actor_type:
        assert result.batch is not None
        candidate = result.batch.candidates[0]
        payload = dict(candidate.payload)
        payload.pop("actor_type")
        result = replace(
            result,
            batch=replace(result.batch, candidates=(replace(candidate, payload=payload),)),
        )

    with pytest.raises(ReviewError) as captured:
        ReviewTemplateAdapter().decode_draft(result, fixture_review_context)

    assert captured.value.code == "FMEA_MODEL_SUGGESTION_INVALID"


@pytest.mark.parametrize(
    ("action", "collection", "should_raise"),
    [
        pytest.param("accept", "proposed_edits", True, id="accept-with-edit"),
        pytest.param("modify_and_accept", "proposed_edits", False, id="modify-with-edit"),
        pytest.param("request_evidence", "evidence_requests", False, id="request-with-request"),
        pytest.param("request_evidence", "proposed_edits", True, id="request-with-edit"),
    ],
)
def test_adapter_enforces_action_linkage(
    fixture_review_context,
    action: str,
    collection: str,
    should_raise: bool,
) -> None:
    payload = _valid_review_payload()
    payload["recommended_action"] = action
    payload["proposed_edits"] = []
    payload["evidence_requests"] = []
    if collection == "proposed_edits":
        payload["proposed_edits"] = _valid_review_payload()["proposed_edits"]
    if collection == "evidence_requests":
        payload["evidence_requests"] = [
            {
                "target_field": "controls",
                "question": "Which startup control is required?",
                "preferred_source_types": ["primary_document"],
                "priority": "normal",
            }
        ]

    result = make_review_generation_result(payload)
    if should_raise:
        with pytest.raises(ReviewError) as captured:
            ReviewTemplateAdapter().decode_draft(result, fixture_review_context)
        assert captured.value.code == "FMEA_MODEL_SUGGESTION_INVALID"
    else:
        draft = ReviewTemplateAdapter().decode_draft(result, fixture_review_context)
        assert draft.recommended_action.value == action


def test_adapter_rejects_claim_evidence_that_is_not_exactly_the_payload_evidence(
    fixture_review_context,
) -> None:
    result = make_review_generation_result(_valid_review_payload())
    assert result.batch is not None
    candidate = result.batch.candidates[0]
    mismatched = replace(
        candidate,
        claims=(
            CandidateClaim("/field_findings/0", ClaimState.KNOWN, ("external-ev",)),
            candidate.claims[1],
        ),
    )
    tampered = replace(result, batch=replace(result.batch, candidates=(mismatched,)))

    with pytest.raises(ReviewError) as captured:
        ReviewTemplateAdapter().decode_draft(tampered, fixture_review_context)

    assert captured.value.code == "FMEA_MODEL_SUGGESTION_INVALID"
