from __future__ import annotations

import json
from dataclasses import replace

import pytest

from core_domain.fmea.states import ClaimStatus
from core_domain.fmea.value_objects import EvidencePack
from core_domain.query_contracts import (
    CitationType,
    EvidenceSelectionProfile,
    validate_evidence_type_membership,
)
from core_domain.structured_output import CandidateClaim, ClaimState
from fmea_application.review_contracts import ReviewAction
from fmea_application.review_errors import ReviewError
from fmea_application.review_projection import build_review_context
from fmea_application.review_template_adapter import ReviewTemplateAdapter
from tests.fmea_review_fixtures import (
    _valid_review_payload,
    make_review_generation_result,
    make_review_source,
)


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


def test_adapter_model_pack_uses_projected_locator_and_quote(
    fixture_review_row, fixture_pack, fixture_review_source
) -> None:
    private_ref = replace(
        fixture_pack.refs[0],
        locator='{"file":"C:/private/manual.pdf","page":42}',
        quote="q" * 5001,
    )
    private_pack = EvidencePack.build(
        pack_id=fixture_pack.pack_id,
        workspace_id=fixture_pack.workspace_id,
        acl_scope=fixture_pack.acl_scope,
        versions=fixture_pack.versions,
        refs=(private_ref,),
        created_at=fixture_pack.created_at,
        expires_at=fixture_pack.expires_at,
    )
    context = build_review_context(
        row=fixture_review_row,
        source=fixture_review_source,
        pack=private_pack,
        suggestions=(),
        decisions=(),
    )

    request = ReviewTemplateAdapter().build_request(
        context,
        private_pack,
        "review-run-1",
        review_policy="default",
        focus_fields=(),
    )

    model_ref = request.evidence_pack.refs[0]
    projected_ref = context.evidence.refs[0]
    assert model_ref.source_type == projected_ref.source_type
    assert model_ref.source_trust == projected_ref.source_trust
    assert model_ref.is_primary == projected_ref.is_primary
    assert model_ref.locator == projected_ref.locator
    assert model_ref.quote == projected_ref.quote
    assert request.evidence_pack.pack_hash == private_pack.pack_hash
    assert context.evidence.pack_hash == "sha256:" + request.evidence_pack.pack_hash
    assert request.evidence_pack.pack_id == private_pack.pack_id
    assert request.evidence_pack.workspace_id == private_pack.workspace_id
    assert request.evidence_pack.acl_scope == private_pack.acl_scope
    assert request.evidence_pack.versions == private_pack.versions
    assert request.evidence_pack.created_at == private_pack.created_at
    assert request.evidence_pack.expires_at == private_pack.expires_at
    assert "C:/private/manual.pdf" not in model_ref.locator
    assert model_ref.quote != private_ref.quote


def test_combined_claim_membership_allows_text_subset_and_rejects_undeclared_graph(
    fixture_review_row, fixture_pack
) -> None:
    assert validate_evidence_type_membership(
        EvidenceSelectionProfile.COMBINED,
        (CitationType.TEXT, CitationType.GRAPH),
        ("primary_document",),
        allow_subset=True,
    ) == (CitationType.TEXT,)
    with pytest.raises(ValueError, match="declared evidence_types"):
        validate_evidence_type_membership(
            EvidenceSelectionProfile.COMBINED,
            (CitationType.TEXT,),
            ("graphrag_relation",),
            allow_subset=True,
        )

    graph_ref = replace(
        fixture_pack.refs[0],
        evidence_id="ev-graph",
        source_type="graphrag_relation",
        evidence_hash="a" * 64,
        locator="relation:filter-blockage",
        quote="filter causes blockage",
        normalized_quote="filter causes blockage",
    )
    combined_pack = EvidencePack.build(
        pack_id=fixture_pack.pack_id,
        workspace_id=fixture_pack.workspace_id,
        acl_scope=fixture_pack.acl_scope,
        versions=fixture_pack.versions,
        refs=(fixture_pack.refs[0], graph_ref),
        created_at=fixture_pack.created_at,
        expires_at=fixture_pack.expires_at,
    )
    row = replace(
        fixture_review_row,
        field_evidence=tuple(
            (field, ("ev-graph",) if field == "controls" else evidence_ids)
            for field, evidence_ids in fixture_review_row.field_evidence
        ),
    )
    source = make_review_source(
        requested_evidence_profile=EvidenceSelectionProfile.COMBINED,
        resolved_evidence_profile=EvidenceSelectionProfile.COMBINED,
        evidence_types=(CitationType.TEXT, CitationType.GRAPH),
        retrieval_incomplete=True,
    )
    context = build_review_context(
        row=row,
        source=source,
        pack=combined_pack,
        suggestions=(),
        decisions=(),
    )

    draft = ReviewTemplateAdapter().decode_draft(
        make_review_generation_result(_valid_review_payload()),
        context,
    )
    assert draft.field_findings[0].evidence_ids == ("ev-1",)

    undeclared_context = replace(
        context,
        retrieval=replace(
            context.retrieval,
            evidence_types=(CitationType.TEXT,),
            incomplete=True,
        ),
    )
    graph_payload = _valid_review_payload()
    graph_findings = graph_payload["field_findings"]
    graph_edits = graph_payload["proposed_edits"]
    assert isinstance(graph_findings, list) and isinstance(graph_findings[0], dict)
    assert isinstance(graph_edits, list) and isinstance(graph_edits[0], dict)
    graph_findings[0]["evidence_ids"] = ["ev-graph"]
    graph_edits[0]["evidence_ids"] = ["ev-graph"]

    with pytest.raises(ReviewError) as captured:
        ReviewTemplateAdapter().decode_draft(
            make_review_generation_result(graph_payload),
            undeclared_context,
        )

    assert captured.value.code == "FMEA_MODEL_SUGGESTION_INVALID"


@pytest.mark.parametrize(
    ("field", "forged_value"),
    (
        ("source_type", "rag_text"),
        ("source_trust", "forged"),
        ("is_primary", False),
        ("locator", "forged-locator"),
        ("quote", "FORGED QUOTE"),
    ),
)
def test_adapter_rejects_or_reprojects_stale_raw_evidence_fields(
    fixture_review_context, fixture_pack, field: str, forged_value: object
) -> None:
    stale_ref = replace(fixture_pack.refs[0], **{field: forged_value})
    stale_pack = EvidencePack.build(
        pack_id=fixture_pack.pack_id,
        workspace_id=fixture_pack.workspace_id,
        acl_scope=fixture_pack.acl_scope,
        versions=fixture_pack.versions,
        refs=(stale_ref,),
        created_at=fixture_pack.created_at,
        expires_at=fixture_pack.expires_at,
    )

    try:
        request = ReviewTemplateAdapter().build_request(
            fixture_review_context,
            stale_pack,
            "review-run-1",
            review_policy="default",
            focus_fields=(),
        )
    except ReviewError:
        return

    model_ref = request.evidence_pack.refs[0]
    projected_ref = fixture_review_context.evidence.refs[0]
    assert model_ref.source_type == projected_ref.source_type
    assert model_ref.source_trust == projected_ref.source_trust
    assert model_ref.is_primary == projected_ref.is_primary
    assert model_ref.locator == projected_ref.locator
    assert model_ref.quote == projected_ref.quote


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
