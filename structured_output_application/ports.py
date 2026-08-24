"""Application boundaries for structured-output infrastructure."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from core_domain.structured_output import (
    CompiledTemplate,
    JsonValue,
    TemplateLimits,
    ValidationIssue,
)


class TemplateSourceLoader(Protocol):
    def __call__(
        self,
        path: str | Path,
        limits: TemplateLimits | None = None,
    ) -> dict[str, JsonValue]: ...


class SchemaValidatorPort(Protocol):
    def check_schema(self, schema: dict[str, JsonValue]) -> tuple[ValidationIssue, ...]: ...

    def validate(
        self,
        instance: JsonValue,
        schema: dict[str, JsonValue],
    ) -> tuple[ValidationIssue, ...]: ...


class TemplateRegistry(Protocol):
    def register(
        self,
        template: CompiledTemplate,
        source_bytes: bytes,
        source_suffix: str,
    ) -> CompiledTemplate: ...

    def get(self, template_id: str, version: str) -> CompiledTemplate: ...


__all__ = ["SchemaValidatorPort", "TemplateRegistry", "TemplateSourceLoader"]
