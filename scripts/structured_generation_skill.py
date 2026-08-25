# ruff: noqa: E402 - direct script execution bootstraps the repository import root.
"""Safe one-object CLI for generic and FMEA structured-generation suggestions."""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import NoReturn, Protocol, cast

import orjson

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.value_objects import EvidencePack
from core_domain.structured_generation import (
    GenerationBudget,
    GenerationIssue,
    GenerationRunResult,
    GenerationRunStatus,
    GenerationStage,
    StructuredGenerationError,
    StructuredModelRequest,
    StructuredModelResponse,
)
from core_domain.structured_output import (
    CandidateClaim,
    JsonValue,
    StructuredCandidateBatch,
    StructuredOutputError,
    ValidationIssue,
)
from fmea_application import FmeaAdaptationResult, StructuredCandidateFmeaAdapter
from fmea_application.review_contracts import ReviewSourceSnapshot
from fmea_infrastructure import load_fmea_template_profile
from structured_generation_application import (
    StructuredGenerationPipeline,
    StructuredGenerationService,
)
from structured_generation_infrastructure import (
    StrictCandidateBatchCodec,
    StrictCriticReportCodec,
    build_deepseek_gateway_from_env,
)
from structured_output_application import StructuredCandidateValidator
from structured_output_infrastructure import Draft202012SchemaAdapter, FileTemplateRegistry

SCHEMA_VERSION = "rag.structured-generation.v1"
_MAX_REQUEST_BYTES = 64_000
_MAX_PACK_BYTES = 16_000_000
_MAX_ANALYSIS_BYTES = 2_000_000
_SAFE_MODEL_CODES = frozenset({
    "MODEL_ATTEMPT_LIMIT_EXCEEDED",
    "MODEL_AUTHENTICATION_FAILED",
    "MODEL_CALL_LIMIT_EXCEEDED",
    "MODEL_CONFIGURATION_INVALID",
    "MODEL_EMPTY_RESPONSE",
    "MODEL_ID_MISMATCH",
    "MODEL_OUTPUT_INVALID",
    "MODEL_OUTPUT_LIMIT_EXCEEDED",
    "MODEL_PROMPT_LIMIT_EXCEEDED",
    "MODEL_RATE_LIMITED",
    "MODEL_REQUEST_REJECTED",
    "MODEL_RESPONSE_INVALID",
    "MODEL_TIMEOUT",
    "MODEL_TOTAL_TIMEOUT",
    "MODEL_UPSTREAM_UNAVAILABLE",
})
_SAFE_REGISTRY_CODES = frozenset({
    "TEMPLATE_HASH_MISMATCH",
    "TEMPLATE_NOT_FOUND",
    "TEMPLATE_PATH_INVALID",
    "TEMPLATE_REGISTRY_ERROR",
    "TEMPLATE_VERSION_CONFLICT",
})


class _CliValidationError(ValueError):
    pass


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _CliValidationError from None


def _bounded_seconds(maximum: float) -> Callable[[str], float]:
    def parse(value: str) -> float:
        try:
            seconds = float(value)
        except ValueError:
            raise argparse.ArgumentTypeError from None
        if not math.isfinite(seconds) or seconds <= 0 or seconds > maximum:
            raise argparse.ArgumentTypeError
        return seconds

    return parse


class _Gateway(Protocol):
    def complete(
        self,
        request: StructuredModelRequest,
        *,
        max_attempts: int,
        timeout_seconds: float,
    ) -> StructuredModelResponse: ...


class _FmeaCodec(Protocol):
    def decode_analysis(self, payload: str) -> FmeaAnalysis: ...

    def decode_evidence_pack(self, payload: str) -> EvidencePack: ...


_FMEA_CODEC = cast("_FmeaCodec", import_module("core_domain.fmea.codec"))


@dataclass(frozen=True, slots=True)
class SmokeResult:
    status: GenerationRunStatus
    model_id: str
    response_hash: str
    http_attempts: int


