from dataclasses import replace

import pytest

from core_domain.fmea.states import ClaimStatus
from core_domain.fmea.value_objects import EvidencePack
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile
from fmea_application.review_contracts import ReviewAction, ReviewReasonCode
from fmea_application.review_projection import build_review_context


def test_context_exposes_labels_profile_and_acl_safe_evidence(
    fixture_review_row, fixture_pack, fixture_review_source
) -> None:
    private_ref = replace(
        fixture_pack.refs[0],
        locator='{"file":"C:/private/manual.pdf","page":42,"chunk_id":"c-1"}',
        quote="启动前应检查燃油供给压力。",
    )
    pack = replace(fixture_pack, refs=(private_ref,))
    context = build_review_context(
        row=fixture_review_row,
        source=fixture_review_source,
        pack=pack,
        suggestions=(),
        decisions=(),
    )

    assert context.reviewability is True
    assert context.item_label == "Fuel filter"
    assert context.retrieval.resolved_profile is EvidenceSelectionProfile.RAG_ONLY
    assert context.evidence.workspace_id == fixture_pack.workspace_id
    assert context.evidence.pack_hash == "sha256:" + fixture_pack.pack_hash
    assert context.evidence.refs[0].locator == '{"chunk_id":"c-1","page":42}'
    assert context.evidence.refs[0].quote == "启动前应检查燃油供给压力。"
    assert "private" not in repr(context)


def test_context_folds_field_edits_in_decision_order(
    fixture_review_row,
    fixture_pack,
    fixture_review_source,
    fixture_decision_record,
    fixture_review_edit,
) -> None:
    first = replace(
        fixture_decision_record,
        action=ReviewAction.MODIFY_AND_ACCEPT,
        reason_code=ReviewReasonCode.FIELD_CORRECTION,
        edits=(replace(fixture_review_edit, value=("old control",)),),
    )
    second = replace(
        first,
        decision_id="decision-2",
        previous_record_version=2,
        record_version=3,
        created_at="2026-08-24T00:00:00Z",
        edits=(replace(fixture_review_edit, value=("new control",)),),
    )
    context = build_review_context(
        row=replace(fixture_review_row, record_version=3),
        source=fixture_review_source,
        pack=fixture_pack,
        suggestions=(),
        decisions=(second, first),
    )

    assert context.field_by_name("controls").value == ("new control",)
    assert context.field_by_name("controls").last_decision_id == "decision-2"
    assert tuple(decision.decision_id for decision in context.decision_history) == (
        "decision-1",
        "decision-2",
    )
    assert context.row.claim_status is ClaimStatus.KNOWN


def test_context_uses_conservative_field_claim_aggregation(
    fixture_review_row, fixture_pack, fixture_review_source
) -> None:
    source = replace(
        fixture_review_source,
        field_claim_statuses=(
            ("failure_mode", ClaimStatus.KNOWN),
            ("causes", ClaimStatus.INSUFFICIENT_EVIDENCE),
            ("controls", ClaimStatus.CONFLICT),
        ),
    )
    context = build_review_context(
        row=fixture_review_row,
        source=source,
        pack=fixture_pack,
        suggestions=(),
        decisions=(),
    )

    assert context.row.claim_status is ClaimStatus.CONFLICT


def test_context_selects_latest_suggestion_stably(
    fixture_review_row, fixture_pack, fixture_review_source, fixture_review_suggestion
) -> None:
    first = replace(fixture_review_suggestion, suggestion_id="suggestion-a")
    second = replace(fixture_review_suggestion, suggestion_id="suggestion-b")
    context = build_review_context(
        row=fixture_review_row,
        source=fixture_review_source,
        pack=fixture_pack,
        suggestions=(second, first),
        decisions=(),
    )

    assert context.latest_suggestion is not None
    assert context.latest_suggestion.suggestion_id == "suggestion-b"


def test_context_repr_is_bounded_and_excludes_private_review_content(
    fixture_review_row,
    fixture_pack,
    fixture_review_source,
    fixture_review_suggestion,
    fixture_decision_record,
) -> None:
    row = replace(fixture_review_row, failure_mode="ROW_PRIVATE_MARKER")
    private_ref = replace(
        fixture_pack.refs[0],
        locator='{"safe":"EVIDENCE_LOCATOR_PRIVATE_MARKER"}',
        quote="EVIDENCE_QUOTE_PRIVATE_MARKER",
    )
    suggestion = replace(fixture_review_suggestion, rationale="SUGGESTION_RATIONALE_PRIVATE_MARKER")
    decision = replace(fixture_decision_record, reason="DECISION_REASON_PRIVATE_MARKER")
    context = build_review_context(
        row=row,
        source=fixture_review_source,
        pack=replace(fixture_pack, refs=(private_ref,)),
        suggestions=(suggestion,),
        decisions=(decision,),
    )

    rendered = repr(context)
    assert all(marker not in rendered for marker in (
        "ROW_PRIVATE_MARKER",
        "EVIDENCE_LOCATOR_PRIVATE_MARKER",
        "EVIDENCE_QUOTE_PRIVATE_MARKER",
        "SUGGESTION_RATIONALE_PRIVATE_MARKER",
        "DECISION_REASON_PRIVATE_MARKER",
    ))
    assert "ReviewContext(" in rendered
    assert "row_id='row-1'" in rendered
    assert "reviewability=True" in rendered
    assert "field_count=8" in rendered


