from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from core_domain.fmea.states import RunStatus
from core_domain.structured_generation import GenerationRunStatus
from fmea_application.review_contracts import ReviewModelRequest
from fmea_application.review_errors import ReviewError
from fmea_infrastructure.review_executor import ThreadPoolReviewRunExecutor
from fmea_infrastructure.review_generator import EnvironmentReviewSuggestionGenerator


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


@pytest.mark.parametrize(
    ("case", "expected_code", "expected_retryable"),
    [
        ("noncallable", "FMEA_REVIEW_REQUEST_INVALID", False),
        ("closed", "FMEA_MODEL_SUGGESTION_UNAVAILABLE", True),
    ],
)
def test_executor_rejects_noncallable_or_closed_submission(
    case, expected_code, expected_retryable,
) -> None:
    executor = ThreadPoolReviewRunExecutor(max_workers=1, max_pending_runs=1)
    try:
        if case == "closed":
            executor.close()
            operation = lambda: None
        else:
            operation = object()
        with pytest.raises(ReviewError) as raised:
            executor.submit("run-1", operation)
        assert raised.value.code == expected_code
        assert raised.value.retryable is expected_retryable
    finally:
        executor.close()


def test_generator_maps_failed_provider_rate_limit_to_safe_unavailable(
    fixture_review_context, fixture_pack, monkeypatch,
) -> None:
    request = ReviewModelRequest(
        run_id="run-1",
        context=fixture_review_context,
        evidence_pack=fixture_pack,
        review_policy="default",
        focus_fields=(),
        template_id="fmea-row-review",
        template_version="1.0.0",
    )

    class FailedService:
        def run(self, **kwargs):
            return SimpleNamespace(
                status=GenerationRunStatus.FAILED,
                generation_issues=(SimpleNamespace(code="MODEL_RATE_LIMITED"),),
            )

    generator = EnvironmentReviewSuggestionGenerator()
    monkeypatch.setattr(generator, "_compose", lambda: (FailedService(), SimpleNamespace()))
    with pytest.raises(ReviewError) as raised:
        generator.generate(request)
    assert raised.value.code == "FMEA_MODEL_SUGGESTION_UNAVAILABLE"
    assert raised.value.retryable is True


def test_generator_rejects_stale_registered_template_hash(tmp_path, monkeypatch) -> None:
    source = Path(__file__).resolve().parents[2] / "templates" / "examples" / "fmea-row-review.yaml"
    changed_source = tmp_path / "fmea-row-review.yaml"
    changed_source.write_text(
        source.read_text(encoding="utf-8").replace(
            "Produce a bounded advisory review",
            "Produce a changed bounded advisory review",
            1,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    registry_root = tmp_path / "registry"
    EnvironmentReviewSuggestionGenerator(
        registry_root=registry_root,
        template_path=source,
    )._compose()
    with pytest.raises(ReviewError) as raised:
        EnvironmentReviewSuggestionGenerator(
            registry_root=registry_root,
            template_path=changed_source,
        )._compose()
    assert raised.value.code == "FMEA_MODEL_SUGGESTION_INVALID"
