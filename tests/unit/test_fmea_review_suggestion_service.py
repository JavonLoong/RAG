from __future__ import annotations

from dataclasses import replace

import pytest

from core_domain.fmea.states import RunStatus
from fmea_application.review_errors import ReviewError


def test_start_suggestion_persists_before_executor_submission(
    recording_review_service, recording_repository, recording_executor,
    fixture_human_reviewer, fixture_start_suggestion_command
) -> None:
    run = recording_review_service.start_suggestion(
        fixture_start_suggestion_command, fixture_human_reviewer
    )
    assert run.status is RunStatus.QUEUED
    assert recording_repository.calls[0] == "reserve_suggestion_run"
    assert recording_executor.calls == [(run.run_id, True)]


def test_model_suggestion_never_mutates_row(
    inline_review_service, seeded_review_repository,
    fixture_human_reviewer, fixture_start_suggestion_command
) -> None:
    before = seeded_review_repository.get_row("row-1", "ws-1")
    run = inline_review_service.start_suggestion(
        fixture_start_suggestion_command, fixture_human_reviewer
    )
    after = seeded_review_repository.get_row("row-1", "ws-1")
    assert run.status in {RunStatus.QUEUED, RunStatus.SUCCEEDED}
    assert after == before
    suggestion = seeded_review_repository.list_suggestions("row-1", "ws-1")[0]
    assert suggestion.model_manifest.model == "deepseek-v4-pro"
    assert suggestion.model_manifest.prompt_hash.startswith("sha256:")


def test_finished_suggestion_is_marked_stale_when_row_version_changed(
    suggestion_worker, seeded_review_repository,
    running_suggestion_run, advance_seeded_row_to_version_2,
) -> None:
    advance_seeded_row_to_version_2()
    completed = suggestion_worker(running_suggestion_run.run_id)
    assert completed.status is RunStatus.SUCCEEDED
    assert seeded_review_repository.list_suggestions("row-1", "ws-1")[0].stale is True


def test_exact_start_replay_skips_current_version_check(
    inline_review_service, inline_executor, seeded_review_repository,
    fixture_human_reviewer, fixture_start_suggestion_command,
    advance_seeded_row_to_version_2,
) -> None:
    first = inline_review_service.start_suggestion(
        fixture_start_suggestion_command, fixture_human_reviewer
    )
    advance_seeded_row_to_version_2()
    replay = inline_review_service.start_suggestion(
        fixture_start_suggestion_command, fixture_human_reviewer
    )
    assert replay == first
    assert len(inline_executor.calls) == 1


@pytest.mark.parametrize("failure", ["generator", "executor"])
def test_failed_or_rejected_worker_has_safe_terminal_state(
    recording_review_service, recording_repository, recording_executor,
    fixture_human_reviewer, fixture_start_suggestion_command, failure,
) -> None:
    if failure == "generator":
        recording_review_service._suggestion_generator.generate = lambda request: (_ for _ in ()).throw(RuntimeError("secret"))
    else:
        recording_executor.submit = lambda run_id, operation: (_ for _ in ()).throw(
            ReviewError("FMEA_REVIEW_RATE_LIMITED", "review execution capacity is full", retryable=True)
        )
    run = recording_review_service.start_suggestion(
        fixture_start_suggestion_command, fixture_human_reviewer
    )
    assert run.status is RunStatus.QUEUED
    if failure == "generator":
        recording_executor.operations[run.run_id]()
    stored = recording_repository.get_suggestion_run(run.run_id, "ws-1")
    assert stored is not None
    assert stored.status is RunStatus.FAILED
    assert stored.error_code in {"FMEA_MODEL_SUGGESTION_UNAVAILABLE", "FMEA_REVIEW_RATE_LIMITED"}


def test_distinct_fifth_active_reservation_is_rate_limited_without_side_effects(
    recording_review_service, recording_repository,
    fixture_human_reviewer, fixture_start_suggestion_command,
) -> None:
    for index in range(4):
        command = replace(
            fixture_start_suggestion_command,
            idempotency_key=f"00000000-0000-4000-8000-{index + 2:012d}",
        )
        recording_review_service.start_suggestion(command, fixture_human_reviewer)
    before = (len(recording_repository.runs), len(recording_repository.reservations), len(recording_repository.audits))
    command = replace(
        fixture_start_suggestion_command,
        idempotency_key="00000000-0000-4000-8000-000000000099",
    )
    with pytest.raises(ReviewError) as raised:
        recording_review_service.start_suggestion(command, fixture_human_reviewer)
    assert raised.value.code == "FMEA_REVIEW_RATE_LIMITED"
    assert (len(recording_repository.runs), len(recording_repository.reservations), len(recording_repository.audits)) == before
