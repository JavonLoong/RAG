"""Immutable, transport-neutral contracts for versioned FMEA domain packs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import FmeaDomainError

_IDENTITY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RANGE_PART = re.compile(
    r"^(?:[<>=~^]{0,2})?(?:\*|(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))$"
)
_DEFAULT_KERNEL_COMPATIBILITY_RANGE = ">=1.0.0,<2.0.0"


def _non_empty_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FmeaDomainError(f"{field_name} must not be empty")  # noqa: TRY003
    return value.strip()


def _identity(value: object, field_name: str) -> str:
    normalized = _non_empty_text(value, field_name)
    if _IDENTITY.fullmatch(normalized) is None:
        raise FmeaDomainError(f"{field_name} is not a valid identity")  # noqa: TRY003
    return normalized


def _semver(value: object, field_name: str) -> str:
    normalized = _non_empty_text(value, field_name)
    if _SEMVER.fullmatch(normalized) is None:
        raise FmeaDomainError(f"{field_name} must be a semantic version")  # noqa: TRY003
    return normalized


def _unique_texts(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or value is None:
        raise FmeaDomainError(f"{field_name} must be a sequence")  # noqa: TRY003
    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise FmeaDomainError(f"{field_name} must be a sequence") from exc
    normalized = tuple(_identity(item, field_name) for item in items)
    if not normalized:
        raise FmeaDomainError(f"{field_name} must not be empty")  # noqa: TRY003
    if len(normalized) != len(set(normalized)):
        raise FmeaDomainError(f"duplicate {field_name[:-1] if field_name.endswith('s') else field_name}")  # noqa: TRY003
    return normalized


def _identity_pairs(value: object, field_name: str, label: str) -> tuple[tuple[str, str], ...]:
    if isinstance(value, str | bytes) or value is None:
        raise FmeaDomainError(f"{field_name} must be a sequence")  # noqa: TRY003
    try:
        raw_items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise FmeaDomainError(f"{field_name} must be a sequence") from exc

    normalized: list[tuple[str, str]] = []
    for item in raw_items:
        if not isinstance(item, tuple | list) or len(item) != 2:
            raise FmeaDomainError(f"{field_name} must contain identity pairs")  # noqa: TRY003
        normalized.append((_identity(item[0], f"{label} id"), _semver(item[1], f"{label} version")))
    result = tuple(normalized)
    if len(result) != len(set(result)):
        raise FmeaDomainError(f"duplicate {label} identity")  # noqa: TRY003
    return result


def _extension_fields(value: object) -> tuple[tuple[str, str], ...]:
    if isinstance(value, str | bytes) or value is None:
        raise FmeaDomainError("extension_fields must be a sequence")  # noqa: TRY003
    try:
        raw_items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise FmeaDomainError("extension_fields must be a sequence") from exc

    result: list[tuple[str, str]] = []
    for item in raw_items:
        if not isinstance(item, tuple | list) or len(item) != 2:
            raise FmeaDomainError("extension_fields must contain field/type pairs")  # noqa: TRY003
        field_key = _identity(item[0], "extension field key")
        if "." not in field_key:
            raise FmeaDomainError("extension field key must be namespaced")  # noqa: TRY003
        value_type = _non_empty_text(item[1], "extension field value_type")
        result.append((field_key, value_type))
    normalized = tuple(result)
    if len(normalized) != len({field_key for field_key, _ in normalized}):
        raise FmeaDomainError("duplicate extension field key")  # noqa: TRY003
    return normalized


def _compatibility_range(value: object) -> str:
    normalized = _non_empty_text(value, "kernel_compatibility_range")
    parts = tuple(part.strip() for part in normalized.split(","))
    if not parts or any(_RANGE_PART.fullmatch(part) is None for part in parts):
        raise FmeaDomainError("kernel_compatibility_range is invalid")  # noqa: TRY003
    return ",".join(parts)


@dataclass(frozen=True, slots=True)
class DomainPackManifest:
    """Identity and capability declarations for one immutable domain pack."""

    pack_id: str
    version: str
    content_hash: str
    compatible_schema_ids: tuple[str, ...]
    analysis_types: tuple[str, ...]
    template_identities: tuple[tuple[str, str], ...]
    scoring_rule_identities: tuple[tuple[str, str], ...]
    propagation_rule_identities: tuple[tuple[str, str], ...]
    extension_fields: tuple[tuple[str, str], ...]
    kernel_compatibility_range: str = _DEFAULT_KERNEL_COMPATIBILITY_RANGE

    def __post_init__(self) -> None:
        object.__setattr__(self, "pack_id", _identity(self.pack_id, "pack_id"))
        object.__setattr__(self, "version", _semver(self.version, "version"))
        if not isinstance(self.content_hash, str) or _SHA256.fullmatch(self.content_hash) is None:
            raise FmeaDomainError("content_hash must be lowercase SHA-256")  # noqa: TRY003
        object.__setattr__(self, "compatible_schema_ids", _unique_texts(self.compatible_schema_ids, "compatible_schema_ids"))
        object.__setattr__(self, "analysis_types", _unique_texts(self.analysis_types, "analysis_types"))
        object.__setattr__(
            self,
            "template_identities",
            _identity_pairs(self.template_identities, "template_identities", "template"),
        )
        object.__setattr__(
            self,
            "scoring_rule_identities",
            _identity_pairs(self.scoring_rule_identities, "scoring_rule_identities", "scoring rule"),
        )
        object.__setattr__(
            self,
            "propagation_rule_identities",
            _identity_pairs(self.propagation_rule_identities, "propagation_rule_identities", "propagation rule"),
        )
        object.__setattr__(self, "extension_fields", _extension_fields(self.extension_fields))
        object.__setattr__(
            self,
            "kernel_compatibility_range",
            _compatibility_range(self.kernel_compatibility_range),
        )


__all__ = ["DomainPackManifest"]
