"""Safe, local-only JSON and YAML template source loading."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import orjson
import yaml  # type: ignore[import-untyped]

from core_domain.structured_output import (
    JsonValue,
    StructuredOutputError,
    TemplateLimits,
    validate_json_value,
)


def _source_error(message: str = "Template source is invalid.") -> StructuredOutputError:
    return StructuredOutputError("TEMPLATE_SOURCE_INVALID", message)


def _load_yaml(text: str) -> object:
    try:
        events = tuple(yaml.parse(text))
        if sum(isinstance(event, yaml.events.DocumentStartEvent) for event in events) > 1:
            raise _source_error()
        if any(
            isinstance(event, yaml.events.AliasEvent) or getattr(event, "anchor", None) is not None
            for event in events
        ):
            raise _source_error()
        return yaml.safe_load(text)
    except StructuredOutputError:
        raise
    except yaml.YAMLError as exc:
        raise _source_error() from exc


def load_template_source(  # noqa: C901 - staged safety checks retain distinct errors
    path: str | Path,
    limits: TemplateLimits | None = None,
) -> dict[str, JsonValue]:
    """Load one bounded JSON/YAML object without constructing custom objects."""

    active_limits = limits or TemplateLimits()
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise _source_error() from exc
    if len(raw) > active_limits.max_source_bytes:
        raise StructuredOutputError(
            "TEMPLATE_LIMIT_EXCEEDED",
            "Template source exceeds the configured byte limit.",
        )
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _source_error() from exc

    suffix = source.suffix.lower()
    try:
        if suffix == ".json":
            loaded = orjson.loads(text)
        elif suffix in {".yaml", ".yml"}:
            loaded = _load_yaml(text)
        else:
            raise _source_error()
    except StructuredOutputError:
        raise
    except (orjson.JSONDecodeError, TypeError, ValueError) as exc:
        raise _source_error() from exc

    if not isinstance(loaded, dict):
        raise _source_error()
    try:
        validate_json_value(loaded, active_limits)
    except StructuredOutputError as exc:
        if exc.code == "TEMPLATE_LIMIT_EXCEEDED":
            raise
        raise _source_error() from exc
    return cast("dict[str, JsonValue]", loaded)


__all__ = ["load_template_source"]
