from __future__ import annotations

import json
from dataclasses import replace

import pytest

from core_domain.fmea.states import ClaimStatus
from core_domain.fmea.value_objects import EvidencePack
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


def test_adapter_task_carries_canonical_retrieval_provenance(
    fixture_review_context, fixture_pack
) -> None:
    request = ReviewTemplateAdapter().build_request(
        fixture_review_context,
        fixture_pack,
        "review-run-1",
        review_policy="default",
        focus_fields=(),
    )
    task = json.loads(ReviewTemplateAdapter().render_task(request))
    assert task["retrieval"] == {
        "requested_profile": "rag_only",
        "resolved_profile": "rag_only",
        "allowed_evidence_types": ["text"],
        "warnings": [],
        "incomplete": False,
    }


def test_adapter_rejects_same_pack_identity_from_other_workspace(
    fixture_review_context, fixture_pack
) -> None:
    other_refs = tuple(replace(ref, workspace_id="ws-2") for ref in fixture_pack.refs)
    other_pack = EvidencePack.build(
        pack_id=fixture_pack.pack_id,
        workspace_id="ws-2",
        acl_scope=fixture_pack.acl_scope,
        versions=fixture_pack.versions,
        refs=other_refs,
        created_at=fixture_pack.created_at,
        expires_at=fixture_pack.expires_at,
    )
    assert other_pack.pack_hash == fixture_pack.pack_hash
    assert tuple(ref.evidence_id for ref in other_pack.refs) == tuple(
        ref.evidence_id for ref in fixture_pack.refs
    )

    with pytest.raises(ReviewError) as captured:
        ReviewTemplateAdapter().build_request(
            fixture_review_context,
            other_pack,
            "review-run-1",
            review_policy="default",
            focus_fields=("controls",),
        )

    assert captured.value.code == "FMEA_REVIEW_REQUEST_INVALID"


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
    ("action", "collections", "should_raise"),
    [
        pytest.param("accept", "edit", True, id="accept-with-edit"),
        pytest.param("accept", "request", True, id="accept-with-request"),
        pytest.param("modify_and_accept", "edit", False, id="modify-with-edit"),
        pytest.param("request_evidence", "request", False, id="request-with-request"),
        pytest.param("request_evidence", "both", True, id="request-with-request-and-edit"),
    ],
)
def test_adapter_enforces_action_linkage(
    fixture_review_context,
    action: str,
    collections: str,
    should_raise: bool,
) -> None:
    payload = _valid_review_payload()
    payload["recommended_action"] = action
    payload["proposed_edits"] = []
    payload["evidence_requests"] = []
    if collections in {"edit", "both"}:
        payload["proposed_edits"] = _valid_review_payload()["proposed_edits"]
    if collections in {"request", "both"}:
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


def test_adapter_preserves_insufficient_evidence_claim_with_bound_evidence(
    fixture_review_context,
) -> None:
    payload = _valid_review_payload()
    payload["field_findings"][0]["recommended_claim_status"] = "insufficient_evidence"
    result = make_review_generation_result(payload)

    draft = ReviewTemplateAdapter().decode_draft(result, fixture_review_context)

    assert draft.field_findings[0].recommended_claim_status is ClaimStatus.INSUFFICIENT_EVIDENCE


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
