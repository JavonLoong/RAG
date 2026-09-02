from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from core_domain.structured_output import StructuredOutputError, TemplateLimits
from structured_output_application import TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source

FIXTURES = Path(__file__).parents[1] / "fixtures" / "structured_output"
DIALECT = "https://json-schema.org/draft/2020-12/schema"


def compiler(limits: TemplateLimits | None = None) -> TemplateCompiler:
    return TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=load_template_source,
        limits=limits,
    )


def minimal_source() -> dict[str, object]:
    return {
        "template": {
            "id": "rows-template",
            "version": "1.0.0",
            "title": "Rows",
            "description": "",
            "domain_tags": ["zeta", "alpha"],
            "schema_dialect": DIALECT,
        },
        "output_schema": {
            "$schema": DIALECT,
            "$defs": {
                "row": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["field"],
                    "properties": {"field": {"type": "string"}},
                }
            },
            "type": "object",
            "additionalProperties": False,
            "required": ["rows"],
            "properties": {
                "rows": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/row"},
                }
            },
        },
        "evidence_bindings": [
            {
                "target": "/rows/*/field",
                "requirement": "required",
                "min_refs": 1,
                "allowed_source_types": ["rag_text", "graph_fact"],
            }
        ],
    }


def test_three_unrelated_fixture_templates_compile_through_one_api() -> None:
    compiled = {
        path.stem: compiler().compile_path(path)
        for path in (
            FIXTURES / "fmea.yaml",
            FIXTURES / "maintenance.json",
            FIXTURES / "research.yaml",
        )
    }

    assert compiled["fmea"].metadata.template_id == "fuel-combustion-fmea"
    assert "asset_id" in compiled["maintenance"].output_schema["properties"]
    assert "paper_id" in compiled["research"].output_schema["properties"]


def test_semantically_equal_reordered_sources_have_same_canonical_hash() -> None:
    source = minimal_source()
    reordered = {
        "evidence_bindings": deepcopy(source["evidence_bindings"]),
        "output_schema": deepcopy(source["output_schema"]),
        "template": {
            "schema_dialect": DIALECT,
            "domain_tags": ["alpha", "zeta"],
            "description": "",
            "title": "Rows",
            "version": "1.0.0",
            "id": "rows-template",
        },
    }

    left = compiler().compile(source)
    right = compiler().compile(reordered)

    assert left.template_hash == right.template_hash
    assert left.canonical_json == right.canonical_json
    assert left.metadata.domain_tags == ("alpha", "zeta")
    assert left.evidence_bindings[0].allowed_source_types == ("graph_fact", "rag_text")


@pytest.mark.parametrize("change", ["version", "schema", "binding"])
def test_version_schema_or_binding_change_changes_template_hash(change: str) -> None:
    original = minimal_source()
    changed = deepcopy(original)
    if change == "version":
        changed["template"]["version"] = "1.0.1"
    elif change == "schema":
        changed["output_schema"]["properties"]["rows"]["maxItems"] = 2
    else:
        changed["evidence_bindings"][0]["max_refs"] = 3

    assert compiler().compile(original).template_hash != compiler().compile(changed).template_hash


def test_unknown_root_key_is_rejected() -> None:
    source = minimal_source()
    source["typo"] = True

    with pytest.raises(StructuredOutputError) as raised:
        compiler().compile(source)

    assert raised.value.code == "TEMPLATE_ROOT_INVALID"


def test_optional_source_mappings_are_canonical_and_empty_extension_is_backward_compatible() -> None:
    source = minimal_source()
    baseline = compiler().compile(source)
    with_empty = deepcopy(source)
    with_empty["source_mappings"] = {}
    mapped = deepcopy(source)
    mapped["source_mappings"] = {"legacy_rows": "rows"}

    compiled = compiler().compile(mapped)

    assert compiler().compile(with_empty).template_hash == baseline.template_hash
    assert compiled.source_mappings == {"legacy_rows": "rows"}
    assert '"source_mappings":{"legacy_rows":"rows"}' in compiled.canonical_json
    assert compiled.template_hash != baseline.template_hash


def test_source_mapping_must_target_a_top_level_output_property() -> None:
    source = minimal_source()
    source["source_mappings"] = {"legacy_rows": "missing"}

    with pytest.raises(StructuredOutputError) as raised:
        compiler().compile(source)

    assert raised.value.code == "TEMPLATE_MAPPING_INVALID"


def test_source_mapping_identity_rejects_leading_digit_at_compiler_boundary() -> None:
    source = minimal_source()
    source["source_mappings"] = {"1legacy": "rows"}

    with pytest.raises(StructuredOutputError) as raised:
        compiler().compile(source)

    assert raised.value.code == "TEMPLATE_MAPPING_INVALID"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "../escape"),
        ("id", "UPPERCASE"),
        ("version", "latest"),
        ("version", "1.0"),
        ("schema_dialect", "https://json-schema.org/draft/2019-09/schema"),
        ("domain_tags", ["same", "same"]),
    ],
)
def test_invalid_metadata_is_rejected(field: str, value: object) -> None:
    source = minimal_source()
    source["template"][field] = value

    with pytest.raises(StructuredOutputError) as raised:
        compiler().compile(source)

    assert raised.value.code == "TEMPLATE_METADATA_INVALID"


def test_binding_limit_duplicate_and_constructor_invariants_are_rejected() -> None:
    source = minimal_source()
    source["evidence_bindings"].append(deepcopy(source["evidence_bindings"][0]))
    with pytest.raises(StructuredOutputError) as duplicate:
        compiler().compile(source)
    assert duplicate.value.code == "TEMPLATE_BINDING_INVALID"

    source = minimal_source()
    with pytest.raises(StructuredOutputError) as limit:
        compiler(TemplateLimits(max_bindings=1)).compile({
            **source,
            "evidence_bindings": [
                source["evidence_bindings"][0],
                {"target": "/rows", "requirement": "optional"},
            ],
        })
    assert limit.value.code == "TEMPLATE_LIMIT_EXCEEDED"

    source = minimal_source()
    source["evidence_bindings"][0]["min_refs"] = 0
    with pytest.raises(StructuredOutputError) as invariant:
        compiler().compile(source)
    assert invariant.value.code == "TEMPLATE_BINDING_INVALID"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("requirement", []),
        ("allowed_source_types", ["rag_text", 1]),
    ],
)
def test_malformed_binding_types_return_stable_domain_error(field: str, value: object) -> None:
    source = minimal_source()
    source["evidence_bindings"][0][field] = value

    with pytest.raises(StructuredOutputError) as raised:
        compiler().compile(source)

    assert raised.value.code == "TEMPLATE_BINDING_INVALID"


def test_static_reachability_supports_arrays_and_local_refs() -> None:
    compiled = compiler().compile(minimal_source())

    assert compiled.evidence_bindings[0].target == "/rows/*/field"


@pytest.mark.parametrize("target", ["/rows/**/field", "/rows/*/missing"])
def test_invalid_or_zero_match_binding_target_is_rejected(target: str) -> None:
    source = minimal_source()
    source["evidence_bindings"][0]["target"] = target

    with pytest.raises(StructuredOutputError) as raised:
        compiler().compile(source)

    assert raised.value.code == "TEMPLATE_BINDING_TARGET_INVALID"
