"""Focused integration tests for the service-facing FMEA review CLI."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest

from core_domain.fmea.states import PublicationStatus, ReviewStatus, RunStatus
from fmea_application import ReviewError
from fmea_application.review_contracts import (
    ActorContext,
    ReviewDecisionResult,
    ReviewSuggestionRun,
)
from scripts import fmea_skill


def valid_decision_request() -> dict[str, object]:
    return {
        "row_id": "row-1",
        "expected_record_version": 1,
        "idempotency_key": "00000000-0000-4000-8000-000000000011",
        "action": "accept",
        "suggestion_id": None,
        "reason_code": "ACCEPT_AS_IS",
        "reason": "Human reviewer accepts the supported row.",
        "edits": [],
        "evidence_requests": [],
        "unresolved_acknowledgements": [],
    }


@dataclass(frozen=True)
class FakeCliRuntime:
    service: Any
    actor: ActorContext
    close: Callable[[], None]


@dataclass
class FakeReviewService:
    context: Any
    queued_run: ReviewSuggestionRun
    terminal_run: ReviewSuggestionRun
    decisions: tuple[Any, ...]
    decision_result: ReviewDecisionResult
    calls: list[str] = field(default_factory=list)
    status_values: list[ReviewSuggestionRun] = field(default_factory=list)
    error: ReviewError | None = None

    def get_context(self, row_id: str, actor: ActorContext) -> Any:
        self.calls.append("get_context")
        if self.error is not None:
            raise self.error
        return self.context

    def start_suggestion(self, command: Any, actor: ActorContext) -> ReviewSuggestionRun:
        self.calls.append("start_suggestion")
        if self.error is not None:
            raise self.error
        return self.queued_run

    def get_suggestion_run(self, run_id: str, actor: ActorContext) -> ReviewSuggestionRun:
        self.calls.append("get_suggestion_run")
        if self.error is not None:
            raise self.error
        if self.status_values:
            return self.status_values.pop(0)
        return self.terminal_run

    def submit_decision(self, command: Any, actor: ActorContext) -> ReviewDecisionResult:
        self.calls.append("submit_decision")
        if self.error is not None:
            raise self.error
        return self.decision_result

    def list_decisions(self, row_id: str, actor: ActorContext) -> tuple[Any, ...]:
        self.calls.append("list_decisions")
        if self.error is not None:
            raise self.error
        return self.decisions


def fake_cli_runtime(
    fake_review_service: FakeReviewService,
    actor: ActorContext,
    close_calls: list[int] | None = None,
) -> FakeCliRuntime:
    def close() -> None:
        if close_calls is not None:
            close_calls.append(1)

    return FakeCliRuntime(fake_review_service, actor, close)


@pytest.fixture
def fake_review_service(
    fixture_review_context: Any,
    fixture_suggestion_run: ReviewSuggestionRun,
    fixture_review_row: Any,
    fixture_decision_record: Any,
) -> FakeReviewService:
    terminal_run = ReviewSuggestionRun(
        run_id="run-1",
        row_id="row-1",
        source_record_version=1,
        status=RunStatus.SUCCEEDED,
        suggestion_id="suggestion-1",
        error_code=None,
        retryable=False,
        request_id="request-1",
        trace_id="trace-1",
        created_at="2026-08-25T00:00:00Z",
        started_at="2026-08-25T00:00:01Z",
        finished_at="2026-08-25T00:00:02Z",
    )
    decision_result = ReviewDecisionResult(
        decision_id="decision-1",
        row=fixture_review_row,
        previous_record_version=1,
        record_version=2,
        review_status=ReviewStatus.ACCEPTED,
        publication_status=PublicationStatus.UNPUBLISHED,
        audit_event_id="audit-1",
        suggestion_id=None,
        evidence_requests=(),
        persisted=True,
        request_id="request-2",
        trace_id="trace-2",
    )
    return FakeReviewService(
        context=fixture_review_context,
        queued_run=fixture_suggestion_run,
        terminal_run=terminal_run,
        decisions=(fixture_decision_record,),
        decision_result=decision_result,
    )


@pytest.fixture
def fake_actor(fixture_human_reviewer: ActorContext) -> ActorContext:
    return fixture_human_reviewer


def test_context_emits_one_v1_json_object(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_review_service: FakeReviewService,
    fake_actor: ActorContext,
) -> None:
    close_calls: list[int] = []
    monkeypatch.setattr(
        fmea_skill,
        "build_cli_runtime",
        lambda: fake_cli_runtime(fake_review_service, fake_actor, close_calls),
    )

    exit_code = fmea_skill.main(["review", "context", "--row-id", "row-1"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["schema_version"] == "graphrag.fmea.v1"
    assert payload["resource_type"] == "review_context"
    assert "field_evidence" not in payload["data"]["row"]
    assert "workspace_id" not in payload["data"]["evidence"]
    assert "prompt_hash" not in captured.out
    assert captured.out.count("\n") == 1
    assert captured.err == ""
    assert close_calls == [1]
    assert fake_review_service.calls == ["get_context"]


def test_successful_suggestion_output_omits_private_model_and_reasoning_markers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_review_service: FakeReviewService,
    fake_actor: ActorContext,
    fixture_review_suggestion: Any,
) -> None:
    fake_review_service.context = replace(
        fake_review_service.context,
        latest_suggestion=fixture_review_suggestion,
    )
    monkeypatch.setattr(
        fmea_skill,
        "build_cli_runtime",
        lambda: fake_cli_runtime(fake_review_service, fake_actor),
    )

    exit_code = fmea_skill.main(["review", "context", "--row-id", "row-1"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "test-provider" not in captured.out
    assert "test-model" not in captured.out
    assert "The current control is supported." not in captured.out
    assert "The candidate is supported by the current evidence." not in captured.out
    assert "prompt_hash" not in captured.out


def test_decide_requires_explicit_human_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    fake_review_service: FakeReviewService,
    fake_actor: ActorContext,
) -> None:
    request = tmp_path / "decision.json"
    request.write_text(json.dumps(valid_decision_request()), encoding="utf-8")
    monkeypatch.setattr(
        fmea_skill,
        "build_cli_runtime",
        lambda: pytest.fail("runtime must not be constructed without confirmation"),
    )

    exit_code = fmea_skill.main(["review", "decide", "--request-file", str(request)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["error"]["code"] == "FMEA_REVIEW_CONFIRMATION_REQUIRED"
    assert fake_review_service.calls == []


def test_cli_never_accepts_or_echoes_token_argument(
    capsys: pytest.CaptureFixture[str],
) -> None:
    marker = "TOPSECRET-review-token"

    exit_code = fmea_skill.main(["review", "context", "--row-id", "row-1", "--token", marker])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert marker not in captured.out + captured.err
    assert captured.err == ""


def test_suggest_polls_until_persistent_run_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_review_service: FakeReviewService,
    fake_actor: ActorContext,
) -> None:
    close_calls: list[int] = []
    fake_review_service.status_values = [fake_review_service.terminal_run]
    monkeypatch.setattr(fmea_skill.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        fmea_skill,
        "build_cli_runtime",
        lambda: fake_cli_runtime(fake_review_service, fake_actor, close_calls),
    )

    exit_code = fmea_skill.main(
        [
            "review",
            "suggest",
            "--row-id",
            "row-1",
            "--record-version",
            "1",
            "--idempotency-key",
            "00000000-0000-4000-8000-000000000011",
            "--focus-field",
            "controls",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["resource_type"] == "review_suggestion_run"
    assert payload["data"]["status"] == "succeeded"
    assert fake_review_service.calls == ["start_suggestion", "get_suggestion_run"]
    assert close_calls == [1]


def test_suggest_deadline_returns_latest_run_and_closes_runtime(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_review_service: FakeReviewService,
    fake_actor: ActorContext,
) -> None:
    close_calls: list[int] = []
    monkeypatch.setattr(fmea_skill, "SUGGESTION_DEADLINE_SECONDS", 0.0)
    monkeypatch.setattr(
        fmea_skill,
        "build_cli_runtime",
        lambda: fake_cli_runtime(fake_review_service, fake_actor, close_calls),
    )

    exit_code = fmea_skill.main(
        [
            "review",
            "suggest",
            "--row-id",
            "row-1",
            "--record-version",
            "1",
            "--idempotency-key",
            "00000000-0000-4000-8000-000000000011",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 6
    assert payload["data"]["run_id"] == "run-1"
    assert payload["error"]["code"] == "FMEA_MODEL_SUGGESTION_UNAVAILABLE"
    assert close_calls == [1]


@pytest.mark.parametrize("review_command", ["suggest", "suggestion-status"])
def test_failed_suggestion_emits_error_envelope_and_closes_once(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_review_service: FakeReviewService,
    fake_actor: ActorContext,
    review_command: str,
) -> None:
    failed_run = replace(
        fake_review_service.terminal_run,
        status=RunStatus.FAILED,
        suggestion_id=None,
        error_code="FMEA_MODEL_SUGGESTION_UNAVAILABLE",
        retryable=True,
    )
    fake_review_service.terminal_run = failed_run
    if review_command == "suggest":
        fake_review_service.status_values = [failed_run]
    close_calls: list[int] = []
    monkeypatch.setattr(
        fmea_skill,
        "build_cli_runtime",
        lambda: fake_cli_runtime(fake_review_service, fake_actor, close_calls),
    )

    argv = ["review", review_command]
    if review_command == "suggest":
        argv += [
            "--row-id",
            "row-1",
            "--record-version",
            "1",
            "--idempotency-key",
            "00000000-0000-4000-8000-000000000011",
        ]
    else:
        argv += ["--run-id", "run-1"]

    exit_code = fmea_skill.main(argv)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 6
    assert payload["status"] == "error"
    assert payload["resource_type"] == "review_suggestion_run"
    assert payload["error"]["code"] == "FMEA_MODEL_SUGGESTION_UNAVAILABLE"
    assert payload["data"]["run_id"] == "run-1"
    assert payload["data"]["status"] == "failed"
    assert close_calls == [1]


@pytest.mark.parametrize(
    ("error_code", "expected_exit"),
    [
        ("FMEA_REVIEW_REQUEST_INVALID", 2),
        ("FMEA_ROW_NOT_FOUND", 3),
        ("FMEA_AUTH_REQUIRED", 4),
        ("FMEA_VERSION_CONFLICT", 5),
        ("FMEA_MODEL_SUGGESTION_INVALID", 6),
        ("FMEA_REVIEW_STORAGE_UNAVAILABLE", 7),
    ],
)
def test_review_error_exit_mapping(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_review_service: FakeReviewService,
    fake_actor: ActorContext,
    error_code: str,
    expected_exit: int,
) -> None:
    close_calls: list[int] = []
    fake_review_service.error = ReviewError(error_code, "safe public detail", retryable=True)
    monkeypatch.setattr(
        fmea_skill,
        "build_cli_runtime",
        lambda: fake_cli_runtime(fake_review_service, fake_actor, close_calls),
    )

    exit_code = fmea_skill.main(["review", "context", "--row-id", "row-1"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == expected_exit
    assert payload["status"] == "error"
    assert payload["error"]["code"] == error_code
    assert payload["error"]["detail"] == "safe public detail"
    assert close_calls == [1]


def test_decision_request_is_passed_to_service_after_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    fake_review_service: FakeReviewService,
    fake_actor: ActorContext,
) -> None:
    request = tmp_path / "decision.json"
    request.write_text(json.dumps(valid_decision_request()), encoding="utf-8")
    close_calls: list[int] = []
    monkeypatch.setattr(
        fmea_skill,
        "build_cli_runtime",
        lambda: fake_cli_runtime(fake_review_service, fake_actor, close_calls),
    )

    exit_code = fmea_skill.main(
        [
            "review",
            "decide",
            "--request-file",
            str(request),
            "--confirm-human-review",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["resource_type"] == "review_decision"
    assert payload["data"]["decision_id"] == "decision-1"
    assert fake_review_service.calls == ["submit_decision"]
    assert close_calls == [1]


def test_invalid_decision_domain_value_is_sanitized_and_closes_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    fake_review_service: FakeReviewService,
    fake_actor: ActorContext,
) -> None:
    request_payload = valid_decision_request()
    request_payload["action"] = "not-an-action"
    request = tmp_path / "decision.json"
    request.write_text(json.dumps(request_payload), encoding="utf-8")
    close_calls: list[int] = []
    monkeypatch.setattr(
        fmea_skill,
        "build_cli_runtime",
        lambda: fake_cli_runtime(fake_review_service, fake_actor, close_calls),
    )

    exit_code = fmea_skill.main(
        [
            "review",
            "decide",
            "--request-file",
            str(request),
            "--confirm-human-review",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["error"]["code"] == "FMEA_REVIEW_REQUEST_INVALID"
    assert fake_review_service.calls == []
    assert close_calls == [1]
