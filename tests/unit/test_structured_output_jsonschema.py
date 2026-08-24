from __future__ import annotations

import pytest

from structured_output_infrastructure import Draft202012SchemaAdapter


def adapter() -> Draft202012SchemaAdapter:
    return Draft202012SchemaAdapter()


def valid_local_ref_schema() -> dict[str, object]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": {"item": {"type": "string", "minLength": 2}},
        "type": "object",
        "properties": {"name": {"$ref": "#/$defs/item"}},
        "required": ["name"],
        "additionalProperties": False,
    }


def test_valid_local_definition_reference_is_accepted() -> None:
    assert adapter().check_schema(valid_local_ref_schema()) == ()
    assert adapter().validate({"name": "ok"}, valid_local_ref_schema()) == ()


@pytest.mark.parametrize(
    "reference",
    ["https://example.com/schema.json", "file:///private/schema.json", "../schema.json"],
)
def test_non_local_definition_references_are_rejected(reference: str) -> None:
    schema = {"$ref": reference}

    issues = adapter().check_schema(schema)

    assert issues[0].code == "TEMPLATE_SCHEMA_UNSUPPORTED"
    assert issues[0].pointer == "/$ref"


@pytest.mark.parametrize(
    "keyword",
    [
        "$dynamicRef",
        "$dynamicAnchor",
        "contentEncoding",
        "contentMediaType",
        "allOf",
        "anyOf",
        "oneOf",
        "not",
        "if",
        "then",
        "else",
        "contains",
        "dependentSchemas",
        "patternProperties",
        "unevaluatedProperties",
        "unevaluatedItems",
        "format",
    ],
)
def test_unsupported_schema_keywords_fail_closed(keyword: str) -> None:
    schema = {keyword: [] if keyword.endswith("Of") else {}}

    issues = adapter().check_schema(schema)

    assert issues[0].code == "TEMPLATE_SCHEMA_UNSUPPORTED"
    assert issues[0].pointer == f"/{keyword}"


@pytest.mark.parametrize(
    "definitions",
    [
        {"self": {"$ref": "#/$defs/self"}},
        {
            "A": {"$ref": "#/$defs/B"},
            "B": {"$ref": "#/$defs/A"},
        },
    ],
)
def test_cyclic_local_reference_graph_is_rejected(definitions: dict[str, object]) -> None:
    issues = adapter().check_schema({"$defs": definitions, "$ref": "#/$defs/A"} if "A" in definitions else {"$defs": definitions})

    assert any(issue.code == "TEMPLATE_SCHEMA_REF_CYCLE" for issue in issues)


def test_unresolved_local_reference_is_rejected() -> None:
    issues = adapter().check_schema({"$defs": {}, "$ref": "#/$defs/missing"})

    assert issues[0].code == "TEMPLATE_SCHEMA_REF_INVALID"


def test_invalid_schema_is_returned_as_safe_template_issue() -> None:
    issues = adapter().check_schema({"type": "invented"})

    assert issues[0].code == "TEMPLATE_SCHEMA_INVALID"
    assert "invented" not in issues[0].message


def test_instance_issues_are_stable_sorted_and_do_not_leak_values() -> None:
    schema = {
        "type": "object",
        "properties": {
            "a/b": {"type": "integer"},
            "z": {"type": "string", "minLength": 3},
        },
        "required": ["a/b", "z"],
        "additionalProperties": False,
    }
    instance = {"z": "x", "a/b": "TOP-SECRET"}

    issues = adapter().validate(instance, schema)

    assert tuple(issue.pointer for issue in issues) == ("/a~1b", "/z")
    assert all(issue.code == "CANDIDATE_SCHEMA_INVALID" for issue in issues)
    assert "TOP-SECRET" not in " ".join(issue.message for issue in issues)
