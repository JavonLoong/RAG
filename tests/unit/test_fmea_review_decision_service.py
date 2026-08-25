from __future__ import annotations

from dataclasses import replace

import pytest

from core_domain.fmea.states import PublicationStatus, ReviewStatus
from fmea_application.review_contracts import ReviewAction, ReviewReasonCode
from fmea_application.review_errors import ReviewError
from fmea_application.review_service import ReviewService


@pytest.mark.parametrize("action", tuple(ReviewAction))
def test_model_actor_cannot_submit_any_review_action(
    sqlite_review_service, fixture_model_actor, valid_review_decision_commands, action
) -> None:
    with pytest.raises(ReviewError) as captured:
        sqlite_review_service.submit_decision(valid_review_decision_commands[action], fixture_model_actor)

    assert captured.value.code == "FMEA_REVIEW_FORBIDDEN"


def test_forbidden_model_actor_is_rejected_before_malformed_command_parsing(
    recording_repository, fixture_model_actor
) -> None:
    class OpaqueMalformedCommand:
        pass

    with pytest.raises(ReviewError) as captured:
        ReviewService.for_queries(recording_repository).submit_decision(OpaqueMalformedCommand(), fixture_model_actor)

    assert captured.value.code == "FMEA_REVIEW_FORBIDDEN"
    assert recording_repository.calls == []


def test_modify_and_accept_replaces_only_allowed_field_and_preserves_risk_and_publication(
    sqlite_review_service, fixture_human_reviewer, fixture_decision_command, fixture_review_edit
) -> None:
    edit = replace(fixture_review_edit, value=("startup pressure check",))
    command = replace(
        fixture_decision_command,
        action=ReviewAction.MODIFY_AND_ACCEPT,
        reason_code=ReviewReasonCode.FIELD_CORRECTION,
        edits=(edit,),
    )

    result = sqlite_review_service.submit_decision(command, fixture_human_reviewer)

    assert result.row.controls == ("startup pressure check",)
    assert result.row.risk_assessment is None
    assert result.row.publication_status is PublicationStatus.UNPUBLISHED
    assert result.row.review_status is ReviewStatus.ACCEPTED


def test_accept_with_unresolved_field_requires_one_field_acknowledgement(
    unresolved_accept_service, fixture_human_reviewer, unresolved_accept_command
) -> None:
    with pytest.raises(ReviewError) as captured:
        unresolved_accept_service.submit_decision(unresolved_accept_command, fixture_human_reviewer)

    assert captured.value.code == "FMEA_UNRESOLVED_ACK_REQUIRED"


def test_stale_suggestion_cannot_be_referenced(
    sqlite_review_service, fixture_human_reviewer, decision_referencing_stale_suggestion
) -> None:
    with pytest.raises(ReviewError) as captured:
        sqlite_review_service.submit_decision(decision_referencing_stale_suggestion, fixture_human_reviewer)

    assert captured.value.code == "FMEA_REVIEW_SUGGESTION_STALE"


def test_missing_source_blocks_accept_but_allows_request_evidence(
    legacy_missing_source_service,
    fixture_human_reviewer,
    missing_source_accept_command,
    missing_source_request_command,
) -> None:
    with pytest.raises(ReviewError) as captured:
        legacy_missing_source_service.submit_decision(missing_source_accept_command, fixture_human_reviewer)
    assert captured.value.code == "FMEA_REVIEW_SOURCE_MISSING"

    result = legacy_missing_source_service.submit_decision(missing_source_request_command, fixture_human_reviewer)
    assert result.review_status is ReviewStatus.IN_REVIEW
