"""Strict compiler from generic template source to immutable version identity."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import cast

from core_domain.structured_output import (
    CompiledTemplate,
    EvidenceBinding,
    JsonValue,
    StructuredOutputError,
    TemplateLimits,
    TemplateMetadata,
    canonical_hash,
    canonical_json,
    measure_schema,
    pattern_matches,
)

from .ports import SchemaValidatorPort, TemplateSourceLoader

_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_ID = re.compile(r"^[a-z0-9._-]{1,128}$")
_MAPPING_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_BASE_ROOT_KEYS = frozenset({"template", "output_schema", "evidence_bindings"})
_ROOT_KEYS_WITH_MAPPINGS = _BASE_ROOT_KEYS | {"source_mappings"}
_METADATA_KEYS = frozenset({"id", "version", "title", "description", "domain_tags", "schema_dialect"})
_BINDING_KEYS = frozenset({"target", "requirement", "min_refs", "max_refs", "allowed_source_types"})


def _error(code: str, message: str, pointer: str = "") -> StructuredOutputError:
    return StructuredOutputError(code, message, pointer)


def _require_exact_keys(
    value: object,
    expected: frozenset[str],
    *,
    code: str,
    pointer: str,
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise _error(code, "Object has missing or unsupported fields.", pointer)
    return cast("dict[str, object]", value)


def _parse_metadata(value: object) -> TemplateMetadata:
    metadata = _require_exact_keys(
        value,
        _METADATA_KEYS,
        code="TEMPLATE_METADATA_INVALID",
        pointer="/template",
    )
    template_id = metadata["id"]
    version = metadata["version"]
    title = metadata["title"]
    description = metadata["description"]
    tags = metadata["domain_tags"]
    dialect = metadata["schema_dialect"]
    if not isinstance(template_id, str) or _ID.fullmatch(template_id) is None or ".." in template_id:
        raise _error("TEMPLATE_METADATA_INVALID", "Template ID is invalid.", "/template/id")
    if not isinstance(version, str) or _SEMVER.fullmatch(version) is None:
        raise _error("TEMPLATE_METADATA_INVALID", "Template version is invalid.", "/template/version")
    if not isinstance(title, str) or not 1 <= len(title) <= 200:
        raise _error("TEMPLATE_METADATA_INVALID", "Template title is invalid.", "/template/title")
    if not isinstance(description, str) or len(description) > 2000:
        raise _error(
            "TEMPLATE_METADATA_INVALID",
            "Template description is invalid.",
            "/template/description",
        )
    if (
        not isinstance(tags, list)
        or len(tags) > 32
        or any(not isinstance(tag, str) or not 1 <= len(tag) <= 64 for tag in tags)
        or len(tags) != len(set(tags))
    ):
        raise _error(
            "TEMPLATE_METADATA_INVALID",
            "Template domain tags are invalid.",
            "/template/domain_tags",
        )
    if dialect != _DIALECT:
        raise _error(
            "TEMPLATE_METADATA_INVALID",
            "Template schema dialect is invalid.",
            "/template/schema_dialect",
        )
    return TemplateMetadata(
        template_id=template_id,
        version=version,
        title=title,
        description=description,
        domain_tags=tuple(sorted(tags)),
        schema_dialect=cast("str", dialect),
    )


def _parse_bindings(value: object, limits: TemplateLimits) -> tuple[EvidenceBinding, ...]:
    if not isinstance(value, list):
        raise _error("TEMPLATE_BINDING_INVALID", "Evidence bindings must be an array.", "/evidence_bindings")
    if len(value) > limits.max_bindings:
        raise _error(
            "TEMPLATE_LIMIT_EXCEEDED",
            "Evidence binding count exceeds the configured limit.",
            "/evidence_bindings",
        )
    bindings: list[EvidenceBinding] = []
    for index, raw_binding in enumerate(value):
        pointer = f"/evidence_bindings/{index}"
        if not isinstance(raw_binding, dict) or not {"target", "requirement"} <= set(raw_binding):
            raise _error("TEMPLATE_BINDING_INVALID", "Evidence binding is invalid.", pointer)
        if not set(raw_binding) <= _BINDING_KEYS:
            raise _error("TEMPLATE_BINDING_INVALID", "Evidence binding has unsupported fields.", pointer)
        source_types = raw_binding.get("allowed_source_types", [])
        if (
            not isinstance(source_types, list)
            or any(not isinstance(source_type, str) or not source_type for source_type in source_types)
            or len(source_types) != len(set(source_types))
        ):
            raise _error("TEMPLATE_BINDING_INVALID", "Allowed source types must be an array.", pointer)
        requirement = raw_binding["requirement"]
        if not isinstance(requirement, str):
            raise _error("TEMPLATE_BINDING_INVALID", "Evidence requirement is invalid.", pointer)
        binding = EvidenceBinding(
            target=cast("str", raw_binding["target"]),
            requirement=cast("object", requirement),  # type: ignore[arg-type]
            min_refs=cast("int", raw_binding.get("min_refs", 0)),
            max_refs=cast("int | None", raw_binding.get("max_refs")),
            allowed_source_types=tuple(sorted(cast("list[str]", source_types))),
        )
        bindings.append(binding)
    targets = tuple(binding.target for binding in bindings)
    if len(targets) != len(set(targets)):
        raise _error("TEMPLATE_BINDING_INVALID", "Evidence binding target is duplicated.", "/evidence_bindings")
    return tuple(sorted(bindings, key=lambda binding: binding.target))


def _parse_source_mappings(value: object, limits: TemplateLimits) -> dict[str, str]:
    if not isinstance(value, dict) or len(value) > limits.max_properties:
        raise _error("TEMPLATE_MAPPING_INVALID", "Source mappings must be a bounded object.", "/source_mappings")
    mappings: dict[str, str] = {}
    for source, target in value.items():
        if (
            not isinstance(source, str)
            or _MAPPING_KEY.fullmatch(source) is None
            or not isinstance(target, str)
            or not target
            or len(target) > limits.max_string_length
        ):
            raise _error("TEMPLATE_MAPPING_INVALID", "Source mapping identity is invalid.", "/source_mappings")
        mappings[source] = target
    return dict(sorted(mappings.items()))


def _encode_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _schema_locations(schema: dict[str, JsonValue]) -> tuple[str, ...]:
    raw_definitions = schema.get("$defs", {})
    definitions = raw_definitions if isinstance(raw_definitions, dict) else {}
    locations: set[str] = set()

    def walk(node: JsonValue, parts: tuple[str, ...], resolving: frozenset[str]) -> None:
        if isinstance(node, bool) or not isinstance(node, dict):
            return
        if parts:
            locations.add("/" + "/".join(_encode_token(part) for part in parts))
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            definition_name = reference.removeprefix("#/$defs/").replace("~1", "/").replace("~0", "~")
            if definition_name in definitions and definition_name not in resolving:
                walk(
                    definitions[definition_name],
                    parts,
                    resolving | {definition_name},
                )
        properties = node.get("properties")
        if isinstance(properties, dict):
            for name, child in properties.items():
                walk(child, (*parts, name), resolving)
        items = node.get("items")
        if isinstance(items, dict | bool):
            walk(items, (*parts, "0"), resolving)

    walk(schema, (), frozenset())
    return tuple(sorted(locations))


def _validate_binding_targets(
    bindings: tuple[EvidenceBinding, ...],
    schema: dict[str, JsonValue],
) -> None:
    locations = _schema_locations(schema)
    for binding in bindings:
        try:
            reachable = any(pattern_matches(binding.target, location) for location in locations)
        except StructuredOutputError as exc:
            raise _error(
                "TEMPLATE_BINDING_TARGET_INVALID",
                "Evidence binding target pattern is invalid.",
                binding.target,
            ) from exc
        if not reachable:
            raise _error(
                "TEMPLATE_BINDING_TARGET_INVALID",
                "Evidence binding target does not reach the output schema.",
                binding.target,
            )


def _canonical_object(
    metadata: TemplateMetadata,
    schema: dict[str, JsonValue],
    bindings: tuple[EvidenceBinding, ...],
    source_mappings: dict[str, str],
) -> dict[str, JsonValue]:
    canonical: dict[str, JsonValue] = {
        "template": {
            "id": metadata.template_id,
            "version": metadata.version,
            "title": metadata.title,
            "description": metadata.description,
            "domain_tags": list(metadata.domain_tags),
            "schema_dialect": metadata.schema_dialect,
        },
        "output_schema": schema,
        "evidence_bindings": [
            {
                "target": binding.target,
                "requirement": binding.requirement,
                "min_refs": binding.min_refs,
                "max_refs": binding.max_refs,
                "allowed_source_types": list(binding.allowed_source_types),
            }
            for binding in bindings
        ],
    }
    if source_mappings:
        canonical["source_mappings"] = source_mappings
    return canonical


class TemplateCompiler:
    def __init__(
        self,
        *,
        schema_validator: SchemaValidatorPort,
        source_loader: TemplateSourceLoader,
        limits: TemplateLimits | None = None,
    ) -> None:
        self._schema_validator = schema_validator
        self._source_loader = source_loader
        self._limits = limits or TemplateLimits()

    def compile_path(self, path: str | Path) -> CompiledTemplate:
        return self.compile(self._source_loader(path, self._limits))

    def compile(self, source: dict[str, JsonValue]) -> CompiledTemplate:
        if frozenset(source) not in {_BASE_ROOT_KEYS, _ROOT_KEYS_WITH_MAPPINGS}:
            raise _error("TEMPLATE_ROOT_INVALID", "Template root has missing or unsupported fields.")
        metadata = _parse_metadata(source["template"])
        raw_schema = source["output_schema"]
        if not isinstance(raw_schema, dict):
            raise _error("TEMPLATE_SCHEMA_INVALID", "Output schema must be an object.", "/output_schema")
        schema = deepcopy(cast("dict[str, JsonValue]", raw_schema))
        schema_issues = self._schema_validator.check_schema(schema)
        if schema_issues:
            issue = schema_issues[0]
            raise _error(issue.code, issue.message, f"/output_schema{issue.pointer}")
        measure_schema(schema, self._limits)
        bindings = _parse_bindings(source["evidence_bindings"], self._limits)
        _validate_binding_targets(bindings, schema)
        source_mappings = _parse_source_mappings(source.get("source_mappings", {}), self._limits)
        raw_properties = schema.get("properties", {})
        if source_mappings and not isinstance(raw_properties, dict):
            raise _error(
                "TEMPLATE_MAPPING_INVALID",
                "Source mappings require top-level output properties.",
                "/source_mappings",
            )
        if any(target not in raw_properties for target in source_mappings.values()):
            raise _error(
                "TEMPLATE_MAPPING_INVALID",
                "Source mappings must target top-level output properties.",
                "/source_mappings",
            )
        canonical_object = _canonical_object(metadata, schema, bindings, source_mappings)
        serialized = canonical_json(canonical_object)
        return CompiledTemplate(
            metadata=metadata,
            output_schema=schema,
            evidence_bindings=bindings,
            template_hash=canonical_hash(canonical_object),
            canonical_json=serialized,
            source_mappings=source_mappings,
        )


__all__ = ["TemplateCompiler"]