def _read_bounded(path_value: str, maximum: int) -> str:
    try:
        path = Path(path_value)
        if path.stat().st_size > maximum:
            raise _CliValidationError
        data = path.read_bytes()
        if len(data) > maximum:
            raise _CliValidationError
        return data.decode("utf-8", errors="strict")
    except (OSError, UnicodeError):
        raise _CliValidationError from None


def _request_payload(path_value: str) -> tuple[str, str]:
    try:
        value = orjson.loads(_read_bounded(path_value, _MAX_REQUEST_BYTES))
    except orjson.JSONDecodeError:
        raise _CliValidationError from None
    if not isinstance(value, dict) or set(value) != {"run_id", "task"}:
        raise _CliValidationError
    run_id = value["run_id"]
    task = value["task"]
    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or len(run_id) > 256
        or not isinstance(task, str)
        or not task.strip()
        or len(task) > 4000
    ):
        raise _CliValidationError
    return run_id, task


def _template_ref(value: str) -> tuple[str, str]:
    parts = value.split("@")
    if len(parts) != 2 or not all(parts):
        raise _CliValidationError
    return parts[0], parts[1]


def _decode_pack(path_value: str) -> EvidencePack:
    try:
        return _FMEA_CODEC.decode_evidence_pack(_read_bounded(path_value, _MAX_PACK_BYTES))
    except (FmeaDomainError, KeyError, TypeError, ValueError):
        raise _CliValidationError from None


def _decode_fmea_analysis(path_value: str) -> FmeaAnalysis:
    try:
        return _FMEA_CODEC.decode_analysis(_read_bounded(path_value, _MAX_ANALYSIS_BYTES))
    except (FmeaDomainError, KeyError, TypeError, ValueError):
        raise _CliValidationError from None


def _claim(claim: CandidateClaim) -> dict[str, JsonValue]:
    return {
        "target": claim.target,
        "state": claim.state.value,
        "evidence_ids": list(claim.evidence_ids),
    }


def _batch(batch: StructuredCandidateBatch | None) -> dict[str, JsonValue] | None:
    if batch is None:
        return None
    return {
        "template_id": batch.template_id,
        "template_version": batch.template_version,
        "template_hash": batch.template_hash,
        "evidence_pack_id": batch.evidence_pack_id,
        "candidates": [
            {
                "candidate_id": candidate.candidate_id,
                "payload": candidate.payload,
                "claims": [_claim(claim) for claim in candidate.claims],
            }
            for candidate in batch.candidates
        ],
    }


def _issue_code(code: str) -> str:
    return code if code in _SAFE_MODEL_CODES or not code.startswith("MODEL_") else "MODEL_FAILED"


def _registry_code(code: str) -> str:
    return code if code in _SAFE_REGISTRY_CODES else "TEMPLATE_REGISTRY_ERROR"


def _generation_issue(issue: GenerationIssue) -> dict[str, JsonValue]:
    return {
        "code": _issue_code(issue.code),
        "stage": issue.stage.value if issue.stage is not None else None,
        "retryable": issue.retryable,
        "pointer": issue.pointer,
    }


def _validation_issue(issue: ValidationIssue) -> dict[str, JsonValue]:
    return {
        "code": issue.code,
        "pointer": issue.pointer,
        "candidate_id": issue.candidate_id,
        "target": issue.target,
        "binding": issue.binding,
    }


