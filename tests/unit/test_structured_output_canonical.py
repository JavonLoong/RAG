from __future__ import annotations

import pytest

from core_domain.structured_output import (
    StructuredOutputError,
    canonical_hash,
    canonical_json,
    expand_pattern,
    parse_pointer,
    pattern_matches,
    resolve_pointer,
)


def test_equivalent_objects_have_identical_canonical_hash() -> None:
    left = {"b": [2, 1], "a": {"z": True}}
    right = {"a": {"z": True}, "b": [2, 1]}

    assert canonical_json(left) == '{"a":{"z":true},"b":[2,1]}'
    assert canonical_hash(left) == canonical_hash(right)


def test_pointer_pattern_expands_array_members_and_escapes_tokens() -> None:
    payload = {"a/b": {"effects": ["low pressure", "unstable flame"]}}

    assert expand_pattern(payload, "/a~1b/effects/*") == (
        "/a~1b/effects/0",
        "/a~1b/effects/1",
    )
    assert resolve_pointer(payload, "/a~1b/effects/1") == "unstable flame"
    assert parse_pointer("/a~1b/~0value") == ("a/b", "~value")


@pytest.mark.parametrize(
    "pointer",
    ["", "field", "#/field", "/a/**", "/a/pre*", "/a/*post", "/a/~", "/a/~2"],
)
def test_pointer_and_pattern_syntax_fail_closed(pointer: str) -> None:
    with pytest.raises(StructuredOutputError, match="pointer"):
        expand_pattern({"a": []}, pointer)


@pytest.mark.parametrize("pointer", ["/items/-1", "/items/+1", "/items/1.0"])
def test_array_pointer_rejects_non_canonical_indexes(pointer: str) -> None:
    with pytest.raises(StructuredOutputError) as raised:
        resolve_pointer({"items": ["a", "b"]}, pointer)

    assert raised.value.code == "POINTER_RESOLUTION_FAILED"
    assert raised.value.pointer == pointer


def test_array_pattern_rejects_non_canonical_exact_index() -> None:
    with pytest.raises(StructuredOutputError) as raised:
        expand_pattern({"items": ["a"]}, "/items/-1")

    assert raised.value.code == "POINTER_RESOLUTION_FAILED"


def test_pattern_matching_requires_equal_segments_and_whole_wildcards() -> None:
    assert pattern_matches("/checks/*/result", "/checks/12/result") is True
    assert pattern_matches("/checks/*/result", "/checks/12/result/value") is False
    assert pattern_matches("/checks/1/result", "/checks/12/result") is False


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), {1: "bad"}, b"bad", object()],
)
def test_canonical_json_rejects_non_json_values(value: object) -> None:
    with pytest.raises(StructuredOutputError) as raised:
        canonical_json(value)

    assert raised.value.code == "JSON_VALUE_INVALID"
