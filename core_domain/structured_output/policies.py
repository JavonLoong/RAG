"""Fail-closed resource policies for templates and candidate payloads."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .contracts import JsonValue, StructuredOutputError


@dataclass(frozen=True, slots=True)
class TemplateLimits:
    max_source_bytes: int = 1_048_576
    max_schema_depth: int = 16
    max_properties: int = 500
    max_bindings: int = 500
    max_candidates: int = 100
    max_claims_per_candidate: int = 1000
    max_array_items: int = 1000
    max_string_length: int = 65536

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise StructuredOutputError(
                    "TEMPLATE_LIMIT_INVALID",
                    f"{field_name} must be a positive integer",
                )


def _encode_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _child_pointer(pointer: str, token: str) -> str:
    return f"{pointer}/{_encode_token(token)}"


def validate_json_value(  # noqa: C901 - explicit recursive JSON type dispatch
    value: object,
    limits: TemplateLimits | None = None,
    *,
    pointer: str = "",
    depth: int = 0,
) -> None:
    """Validate a recursively JSON-compatible value and its resource usage."""

    active_limits = limits or TemplateLimits()
    if depth > active_limits.max_schema_depth:
        raise StructuredOutputError(
            "TEMPLATE_LIMIT_EXCEEDED",
            "JSON depth exceeds the configured limit",
            pointer,
        )

    if value is None or isinstance(value, bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StructuredOutputError("JSON_VALUE_INVALID", "number must be finite", pointer)
        return
    if isinstance(value, str):
        if len(value) > active_limits.max_string_length:
            raise StructuredOutputError(
                "TEMPLATE_LIMIT_EXCEEDED",
                "string length exceeds the configured limit",
                pointer,
            )
        return
    if isinstance(value, list):
        if len(value) > active_limits.max_array_items:
            raise StructuredOutputError(
                "TEMPLATE_LIMIT_EXCEEDED",
                "array length exceeds the configured limit",
                pointer,
            )
        for index, item in enumerate(value):
            validate_json_value(
                item,
                active_limits,
                pointer=_child_pointer(pointer, str(index)),
                depth=depth + 1,
            )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise StructuredOutputError(
                    "JSON_VALUE_INVALID",
                    "object keys must be strings",
                    pointer,
                )
            validate_json_value(
                item,
                active_limits,
                pointer=_child_pointer(pointer, key),
                depth=depth + 1,
            )
        return
    raise StructuredOutputError("JSON_VALUE_INVALID", "value is not valid JSON", pointer)


def measure_schema(  # noqa: C901 - schema traversal keeps limit failures local
    schema: dict[str, JsonValue],
    limits: TemplateLimits | None = None,
) -> tuple[int, int]:
    """Return structural depth and property count without resolving references."""

    active_limits = limits or TemplateLimits()
    maximum_depth = 0
    property_count = 0

    def walk(value: JsonValue, pointer: str, depth: int) -> None:
        nonlocal maximum_depth, property_count
        if not isinstance(value, dict | list):
            return
        maximum_depth = max(maximum_depth, depth)
        if depth > active_limits.max_schema_depth:
            raise StructuredOutputError(
                "TEMPLATE_LIMIT_EXCEEDED",
                "schema depth exceeds the configured limit",
                pointer,
            )
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict):
                for property_name in properties:
                    property_count += 1
                    if property_count > active_limits.max_properties:
                        raise StructuredOutputError(
                            "TEMPLATE_LIMIT_EXCEEDED",
                            "schema property count exceeds the configured limit",
                            _child_pointer(_child_pointer(pointer, "properties"), property_name),
                        )
            for key, item in value.items():
                walk(item, _child_pointer(pointer, key), depth + 1)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, _child_pointer(pointer, str(index)), depth + 1)

    validate_json_value(schema, active_limits)
    walk(schema, "", 0)
    return maximum_depth, property_count


__all__ = ["TemplateLimits", "measure_schema", "validate_json_value"]
