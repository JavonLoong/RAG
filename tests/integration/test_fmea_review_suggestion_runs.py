from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fmea_review_fixtures import (
    FakeReviewSuggestionGenerator,
    RecordingReviewExecutor,
    make_start_suggestion_command,
)

from core_domain.fmea.states import ActorType, RunStatus
from fmea_application.review_errors import ReviewError
from fmea_application.review_service import ReviewService
from fmea_infrastructure.repository_sqlite import (
    SqliteFmeaRepository,
    _decode_audit_event,
)


class SeededReviewDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    def insert_run(self, status: str) -> None:
        connection = sqlite3.connect(self.path)
        try:
            connection.execute(
                "INSERT INTO review_suggestion_runs "
                "(run_id, row_id, workspace_id, actor_id, source_record_version, status, request_hash, "
                "idempotency_scope, request_id, trace_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "run-1", "row-1", "ws-1", "reviewer-1", 1, status,
                    "sha256:" + "b" * 64, "scope-1", "request-1", "trace-1", "2026-08-23T00:00:00Z",
                ),
            )
            connection.commit()
        finally:
            connection.close()


class RejectingReviewExecutor:
    def submit(self, run_id, operation) -> None:
        raise ReviewError("FMEA_REVIEW_RATE_LIMITED", "review execution capacity is full", retryable=True)

    def close(self) -> None:
        return None


def test_interrupted_run_is_recovered_as_safe_failure(tmp_path, seeded_review_repository) -> None:
    seeded_database = SeededReviewDatabase(seeded_review_repository.database_path)
    seeded_database.insert_run(status="running")
    repository = SqliteFmeaRepository(seeded_database.path)
    repository.initialize()
    run = repository.get_suggestion_run("run-1", "ws-1")
    assert run is not None
    assert run.status is RunStatus.FAILED
    assert run.error_code == "FMEA_REVIEW_RUN_INTERRUPTED"
    assert run.retryable is True
    connection = repository._connect()
    try:
        event = connection.execute(
            "SELECT event_id, command, canonical_payload_hash, event_json "
            "FROM audit_events WHERE event_id LIKE 'recovery-%'"
        ).fetchone()
    finally:
        connection.close()
    assert event is not None
    payload = json.loads(event["event_json"])
    assert payload["analysis_id"] == "analysis-1"
    assert payload["request_id"] == "request-1"
    assert payload["trace_id"] == "trace-1"
    assert payload["request_hash"] == "sha256:" + "b" * 64
    assert event["command"] == "review.suggestion.fail"
    assert event["canonical_payload_hash"] == "sha256:" + "b" * 64
    decoded = _decode_audit_event(event["event_json"])
    assert decoded.event_id == event["event_id"]
    assert decoded.command == "review.suggestion.fail"
    assert decoded.error_code == "FMEA_REVIEW_RUN_INTERRUPTED"
    assert decoded.retryable is True


def test_success_and_failure_runs_have_one_terminal_audit_and_no_decision(
    inline_review_service,
    inline_executor,
    seeded_review_repository,
    fixture_human_reviewer,
    fixture_start_suggestion_command,
) -> None:
    succeeded = inline_review_service.start_suggestion(fixture_start_suggestion_command, fixture_human_reviewer)
    generator = inline_review_service._suggestion_generator
    assert generator is not None
    generator.generate = lambda request: (_ for _ in ()).throw(RuntimeError("private provider failure"))
    failed_command = replace(
        fixture_start_suggestion_command,
        idempotency_key="00000000-0000-4000-8000-000000000002",
    )
    failed = inline_review_service.start_suggestion(failed_command, fixture_human_reviewer)
    succeeded_terminal = inline_review_service.get_suggestion_run(succeeded.run_id, fixture_human_reviewer)
    failed_terminal = inline_review_service.get_suggestion_run(failed.run_id, fixture_human_reviewer)
    assert succeeded.status is RunStatus.QUEUED
    assert failed.status is RunStatus.QUEUED
    assert succeeded_terminal.status is RunStatus.SUCCEEDED, succeeded_terminal.error_code
    assert failed_terminal.status is RunStatus.FAILED

    connection = seeded_review_repository._connect()
    try:
        events = connection.execute(
            "SELECT event_id, command, canonical_payload_hash, event_json, created_at "
            "FROM audit_events ORDER BY created_at, event_id"
        ).fetchall()
        decisions = connection.execute("SELECT COUNT(*) AS count FROM review_decisions").fetchone()["count"]
    finally:
        connection.close()
    assert [row["command"] for row in events] == [
        "review.suggestion.create",
        "review.suggestion.complete",
        "review.suggestion.create",
        "review.suggestion.fail",
    ]
    assert decisions == 0
    payloads = [json.loads(row["event_json"]) for row in events]
    decoded_events = [_decode_audit_event(row["event_json"]) for row in events]
    assert all(row["created_at"] == payload["occurred_at_server"] for row, payload in zip(events, payloads, strict=True))
    assert all(row["command"] == payload["command"] for row, payload in zip(events, payloads, strict=True))
    assert all(
        row["canonical_payload_hash"] == payload["canonical_payload_hash"]
        for row, payload in zip(events, payloads, strict=True)
    )
    for run in (succeeded, failed):
        run_events = [payload for payload in payloads if payload["request_id"] == run.request_id]
        assert len(run_events) == 2
        assert {payload["trace_id"] for payload in run_events} == {run.trace_id}
        assert len({payload["canonical_payload_hash"] for payload in run_events}) == 1
    complete_payload = payloads[1]
    failed_payload = payloads[3]
    assert decoded_events[0].event_id == events[0]["event_id"]
    assert decoded_events[1].suggestion_id == succeeded_terminal.suggestion_id
    assert decoded_events[3].error_code == "FMEA_MODEL_SUGGESTION_UNAVAILABLE"
    assert decoded_events[3].retryable is True
    assert complete_payload["model_manifest"]["model"] == "deepseek-v4-pro"
    assert complete_payload["suggestion_id"] == succeeded_terminal.suggestion_id
    assert failed_payload["error_code"] == "FMEA_MODEL_SUGGESTION_UNAVAILABLE"
    assert all(payload["analysis_id"] == "analysis-1" for payload in payloads)


