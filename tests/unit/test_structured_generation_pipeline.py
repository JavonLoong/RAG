from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

import pytest

from core_domain.fmea.value_objects import EvidencePack
from core_domain.structured_generation import (
    GenerationBudget,
    GenerationRunStatus,
    GenerationStage,
    StructuredGenerationError,
    StructuredModelRequest,
    StructuredModelResponse,
)
from structured_generation_application import GenerationRunRequest, StructuredGenerationPipeline
from structured_generation_infrastructure import StrictCandidateBatchCodec, StrictCriticReportCodec
from structured_output_application import StructuredCandidateValidator, TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source


class QueueGateway:
    def __init__(self, values: Iterable[StructuredModelResponse | BaseException]) -> None:
        self.values = list(values)
        self.calls: list[tuple[StructuredModelRequest, int, float]] = []

    def complete(
        self,
        request: StructuredModelRequest,
        *,
        max_attempts: int,
        timeout_seconds: float,
    ) -> StructuredModelResponse:
        self.calls.append((request, max_attempts, timeout_seconds))
        value = self.values.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def _template():
    source = {
        "template": {
            "id": "failure-demo",
            "version": "1.0.0",
            "title": "Failure demo",
            "description": "",
            "domain_tags": ["demo"],
            "schema_dialect": "https://json-schema.org/draft/2020-12/schema",
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["failure_mode"],
            "properties": {"failure_mode": {"type": "string", "minLength": 1}},
        },
        "evidence_bindings": [
            {
                "target": "/failure_mode",
                "requirement": "required",
                "min_refs": 1,
                "allowed_source_types": ["primary_document"],
            }
        ],
    }
    return TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=load_template_source,
    ).compile(source)


def _request(pack: EvidencePack, *, budget: GenerationBudget | None = None) -> GenerationRunRequest:
    return GenerationRunRequest(
        run_id="run-1",
        task="Extract one failure mode.",
        template=_template(),
        evidence_pack=pack,
        budget=budget or GenerationBudget(),
    )


def _batch_json(pack: EvidencePack, *, valid: bool = True) -> str:
    template = _template()
    return json.dumps(
        {
            "template_id": template.metadata.template_id,
            "template_version": template.metadata.version,
            "template_hash": template.template_hash,
            "evidence_pack_id": pack.pack_id,
            "candidates": [
                {
                    "candidate_id": "candidate-1",
                    "payload": {"failure_mode": "pressure loss" if valid else 7},
                    "claims": [
                        {"target": "/failure_mode", "state": "known", "evidence_ids": ["ev-1"]}
                    ],
                }
            ],
        }
    )


def _critic_json(*, verdict: str = "accept", support: str = "supported") -> str:
    return json.dumps(
        {
            "verdict": verdict,
            "findings": [
                {
                    "candidate_id": "candidate-1",
                    "target": "/failure_mode",
                    "support": support,
                    "code": "EVIDENCE_SUPPORTS_CLAIM",
                    "evidence_ids": ["ev-1"],
                    "explanation": "The evidence was checked.",
                }
            ],
            "summary": "Critic completed.",
        }
    )


def _response(content: str, model_id: str, *, attempts: int = 1) -> StructuredModelResponse:
    return StructuredModelResponse(
        content=content,
        model_id=model_id,
        finish_reason="stop",
        input_tokens=10,
        output_tokens=4,
        response_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        http_attempts=attempts,
    )


def _pipeline(gateway: QueueGateway, *, monotonic=None) -> StructuredGenerationPipeline:
    kwargs = {} if monotonic is None else {"monotonic": monotonic}
    return StructuredGenerationPipeline(
        gateway=gateway,
        batch_codec=StrictCandidateBatchCodec(),
        critic_codec=StrictCriticReportCodec(),
        candidate_validator=StructuredCandidateValidator(Draft202012SchemaAdapter()),
        **kwargs,
    )


def test_valid_generation_and_accepting_critic_succeeds(fixture_pack: EvidencePack) -> None:
    gateway = QueueGateway(
        [
            _response(_batch_json(fixture_pack), "deepseek-v4-flash"),
            _response(_critic_json(), "deepseek-v4-pro"),
        ]
    )

    result = _pipeline(gateway).run(_request(fixture_pack))

    assert result.status is GenerationRunStatus.SUCCEEDED
    assert [trace.stage for trace in result.traces] == [GenerationStage.GENERATE, GenerationStage.CRITIC]
    assert result.repair_count == 0
    assert result.deterministic_issues == result.generation_issues == ()


