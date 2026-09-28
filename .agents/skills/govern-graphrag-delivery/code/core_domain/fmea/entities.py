from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import cast

from .errors import FmeaDomainError
from .scoring import RiskAssessment
from .states import ClaimStatus, EvidenceSupportStatus, PublicationStatus, ReviewStatus
from .value_objects import VersionSet

_FIELD_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DECIMAL = re.compile(r"^[+-]?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_VALUE_TYPE_ALIASES = {
    "string": "string",
    "text": "string",
    "enum": "string",
    "integer": "integer",
    "int": "integer",
    "decimal": "decimal",
    "number": "decimal",
    "float": "decimal",
    "boolean": "boolean",
    "bool": "boolean",
}


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FmeaDomainError(f"{field_name} must not be empty")  # noqa: TRY003
    return value.strip()


def _field_key(value: object, field_name: str) -> str:
    normalized = _text(value, field_name)
    if _FIELD_KEY.fullmatch(normalized) is None:
        raise FmeaDomainError(f"{field_name} is invalid")  # noqa: TRY003
    return normalized


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or value is None:
        raise FmeaDomainError(f"{field_name} must be a sequence")  # noqa: TRY003
    try:
        result = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise FmeaDomainError(f"{field_name} must be a sequence") from exc  # noqa: TRY003
    if any(not isinstance(item, str) or not item for item in result):
        raise FmeaDomainError(f"{field_name} must contain non-empty strings")  # noqa: TRY003
    if len(result) != len(set(result)):
        raise FmeaDomainError(f"{field_name} must not contain duplicates")  # noqa: TRY003
    return cast(tuple[str, ...], result)


@dataclass(frozen=True, slots=True)
class FieldValue:
    """A typed, namespaced extension value owned by a FMEA row."""

    field_key: str
    value_type: str
    value: object

    def __post_init__(self) -> None:
        field_key = _field_key(self.field_key, "field_key")
        if "." not in field_key:
            raise FmeaDomainError("field_key must be namespaced")  # noqa: TRY003
        object.__setattr__(self, "field_key", field_key)
        value_type = _text(self.value_type, "value_type")
        canonical_type = _canonical_value_type(value_type)
        object.__setattr__(self, "value_type", value_type)

        value = self.value
        if canonical_type.endswith("[]"):
            if not isinstance(value, list | tuple):
                raise FmeaDomainError(f"field value is invalid for extension field: {field_key}")  # noqa: TRY003
            value = tuple(value)
            object.__setattr__(self, "value", value)
        if not _value_matches(value, value_type):
            raise FmeaDomainError(f"field value is invalid for extension field: {field_key}")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class FieldClaim:
    """Evidence and uncertainty state for one canonical or extension field."""

    field_key: str
    claim_status: ClaimStatus
    support_status: EvidenceSupportStatus
    evidence_ids: tuple[str, ...]
    uncertainty: str | None = None
    conflict_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "field_key", _field_key(self.field_key, "field_key"))
        if not isinstance(self.claim_status, ClaimStatus):
            raise FmeaDomainError("claim_status must be a ClaimStatus")  # noqa: TRY003
        if not isinstance(self.support_status, EvidenceSupportStatus):
            raise FmeaDomainError("support_status must be an EvidenceSupportStatus")  # noqa: TRY003
        object.__setattr__(self, "evidence_ids", _string_tuple(self.evidence_ids, "evidence_ids"))
        object.__setattr__(self, "conflict_ids", _string_tuple(self.conflict_ids, "conflict_ids"))
        if self.uncertainty is not None:
            object.__setattr__(self, "uncertainty", _text(self.uncertainty, "uncertainty"))
        if self.claim_status in {ClaimStatus.UNKNOWN, ClaimStatus.NOT_APPLICABLE} and self.evidence_ids:
            raise FmeaDomainError("unknown or not_applicable claim cannot cite evidence")  # noqa: TRY003
        if self.claim_status is ClaimStatus.KNOWN:
            if not self.evidence_ids:
                raise FmeaDomainError("known claim requires evidence")  # noqa: TRY003
            if self.support_status in {
                EvidenceSupportStatus.CONTRADICTED,
                EvidenceSupportStatus.NOT_SUPPORTED,
            }:
                raise FmeaDomainError("known claim cannot use unsupported evidence")  # noqa: TRY003


def _extension_schema(template: object) -> dict[str, str]:  # noqa: C901
    """Read only a structural extension-field contract from a template-like value."""

    raw: object = None
    if isinstance(template, Mapping):
        raw = template.get("extension_fields") or template.get("field_definitions")
    else:
        raw = getattr(template, "extension_fields", None) or getattr(template, "field_definitions", None)
    result: dict[str, str] = {}

    def add(field_key: object, value_type: object) -> None:
        key = _field_key(field_key, "extension field key")
        if "." not in key:
            raise FmeaDomainError("extension field key must be namespaced")  # noqa: TRY003
        type_name = _text(value_type, "extension field value_type")
        if key in result:
            raise FmeaDomainError(f"duplicate extension field key: {key}")  # noqa: TRY003
        result[key] = type_name

    if isinstance(raw, Mapping):
        for key, definition in raw.items():
            if isinstance(definition, Mapping):
                add(key, definition.get("value_type") or definition.get("type"))
            else:
                add(key, definition)
    elif raw is not None:
        if isinstance(raw, str | bytes) or not isinstance(raw, Sequence):
            raise FmeaDomainError("template extension_fields must be structural")  # noqa: TRY003
        for definition in raw:
            if isinstance(definition, Mapping):
                add(
                    definition.get("field_key") or definition.get("key") or definition.get("name"),
                    definition.get("value_type") or definition.get("type"),
                )
            elif isinstance(definition, tuple | list) and len(definition) == 2:
                add(definition[0], definition[1])
            else:
                add(getattr(definition, "field_key", None), getattr(definition, "value_type", None))

    schema: object = template.get("output_schema") if isinstance(template, Mapping) else getattr(template, "output_schema", None)
    if isinstance(schema, Mapping):
        def walk(node: object, path: tuple[str, ...] = ()) -> None:
            if not isinstance(node, Mapping):
                return
            properties = node.get("properties")
            if isinstance(properties, Mapping):
                for key, child in properties.items():
                    child_path = (*path, str(key))
                    if "." in str(key) and isinstance(child, Mapping):
                        add(str(key), child.get("x-value-type") or child.get("value_type") or child.get("type"))
                    walk(child, child_path)
            if isinstance(node.get("items"), Mapping):
                walk(node["items"], (*path, "0"))

        walk(schema)
    return result