def test_sqlite_executor_rejection_preserves_queued_response_and_replays_it(
    seeded_review_repository,
    fixture_human_reviewer,
    fixture_start_suggestion_command,
    fixture_review_model_manifest,
    valid_review_suggestion_draft,
) -> None:
    ids: dict[str, int] = {}

    def id_factory(prefix: str) -> str:
        ids[prefix] = ids.get(prefix, 0) + 1
        return f"{prefix}-reject-{ids[prefix]}"

    service = ReviewService(
        seeded_review_repository,
        FakeReviewSuggestionGenerator(valid_review_suggestion_draft, fixture_review_model_manifest),
        RejectingReviewExecutor(),
        clock=lambda: "2026-08-23T00:00:00Z",
        id_factory=id_factory,
    )
    before = seeded_review_repository.get_row("row-1", "ws-1")
    queued = service.start_suggestion(fixture_start_suggestion_command, fixture_human_reviewer)
    failed = service.get_suggestion_run(queued.run_id, fixture_human_reviewer)
    replay = service.start_suggestion(fixture_start_suggestion_command, fixture_human_reviewer)
    after = seeded_review_repository.get_row("row-1", "ws-1")
    assert queued.status is RunStatus.QUEUED
    assert failed.status is RunStatus.FAILED
    assert failed.error_code == "FMEA_REVIEW_RATE_LIMITED"
    assert replay == queued
    assert after == before

    connection = seeded_review_repository._connect()
    try:
        events = connection.execute(
            "SELECT command, event_json FROM audit_events WHERE row_id = ? ORDER BY created_at, event_id",
            ("row-1",),
        ).fetchall()
        decisions = connection.execute("SELECT COUNT(*) AS count FROM review_decisions").fetchone()["count"]
    finally:
        connection.close()
    payloads = [json.loads(row["event_json"]) for row in events]
    assert [row["command"] for row in events] == ["review.suggestion.create", "review.suggestion.fail"]
    assert decisions == 0
    assert all(payload["request_id"] == queued.request_id for payload in payloads)
    assert all(payload["trace_id"] == queued.trace_id for payload in payloads)
    assert len({payload["canonical_payload_hash"] for payload in payloads}) == 1
    assert all(payload["analysis_id"] == "analysis-1" for payload in payloads)