def _run_result(result: GenerationRunResult) -> dict[str, JsonValue]:
    critic = result.critic_report
    return {
        "batch": _batch(result.batch),
        "critic": None
        if critic is None
        else {
            "verdict": critic.verdict.value,
            "findings": [
                {
                    "candidate_id": finding.candidate_id,
                    "target": finding.target,
                    "support": finding.support.value,
                    "code": finding.code,
                    "evidence_ids": list(finding.evidence_ids),
                }
                for finding in critic.findings
            ],
        },
        "deterministic_issues": [_validation_issue(issue) for issue in result.deterministic_issues],
        "generation_issues": [_generation_issue(issue) for issue in result.generation_issues],
        "traces": [
            {
                "stage": trace.stage.value,
                "model_id": trace.model_id,
                "prompt_hash": trace.prompt_hash,
                "response_hash": trace.response_hash,
                "http_attempts": trace.http_attempts,
                "input_tokens": trace.input_tokens,
                "output_tokens": trace.output_tokens,
                "error_code": _issue_code(trace.error_code) if trace.error_code is not None else None,
            }
            for trace in result.traces
        ],
        "repair_count": result.repair_count,
    }


def _row(row: FmeaRow) -> dict[str, JsonValue]:
    return {
        "row_id": row.row_id,
        "analysis_id": row.analysis_id,
        "evidence_pack_id": row.evidence_pack_id,
        "item_id": row.item_id,
        "function_id": row.function_id,
        "failure_mode": row.failure_mode,
        "causes": list(row.causes),
        "mechanisms": list(row.mechanisms),
        "effects": list(row.effects),
        "symptoms": list(row.symptoms),
        "controls": list(row.controls),
        "barriers": list(row.barriers),
        "actions": list(row.actions),
        "risk_assessment": None,
        "field_evidence": [[name, list(ids)] for name, ids in row.field_evidence],
        "field_support": [[name, support.value] for name, support in row.field_support],
        "claim_status": row.claim_status.value,
        "review_status": row.review_status.value,
        "publication_status": row.publication_status.value,
        "record_version": row.record_version,
    }


def _source_snapshot(source: ReviewSourceSnapshot) -> dict[str, JsonValue]:
    return {
        "row_id": source.row_id,
        "source_record_version": source.source_record_version,
        "candidate_id": source.candidate_id,
        "item_label": source.item_label,
        "function_label": source.function_label,
        "template_id": source.template_id,
        "template_version": source.template_version,
        "profile_id": source.profile_id,
        "profile_version": source.profile_version,
        "generation_run_id": source.generation_run_id,
        "requested_evidence_profile": source.requested_evidence_profile.value,
        "resolved_evidence_profile": source.resolved_evidence_profile.value,
        "evidence_types": [evidence_type.value for evidence_type in source.evidence_types],
        "trace_id": source.trace_id,
        "retrieval_warnings": list(source.retrieval_warnings),
        "retrieval_incomplete": source.retrieval_incomplete,
        "field_claim_statuses": [
            [field_name, claim_status.value] for field_name, claim_status in source.field_claim_statuses
        ],
        "source_hash": source.source_hash,
    }


def _fmea(adaptation: FmeaAdaptationResult) -> dict[str, JsonValue]:
    return {
        "persisted": False,
        "needs_review": adaptation.needs_review,
        "rows": [_row(row) for row in adaptation.rows],
        "source_snapshots": [_source_snapshot(source) for source in adaptation.source_snapshots],
        "issues": [_generation_issue(issue) for issue in adaptation.issues],
    }


def _result_envelope(
    result: GenerationRunResult,
    *,
    adaptation: FmeaAdaptationResult | None = None,
    status: GenerationRunStatus | None = None,
) -> dict[str, JsonValue]:
    payload = _run_result(result)
    if adaptation is not None:
        payload["fmea"] = _fmea(adaptation)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": (status or result.status).value,
        "run_id": result.run_id,
        "result": payload,
        "error": None,
    }


def _error_envelope(code: str, error_class: str) -> dict[str, JsonValue]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": GenerationRunStatus.FAILED.value,
        "run_id": None,
        "result": None,
        "error": {
            "class": error_class,
            "code": code,
            "message": "Structured generation could not complete safely.",
        },
    }


def _emit(value: dict[str, JsonValue], *, pretty: bool) -> None:
    option = orjson.OPT_INDENT_2 if pretty else 0
    sys.stdout.buffer.write(orjson.dumps(value, option=option))
    sys.stdout.buffer.write(b"\n")


