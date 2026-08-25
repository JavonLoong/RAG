from dataclasses import replace

import pytest

from core_domain.fmea.states import PublicationStatus, ReviewStatus
from fmea_application.review_errors import ReviewError
from fmea_application.review_service import ReviewService


def test_service_returns_non_reviewable_context_when_source_is_missing(
    memory_review_repository, fixture_human_reviewer, fixture_review_row, fixture_pack
) -> None:
    memory_review_repository.seed(row=fixture_review_row, pack=fixture_pack, source=None)
    context = ReviewService.for_queries(memory_review_repository).get_context(
        fixture_review_row.row_id, fixture_human_reviewer
    )

    assert context.reviewability is False
    assert context.item_label == fixture_review_row.item_id
    assert context.function_label == fixture_review_row.function_id
    assert context.retrieval.requested_profile.value == "custom"
    assert context.retrieval.resolved_profile.value == "custom"
    assert context.retrieval.trace_id == "legacy:row-1"
    assert context.retrieval.incomplete is True
    assert context.warnings == ("FMEA_REVIEW_SOURCE_MISSING",)
    assert memory_review_repository.calls == [
        "get_row",
        "get_evidence_pack",
        "get_review_source",
        "list_suggestions",
        "list_decisions",
    ]


def test_service_persists_generated_rows_and_sources_as_one_bundle(
    memory_review_repository, fixture_system_actor, fixture_review_bundle
) -> None:
    service = ReviewService.for_queries(memory_review_repository)
    rows = service.persist_generated_candidates(fixture_review_bundle, fixture_system_actor)

    assert rows[0].review_status is ReviewStatus.SUGGESTED
    assert rows[0].publication_status is PublicationStatus.UNPUBLISHED
    assert memory_review_repository.saved_bundle is fixture_review_bundle
    assert memory_review_repository.calls == ["save_review_candidate_bundle"]


def test_model_query_is_rejected_before_repository_access(
    memory_review_repository, fixture_model_actor
) -> None:
    with pytest.raises(ReviewError) as captured:
        ReviewService.for_queries(memory_review_repository).get_context("row-1", fixture_model_actor)

    assert captured.value.code == "FMEA_REVIEW_FORBIDDEN"
    assert memory_review_repository.calls == []


def test_non_analyst_candidate_persistence_is_rejected_before_repository_access(
    memory_review_repository, fixture_human_reviewer, fixture_review_bundle
) -> None:
    with pytest.raises(ReviewError) as captured:
        ReviewService.for_queries(memory_review_repository).persist_generated_candidates(
            fixture_review_bundle, fixture_human_reviewer
        )

    assert captured.value.code == "FMEA_REVIEW_FORBIDDEN"
    assert memory_review_repository.calls == []


def test_candidate_workspace_is_rejected_before_repository_access(
    memory_review_repository, fixture_system_actor, fixture_review_bundle
) -> None:
    bundle = replace(
        fixture_review_bundle,
        evidence_pack=replace(fixture_review_bundle.evidence_pack, workspace_id="other-workspace"),
    )
    with pytest.raises(ReviewError) as captured:
        ReviewService.for_queries(memory_review_repository).persist_generated_candidates(bundle, fixture_system_actor)

    assert captured.value.code == "FMEA_REVIEW_FORBIDDEN"
    assert memory_review_repository.calls == []


def test_query_history_is_stably_ordered(
    memory_review_repository,
    fixture_human_reviewer,
    fixture_review_row,
    fixture_pack,
    fixture_review_source,
    fixture_review_suggestion,
    fixture_decision_record,
) -> None:
    older_suggestion = replace(fixture_review_suggestion, suggestion_id="suggestion-a")
    newer_suggestion = replace(fixture_review_suggestion, suggestion_id="suggestion-b")
    older_decision = fixture_decision_record
    newer_decision = replace(fixture_decision_record, decision_id="decision-2", record_version=3)
    memory_review_repository.seed(
        row=fixture_review_row,
        pack=fixture_pack,
        source=fixture_review_source,
        suggestions=(newer_suggestion, older_suggestion),
        decisions=(newer_decision, older_decision),
    )
    service = ReviewService.for_queries(memory_review_repository)

    assert tuple(item.suggestion_id for item in service.list_suggestions("row-1", fixture_human_reviewer)) == (
        "suggestion-a",
        "suggestion-b",
    )
    assert tuple(item.decision_id for item in service.list_decisions("row-1", fixture_human_reviewer)) == (
        "decision-1",
        "decision-2",
    )


def test_query_history_page_and_trace_do_not_build_full_context(
    memory_review_repository,
    fixture_human_reviewer,
    fixture_review_row,
    fixture_pack,
    fixture_review_source,
    fixture_review_suggestion,
    fixture_decision_record,
) -> None:
    memory_review_repository.seed(
        row=fixture_review_row,
        pack=fixture_pack,
        source=fixture_review_source,
        suggestions=(fixture_review_suggestion,),
        decisions=(fixture_decision_record,),
    )
    service = ReviewService.for_queries(memory_review_repository)

    assert service.get_retrieval_trace("row-1", fixture_human_reviewer) == fixture_review_source.trace_id
    assert service.page_suggestions("row-1", fixture_human_reviewer, after=None, limit=1)
    assert service.page_decisions("row-1", fixture_human_reviewer, after=None, limit=1)
    assert "list_suggestions" not in memory_review_repository.calls
    assert "list_decisions" not in memory_review_repository.calls