@pytest.mark.parametrize(
    ("mutation", "workspace_id", "expected_code"),
    [
        ("running", "wrong-workspace", "FMEA_REVIEW_SUGGESTION_NOT_FOUND"),
        ("complete-queued", "ws-1", "FMEA_REVIEW_TERMINAL"),
        ("repeated-running", "ws-1", "FMEA_REVIEW_TERMINAL"),
        ("succeeded-wrong-suggestion-id", "ws-1", "FMEA_REVIEW_REQUEST_INVALID"),
    ],
)
def test_sqlite_run_mutations_fail_closed_on_workspace_or_transition(
    seeded_review_repository,
    fixture_human_reviewer,
    fixture_start_suggestion_command,
    fixture_review_model_manifest,
    valid_review_suggestion_draft,
    recording_executor,
    inline_review_service,
    mutation,
    workspace_id,
    expected_code,
) -> None:
    service = (
        inline_review_service
        if mutation == "succeeded-wrong-suggestion-id"
        else ReviewService(
            seeded_review_repository,
            FakeReviewSuggestionGenerator(valid_review_suggestion_draft, fixture_review_model_manifest),
            recording_executor,
            clock=lambda: "2026-08-23T00:00:00Z",
            id_factory=lambda prefix: f"{prefix}-mismatch",
        )
    )
    run = service.start_suggestion(fixture_start_suggestion_command, fixture_human_reviewer)
    with pytest.raises(ReviewError) as raised:
        if mutation == "running":
            seeded_review_repository.mark_suggestion_run_running(run.run_id, workspace_id)
        elif mutation == "repeated-running":
            seeded_review_repository.mark_suggestion_run_running(run.run_id, workspace_id)
            seeded_review_repository.mark_suggestion_run_running(run.run_id, workspace_id)
        elif mutation == "succeeded-wrong-suggestion-id":
            suggestion = seeded_review_repository.list_suggestions("row-1", "ws-1")[0]
            connection = seeded_review_repository._connect()
            try:
                request_hash = connection.execute(
                    "SELECT request_hash FROM review_suggestion_runs WHERE run_id = ? AND workspace_id = ?",
                    (run.run_id, workspace_id),
                ).fetchone()["request_hash"]
                connection.execute(
                    "UPDATE review_suggestion_runs SET suggestion_id = ? WHERE run_id = ? AND workspace_id = ?",
                    ("wrong-suggestion", run.run_id, workspace_id),
                )
                connection.commit()
            finally:
                connection.close()
            audit = SimpleNamespace(
                workspace_id=workspace_id,
                row_id=suggestion.row_id,
                request_id=run.request_id,
                trace_id=run.trace_id,
                canonical_payload_hash=request_hash,
                expected_record_version=suggestion.source_record_version,
                command="review.suggestion.complete",
                suggestion_id=suggestion.suggestion_id,
                model_manifest=suggestion.model_manifest,
                action=suggestion.recommended_action,
                actor_type=ActorType.MODEL,
                actor_id="review-model",
                decision_id=None,
            )
            seeded_review_repository.complete_suggestion_run(run.run_id, workspace_id, suggestion, audit)
        else:
            seeded_review_repository.complete_suggestion_run(run.run_id, workspace_id, object(), object())
    assert raised.value.code == expected_code


def test_fifth_active_sqlite_reservation_has_zero_side_effects(
    seeded_review_repository,
    fixture_human_reviewer,
    fixture_review_model_manifest,
    valid_review_suggestion_draft,
) -> None:
    executor = RecordingReviewExecutor()
    counts: dict[str, int] = {}

    def id_factory(prefix: str) -> str:
        counts[prefix] = counts.get(prefix, 0) + 1
        return f"{prefix}-{counts[prefix]}"

    service = ReviewService(
        seeded_review_repository,
        FakeReviewSuggestionGenerator(valid_review_suggestion_draft, fixture_review_model_manifest),
        executor,
        clock=lambda: "2026-08-23T00:00:00Z",
        id_factory=id_factory,
    )
    for index in range(4):
        service.start_suggestion(
            replace(
                make_start_suggestion_command(),
                idempotency_key=f"00000000-0000-4000-8000-{index + 10:012d}",
            ),
            fixture_human_reviewer,
        )
    connection = seeded_review_repository._connect()
    try:
        before = tuple(
            connection.execute(query).fetchone()["count"]
            for query in (
                "SELECT COUNT(*) AS count FROM review_suggestion_runs",
                "SELECT COUNT(*) AS count FROM idempotency_records",
                "SELECT COUNT(*) AS count FROM audit_events",
            )
        )
    finally:
        connection.close()
    with pytest.raises(ReviewError) as raised:
        service.start_suggestion(
            replace(
                make_start_suggestion_command(),
                idempotency_key="00000000-0000-4000-8000-000000000099",
            ),
            fixture_human_reviewer,
        )
    assert raised.value.code == "FMEA_REVIEW_RATE_LIMITED"
    connection = seeded_review_repository._connect()
    try:
        after = tuple(
            connection.execute(query).fetchone()["count"]
            for query in (
                "SELECT COUNT(*) AS count FROM review_suggestion_runs",
                "SELECT COUNT(*) AS count FROM idempotency_records",
                "SELECT COUNT(*) AS count FROM audit_events",
            )
        )
    finally:
        connection.close()
    assert after == before