@pytest.mark.parametrize(
    ("locator", "expected"),
    (
        ('{"FILE":"C:/private/manual.pdf","Page":42,"chunk_id":"c-1"}', '{"Page":42,"chunk_id":"c-1"}'),
        ('{"nested":{"PaTh":"C:/private/manual.pdf","safe":"keep"}}', '{"nested":{"safe":"keep"}}'),
        ('{"safe":"C:private/manual.pdf","items":["https://private.example","ok","../private"]}', '{"items":["redacted","ok","redacted"],"safe":"redacted"}'),
        ("manual.pdf#page=4", "manual.pdf#page=4"),
        ("C:private/manual.pdf", "redacted"),
        ("C:/private/manual.pdf", "redacted"),
        (r"\\server\private\manual.pdf", "redacted"),
        ("//server/private/manual.pdf", "redacted"),
        ("../private/manual.pdf", "redacted"),
        ("file://private/manual.pdf", "redacted"),
        ("https://private.example/manual.pdf", "redacted"),
    ),
)
def test_context_sanitizes_locators_and_bounds_quotes(
    fixture_review_row, fixture_pack, fixture_review_source, locator: str, expected: str
) -> None:
    private_ref = replace(fixture_pack.refs[0], locator=locator, quote="q" * 5001)
    context = build_review_context(
        row=fixture_review_row,
        source=fixture_review_source,
        pack=replace(fixture_pack, refs=(private_ref,)),
        suggestions=(),
        decisions=(),
    )

    assert context.evidence.refs[0].locator == expected
    assert len(context.evidence.refs[0].quote) == 4000


@pytest.mark.parametrize("pack_hash", ("A" * 64, "sha256:" + "A" * 64, "sha256:" + "0" * 63))
def test_context_rejects_non_strict_pack_hashes(fixture_review_row, fixture_pack, fixture_review_source, pack_hash: str) -> None:
    with pytest.raises(ValueError, match="pack_hash"):
        build_review_context(
            row=fixture_review_row,
            source=fixture_review_source,
            pack=replace(fixture_pack, pack_hash=pack_hash),
            suggestions=(),
            decisions=(),
        )


def test_projection_does_not_change_supplied_row_or_source(
    fixture_review_row, fixture_pack, fixture_review_source, fixture_review_edit, fixture_decision_record
) -> None:
    original_row = fixture_review_row
    original_source = fixture_review_source
    decision = replace(
        fixture_decision_record,
        action=ReviewAction.MODIFY_AND_ACCEPT,
        reason_code=ReviewReasonCode.FIELD_CORRECTION,
        edits=(fixture_review_edit,),
    )
    build_review_context(
        row=fixture_review_row,
        source=fixture_review_source,
        pack=fixture_pack,
        suggestions=(),
        decisions=(decision,),
    )

    assert fixture_review_row == original_row
    assert fixture_review_source == original_source


def test_projection_fails_closed_for_mixed_pack_outside_profile_allowlist(
    fixture_review_row, fixture_pack, fixture_review_source
) -> None:
    graph_ref = replace(
        fixture_pack.refs[0],
        evidence_id="ev-graph",
        source_type="graphrag_relation",
        evidence_hash="a" * 64,
    )
    mixed_pack = EvidencePack.build(
        pack_id=fixture_pack.pack_id,
        workspace_id=fixture_pack.workspace_id,
        acl_scope=fixture_pack.acl_scope,
        versions=fixture_pack.versions,
        refs=(fixture_pack.refs[0], graph_ref),
        created_at=fixture_pack.created_at,
        expires_at=fixture_pack.expires_at,
    )
    with pytest.raises(ValueError, match="evidence profile"):
        build_review_context(
            row=fixture_review_row,
            source=fixture_review_source,
            pack=mixed_pack,
            suggestions=(),
            decisions=(),
        )


@pytest.mark.parametrize(
    ("profile", "evidence_types"),
    [
        (EvidenceSelectionProfile.RAG_ONLY, (CitationType.GRAPH,)),
        (EvidenceSelectionProfile.GRAPHRAG_ONLY, (CitationType.TEXT,)),
        (EvidenceSelectionProfile.CUSTOM, (CitationType.COMMUNITY, CitationType.TEXT)),
    ],
)
def test_source_snapshot_profile_and_evidence_types_are_consistent(
    fixture_review_source, profile, evidence_types
) -> None:
    with pytest.raises(ValueError, match="evidence profile"):
        type(fixture_review_source).build(
            **{
                field.name: (
                    profile
                    if field.name == "resolved_evidence_profile"
                    else evidence_types
                    if field.name == "evidence_types"
                    else getattr(fixture_review_source, field.name)
                )
                for field in __import__("dataclasses").fields(fixture_review_source)
                if field.name != "source_hash"
            },
        )