def _canonical_value_type(value_type: str) -> str:
    is_array = value_type.endswith("[]")
    base_type = value_type[:-2] if is_array else value_type
    canonical_base = _VALUE_TYPE_ALIASES.get(base_type)
    if canonical_base is None:
        raise FmeaDomainError(f"value_type is invalid: {value_type}")  # noqa: TRY003
    return f"{canonical_base}[]" if is_array else canonical_base


def _type_matches(value_type: str, expected: str) -> bool:
    try:
        return _canonical_value_type(value_type) == _canonical_value_type(expected)
    except FmeaDomainError:
        return False


def _scalar_value_matches(value: object, value_type: str) -> bool:
    if value_type == "string":
        return isinstance(value, str)
    if value_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "decimal":
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        if isinstance(value, float):
            return isfinite(value)
        return isinstance(value, str) and _DECIMAL.fullmatch(value.strip()) is not None
    if value_type == "boolean":
        return isinstance(value, bool)
    return False


def _value_matches(value: object, value_type: str) -> bool:
    try:
        canonical_type = _canonical_value_type(value_type)
    except FmeaDomainError:
        return False
    if canonical_type.endswith("[]"):
        return isinstance(value, tuple | list) and all(
            _scalar_value_matches(item, canonical_type[:-2]) for item in value
        )
    return _scalar_value_matches(value, canonical_type)


def validate_extension_values(row: object, compiled_template: object) -> None:
    """Validate row extensions using only a structural template/value contract."""

    values = tuple(getattr(row, "extension_values", ()))
    schema = _extension_schema(compiled_template)
    seen: set[str] = set()
    for field_value in values:
        if not isinstance(field_value, FieldValue):
            raise FmeaDomainError("extension_values must contain FieldValue objects")  # noqa: TRY003
        if field_value.field_key in seen:
            raise FmeaDomainError(f"duplicate extension field value: {field_value.field_key}")  # noqa: TRY003
        seen.add(field_value.field_key)
        expected = schema.get(field_value.field_key)
        if expected is None:
            raise FmeaDomainError(f"extension field is not declared by template: {field_value.field_key}")  # noqa: TRY003
        if not _type_matches(field_value.value_type, expected) or not _value_matches(
            field_value.value, field_value.value_type
        ):
            raise FmeaDomainError(f"extension field type is invalid: {field_value.field_key}")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class FmeaAnalysis:
    analysis_id: str
    project_id: str
    analysis_type: str
    lifecycle_stage: str
    scope: str
    system_boundary: str
    exclusions: tuple[str, ...]
    equipment_configuration: str
    control_software_version: str
    fuel_type: str
    operating_modes: tuple[str, ...]
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]
    unanalysed_parts: tuple[str, ...]
    versions: VersionSet
    owner_actor_id: str
    reviewer_actor_ids: tuple[str, ...]
    approver_actor_id: str | None
    approved_at: str | None
    parent_revision_id: str | None
    current_revision_id: str | None
    record_version: int = 1


@dataclass(frozen=True, slots=True)
class FmeaRow:
    row_id: str
    analysis_id: str
    evidence_pack_id: str
    item_id: str
    function_id: str
    failure_mode: str
    causes: tuple[str, ...]
    mechanisms: tuple[str, ...]
    effects: tuple[str, ...]
    symptoms: tuple[str, ...]
    controls: tuple[str, ...]
    barriers: tuple[str, ...]
    actions: tuple[str, ...]
    risk_assessment: RiskAssessment | None
    field_evidence: tuple[tuple[str, tuple[str, ...]], ...]
    field_support: tuple[tuple[str, EvidenceSupportStatus], ...]
    claim_status: ClaimStatus
    review_status: ReviewStatus
    publication_status: PublicationStatus
    record_version: int = 1
    extension_values: tuple[FieldValue, ...] = ()
    field_claims: tuple[FieldClaim, ...] = ()

    def __post_init__(self) -> None:
        extension_values = tuple(self.extension_values)
        if any(not isinstance(value, FieldValue) for value in extension_values):
            raise FmeaDomainError("extension_values must contain FieldValue objects")  # noqa: TRY003
        extension_keys = tuple(value.field_key for value in extension_values)
        if len(extension_keys) != len(set(extension_keys)):
            raise FmeaDomainError("duplicate extension field value")  # noqa: TRY003
        object.__setattr__(self, "extension_values", extension_values)

        field_claims = tuple(self.field_claims)
        if any(not isinstance(claim, FieldClaim) for claim in field_claims):
            raise FmeaDomainError("field_claims must contain FieldClaim objects")  # noqa: TRY003
        claim_keys = tuple(claim.field_key for claim in field_claims)
        if len(claim_keys) != len(set(claim_keys)):
            raise FmeaDomainError("duplicate field claim")  # noqa: TRY003
        object.__setattr__(self, "field_claims", field_claims)