def _compose(registry_root: Path) -> StructuredGenerationService:
    schema_validator = Draft202012SchemaAdapter()
    pipeline = StructuredGenerationPipeline(
        gateway=build_deepseek_gateway_from_env(),
        batch_codec=StrictCandidateBatchCodec(),
        critic_codec=StrictCriticReportCodec(),
        candidate_validator=StructuredCandidateValidator(schema_validator),
    )
    return StructuredGenerationService(
        registry=FileTemplateRegistry(registry_root),
        pipeline=pipeline,
        fmea_adapter=StructuredCandidateFmeaAdapter(),
    )


def run_live_smoke(
    *,
    gateway: _Gateway | None = None,
    timeout_seconds: float = 30.0,
) -> SmokeResult:
    active_gateway = gateway if gateway is not None else build_deepseek_gateway_from_env()
    request = StructuredModelRequest(
        stage=GenerationStage.GENERATE,
        model_id="deepseek-v4-flash",
        system_prompt=(
            "Return exactly one JSON object matching the supplied identity and candidate contract. "
            "Do not add markdown or prose."
        ),
        user_prompt=(
            "Return template_id deepseek-connectivity-smoke, template_version 1.0.0, "
            f"template_hash {'0' * 64}, evidence_pack_id smoke-pack, and exactly one candidate "
            'with candidate_id smoke-candidate, payload {"message":"ok"}, and an empty claims array.'
        ),
        max_output_tokens=512,
        thinking_enabled=False,
        reasoning_effort=None,
    )
    response = active_gateway.complete(request, max_attempts=2, timeout_seconds=timeout_seconds)
    batch = StrictCandidateBatchCodec().decode_batch(response.content)
    expected = (
        batch.template_id == "deepseek-connectivity-smoke"
        and batch.template_version == "1.0.0"
        and batch.template_hash == "0" * 64
        and batch.evidence_pack_id == "smoke-pack"
        and len(batch.candidates) == 1
        and batch.candidates[0].candidate_id == "smoke-candidate"
        and batch.candidates[0].payload == {"message": "ok"}
        and not batch.candidates[0].claims
    )
    if not expected:
        raise StructuredGenerationError(
            "MODEL_OUTPUT_INVALID",
            "DeepSeek smoke output does not match the fixed contract.",
            stage=GenerationStage.GENERATE,
            attempts=response.http_attempts,
        )
    return SmokeResult(
        status=GenerationRunStatus.SUCCEEDED,
        model_id=response.model_id,
        response_hash=response.response_hash,
        http_attempts=response.http_attempts,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(
        prog="structured-generation-skill",
        allow_abbrev=False,
        add_help=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("run", "run-fmea"):
        active = subparsers.add_parser(command, allow_abbrev=False, add_help=False)
        active.add_argument("--template", required=True)
        active.add_argument("--pack", required=True)
        active.add_argument("--registry", required=True)
        active.add_argument("--request", required=True)
        active.add_argument("--pretty", action="store_true")
        if command == "run-fmea":
            active.add_argument("--analysis", required=True)
            active.add_argument("--profile", required=True)
            active.add_argument(
                "--request-timeout-seconds",
                type=_bounded_seconds(90.0),
                default=30.0,
            )
            active.add_argument(
                "--total-timeout-seconds",
                type=_bounded_seconds(300.0),
                default=90.0,
            )
    smoke_parser = subparsers.add_parser("smoke", allow_abbrev=False, add_help=False)
    smoke_parser.add_argument("--pretty", action="store_true")
    smoke_parser.add_argument(
        "--timeout-seconds",
        type=_bounded_seconds(60.0),
        default=30.0,
    )
    return parser


def _pretty_requested(argv: list[str] | None) -> bool:
    return "--pretty" in (sys.argv[1:] if argv is None else argv)


def _structured_error_exit(error: StructuredGenerationError) -> int:
    if error.code in {"MODEL_CONFIGURATION_INVALID", "FMEA_ADAPTER_UNAVAILABLE"}:
        return 3
    if error.code in {"GENERATION_REQUEST_INVALID", "GENERATION_CONTRACT_INVALID"}:
        return 2
    return 5


def _effective_status(
    result: GenerationRunResult,
    adaptation: FmeaAdaptationResult | None,
) -> GenerationRunStatus:
    if result.status is GenerationRunStatus.SUCCEEDED and adaptation is not None and adaptation.needs_review:
        return GenerationRunStatus.NEEDS_REVIEW
    return result.status


def main(
    argv: list[str] | None = None,
    *,
    compose: Callable[[Path], StructuredGenerationService] = _compose,
    smoke: Callable[..., SmokeResult] = run_live_smoke,
) -> int:
    pretty = _pretty_requested(argv)
    try:
        args = build_parser().parse_args(argv)
        pretty = args.pretty
        if args.command == "smoke":
            smoke_result = smoke(timeout_seconds=args.timeout_seconds)
            _emit(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": smoke_result.status.value,
                    "run_id": None,
                    "result": {
                        "smoke": {
                            "model_id": smoke_result.model_id,
                            "response_hash": smoke_result.response_hash,
                            "http_attempts": smoke_result.http_attempts,
                        }
                    },
                    "error": None,
                },
                pretty=pretty,
            )
            return 0

        template_id, template_version = _template_ref(args.template)
        run_id, task = _request_payload(args.request)
        evidence_pack = _decode_pack(args.pack)
        if args.command == "run-fmea":
            budget = GenerationBudget(
                request_timeout_seconds=args.request_timeout_seconds,
                total_timeout_seconds=args.total_timeout_seconds,
            )
            analysis = _decode_fmea_analysis(args.analysis)
            try:
                profile = load_fmea_template_profile(args.profile)
            except FmeaDomainError:
                _emit(_error_envelope("FMEA_PROFILE_INVALID", "configuration"), pretty=pretty)
                return 3
            service = compose(Path(args.registry))
            result, adaptation = service.run_fmea(
                run_id=run_id,
                task=task,
                template_id=template_id,
                version=template_version,
                evidence_pack=evidence_pack,
                analysis=analysis,
                profile=profile,
                budget=budget,
            )
        else:
            service = compose(Path(args.registry))
            result = service.run(
                run_id=run_id,
                task=task,
                template_id=template_id,
                version=template_version,
                evidence_pack=evidence_pack,
            )
            adaptation = None
        effective_status = _effective_status(result, adaptation)
        _emit(
            _result_envelope(result, adaptation=adaptation, status=effective_status),
            pretty=pretty,
        )
        return {
            GenerationRunStatus.SUCCEEDED: 0,
            GenerationRunStatus.NEEDS_REVIEW: 4,
            GenerationRunStatus.FAILED: 5,
        }[effective_status]
    except _CliValidationError:
        _emit(_error_envelope("REQUEST_VALIDATION_FAILED", "validation"), pretty=pretty)
        return 2
    except StructuredOutputError as error:
        _emit(_error_envelope(_registry_code(error.code), "registry"), pretty=pretty)
        return 3
    except StructuredGenerationError as error:
        exit_code = _structured_error_exit(error)
        error_class = {2: "validation", 3: "configuration"}.get(exit_code, "model")
        _emit(_error_envelope(_issue_code(error.code), error_class), pretty=pretty)
        return exit_code
    except FmeaDomainError:
        _emit(_error_envelope("FMEA_CONFIGURATION_INVALID", "configuration"), pretty=pretty)
        return 3
    except Exception:
        _emit(_error_envelope("INTERNAL_ERROR", "internal"), pretty=pretty)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SCHEMA_VERSION", "SmokeResult", "build_parser", "main", "run_live_smoke"]
