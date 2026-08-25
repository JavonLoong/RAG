from __future__ import annotations

import json
import sqlite3
from dataclasses import replace

import pytest

from core_domain.fmea.states import ReviewStatus
from fmea_application.review_contracts import ReviewAction, encode_review_json
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


def test_decision_replay_accepts_exact_canonical_legacy_audit_event(
    sqlite_review_service,
    seeded_review_repository,
    fixture_human_reviewer,
    valid_review_decision_commands,
) -> None:
    command = valid_review_decision_commands[ReviewAction.ACCEPT]
    result = sqlite_review_service.submit_decision(command, fixture_human_reviewer)
    new_fields = {"run_id", "request_hash", "error_code", "retryable"}

    connection = seeded_review_repository._connect()
    try:
        row = connection.execute(
            "SELECT * FROM audit_events WHERE event_id = ?",
            (result.audit_event_id,),
        ).fetchone()
        assert row is not None
        current_payload = json.loads(row["event_json"])
        legacy_event_id = "legacy-audit-1"
        current_payload["event_id"] = legacy_event_id
        legacy_payload = {key: value for key, value in current_payload.items() if key not in new_fields}
        assert set(current_payload) - set(legacy_payload) == new_fields
        legacy_json = encode_review_json(legacy_payload)
        assert legacy_json == json.dumps(legacy_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        connection.execute(
            "INSERT INTO audit_events "
            "(event_id, row_id, workspace_id, actor_id, actor_type, command, action, suggestion_id, decision_id, "
            "expected_record_version, applied_record_version, before_hash, after_hash, canonical_payload_hash, event_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                legacy_event_id,
                row["row_id"],
                row["workspace_id"],
                row["actor_id"],
                row["actor_type"],
                row["command"],
                row["action"],
                row["suggestion_id"],
                row["decision_id"],
                row["expected_record_version"],
                row["applied_record_version"],
                row["before_hash"],
                row["after_hash"],
                row["canonical_payload_hash"],
                legacy_json,
                row["created_at"],
            ),
        )
        updated_result = replace(result, audit_event_id=legacy_event_id)
        connection.execute(
            "UPDATE idempotency_records SET response_json = ? WHERE resource_id = ?",
            (encode_review_json(updated_result), result.decision_id),
        )
        connection.commit()
    finally:
        connection.close()

    replayed = sqlite_review_service.submit_decision(command, fixture_human_reviewer)

    assert replayed == updated_result


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
