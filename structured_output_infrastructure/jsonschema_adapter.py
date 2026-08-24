"""Offline-safe adapter for a deterministic Draft 2020-12 subset."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]

from core_domain.structured_output import JsonValue, ValidationIssue, parse_pointer

_ALLOWED_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "$defs",
        "$ref",
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "enum",
        "const",
        "title",
        "description",
        "default",
        "examples",
        "readOnly",
        "writeOnly",
        "deprecated",
        "$comment",
    }
)


def _encode_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _pointer(parts: Iterator[object] | tuple[object, ...] | list[object]) -> str:
    encoded = tuple(_encode_token(str(part)) for part in parts)
    return "" if not encoded else "/" + "/".join(encoded)


def _child(pointer: str, key: str) -> str:
    return f"{pointer}/{_encode_token(key)}"


def _issue(code: str, message: str, pointer: str) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, pointer=pointer)


def _local_ref_name(reference: object) -> str | None:
    if not isinstance(reference, str) or not reference.startswith("#/"):
        return None
    try:
        parts = parse_pointer(reference[1:])
    except ValueError:
        return None
    if len(parts) != 2 or parts[0] != "$defs":
        return None
    return parts[1]


def _schema_children(schema: dict[str, JsonValue], pointer: str) -> Iterator[tuple[object, str]]:
    for keyword in ("$defs", "properties"):
        children = schema.get(keyword)
        if isinstance(children, dict):
            for name, child in children.items():
                yield child, _child(_child(pointer, keyword), name)
    for keyword in ("items", "additionalProperties"):
        child = schema.get(keyword)
        if isinstance(child, dict | bool):
            yield child, _child(pointer, keyword)


def _walk_schema(
    schema: object,
    pointer: str,
    definitions: dict[str, JsonValue],
    issues: list[ValidationIssue],
) -> None:
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        return
    typed_schema = cast("dict[str, JsonValue]", schema)
    for keyword in typed_schema:
        if keyword not in _ALLOWED_KEYWORDS:
            issues.append(
                _issue(
                    "TEMPLATE_SCHEMA_UNSUPPORTED",
                    "Schema keyword is not supported by this template-engine version.",
                    _child(pointer, keyword),
                )
            )
    if "$ref" in typed_schema:
        reference_name = _local_ref_name(typed_schema["$ref"])
        ref_pointer = _child(pointer, "$ref")
        if reference_name is None:
            issues.append(
                _issue(
                    "TEMPLATE_SCHEMA_UNSUPPORTED",
                    "Only local root-definition references are supported.",
                    ref_pointer,
                )
            )
        elif reference_name not in definitions:
            issues.append(
                _issue(
                    "TEMPLATE_SCHEMA_REF_INVALID",
                    "Local schema reference does not resolve.",
                    ref_pointer,
                )
            )
    for child, child_pointer in _schema_children(typed_schema, pointer):
        _walk_schema(child, child_pointer, definitions, issues)


def _definition_edges(definition: object) -> set[str]:
    edges: set[str] = set()

    def visit(schema: object) -> None:
        if isinstance(schema, bool) or not isinstance(schema, dict):
            return
        typed_schema = cast("dict[str, JsonValue]", schema)
        if "$ref" in typed_schema:
            name = _local_ref_name(typed_schema["$ref"])
            if name is not None:
                edges.add(name)
        for child, _ in _schema_children(typed_schema, ""):
            visit(child)

    visit(definition)
    return edges


def _cycle_issues(definitions: dict[str, JsonValue]) -> tuple[ValidationIssue, ...]:
    graph = {name: _definition_edges(definition) for name, definition in definitions.items()}
    visiting: set[str] = set()
    visited: set[str] = set()
    issues: list[ValidationIssue] = []

    def visit(name: str) -> None:
        if name in visiting:
            issues.append(
                _issue(
                    "TEMPLATE_SCHEMA_REF_CYCLE",
                    "Local schema reference graph contains a cycle.",
                    _child(_child("", "$defs"), name),
                )
            )
            return
        if name in visited:
            return
        visiting.add(name)
        for target in sorted(graph.get(name, ())):
            if target in graph:
                visit(target)
        visiting.remove(name)
        visited.add(name)

    for definition_name in sorted(graph):
        visit(definition_name)
    unique = {(issue.code, issue.pointer): issue for issue in issues}
    return tuple(unique[key] for key in sorted(unique))


class Draft202012SchemaAdapter:
    """Validate schemas and instances without remote retrieval or format hooks."""

    def check_schema(self, schema: dict[str, JsonValue]) -> tuple[ValidationIssue, ...]:
        raw_definitions = schema.get("$defs", {})
        definitions = (
            cast("dict[str, JsonValue]", raw_definitions)
            if isinstance(raw_definitions, dict)
            else {}
        )
        issues: list[ValidationIssue] = []
        _walk_schema(schema, "", definitions, issues)
        issues.extend(_cycle_issues(definitions))
        if issues:
            return tuple(sorted(issues, key=lambda issue: (issue.pointer, issue.code)))
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            return (
                _issue(
                    "TEMPLATE_SCHEMA_INVALID",
                    "Schema does not conform to Draft 2020-12.",
                    _pointer(tuple(exc.absolute_schema_path)),
                ),
            )
        return ()

    def validate(
        self,
        instance: JsonValue,
        schema: dict[str, JsonValue],
    ) -> tuple[ValidationIssue, ...]:
        schema_issues = self.check_schema(schema)
        if schema_issues:
            return schema_issues
        validator = Draft202012Validator(schema)
        errors = sorted(
            validator.iter_errors(instance),
            key=lambda error: (_pointer(tuple(error.absolute_path)), str(error.validator)),
        )
        return tuple(
            ValidationIssue(
                code="CANDIDATE_SCHEMA_INVALID",
                message=f"Candidate violates schema keyword '{error.validator}'.",
                pointer=_pointer(tuple(error.absolute_path)),
            )
            for error in errors
        )


__all__ = ["Draft202012SchemaAdapter"]
