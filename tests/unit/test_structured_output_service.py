from __future__ import annotations

from pathlib import Path

import pytest

from core_domain.fmea.value_objects import EvidencePack
from core_domain.structured_output import ClaimState, StructuredOutputError, TemplateLimits
from structured_output_application import (
    StructuredCandidateValidator,
    StructuredOutputService,
    TemplateCompiler,
)
from structured_output_infrastructure import (
    Draft202012SchemaAdapter,
    FileTemplateRegistry,
    load_template_source,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "structured_output" / "fmea.yaml"


def service(root: Path) -> StructuredOutputService:
    adapter = Draft202012SchemaAdapter()
    compiler = TemplateCompiler(schema_validator=adapter, source_loader=load_template_source)
    return StructuredOutputService(
        compiler=compiler,
        registry=FileTemplateRegistry(root),
        schema_validator=adapter,
        candidate_validator=StructuredCandidateValidator(adapter),
    )


def test_validate_compile_register_and_get_source_use_one_service(tmp_path: Path) -> None:
    output = service(tmp_path)

    validation = output.validate_source(FIXTURE)
    compiled = output.compile_source(FIXTURE)
    registered = output.register_source(FIXTURE)
    loaded = output.get_template(compiled.metadata.template_id, compiled.metadata.version)

    assert validation.valid is True
    assert validation.compiled_template == compiled
    assert registered == loaded == compiled


def test_validate_source_returns_a_stable_report_for_bad_template(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("template: {}\n", encoding="utf-8")

    report = service(tmp_path / "registry").validate_source(invalid)

    assert report.valid is False
    assert report.compiled_template is None
    assert report.issues[0].code == "TEMPLATE_ROOT_INVALID"


def test_make_example_is_deterministic_schema_valid_and_fact_free(tmp_path: Path) -> None:
    output = service(tmp_path)
    template = output.register_source(FIXTURE)

    first = output.make_example(template.metadata.template_id, template.metadata.version)
    second = output.make_example(template.metadata.template_id, template.metadata.version)

    assert first == second
    assert first.evidence_pack_id == "example-only"
    assert len(first.candidates) == 1
    item = first.candidates[0]
    assert item.candidate_id == "example-1"
    assert item.payload == {"effects": ["?"], "failure_mode": "?", "item": "?"}
    assert all(claim.state is ClaimState.UNKNOWN for claim in item.claims)
    assert all(claim.evidence_ids == () for claim in item.claims)
    assert Draft202012SchemaAdapter().validate(item.payload, template.output_schema) == ()


class RecordingRegistry:
    def __init__(self, template) -> None:
        self.template = template
        self.calls: list[tuple[str, str]] = []

    def get(self, template_id: str, version: str):
        self.calls.append((template_id, version))
        return self.template


class RecordingValidator:
    def __init__(self) -> None:
        self.templates = []

    def validate(self, batch, template, evidence_pack):
        self.templates.append(template)
        from core_domain.structured_output import CandidateValidationReport

        return CandidateValidationReport(valid=True, issues=(), batch=batch)


def test_candidate_validation_loads_registered_template_first(
    tmp_path: Path,
    fixture_pack: EvidencePack,
) -> None:
    adapter = Draft202012SchemaAdapter()
    compiler = TemplateCompiler(schema_validator=adapter, source_loader=load_template_source)
    template = compiler.compile_path(FIXTURE)
    registry = RecordingRegistry(template)
    validator = RecordingValidator()
    output = StructuredOutputService(
        compiler=compiler,
        registry=registry,
        schema_validator=adapter,
        candidate_validator=validator,
    )
    example = output.make_example(template.metadata.template_id, template.metadata.version)
    registry.calls.clear()

    report = output.validate_candidates(example, fixture_pack)

    assert report.valid is True
    assert registry.calls == [(example.template_id, example.template_version)]
    assert validator.templates == [template]


def test_example_generation_obeys_array_resource_limit(tmp_path: Path) -> None:
    adapter = Draft202012SchemaAdapter()
    compiler = TemplateCompiler(schema_validator=adapter, source_loader=load_template_source)
    source = load_template_source(FIXTURE)
    source["output_schema"]["properties"]["effects"]["minItems"] = 2
    template = compiler.compile(source)
    output = StructuredOutputService(
        compiler=compiler,
        registry=RecordingRegistry(template),
        schema_validator=adapter,
        candidate_validator=RecordingValidator(),
        limits=TemplateLimits(max_array_items=1),
    )

    with pytest.raises(StructuredOutputError) as raised:
        output.make_example(template.metadata.template_id, template.metadata.version)

    assert raised.value.code == "TEMPLATE_LIMIT_EXCEEDED"


def test_example_generation_supports_boolean_subschemas() -> None:
    adapter = Draft202012SchemaAdapter()
    compiler = TemplateCompiler(schema_validator=adapter, source_loader=load_template_source)
    template = compiler.compile(
        {
            "template": {
                "id": "boolean-schema",
                "version": "1.0.0",
                "title": "Boolean schema",
                "description": "",
                "domain_tags": [],
                "schema_dialect": "https://json-schema.org/draft/2020-12/schema",
            },
            "output_schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["value"],
                "properties": {"value": True},
            },
            "evidence_bindings": [],
        }
    )
    output = StructuredOutputService(
        compiler=compiler,
        registry=RecordingRegistry(template),
        schema_validator=adapter,
        candidate_validator=RecordingValidator(),
    )

    example = output.make_example(template.metadata.template_id, template.metadata.version)

    assert example.candidates[0].payload == {"value": None}
