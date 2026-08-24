from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import orjson
import pytest

from core_domain.fmea.codec import encode_json
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.states import PublicationStatus, ReviewStatus
from core_domain.structured_generation import (
    CriticReport,
    CriticVerdict,
    GenerationIssue,
    GenerationRunResult,
    GenerationRunStatus,
    GenerationStage,
    ModelCallTrace,
    StructuredGenerationError,
)
from core_domain.structured_output import (
    CandidateClaim,
    ClaimState,
    StructuredCandidate,
    StructuredCandidateBatch,
    StructuredOutputError,
)
from fmea_application import FmeaAdaptationResult
from scripts.structured_generation_skill import main

ROOT = Path(__file__).parents[2]
PROFILE = ROOT / "templates" / "fmea_profiles" / "fuel-combustion-fmea-full.json"


class FakeService:
    def __init__(
        self,
        result: GenerationRunResult,
        *,
        adaptation: FmeaAdaptationResult | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.result = result
        self.adaptation = adaptation
        self.error = error
        self.calls: list[str] = []

    def run(self, **_: object) -> GenerationRunResult:
        self.calls.append("run")
        if self.error is not None:
            raise self.error
        return self.result

    def run_fmea(self, **_: object) -> tuple[GenerationRunResult, FmeaAdaptationResult]:
        self.calls.append("run_fmea")
        if self.error is not None:
            raise self.error
        assert self.adaptation is not None
        return self.result, self.adaptation


def _batch(pack_id: str) -> StructuredCandidateBatch:
    return StructuredCandidateBatch(
        template_id="demo",
        template_version="1.0.0",
        template_hash="a" * 64,
        evidence_pack_id=pack_id,
        candidates=(
            StructuredCandidate(
                candidate_id="candidate-1",
                payload={"result": "safe"},
                claims=(CandidateClaim("/result", ClaimState.UNKNOWN, ()),),
            ),
        ),
    )


def _result(pack_id: str, status: GenerationRunStatus = GenerationRunStatus.SUCCEEDED) -> GenerationRunResult:
    batch = _batch(pack_id) if status is not GenerationRunStatus.FAILED else None
    critic = (
        CriticReport(verdict=CriticVerdict.ACCEPT, findings=(), summary="accepted")
        if status is GenerationRunStatus.SUCCEEDED
        else None
    )
    issues = (
        (
            GenerationIssue(
                code="MODEL_TIMEOUT",
                message="provider-private-marker",
                stage=GenerationStage.GENERATE,
                retryable=True,
            ),
        )
        if status is GenerationRunStatus.FAILED
        else ()
    )
    return GenerationRunResult(
        run_id="run-1",
        status=status,
        batch=batch,
        critic_report=critic,
        deterministic_issues=(),
        generation_issues=issues,
        traces=(),
        repair_count=0,
    )


def _files(tmp_path: Path, fixture_pack, fixture_analysis, *, request: object | None = None):
    pack_path = tmp_path / "pack.json"
    analysis_path = tmp_path / "analysis.json"
    request_path = tmp_path / "request.json"
    pack_path.write_text(encode_json(fixture_pack), encoding="utf-8")
    analysis_path.write_text(encode_json(fixture_analysis), encoding="utf-8")
    request_path.write_text(
        json.dumps(request or {"run_id": "run-1", "task": "request-private-marker"}),
        encoding="utf-8",
    )
    return pack_path, analysis_path, request_path


def _run_args(tmp_path: Path, pack_path: Path, request_path: Path) -> list[str]:
    return [
        "run",
        "--template",
        "demo@1.0.0",
        "--pack",
        str(pack_path),
        "--registry",
        str(tmp_path / "registry-private-marker"),
        "--request",
        str(request_path),
    ]


def test_run_emits_one_success_envelope(
    tmp_path: Path,
    fixture_pack,
    fixture_analysis,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack_path, _, request_path = _files(tmp_path, fixture_pack, fixture_analysis)
    service = FakeService(_result(fixture_pack.pack_id))

    exit_code = main(_run_args(tmp_path, pack_path, request_path), compose=lambda _: service)
    captured = capsys.readouterr()
    body = orjson.loads(captured.out)

    assert (exit_code, body["schema_version"], body["status"], captured.err) == (
        0,
        "rag.structured-generation.v1",
        "succeeded",
        "",
    )
    assert service.calls == ["run"]
    assert captured.out.count("rag.structured-generation.v1") == 1


def test_pretty_output_is_still_exactly_one_json_object(
    tmp_path: Path,
    fixture_pack,
    fixture_analysis,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack_path, _, request_path = _files(tmp_path, fixture_pack, fixture_analysis)
    args = [*_run_args(tmp_path, pack_path, request_path), "--pretty"]

    exit_code = main(args, compose=lambda _: FakeService(_result(fixture_pack.pack_id)))
    captured = capsys.readouterr()

    assert exit_code == 0
    assert orjson.loads(captured.out)["schema_version"] == "rag.structured-generation.v1"
    assert captured.out.count("\n{") == 0
    assert captured.err == ""


def test_run_fmea_outputs_unpersisted_suggestion(
    tmp_path: Path,
    fixture_pack,
    fixture_analysis,
    fixture_row,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack_path, analysis_path, request_path = _files(tmp_path, fixture_pack, fixture_analysis)
    row = replace(
        fixture_row,
        risk_assessment=None,
        review_status=ReviewStatus.SUGGESTED,
        publication_status=PublicationStatus.UNPUBLISHED,
    )
    service = FakeService(
        _result(fixture_pack.pack_id),
        adaptation=FmeaAdaptationResult(rows=(row,), issues=(), needs_review=False),
    )
    args = [
        "run-fmea",
        "--template",
        "demo@1.0.0",
        "--pack",
        str(pack_path),
        "--analysis",
        str(analysis_path),
        "--profile",
        str(PROFILE),
        "--registry",
        str(tmp_path / "registry"),
        "--request",
        str(request_path),
    ]

    exit_code = main(args, compose=lambda _: service)
    body = orjson.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert body["result"]["fmea"]["persisted"] is False
    assert body["result"]["fmea"]["rows"][0]["review_status"] == "suggested"
    assert body["result"]["fmea"]["rows"][0]["publication_status"] == "unpublished"


def test_run_fmea_adaptation_review_flag_controls_process_status(
    tmp_path: Path,
    fixture_pack,
    fixture_analysis,
    fixture_row,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack_path, analysis_path, request_path = _files(tmp_path, fixture_pack, fixture_analysis)
    service = FakeService(
        _result(fixture_pack.pack_id),
        adaptation=FmeaAdaptationResult(rows=(fixture_row,), issues=(), needs_review=True),
    )
    args = [
        "run-fmea",
        "--template",
        "demo@1.0.0",
        "--pack",
        str(pack_path),
        "--analysis",
        str(analysis_path),
        "--profile",
        str(PROFILE),
        "--registry",
        str(tmp_path / "registry"),
        "--request",
        str(request_path),
    ]

    exit_code = main(args, compose=lambda _: service)
    body = orjson.loads(capsys.readouterr().out)

    assert (exit_code, body["status"], body["result"]["fmea"]["needs_review"]) == (
        4,
        "needs_review",
        True,
    )


@pytest.mark.parametrize(
    ("status", "expected_exit"),
    [
        (GenerationRunStatus.NEEDS_REVIEW, 4),
        (GenerationRunStatus.FAILED, 5),
    ],
)
def test_result_status_has_stable_exit_class(
    tmp_path: Path,
    fixture_pack,
    fixture_analysis,
    capsys: pytest.CaptureFixture[str],
    status: GenerationRunStatus,
    expected_exit: int,
) -> None:
    pack_path, _, request_path = _files(tmp_path, fixture_pack, fixture_analysis)

    exit_code = main(
        _run_args(tmp_path, pack_path, request_path),
        compose=lambda _: FakeService(_result(fixture_pack.pack_id, status)),
    )
    body = orjson.loads(capsys.readouterr().out)

    assert (exit_code, body["status"]) == (expected_exit, status.value)


@pytest.mark.parametrize(
    ("error", "expected_exit"),
    [
        (StructuredOutputError("TEMPLATE_NOT_FOUND", "path-private-marker"), 3),
        (StructuredOutputError("REGISTRY_PRIVATE_MARKER", "private-marker"), 3),
        (
            StructuredGenerationError(
                "MODEL_CONFIGURATION_INVALID",
                "key-private-marker",
            ),
            3,
        ),
        (
            StructuredGenerationError(
                "FMEA_ADAPTER_UNAVAILABLE",
                "adapter-private-marker",
            ),
            3,
        ),
        (
            StructuredGenerationError(
                "GENERATION_REQUEST_INVALID",
                "request-private-marker",
            ),
            2,
        ),
        (FmeaDomainError("profile-private-marker"), 3),
        (RuntimeError("internal-private-marker"), 1),
    ],
)
def test_boundary_errors_are_safe_and_have_stable_exit_class(
    tmp_path: Path,
    fixture_pack,
    fixture_analysis,
    capsys: pytest.CaptureFixture[str],
    error: BaseException,
    expected_exit: int,
) -> None:
    pack_path, _, request_path = _files(tmp_path, fixture_pack, fixture_analysis)
    exit_code = main(
        _run_args(tmp_path, pack_path, request_path),
        compose=lambda _: FakeService(_result(fixture_pack.pack_id), error=error),
    )
    output = capsys.readouterr().out

    assert exit_code == expected_exit
    assert "private-marker" not in output
    assert "PRIVATE_MARKER" not in output


def test_missing_input_file_is_validation_exit_without_stderr(
    tmp_path: Path,
    fixture_pack,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing-private-marker.json"
    args = _run_args(tmp_path, missing, missing)

    exit_code = main(args, compose=lambda _: FakeService(_result(fixture_pack.pack_id)))
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "private-marker" not in captured.out
    assert captured.err == ""


def test_help_flag_cannot_bypass_the_one_object_process_envelope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["--help"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert orjson.loads(captured.out)["error"]["class"] == "validation"
    assert captured.err == ""


def test_smoke_without_key_is_configuration_exit_and_does_not_compose_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    exit_code = main(
        ["smoke"],
        compose=lambda _: pytest.fail("smoke must not compose the generation service"),
    )
    captured = capsys.readouterr()

    assert exit_code == 3
    assert orjson.loads(captured.out)["error"]["code"] == "MODEL_CONFIGURATION_INVALID"
    assert captured.err == ""


def test_parser_unknown_request_fields_and_bounded_reads_are_validation_errors(
    tmp_path: Path,
    fixture_pack,
    fixture_analysis,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack_path, _, bad_request = _files(
        tmp_path,
        fixture_pack,
        fixture_analysis,
        request={"run_id": "run-1", "task": "safe", "model": "override"},
    )
    service = FakeService(_result(fixture_pack.pack_id))

    assert main(_run_args(tmp_path, pack_path, bad_request), compose=lambda _: service) == 2
    capsys.readouterr()
    oversized = tmp_path / "oversized.json"
    oversized.write_text("x" * 70_000, encoding="utf-8")
    assert main(_run_args(tmp_path, pack_path, oversized), compose=lambda _: service) == 2
    capsys.readouterr()
    abbreviated = _run_args(tmp_path, pack_path, bad_request)
    abbreviated[abbreviated.index("--registry")] = "--reg"
    assert main(abbreviated, compose=lambda _: service) == 2


def test_success_and_failure_envelopes_do_not_leak_inputs_or_raw_model_text(
    tmp_path: Path,
    fixture_pack,
    fixture_analysis,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_ref = replace(
        fixture_pack.refs[0],
        quote="evidence-private-marker",
        normalized_quote="evidence private marker",
    )
    private_pack = replace(fixture_pack, refs=(private_ref,))
    pack_path, _, request_path = _files(tmp_path, private_pack, fixture_analysis)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key-private-marker")

    for status in (GenerationRunStatus.SUCCEEDED, GenerationRunStatus.FAILED):
        active_result = _result(private_pack.pack_id, status)
        if status is GenerationRunStatus.SUCCEEDED:
            active_result = replace(
                active_result,
                traces=(
                    ModelCallTrace(
                        stage=GenerationStage.GENERATE,
                        model_id="deepseek-v4-flash",
                        prompt_hash="b" * 64,
                        response_hash="c" * 64,
                        http_attempts=1,
                        input_tokens=1,
                        output_tokens=1,
                        finish_reason="finish-private-marker",
                        error_code=None,
                    ),
                ),
            )
        exit_code = main(
            _run_args(tmp_path, pack_path, request_path),
            compose=lambda _, run_result=active_result: FakeService(run_result),
        )
        assert exit_code in {0, 5}
        output = capsys.readouterr().out
        for marker in (
            "request-private-marker",
            "evidence-private-marker",
            "registry-private-marker",
            "provider-private-marker",
            "finish-private-marker",
            "key-private-marker",
        ):
            assert marker not in output
