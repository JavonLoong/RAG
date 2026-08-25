from __future__ import annotations

from pathlib import Path

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

ROOT = Path(__file__).parents[2]


def make_structured_output_service(registry_root: Path) -> StructuredOutputService:
    schema = Draft202012SchemaAdapter()
    return StructuredOutputService(
        compiler=TemplateCompiler(schema_validator=schema, source_loader=load_template_source),
        registry=FileTemplateRegistry(registry_root),
        schema_validator=schema,
        candidate_validator=StructuredCandidateValidator(schema),
    )


def test_review_template_compiles_registers_and_replays_same_hash(tmp_path: Path) -> None:
    service = make_structured_output_service(tmp_path / "registry")
    first = service.register_source(ROOT / "templates/examples/fmea-row-review.yaml")
    second = service.register_source(ROOT / "templates/examples/fmea-row-review.yaml")

    assert first.metadata.template_id == "fmea-row-review"
    assert first.metadata.version == "1.0.0"
    assert second.template_hash == first.template_hash
