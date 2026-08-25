from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from core_domain.fmea.states import ReviewStatus
from fmea_application.review_contracts import ReviewAction
from fmea_application.review_errors import ReviewError


def _history_counts(repository, row_id: str) -> tuple[int, int]:
    connection = sqlite3.connect(repository.database_path)
    try:
        return tuple(
            int(connection.execute(query, (row_id,)).fetchone()[0])
            for query in (
                "SELECT COUNT(*) FROM review_decisions WHERE row_id = ?",
                "SELECT COUNT(*) FROM audit_events WHERE row_id = ? AND command = 'review.decision'",
            )
        )
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("action", "expected_status"),
    (
        (ReviewAction.ACCEPT, ReviewStatus.ACCEPTED),
        (ReviewAction.MODIFY_AND_ACCEPT, ReviewStatus.ACCEPTED),
        (ReviewAction.REJECT, ReviewStatus.REJECTED),
        (ReviewAction.REQUEST_EVIDENCE, ReviewStatus.IN_REVIEW),
        (ReviewAction.DEFER, ReviewStatus.IN_REVIEW),
    ),
)
def test_each_human_review_action_applies_once_and_audits_once(
    sqlite_review_service,
    seeded_review_repository,
    fixture_human_reviewer,
    valid_review_decision_commands,
    action,
    expected_status,
) -> None:
    result = sqlite_review_service.submit_decision(valid_review_decision_commands[action], fixture_human_reviewer)

    assert result.review_status is expected_status
    assert result.record_version == 2
    assert result.row.record_version == 2
    assert _history_counts(seeded_review_repository, "row-1") == (1, 1)


@pytest.mark.parametrize(
    ("initial_action", "follow_up_action"),
    (
        (ReviewAction.ACCEPT, ReviewAction.MODIFY_AND_ACCEPT),
        (ReviewAction.REJECT, ReviewAction.ACCEPT),
    ),
)
def test_accepted_and_rejected_rows_cannot_be_edited_or_reopened(
    sqlite_review_service,
    seeded_review_repository,
    fixture_human_reviewer,
    valid_review_decision_commands,
    fixture_review_edit,
    initial_action,
    follow_up_action,
) -> None:
    sqlite_review_service.submit_decision(valid_review_decision_commands[initial_action], fixture_human_reviewer)
    follow_up = replace(
        valid_review_decision_commands[follow_up_action],
        expected_record_version=2,
        idempotency_key="00000000-0000-4000-8000-000000000099",
    )

    with pytest.raises(ReviewError) as captured:
        sqlite_review_service.submit_decision(follow_up, fixture_human_reviewer)

    assert captured.value.code == "FMEA_REVIEW_TERMINAL"
    assert seeded_review_repository.get_row("row-1", "ws-1").record_version == 2
    assert _history_counts(seeded_review_repository, "row-1") == (1, 1)
