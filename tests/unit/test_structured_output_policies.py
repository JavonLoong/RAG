from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from core_domain.structured_output import (
    StructuredOutputError,
    TemplateLimits,
    measure_schema,
    validate_json_value,
)


def test_template_limits_are_fixed_and_frozen() -> None:
    limits = TemplateLimits()

    assert limits.max_source_bytes == 1_048_576
    assert limits.max_schema_depth == 16
    assert limits.max_properties == 500
    assert limits.max_bindings == 500
    assert limits.max_candidates == 100
    assert limits.max_claims_per_candidate == 1000
    assert limits.max_array_items == 1000
    assert limits.max_string_length == 65536
    with pytest.raises(FrozenInstanceError):
        limits.max_properties = 1


def test_validate_json_value_reports_exact_pointer() -> None:
    limits = TemplateLimits(max_string_length=4)

    with pytest.raises(StructuredOutputError) as raised:
        validate_json_value({"a/b": ["ok", "too long"]}, limits)

    assert raised.value.code == "TEMPLATE_LIMIT_EXCEEDED"
    assert raised.value.pointer == "/a~1b/1"


def test_validate_json_value_enforces_depth_and_array_limits() -> None:
    with pytest.raises(StructuredOutputError, match="depth"):
        validate_json_value({"a": {"b": 1}}, TemplateLimits(max_schema_depth=1))
    with pytest.raises(StructuredOutputError) as raised:
        validate_json_value({"items": [1, 2]}, TemplateLimits(max_array_items=1))

    assert raised.value.pointer == "/items"


def test_measure_schema_counts_properties_and_depth_without_following_refs() -> None:
    schema = {
        "type": "object",
        "properties": {
            "asset": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
            "copy": {"$ref": "#/$defs/asset"},
        },
        "$defs": {
            "asset": {
                "type": "object",
                "properties": {"ignored_by_ref_walk": {"type": "string"}},
            }
        },
    }

    depth, property_count = measure_schema(schema)

    assert depth == 4
    assert property_count == 4


def test_measure_schema_rejects_property_and_depth_limits() -> None:
    schema = {"type": "object", "properties": {"a": {}, "b": {}}}
    with pytest.raises(StructuredOutputError) as raised:
        measure_schema(schema, TemplateLimits(max_properties=1))

    assert raised.value.code == "TEMPLATE_LIMIT_EXCEEDED"
    assert raised.value.pointer == "/properties/b"
