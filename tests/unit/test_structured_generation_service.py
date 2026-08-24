from __future__ import annotations

from core_domain.fmea.value_objects import EvidencePack
from core_domain.structured_generation import (
    GenerationBudget,
    GenerationRunResult,
    GenerationRunStatus,
)
from structured_generation_application import (
    GenerationRunRequest,
    StructuredGenerationService,
)
from structured_output_application import TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source


def _compiled_template():
    return TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=load_template_source,
    ).compile({
        "template": {
            "id": "service-timeout-test",
            "version": "1.0.0",
            "title": "Service timeout test",
            "description": "",
            "domain_tags": [],
            "schema_dialect": "https://json-schema.org/draft/2020-12/schema",
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"result": {"type": "string"}},
        },
        "evidence_bindings": [],
    })


class _Registry:
    def __init__(self) -> None:
        self.template = _compiled_template()

    def get(self, template_id: str, version: str):
        assert (template_id, version) == ("service-timeout-test", "1.0.0")
        return self.template


class _RecordingPipeline:
    def __init__(self) -> None:
        self.request: GenerationRunRequest | None = None

    def run(self, request: GenerationRunRequest) -> GenerationRunResult:
        self.request = request
        return GenerationRunResult(
            run_id=request.run_id,
            status=GenerationRunStatus.FAILED,
            batch=None,
            critic_report=None,
            deterministic_issues=(),
            generation_issues=(),
            traces=(),
            repair_count=0,
        )


def test_service_passes_explicit_budget_into_pipeline(fixture_pack: EvidencePack) -> None:
    pipeline = _RecordingPipeline()
    service = StructuredGenerationService(registry=_Registry(), pipeline=pipeline)  # type: ignore[arg-type]
    budget = GenerationBudget(request_timeout_seconds=90.0, total_timeout_seconds=300.0)

    service.run(
        run_id="run-1",
        task="Generate a bounded candidate.",
        template_id="service-timeout-test",
        version="1.0.0",
        evidence_pack=fixture_pack,
        budget=budget,
    )

    assert pipeline.request is not None
    assert pipeline.request.budget is budget
