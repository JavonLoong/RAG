"""Immutable, bounded contracts for template import and revision migration."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timedelta
from enum import Enum
from itertools import pairwise
from math import isfinite
from types import MappingProxyType
from typing import TypeVar

from .domain_pack import _identity as _pack_identity
from .domain_pack import _semver as _pack_semver
from .errors import FmeaDomainError
from .filename_policy import validate_filename
from .governance import canonical_hash

_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_PATCH_PATH = re.compile(r"^/(?:[^/]+/)*[^/]+$")

_MAX_COLLECTION_ITEMS = 512
_MAX_STRUCTURE_ITEMS = 4096
_MAX_DIFF_ITEMS = 256
_MAX_JSON_DEPTH = 8
_MAX_JSON_ITEMS = 512
_MAX_TEXT_LENGTH = 4096
_MAX_ID_LENGTH = 256
_MAX_FILENAME_LENGTH = 255
_MAX_MIGRATION_STEPS = 64
_E = TypeVar("_E", bound=Enum)


class TemplateDraftStatus(str, Enum):
    DRAFT = "draft"


class TemplatePatchStatus(str, Enum):
    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MigrationReportStatus(str, Enum):
    DRY_RUN = "dry_run"
    CONFIRMED = "confirmed"
    FAILED = "failed"


def _text(value: object, field_name: str, *, limit: int = _MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FmeaDomainError(f"{field_name} must not be empty")  # noqa: TRY003
    normalized = value.strip()
    if len(normalized) > limit:
        raise FmeaDomainError(f"{field_name} exceeds maximum length {limit}")  # noqa: TRY003
    return normalized


def _id(value: object, field_name: str) -> str:
    return _text(value, field_name, limit=_MAX_ID_LENGTH)


def _hash(value: object, field_name: str) -> str:
    normalized = _text(value, field_name, limit=71)
    if _SHA256.fullmatch(normalized) is None:
        raise FmeaDomainError(f"{field_name} must be lowercase SHA-256")  # noqa: TRY003
    return normalized


def _timestamp(value: object, field_name: str) -> str:
    normalized = _text(value, field_name, limit=64)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FmeaDomainError(f"{field_name} must be an ISO-8601 UTC timestamp") from exc  # noqa: TRY003
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise FmeaDomainError(f"{field_name} must be an ISO-8601 UTC timestamp")  # noqa: TRY003
    return normalized


def _enum(value: object, expected: type[_E], field_name: str) -> _E:
    if isinstance(value, expected):
        return value
    try:
        return expected(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(str(member.value) for member in expected)
        raise FmeaDomainError(f"{field_name} must be one of: {allowed}") from exc  # noqa: TRY003


def _sequence(value: object, field_name: str, *, limit: int) -> tuple[object, ...]:
    if not isinstance(value, tuple | list):
        raise FmeaDomainError(f"{field_name} must be a tuple or list")  # noqa: TRY003
    if len(value) > limit:
        raise FmeaDomainError(f"{field_name} exceeds maximum size {limit}")  # noqa: TRY003
    return tuple(value)


def _texts(value: object, field_name: str, *, limit: int = _MAX_COLLECTION_ITEMS) -> tuple[str, ...]:
    items = _sequence(value, field_name, limit=limit)
    result = tuple(_text(item, field_name) for item in items)
    if len(result) != len(set(result)):
        raise FmeaDomainError(f"{field_name} must not contain duplicates")  # noqa: TRY003
    return result


def _text_items(value: object, field_name: str, *, limit: int = _MAX_COLLECTION_ITEMS) -> tuple[str, ...]:
    return tuple(_text(item, field_name) for item in _sequence(value, field_name, limit=limit))


def _freeze_json(value: object, *, depth: int = 0) -> object:  # noqa: C901
    if depth > _MAX_JSON_DEPTH:
        raise FmeaDomainError("canonical value exceeds maximum depth")  # noqa: TRY003
    if value is None or isinstance(value, bool | int | str):
        if isinstance(value, str) and len(value) > _MAX_TEXT_LENGTH:
            raise FmeaDomainError("canonical value string exceeds maximum length")  # noqa: TRY003
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise FmeaDomainError("canonical value numbers must be finite")  # noqa: TRY003
        return value
    if isinstance(value, Mapping):
        if len(value) > _MAX_JSON_ITEMS:
            raise FmeaDomainError("canonical value mapping exceeds maximum size")  # noqa: TRY003
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise FmeaDomainError("canonical value object keys must be non-empty strings")  # noqa: TRY003
            normalized_key = key.strip()
            if normalized_key in result:
                raise FmeaDomainError("canonical value contains duplicate object keys")  # noqa: TRY003
            result[normalized_key] = _freeze_json(item, depth=depth + 1)
        return MappingProxyType(dict(sorted(result.items())))
    if isinstance(value, tuple | list):
        if len(value) > _MAX_JSON_ITEMS:
            raise FmeaDomainError("canonical value array exceeds maximum size")  # noqa: TRY003
        return tuple(_freeze_json(item, depth=depth + 1) for item in value)
    if isinstance(value, Enum):
        return _freeze_json(value.value, depth=depth)
    if is_dataclass(value) and not isinstance(value, type):
        return _freeze_json(
            {field.name: getattr(value, field.name) for field in fields(value)},
            depth=depth,
        )
    raise FmeaDomainError("canonical value contains an unsupported value")  # noqa: TRY003


def _identity(value: object, field_name: str) -> tuple[str, str]:
    if not isinstance(value, tuple | list) or len(value) != 2:
        raise FmeaDomainError(f"{field_name} must be an ID/version pair")  # noqa: TRY003
    return (_pack_identity(value[0], f"{field_name} ID"), _pack_semver(value[1], f"{field_name} version"))


def _filename(value: object, field_name: str) -> str:
    return validate_filename(value, field_name)


def _patch_diff(value: object) -> tuple[Mapping[str, object], ...]:
    raw_diff = _sequence(value, "diff", limit=_MAX_DIFF_ITEMS)
    diff: list[Mapping[str, object]] = []
    paths: list[str] = []
    for item in raw_diff:
        if not isinstance(item, Mapping):
            raise FmeaDomainError("diff must contain mappings")  # noqa: TRY003
        frozen = _freeze_json(item)
        if not isinstance(frozen, Mapping):  # pragma: no cover - mapping input stays a mapping.
            raise FmeaDomainError("diff must contain mappings")  # noqa: TRY003
        operation = frozen.get("op")
        path = frozen.get("path")
        if operation not in {"add", "replace", "remove"}:
            raise FmeaDomainError("diff operations are restricted to add, replace, and remove")  # noqa: TRY003
        if not isinstance(path, str) or _PATCH_PATH.fullmatch(path) is None:
            raise FmeaDomainError("diff paths must be bounded JSON Pointer paths")  # noqa: TRY003
        if path in paths:
            raise FmeaDomainError("diff paths must be unique")  # noqa: TRY003
        if operation != "remove" and "value" not in frozen:
            raise FmeaDomainError("add and replace diff operations require value")  # noqa: TRY003
        paths.append(path)
        diff.append(frozen)
    return tuple(diff)


@dataclass(frozen=True, slots=True)
class SourceStructureItem:
    """One source-document structural fact retained by an import draft."""

    kind: str
    locator: str
    value: object | None = None

    def __post_init__(self) -> None:
        kind = _text(self.kind, "kind", limit=64).casefold()
        locator = _text(self.locator, "locator")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "locator", locator)
        object.__setattr__(self, "value", _freeze_json(self.value))


@dataclass(frozen=True, slots=True)
class ProposedFieldMapping:
    """A structural field mapping proposed by import analysis."""

    source_key: str
    target_field: str
    source_locator: str
    confidence: float | None = None
    rationale: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_key", _text(self.source_key, "source_key", limit=256))
        object.__setattr__(self, "target_field", _text(self.target_field, "target_field", limit=256))
        object.__setattr__(self, "source_locator", _text(self.source_locator, "source_locator"))
        if self.confidence is not None and (
            not isinstance(self.confidence, int | float) or isinstance(self.confidence, bool)
        ):
            raise FmeaDomainError("confidence must be a finite number between 0 and 1")  # noqa: TRY003
        if self.confidence is not None and (not isfinite(self.confidence) or not 0 <= self.confidence <= 1):
            raise FmeaDomainError("confidence must be a finite number between 0 and 1")  # noqa: TRY003
        object.__setattr__(self, "rationale", None if self.rationale is None else _text(self.rationale, "rationale"))


@dataclass(frozen=True, slots=True)
class TemplateDraft:
    draft_id: str
    workspace_id: str
    source_filename: str
    source_sha256: str
    source_type: str
    structure: tuple[SourceStructureItem, ...]
    proposed_fields: tuple[ProposedFieldMapping, ...]
    unknown_fields: tuple[str, ...]
    ambiguous_fields: tuple[str, ...]
    parser_warnings: tuple[str, ...]
    status: TemplateDraftStatus | str
    created_at: str
    identified_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("draft_id", "workspace_id"):
            object.__setattr__(self, field_name, _id(getattr(self, field_name), field_name))
        object.__setattr__(self, "source_filename", _filename(self.source_filename, "source_filename"))
        object.__setattr__(self, "source_sha256", _hash(self.source_sha256, "source_sha256"))
        source_type = _text(self.source_type, "source_type", limit=32).casefold()
        if source_type not in {"xlsx", "docx"}:
            raise FmeaDomainError("source_type must be xlsx or docx")  # noqa: TRY003
        if not self.source_filename.casefold().endswith(f".{source_type}"):
            raise FmeaDomainError("source_filename extension must match source_type")  # noqa: TRY003
        object.__setattr__(self, "source_type", source_type)

        structure = _sequence(self.structure, "structure", limit=_MAX_STRUCTURE_ITEMS)
        if any(not isinstance(item, SourceStructureItem) for item in structure):
            raise FmeaDomainError("structure must contain SourceStructureItem objects")  # noqa: TRY003
        object.__setattr__(self, "structure", structure)

        proposed = _sequence(self.proposed_fields, "proposed_fields", limit=_MAX_COLLECTION_ITEMS)
        proposed_items = tuple(item for item in proposed if isinstance(item, ProposedFieldMapping))
        if len(proposed_items) != len(proposed):
            raise FmeaDomainError("proposed_fields must contain ProposedFieldMapping objects")  # noqa: TRY003
        mapping_keys = tuple(item.source_key for item in proposed_items)
        if len(mapping_keys) != len(set(mapping_keys)):
            raise FmeaDomainError("proposed_fields mapping keys must be unique")  # noqa: TRY003
        object.__setattr__(self, "proposed_fields", proposed_items)
        object.__setattr__(self, "unknown_fields", _text_items(self.unknown_fields, "unknown_fields"))
        object.__setattr__(self, "ambiguous_fields", _text_items(self.ambiguous_fields, "ambiguous_fields"))
        object.__setattr__(self, "parser_warnings", _text_items(self.parser_warnings, "parser_warnings"))
        object.__setattr__(self, "identified_fields", _texts(self.identified_fields, "identified_fields"))
        object.__setattr__(self, "status", _enum(self.status, TemplateDraftStatus, "status"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))


@dataclass(frozen=True, slots=True)
class TemplatePatchCandidate:
    patch_id: str
    draft_id: str
    input_template_version: str
    target_template_id: str
    target_template_version: str
    target_template_hash: str
    domain_pack_id: str
    domain_pack_version: str
    domain_pack_hash: str
    evidence_pack_id: str
    evidence_pack_hash: str
    run_id: str
    trace_id: str
    model_version: str
    prompt_version: str
    diff: tuple[Mapping[str, object], ...]
    evidence_ids: tuple[str, ...]
    status: TemplatePatchStatus | str
    created_at: str
    applied: bool = False

    def __post_init__(self) -> None:
        for field_name in ("patch_id", "draft_id"):
            object.__setattr__(self, field_name, _id(getattr(self, field_name), field_name))
        input_template_version = _pack_semver(self.input_template_version, "input_template_version")
        object.__setattr__(self, "input_template_version", input_template_version)
        object.__setattr__(self, "target_template_id", _pack_identity(self.target_template_id, "target_template_id"))
        object.__setattr__(
            self,
            "target_template_version",
            _pack_semver(self.target_template_version, "target_template_version"),
        )
        if self.input_template_version != self.target_template_version:
            raise FmeaDomainError("input_template_version must match target_template_version")  # noqa: TRY003
        object.__setattr__(self, "target_template_hash", _hash(self.target_template_hash, "target_template_hash"))
        object.__setattr__(self, "domain_pack_id", _pack_identity(self.domain_pack_id, "domain_pack_id"))
        object.__setattr__(self, "domain_pack_version", _pack_semver(self.domain_pack_version, "domain_pack_version"))
        object.__setattr__(self, "domain_pack_hash", _hash(self.domain_pack_hash, "domain_pack_hash"))
        object.__setattr__(self, "evidence_pack_id", _id(self.evidence_pack_id, "evidence_pack_id"))
        object.__setattr__(self, "evidence_pack_hash", _hash(self.evidence_pack_hash, "evidence_pack_hash"))
        object.__setattr__(self, "run_id", _id(self.run_id, "run_id"))
        object.__setattr__(self, "trace_id", _id(self.trace_id, "trace_id"))
        for field_name in ("model_version", "prompt_version"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name, limit=256))
        if not isinstance(self.applied, bool) or self.applied:
            raise FmeaDomainError("TemplatePatchCandidate applied must remain false")  # noqa: TRY003
        object.__setattr__(self, "diff", _patch_diff(self.diff))
        object.__setattr__(self, "evidence_ids", _texts(self.evidence_ids, "evidence_ids"))
        object.__setattr__(self, "status", _enum(self.status, TemplatePatchStatus, "status"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))


@dataclass(frozen=True, slots=True)
class MigrationStep:
    source: tuple[str, str]
    target: tuple[str, str]
    adapter_id: str

    def __post_init__(self) -> None:
        source = _identity(self.source, "migration step source")
        target = _identity(self.target, "migration step target")
        if source == target:
            raise FmeaDomainError("migration step source and target must differ")  # noqa: TRY003
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "adapter_id", _pack_identity(self.adapter_id, "adapter_id"))


MigrationEdge = MigrationStep


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    source: tuple[str, str]
    target: tuple[str, str]
    steps: tuple[MigrationStep, ...]

    def __post_init__(self) -> None:
        source = _identity(self.source, "migration source")
        target = _identity(self.target, "migration target")
        if source[0] != target[0]:
            raise FmeaDomainError("migration source and target domain identities must match")  # noqa: TRY003
        if source == target:
            raise FmeaDomainError("migration source and target must differ")  # noqa: TRY003
        steps = _sequence(self.steps, "steps", limit=_MAX_MIGRATION_STEPS)
        if not steps:
            raise FmeaDomainError("migration path is not explicit")  # noqa: TRY003
        step_items = tuple(step for step in steps if isinstance(step, MigrationStep))
        if len(step_items) != len(steps):
            raise FmeaDomainError("steps must contain MigrationStep objects")  # noqa: TRY003
        if step_items[0].source != source or step_items[-1].target != target:
            raise FmeaDomainError("migration path is not continuous")  # noqa: TRY003
        if any(left.target != right.source for left, right in pairwise(step_items)):
            raise FmeaDomainError("migration path is not continuous")  # noqa: TRY003
        if any(step.source[0] != source[0] or step.target[0] != source[0] for step in step_items):
            raise FmeaDomainError("migration path domain identity does not match source and target")  # noqa: TRY003
        edge_identities = tuple((step.source, step.target) for step in step_items)
        if len(edge_identities) != len(set(edge_identities)):
            raise FmeaDomainError("migration path must not contain duplicate edges")  # noqa: TRY003
        nodes = (step_items[0].source, *(step.target for step in step_items))
        if len(nodes) != len(set(nodes)):
            raise FmeaDomainError("migration path must not repeat nodes or contain cycles")  # noqa: TRY003
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "steps", step_items)


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    source: tuple[str, str]
    target: tuple[str, str]
    compatible: bool
    blocking_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    checked_at: str
    report_hash: str | None = None

    def __post_init__(self) -> None:
        source = _identity(self.source, "compatibility source")
        target = _identity(self.target, "compatibility target")
        if not isinstance(self.compatible, bool):
            raise FmeaDomainError("compatible must be a boolean")  # noqa: TRY003
        blocking = _texts(self.blocking_reasons, "blocking_reasons")
        warnings = _texts(self.warnings, "warnings")
        if not self.compatible and not blocking:
            raise FmeaDomainError("incompatible report requires blocking reasons")  # noqa: TRY003
        if self.compatible and blocking:
            raise FmeaDomainError("compatible report must not contain blocking reasons")  # noqa: TRY003
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "blocking_reasons", blocking)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "checked_at", _timestamp(self.checked_at, "checked_at"))
        expected_hash = canonical_hash(self, exclude_fields=("report_hash", "checked_at"), max_array_items=10_000)
        if (
            self.report_hash is not None
            and _hash(self.report_hash, "report_hash").removeprefix("sha256:") != expected_hash
        ):
            raise FmeaDomainError("report_hash does not match canonical report")  # noqa: TRY003
        object.__setattr__(self, "report_hash", expected_hash)


@dataclass(frozen=True, slots=True)
class MigrationReport:
    migration_id: str
    plan: MigrationPlan
    source_revision_id: str
    source_revision_hash: str
    status: MigrationReportStatus | str
    mapped_fields: tuple[str, ...]
    dropped_fields: tuple[str, ...]
    unresolved_fields: tuple[str, ...]
    warnings: tuple[str, ...]
    created_at: str
    report_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "migration_id", _id(self.migration_id, "migration_id"))
        if not isinstance(self.plan, MigrationPlan):
            raise FmeaDomainError("plan must be a MigrationPlan")  # noqa: TRY003
        object.__setattr__(self, "source_revision_id", _id(self.source_revision_id, "source_revision_id"))
        object.__setattr__(self, "source_revision_hash", _hash(self.source_revision_hash, "source_revision_hash"))
        object.__setattr__(self, "status", _enum(self.status, MigrationReportStatus, "status"))
        for field_name in ("mapped_fields", "dropped_fields", "unresolved_fields", "warnings"):
            object.__setattr__(self, field_name, _texts(getattr(self, field_name), field_name))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        expected_hash = canonical_hash(self, exclude_fields=("report_hash", "created_at"), max_array_items=10_000)
        if (
            self.report_hash is not None
            and _hash(self.report_hash, "report_hash").removeprefix("sha256:") != expected_hash
        ):
            raise FmeaDomainError("report_hash does not match canonical report")  # noqa: TRY003
        object.__setattr__(self, "report_hash", expected_hash)


__all__ = [
    "CompatibilityReport",
    "MigrationEdge",
    "MigrationPlan",
    "MigrationReport",
    "MigrationReportStatus",
    "MigrationStep",
    "ProposedFieldMapping",
    "SourceStructureItem",
    "TemplateDraft",
    "TemplateDraftStatus",
    "TemplatePatchCandidate",
    "TemplatePatchStatus",
]
