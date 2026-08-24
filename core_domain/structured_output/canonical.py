"""Canonical JSON and strict RFC 6901 pointer helpers."""

from __future__ import annotations

import hashlib

import orjson

from .contracts import JsonValue, StructuredOutputError
from .policies import validate_json_value


def canonical_json(value: object) -> str:
    """Serialize a JSON value with stable object-key ordering and no whitespace."""

    validate_json_value(value)
    try:
        return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise StructuredOutputError("JSON_VALUE_INVALID", "value cannot be canonicalized") from exc


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _decode_token(segment: str, pointer: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(segment):
        character = segment[index]
        if character != "~":
            result.append(character)
            index += 1
            continue
        if index + 1 >= len(segment) or segment[index + 1] not in {"0", "1"}:
            raise StructuredOutputError("POINTER_INVALID", "pointer contains an invalid escape", pointer)
        result.append("~" if segment[index + 1] == "0" else "/")
        index += 2
    return "".join(result)


def _parse(pointer: str, *, allow_wildcard: bool) -> tuple[str, ...]:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise StructuredOutputError("POINTER_INVALID", "pointer must start with '/'", str(pointer))
    tokens = tuple(_decode_token(segment, pointer) for segment in pointer[1:].split("/"))
    for segment in tokens:
        if "*" in segment and not (allow_wildcard and segment == "*"):
            raise StructuredOutputError(
                "POINTER_INVALID",
                "pointer wildcard must occupy a complete segment",
                pointer,
            )
    return tokens


def parse_pointer(pointer: str) -> tuple[str, ...]:
    return _parse(pointer, allow_wildcard=False)


def _encode_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _encoded_pointer(tokens: tuple[str, ...]) -> str:
    return "/" + "/".join(_encode_token(token) for token in tokens)


def _array_index(token: str, pointer: str) -> int:
    if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
        raise StructuredOutputError(
            "POINTER_RESOLUTION_FAILED",
            "array pointer segment must be a canonical non-negative integer",
            pointer,
        )
    return int(token)


def resolve_pointer(payload: JsonValue, pointer: str) -> JsonValue:
    current = payload
    for token in parse_pointer(pointer):
        if isinstance(current, dict):
            if token not in current:
                raise StructuredOutputError("POINTER_RESOLUTION_FAILED", "object member does not exist", pointer)
            current = current[token]
        elif isinstance(current, list):
            index = _array_index(token, pointer)
            if index >= len(current):
                raise StructuredOutputError("POINTER_RESOLUTION_FAILED", "array index is out of range", pointer)
            current = current[index]
        else:
            raise StructuredOutputError("POINTER_RESOLUTION_FAILED", "pointer traverses a scalar", pointer)
    return current


def pattern_matches(pattern: str, target: str) -> bool:
    pattern_tokens = _parse(pattern, allow_wildcard=True)
    target_tokens = parse_pointer(target)
    return len(pattern_tokens) == len(target_tokens) and all(
        expected == "*" or expected == actual
        for expected, actual in zip(pattern_tokens, target_tokens, strict=True)
    )


def expand_pattern(payload: JsonValue, pattern: str) -> tuple[str, ...]:
    pattern_tokens = _parse(pattern, allow_wildcard=True)
    frontier: list[tuple[JsonValue, tuple[str, ...]]] = [(payload, ())]
    for segment in pattern_tokens:
        next_frontier: list[tuple[JsonValue, tuple[str, ...]]] = []
        for current, resolved_tokens in frontier:
            if segment == "*":
                if isinstance(current, list):
                    next_frontier.extend(
                        (item, (*resolved_tokens, str(index)))
                        for index, item in enumerate(current)
                    )
                elif isinstance(current, dict):
                    next_frontier.extend(
                        (item, (*resolved_tokens, key)) for key, item in current.items()
                    )
                continue
            if isinstance(current, dict) and segment in current:
                next_frontier.append((current[segment], (*resolved_tokens, segment)))
            elif isinstance(current, list):
                index = _array_index(segment, pattern)
                if index < len(current):
                    next_frontier.append((current[index], (*resolved_tokens, str(index))))
        frontier = next_frontier
    return tuple(_encoded_pointer(tokens) for _, tokens in frontier)


__all__ = [
    "canonical_hash",
    "canonical_json",
    "expand_pattern",
    "parse_pointer",
    "pattern_matches",
    "resolve_pointer",
]
