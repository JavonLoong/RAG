"""Use-case facade for template registration, examples and candidate validation."""

from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from typing import cast

from core_domain.fmea.value_objects import EvidencePack
from core_domain.structured_output import (
    CandidateClaim,
    CandidateValidationReport,
    ClaimState,
    CompiledTemplate,
    JsonValue,
    StructuredCandidate,
    StructuredCandidateBatch,
    StructuredOutputError,
    TemplateLimits,
    TemplateValidationReport,
    ValidationIssue,
    expand_pattern,
)

from .compiler import TemplateCompiler
from .ports import SchemaValidatorPort, TemplateRegistry
from .validators import StructuredCandidateValidator


class StructuredOutputService:
    def __init__(
        self,
        *,
        compiler: TemplateCompiler,
        registry: TemplateRegistry,
        schema_validator: SchemaValidatorPort,
        candidate_validator: StructuredCandidateValidator,
        limits: TemplateLimits | None = None,
    ) -> None:
        self._compiler = compiler
        self._registry = registry
        self._schema_validator = schema_validator
        self._candidate_validator = candidate_validator
        self._limits = limits or TemplateLimits()

    def validate_source(self, path: str | Path) -> TemplateValidationReport:
        try:
            compiled = self._compiler.compile_path(path)
        except StructuredOutputError as exc:
            return TemplateValidationReport(
                valid=False,
                issues=(ValidationIssue(code=exc.code, message=str(exc), pointer=exc.pointer),),
                compiled_template=None,
            )
        return TemplateValidationReport(valid=True, issues=(), compiled_template=compiled)

    def compile_source(self, path: str | Path) -> CompiledTemplate:
        return self._compiler.compile_path(path)

    def register_source(self, path: str | Path) -> CompiledTemplate:
        source_path = Path(path)
        compiled = self.compile_source(source_path)
        try:
            source_bytes = source_path.read_bytes()
        except OSError as exc:
            raise StructuredOutputError("TEMPLATE_SOURCE_INVALID", "Template source could not be read.") from exc
        return self._registry.register(compiled, source_bytes, source_path.suffix.lower())

    def get_template(self, template_id: str, version: str) -> CompiledTemplate:
        return self._registry.get(template_id, version)

    def make_example(self, template_id: str, version: str) -> StructuredCandidateBatch:
        template = self.get_template(template_id, version)
        return self.make_example_for_template(template)

    def make_example_for_template(self, template: CompiledTemplate) -> StructuredCandidateBatch:
        payload = self._build_value(template.output_schema, template.output_schema)
        schema_issues = self._schema_validator.validate(payload, template.output_schema)
        if schema_issues:
            raise StructuredOutputError(
                "TEMPLATE_EXAMPLE_UNSUPPORTED",
                "A deterministic schema-valid example could not be generated.",
                schema_issues[0].pointer,
            )
        targets = {
            target
            for binding in template.evidence_bindings
            if binding.requirement == "required"
            for target in expand_pattern(payload, binding.target)
        }
        claims = tuple(
            CandidateClaim(target=target, state=ClaimState.UNKNOWN, evidence_ids=())
            for target in sorted(targets)
        )
        candidate = StructuredCandidate(candidate_id="example-1", payload=payload, claims=claims)
        return StructuredCandidateBatch(
            template_id=template.metadata.template_id,
            template_version=template.metadata.version,
            template_hash=template.template_hash,
            evidence_pack_id="example-only",
            candidates=(candidate,),
        )

    def _build_value(  # noqa: C901 - deterministic schema-type decision table
        self,
        schema: dict[str, JsonValue] | bool,
        root_schema: dict[str, JsonValue],
    ) -> JsonValue:
        if schema is True:
            return None
        if schema is False:
            raise StructuredOutputError("TEMPLATE_EXAMPLE_UNSUPPORTED", "False schema has no example.")
        if "const" in schema:
            return deepcopy(schema["const"])
        enum = schema.get("enum")
        if isinstance(enum, list) and enum:
            return deepcopy(enum[0])
        reference = schema.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            name = reference.removeprefix("#/$defs/").replace("~1", "/").replace("~0", "~")
            definitions = root_schema.get("$defs", {})
            if isinstance(definitions, dict):
                referenced_schema = definitions.get(name)
                if isinstance(referenced_schema, dict | bool):
                    return self._build_value(referenced_schema, root_schema)
        raw_type = schema.get("type")
        schema_type = raw_type[0] if isinstance(raw_type, list) and raw_type else raw_type
        if schema_type == "object":
            properties = schema.get("properties", {})
            required = schema.get("required", [])
            if not isinstance(properties, dict) or not isinstance(required, list):
                raise StructuredOutputError("TEMPLATE_EXAMPLE_UNSUPPORTED", "Object schema is unsupported.")
            result: dict[str, JsonValue] = {}
            for name in sorted(cast("list[str]", required)):
                child = properties.get(name)
                if not isinstance(child, dict | bool):
                    raise StructuredOutputError("TEMPLATE_EXAMPLE_UNSUPPORTED", "Property schema is unsupported.")
                result[name] = self._build_value(child, root_schema)
            return result
        if schema_type == "array":
            items = schema.get("items")
            count = schema.get("minItems", 0)
            if not isinstance(count, int) or isinstance(count, bool):
                raise StructuredOutputError("TEMPLATE_EXAMPLE_UNSUPPORTED", "Array schema is unsupported.")
            if count > self._limits.max_array_items:
                raise StructuredOutputError(
                    "TEMPLATE_LIMIT_EXCEEDED",
                    "Example array exceeds the configured item limit.",
                )
            if isinstance(items, bool):
                if not items and count > 0:
                    raise StructuredOutputError("TEMPLATE_EXAMPLE_UNSUPPORTED", "Array schema is unsupported.")
                return [self._build_value(items, root_schema) for _ in range(count)]
            if not isinstance(items, dict):
                if count == 0:
                    return []
                raise StructuredOutputError("TEMPLATE_EXAMPLE_UNSUPPORTED", "Array schema is unsupported.")
            return [self._build_value(cast("dict[str, JsonValue]", items), root_schema) for _ in range(count)]
        if schema_type == "string":
            minimum = schema.get("minLength", 1)
            if not isinstance(minimum, int) or isinstance(minimum, bool):
                raise StructuredOutputError("TEMPLATE_EXAMPLE_UNSUPPORTED", "String schema is unsupported.")
            if minimum > self._limits.max_string_length:
                raise StructuredOutputError(
                    "TEMPLATE_LIMIT_EXCEEDED",
                    "Example string exceeds the configured length limit.",
                )
            return "?" * max(1, minimum)
        if schema_type == "integer":
            minimum = schema.get("minimum")
            if isinstance(minimum, int | float) and not isinstance(minimum, bool):
                return math.ceil(minimum)
            exclusive = schema.get("exclusiveMinimum")
            if isinstance(exclusive, int | float) and not isinstance(exclusive, bool):
                return math.floor(exclusive) + 1
            return 0
        if schema_type == "number":
            minimum = schema.get("minimum")
            if isinstance(minimum, int | float) and not isinstance(minimum, bool):
                return minimum
            exclusive = schema.get("exclusiveMinimum")
            if isinstance(exclusive, int | float) and not isinstance(exclusive, bool):
                return exclusive + 1
            return 0
        if schema_type == "boolean":
            return False
        if schema_type == "null" or schema_type is None:
            return None
        raise StructuredOutputError("TEMPLATE_EXAMPLE_UNSUPPORTED", "Schema type is unsupported.")

    def validate_candidates(
        self,
        batch: StructuredCandidateBatch,
        evidence_pack: EvidencePack,
    ) -> CandidateValidationReport:
        template = self.get_template(batch.template_id, batch.template_version)
        return self._candidate_validator.validate(batch, template, evidence_pack)


__all__ = ["StructuredOutputService"]