def test_deterministic_invalid_then_critic_repair_is_never_automatic_success(
    fixture_pack: EvidencePack,
) -> None:
    gateway = QueueGateway(
        [
            _response(_batch_json(fixture_pack, valid=False), "deepseek-v4-flash"),
            _response(_critic_json(verdict="repair", support="not_supported"), "deepseek-v4-pro"),
            _response(_batch_json(fixture_pack), "deepseek-v4-pro"),
        ]
    )

    result = _pipeline(gateway).run(_request(fixture_pack))

    assert result.status is GenerationRunStatus.NEEDS_REVIEW
    assert [trace.stage for trace in result.traces] == [
        GenerationStage.GENERATE,
        GenerationStage.CRITIC,
        GenerationStage.REPAIR,
    ]
    assert result.repair_count == 1
    assert result.critic_report is None
    assert result.deterministic_issues == ()
    assert "CANDIDATE_SCHEMA_INVALID" in {issue.code for issue in result.generation_issues}
    assert len(gateway.calls) == 3


def test_malformed_generator_goes_directly_to_one_repair(fixture_pack: EvidencePack) -> None:
    gateway = QueueGateway(
        [
            _response("not json", "deepseek-v4-flash"),
            _response(_batch_json(fixture_pack), "deepseek-v4-pro"),
        ]
    )

    result = _pipeline(gateway).run(_request(fixture_pack))

    assert result.status is GenerationRunStatus.NEEDS_REVIEW
    assert [trace.stage for trace in result.traces] == [GenerationStage.GENERATE, GenerationStage.REPAIR]
    assert result.repair_count == 1


def test_invalid_repair_fails_without_fabricating_a_batch(fixture_pack: EvidencePack) -> None:
    gateway = QueueGateway(
        [_response("not json", "deepseek-v4-flash"), _response("still bad", "deepseek-v4-pro")]
    )

    result = _pipeline(gateway).run(_request(fixture_pack))

    assert result.status is GenerationRunStatus.FAILED
    assert result.batch is None
    assert result.repair_count == 1


def test_critic_unavailable_preserves_valid_batch_for_review(fixture_pack: EvidencePack) -> None:
    gateway = QueueGateway(
        [
            _response(_batch_json(fixture_pack), "deepseek-v4-flash"),
            StructuredGenerationError(
                "MODEL_TIMEOUT",
                "The model request timed out.",
                stage=GenerationStage.CRITIC,
                retryable=True,
                attempts=1,
            ),
        ]
    )

    result = _pipeline(gateway).run(_request(fixture_pack))

    assert result.status is GenerationRunStatus.NEEDS_REVIEW
    assert result.batch is not None
    assert result.generation_issues[-1].code == "MODEL_TIMEOUT"
    assert result.traces[-1].response_hash is None


def test_invalid_critic_preserves_valid_batch_for_review(fixture_pack: EvidencePack) -> None:
    gateway = QueueGateway(
        [
            _response(_batch_json(fixture_pack), "deepseek-v4-flash"),
            _response("{}", "deepseek-v4-pro"),
        ]
    )

    result = _pipeline(gateway).run(_request(fixture_pack))

    assert result.status is GenerationRunStatus.NEEDS_REVIEW
    assert result.batch is not None
    assert result.generation_issues[-1].code == "MODEL_OUTPUT_INVALID"


def test_attempt_and_logical_call_budgets_are_shared_across_stages(fixture_pack: EvidencePack) -> None:
    gateway = QueueGateway(
        [
            _response(_batch_json(fixture_pack), "deepseek-v4-flash", attempts=5),
            StructuredGenerationError(
                "MODEL_TIMEOUT",
                "The model request timed out.",
                stage=GenerationStage.CRITIC,
                retryable=True,
                attempts=1,
            ),
        ]
    )

    result = _pipeline(gateway).run(_request(fixture_pack))

    assert result.status is GenerationRunStatus.NEEDS_REVIEW
    assert [call[1] for call in gateway.calls] == [6, 1]
    assert sum(trace.http_attempts for trace in result.traces) == 6

    one_call = QueueGateway([_response(_batch_json(fixture_pack), "deepseek-v4-flash")])
    limited = _pipeline(one_call).run(
        _request(fixture_pack, budget=GenerationBudget(max_logical_calls=1))
    )
    assert limited.status is GenerationRunStatus.NEEDS_REVIEW
    assert len(one_call.calls) == 1
    assert limited.generation_issues[-1].code == "MODEL_CALL_LIMIT_EXCEEDED"


def test_run_deadline_is_enforced_after_a_slow_model_return(fixture_pack: EvidencePack) -> None:
    times = iter((0.0, 0.0, 91.0))
    gateway = QueueGateway([_response(_batch_json(fixture_pack), "deepseek-v4-flash")])

    result = _pipeline(gateway, monotonic=lambda: next(times)).run(_request(fixture_pack))

    assert result.status is GenerationRunStatus.FAILED
    assert result.batch is None
    assert result.generation_issues[-1].code == "MODEL_TOTAL_TIMEOUT"


def test_unexpected_gateway_exception_propagates(fixture_pack: EvidencePack) -> None:
    gateway = QueueGateway([RuntimeError("internal defect")])

    with pytest.raises(RuntimeError, match="internal defect"):
        _pipeline(gateway).run(_request(fixture_pack))
