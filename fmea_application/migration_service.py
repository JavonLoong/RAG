"""Provider-neutral application service for explicit FMEA migrations."""

# Immutable public contracts intentionally use ValueError for validation parity
# with the existing FMEA application contracts.
# ruff: noqa: TRY004

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from core_domain.fmea.governance import FmeaRevision, revision_content_hash
from core_domain.fmea.states import ActorType
from core_domain.fmea.template_migration import (
    CompatibilityReport,
    MigrationPlan,
    MigrationReport,
    MigrationReportStatus,
)

from .ports import MigrationReportRequestConflict, MigrationRepository
from .review_contracts import ActorContext, idempotency_key_hash
from .review_errors import ReviewError

_HASH = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_PACK_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SEMVER = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_MAX_ITEMS = 512
_MAX_TEXT_LENGTH = 4096
_MAX_ID_LENGTH = 256

_MIGRATION_ERROR_CODES = frozenset({
    "FMEA_MIGRATION_REQUEST_INVALID",
    "FMEA_MIGRATION_FORBIDDEN",
    "FMEA_MIGRATION_SOURCE_MISSING",
    "FMEA_MIGRATION_SOURCE_STALE",
    "FMEA_MIGRATION_SOURCE_INVALID",
    "FMEA_MIGRATION_SOURCE_PACK_MISSING",
    "FMEA_MIGRATION_SOURCE_PACK_INVALID",
    "FMEA_MIGRATION_SOURCE_PACK_STALE",
    "FMEA_MIGRATION_TARGET_MISSING",
    "FMEA_MIGRATION_TARGET_INVALID",
    "FMEA_MIGRATION_TARGET_STALE",
    "FMEA_MIGRATION_EDGE_MISSING",
    "FMEA_MIGRATION_EDGE_AMBIGUOUS",
    "FMEA_MIGRATION_EDGE_CYCLIC",
    "FMEA_MIGRATION_REGISTRY_INVALID",
    "FMEA_MIGRATION_ADAPTER_INVALID",
    "FMEA_MIGRATION_ADAPTER_FAILED",
    "FMEA_MIGRATION_REPORT_MISSING",
    "FMEA_MIGRATION_REPORT_INVALID",
    "FMEA_MIGRATION_REPORT_STALE",
    "FMEA_MIGRATION_IDEMPOTENCY_CONFLICT",
    "FMEA_VERSION_CONFLICT",
    "FMEA_MIGRATION_STORAGE_UNAVAILABLE",
    "FMEA_MIGRATION_CONFIRMATION_REQUIRED",
    "FMEA_MIGRATION_FAILED",
})


class MigrationServiceError(ReviewError):
    """A safe public ReviewError for migration operations."""

    def __init__(self, code: str, public_message: str, retryable: bool = False) -> None:
        if code not in _MIGRATION_ERROR_CODES:
            raise ValueError(f"unknown migration error code: {code}")  # noqa: TRY003
        if not isinstance(public_message, str) or not public_message.strip():
            raise ValueError("public_message must not be empty")  # noqa: TRY003
        if not isinstance(retryable, bool):
            raise ValueError("retryable must be a boolean")  # noqa: TRY003
        self.code = code
        self.public_message = public_message.strip()
        self.retryable = retryable
        ValueError.__init__(self, self.public_message)

    def __str__(self) -> str:
        return f"{self.code}: {self.public_message}"


def _text(value: object, field_name: str, *, limit: int = _MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")  # noqa: TRY003
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")  # noqa: TRY003
    if len(normalized) > limit:
        raise ValueError(f"{field_name} exceeds maximum length {limit}")  # noqa: TRY003
    if any(ord(character) < 32 and character not in {"\n", "\r", "\t"} for character in normalized):
        raise ValueError(f"{field_name} contains a control character")  # noqa: TRY003
    return normalized


def _id(value: object, field_name: str) -> str:
    return _text(value, field_name, limit=_MAX_ID_LENGTH)


def _hash(value: object, field_name: str) -> str:
    normalized = _text(value, field_name, limit=71)
    if _HASH.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hash")  # noqa: TRY003
    return normalized


def _digest(value: str) -> str:
    return value.removeprefix("sha256:")


def _pack_id(value: object, field_name: str) -> str:
    normalized = _text(value, field_name, limit=128)
    if _PACK_ID.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} is not a valid domain-pack identity")  # noqa: TRY003
    return normalized


def _version(value: object, field_name: str) -> str:
    normalized = _text(value, field_name, limit=128)
    if _SEMVER.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must be a semantic version")  # noqa: TRY003
    return normalized


def _identity(value: object, field_name: str) -> tuple[str, str]:
    if not isinstance(value, tuple | list) or len(value) != 2:
        raise ValueError(f"{field_name} must be an ID/version pair")  # noqa: TRY003
    return _pack_id(value[0], f"{field_name} ID"), _version(value[1], f"{field_name} version")


def _identity_with_hash(value: object, field_name: str) -> tuple[str, str, str]:
    if not isinstance(value, tuple | list) or len(value) != 3:
        raise ValueError(f"{field_name} must be an ID/version/hash triple")  # noqa: TRY003
    identity = _identity(value[:2], field_name)
    return identity[0], identity[1], _hash(value[2], f"{field_name} hash")


def _texts(value: object, field_name: str, *, unique: bool = True) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise ValueError(f"{field_name} must be a tuple or list")  # noqa: TRY003
    if len(value) > _MAX_ITEMS:
        raise ValueError(f"{field_name} exceeds maximum size {_MAX_ITEMS}")  # noqa: TRY003
    result = tuple(_text(item, field_name, limit=_MAX_ID_LENGTH) for item in value)
    if unique and len(result) != len(set(result)):
        raise ValueError(f"{field_name} must not contain duplicates")  # noqa: TRY003
    return result


def _positive(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be positive")  # noqa: TRY003
    return value


def _validate_key(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("idempotency_key must be a canonical lowercase UUID")  # noqa: TRY003
    idempotency_key_hash(value)
    return value


def migration_report_id(workspace_id: str, migration_id: str) -> str:
    """Return the stable public identity of one workspace migration report."""

    return "migration-report-" + sha256(f"{_id(workspace_id, 'workspace_id')}:{_id(migration_id, 'migration_id')}".encode()).hexdigest()[:40]


@dataclass(frozen=True, slots=True)
class MigrationCommand:
    """Immutable request for one source-revision to domain-pack dry run."""

    migration_id: str
    source_revision_id: str
    source_revision_hash: str
    target_domain_pack_id: str
    target_domain_pack_version: str
    target_domain_pack_hash: str
    idempotency_key: str
    expected_source_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "migration_id", _id(self.migration_id, "migration_id"))
        object.__setattr__(self, "source_revision_id", _id(self.source_revision_id, "source_revision_id"))
        object.__setattr__(self, "source_revision_hash", _hash(self.source_revision_hash, "source_revision_hash"))
        object.__setattr__(self, "target_domain_pack_id", _pack_id(self.target_domain_pack_id, "target_domain_pack_id"))
        object.__setattr__(
            self,
            "target_domain_pack_version",
            _version(self.target_domain_pack_version, "target_domain_pack_version"),
        )
        object.__setattr__(
            self, "target_domain_pack_hash", _hash(self.target_domain_pack_hash, "target_domain_pack_hash")
        )
        object.__setattr__(self, "idempotency_key", _validate_key(self.idempotency_key))
        object.__setattr__(
            self, "expected_source_version", _positive(self.expected_source_version, "expected_source_version")
        )


@dataclass(frozen=True, slots=True)
class CompatibilityCommand:
    """Immutable request for checking an explicitly registered migration path."""

    source_domain_pack_id: str
    source_domain_pack_version: str
    target_domain_pack_id: str
    target_domain_pack_version: str
    target_domain_pack_hash: str
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_domain_pack_id", _pack_id(self.source_domain_pack_id, "source_domain_pack_id"))
        object.__setattr__(
            self, "source_domain_pack_version", _version(self.source_domain_pack_version, "source_domain_pack_version")
        )
        object.__setattr__(self, "target_domain_pack_id", _pack_id(self.target_domain_pack_id, "target_domain_pack_id"))
        object.__setattr__(
            self,
            "target_domain_pack_version",
            _version(self.target_domain_pack_version, "target_domain_pack_version"),
        )
        object.__setattr__(
            self, "target_domain_pack_hash", _hash(self.target_domain_pack_hash, "target_domain_pack_hash")
        )
        object.__setattr__(self, "idempotency_key", _validate_key(self.idempotency_key))

    @property
    def source_identity(self) -> tuple[str, str]:
        return self.source_domain_pack_id, self.source_domain_pack_version

    @property
    def target_identity(self) -> tuple[str, str]:
        return self.target_domain_pack_id, self.target_domain_pack_version


@dataclass(frozen=True, slots=True)
class ConfirmMigrationCommand:
    """Immutable human confirmation bound to one stored dry-run report."""

    migration_id: str
    report_hash: str
    source_revision_id: str
    source_revision_hash: str
    target_domain_pack_id: str
    target_domain_pack_version: str
    target_domain_pack_hash: str
    dry_run_command: MigrationCommand
    idempotency_key: str
    confirm_migration: bool
    expected_report_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "migration_id", _id(self.migration_id, "migration_id"))
        object.__setattr__(self, "report_hash", _hash(self.report_hash, "report_hash"))
        object.__setattr__(self, "source_revision_id", _id(self.source_revision_id, "source_revision_id"))
        object.__setattr__(self, "source_revision_hash", _hash(self.source_revision_hash, "source_revision_hash"))
        object.__setattr__(self, "target_domain_pack_id", _pack_id(self.target_domain_pack_id, "target_domain_pack_id"))
        object.__setattr__(
            self,
            "target_domain_pack_version",
            _version(self.target_domain_pack_version, "target_domain_pack_version"),
        )
        object.__setattr__(
            self, "target_domain_pack_hash", _hash(self.target_domain_pack_hash, "target_domain_pack_hash")
        )
        if not isinstance(self.dry_run_command, MigrationCommand):
            raise ValueError("dry_run_command must be a MigrationCommand")  # noqa: TRY003
        object.__setattr__(self, "idempotency_key", _validate_key(self.idempotency_key))
        if not isinstance(self.confirm_migration, bool):
            raise ValueError("confirm_migration must be a boolean")  # noqa: TRY003
        object.__setattr__(
            self, "expected_report_version", _positive(self.expected_report_version, "expected_report_version")
        )


@dataclass(frozen=True, slots=True)
class MigrationCandidate:
    """Immutable provider-neutral output of one registered migration adapter."""

    target_revision: FmeaRevision
    mapped_fields: tuple[str, ...] = ()
    dropped_fields: tuple[str, ...] = ()
    unresolved_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.target_revision, FmeaRevision):
            raise ValueError("target_revision must be an FmeaRevision")  # noqa: TRY003
        for field_name in ("mapped_fields", "dropped_fields", "unresolved_fields", "warnings"):
            object.__setattr__(self, field_name, _texts(getattr(self, field_name), field_name))

    @property
    def target_domain_pack_identity(self) -> tuple[str, str, str]:
        return self.target_revision.domain_pack_identity


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Provider-neutral result returned after one atomic confirmed migration."""

    migration_id: str
    child_revision_id: str
    report_hash: str
    replayed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "migration_id", _id(self.migration_id, "migration_id"))
        object.__setattr__(self, "child_revision_id", _id(self.child_revision_id, "child_revision_id"))
        object.__setattr__(self, "report_hash", _hash(self.report_hash, "report_hash"))
        if not isinstance(self.replayed, bool):
            raise ValueError("replayed must be a boolean")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class PreparedMigration:
    """Complete immutable unit handed to the repository's atomic commit port."""

    command: ConfirmMigrationCommand
    dry_run_command: MigrationCommand
    source: FmeaRevision
    source_record_version: int
    plan: MigrationPlan
    candidate: MigrationCandidate
    report: MigrationReport
    target_domain_pack_identity: tuple[str, str, str]
    actor: ActorContext

    def __post_init__(self) -> None:  # noqa: C901
        if not isinstance(self.command, ConfirmMigrationCommand):
            raise ValueError("command must be a ConfirmMigrationCommand")  # noqa: TRY003
        if not isinstance(self.dry_run_command, MigrationCommand):
            raise ValueError("dry_run_command must be a MigrationCommand")  # noqa: TRY003
        if not isinstance(self.source, FmeaRevision):
            raise ValueError("source must be an FmeaRevision")  # noqa: TRY003
        if not isinstance(self.plan, MigrationPlan):
            raise ValueError("plan must be a MigrationPlan")  # noqa: TRY003
        if not isinstance(self.candidate, MigrationCandidate):
            raise ValueError("candidate must be a MigrationCandidate")  # noqa: TRY003
        if not isinstance(self.report, MigrationReport):
            raise ValueError("report must be a MigrationReport")  # noqa: TRY003
        if not isinstance(self.actor, ActorContext):
            raise ValueError("actor must be an ActorContext")  # noqa: TRY003
        object.__setattr__(
            self, "source_record_version", _positive(self.source_record_version, "source_record_version")
        )
        target = _identity_with_hash(self.target_domain_pack_identity, "target_domain_pack_identity")
        object.__setattr__(self, "target_domain_pack_identity", target)
        expected_target = (
            self.command.target_domain_pack_id,
            self.command.target_domain_pack_version,
            self.command.target_domain_pack_hash,
        )
        if target[:2] != expected_target[:2] or _digest(target[2]) != _digest(expected_target[2]):
            raise ValueError("prepared target domain pack binding is invalid")  # noqa: TRY003
        if self.command.migration_id != self.dry_run_command.migration_id:
            raise ValueError("prepared migration identity is invalid")  # noqa: TRY003
        if self.command.dry_run_command != self.dry_run_command:
            raise ValueError("prepared dry-run request binding is invalid")  # noqa: TRY003
        if self.report.migration_id != self.command.migration_id:
            raise ValueError("prepared report identity is invalid")  # noqa: TRY003
        if self.report.status is not MigrationReportStatus.DRY_RUN:
            raise ValueError("prepared report must be a dry-run report")  # noqa: TRY003
        if self.report.source_revision_id != self.source.revision_id:
            raise ValueError("prepared source revision identity is invalid")  # noqa: TRY003
        if _digest(self.report.source_revision_hash) != _digest(self.source.revision_hash):
            raise ValueError("prepared source revision hash is invalid")  # noqa: TRY003
        if self.report.source_domain_pack_identity != self.source.domain_pack_identity:
            raise ValueError("prepared source domain pack binding is invalid")  # noqa: TRY003
        if self.report.target_domain_pack_identity != target:
            raise ValueError("prepared report target domain pack binding is invalid")  # noqa: TRY003
        if _digest(self.report.target_revision_hash) != _digest(self.candidate.target_revision.revision_hash):
            raise ValueError("prepared report target revision binding is invalid")  # noqa: TRY003
        if self.plan != self.report.plan or self.plan.source != self.source.domain_pack_identity[:2]:
            raise ValueError("prepared migration plan binding is invalid")  # noqa: TRY003
        if self.plan.target != expected_target[:2] or self.candidate.target_domain_pack_identity != target:
            raise ValueError("prepared migration target binding is invalid")  # noqa: TRY003
        try:
            candidate_hash = revision_content_hash(self.candidate.target_revision)
        except Exception:
            raise ValueError("prepared migration candidate is invalid") from None  # noqa: TRY003
        if _digest(candidate_hash) != _digest(self.candidate.target_revision.revision_hash):
            raise ValueError("prepared migration candidate hash is invalid")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class _DryRunRecord:
    command: MigrationCommand
    source: FmeaRevision
    source_record_version: int
    plan: MigrationPlan
    candidate: MigrationCandidate
    report: MigrationReport


def _error(code: str, message: str, *, retryable: bool = False) -> MigrationServiceError:
    return MigrationServiceError(code, message, retryable=retryable)


def _registry_code(exc: Exception) -> str | None:
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and code in _MIGRATION_ERROR_CODES else None


def _same_migration_fields(left: MigrationCommand, right: ConfirmMigrationCommand) -> bool:
    return (
        left.migration_id == right.migration_id
        and left.source_revision_id == right.source_revision_id
        and _digest(left.source_revision_hash) == _digest(right.source_revision_hash)
        and left.target_domain_pack_id == right.target_domain_pack_id
        and left.target_domain_pack_version == right.target_domain_pack_version
        and _digest(left.target_domain_pack_hash) == _digest(right.target_domain_pack_hash)
        and left == right.dry_run_command
    )


class MigrationService:
    """Coordinate explicit migration planning without owning persistence."""

    def __init__(
        self,
        repository: MigrationRepository,
        migration_registry: Any,
        *,
        domain_pack_registry: Any,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._migration_registry = migration_registry
        self._domain_pack_registry = domain_pack_registry
        self._clock = clock or self._default_clock
        self._dry_runs: dict[tuple[str, str], _DryRunRecord] = {}

    @staticmethod
    def _default_clock() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    @staticmethod
    def _authorize(actor: ActorContext) -> None:
        if not isinstance(actor, ActorContext):
            raise _error("FMEA_MIGRATION_REQUEST_INVALID", "migration actor context is invalid")
        if actor.actor_type is not ActorType.HUMAN or "template_admin" not in actor.roles:
            raise _error("FMEA_MIGRATION_FORBIDDEN", "only a human template_admin may run an FMEA migration")

    def _load_source(self, command: MigrationCommand, actor: ActorContext) -> tuple[FmeaRevision, int]:  # noqa: C901
        try:
            source = self._repository.get_revision(command.source_revision_id, actor.workspace_id)
        except Exception:
            raise _error(
                "FMEA_MIGRATION_STORAGE_UNAVAILABLE", "source revision storage is unavailable", retryable=True
            ) from None
        if source is None:
            raise _error("FMEA_MIGRATION_SOURCE_MISSING", "source revision was not found")
        if (
            not isinstance(source, FmeaRevision)
            or source.revision_id != command.source_revision_id
            or source.workspace_id != actor.workspace_id
        ):
            raise _error("FMEA_MIGRATION_SOURCE_MISSING", "source revision was not found")
        if _digest(source.revision_hash) != _digest(command.source_revision_hash):
            raise _error("FMEA_MIGRATION_SOURCE_STALE", "source revision hash is stale")
        try:
            computed_hash = revision_content_hash(source)
        except Exception:
            raise _error("FMEA_MIGRATION_SOURCE_INVALID", "source revision content is invalid") from None
        if _digest(computed_hash) != _digest(source.revision_hash):
            raise _error("FMEA_MIGRATION_SOURCE_INVALID", "source revision content hash is invalid")
        source_pack = self._load_pack_identity(
            source.domain_pack_identity[0],
            source.domain_pack_identity[1],
            missing_code="FMEA_MIGRATION_SOURCE_PACK_MISSING",
            invalid_code="FMEA_MIGRATION_SOURCE_PACK_INVALID",
            label="source",
        )
        if source_pack[:2] != source.domain_pack_identity[:2] or _digest(source_pack[2]) != _digest(
            source.domain_pack_identity[2]
        ):
            raise _error(
                "FMEA_MIGRATION_SOURCE_PACK_STALE",
                "source revision domain-pack identity is stale",
            )
        try:
            record_version = self._repository.get_revision_record_version(
                command.source_revision_id, actor.workspace_id
            )
        except Exception:
            raise _error(
                "FMEA_MIGRATION_STORAGE_UNAVAILABLE", "source revision storage is unavailable", retryable=True
            ) from None
        if isinstance(record_version, bool) or not isinstance(record_version, int) or record_version < 1:
            raise _error("FMEA_MIGRATION_STORAGE_UNAVAILABLE", "source revision version is unavailable", retryable=True)
        if record_version != command.expected_source_version:
            raise _error("FMEA_VERSION_CONFLICT", "source revision version is stale")
        return source, record_version

    def _load_pack_identity(
        self,
        pack_id: str,
        version: str,
        *,
        missing_code: str,
        invalid_code: str,
        label: str,
    ) -> tuple[str, str, str]:
        try:
            pack = self._domain_pack_registry.get(pack_id, version)
        except Exception:
            raise _error(
                "FMEA_MIGRATION_STORAGE_UNAVAILABLE",
                f"{label} domain-pack storage is unavailable",
                retryable=True,
            ) from None
        if pack is None:
            raise _error(missing_code, f"{label} domain pack was not found")
        try:
            return (
                _pack_id(getattr(pack, "pack_id", None), f"{label} domain pack id"),
                _version(getattr(pack, "version", None), f"{label} domain pack version"),
                _hash(getattr(pack, "content_hash", None), f"{label} domain pack hash"),
            )
        except Exception:
            raise _error(invalid_code, f"{label} domain pack identity is invalid") from None

    def _load_target(self, command: MigrationCommand) -> tuple[str, str, str]:
        actual = self._load_pack_identity(
            command.target_domain_pack_id,
            command.target_domain_pack_version,
            missing_code="FMEA_MIGRATION_TARGET_MISSING",
            invalid_code="FMEA_MIGRATION_TARGET_INVALID",
            label="target",
        )
        expected = (
            command.target_domain_pack_id,
            command.target_domain_pack_version,
            command.target_domain_pack_hash,
        )
        if actual[:2] != expected[:2] or _digest(actual[2]) != _digest(expected[2]):
            raise _error("FMEA_MIGRATION_TARGET_STALE", "target domain pack hash or identity is stale")
        return actual

    def _resolve(self, source: tuple[str, str], target: tuple[str, str]) -> MigrationPlan:
        try:
            plan = self._migration_registry.resolve(source, target)
        except Exception as exc:
            code = _registry_code(exc) or "FMEA_MIGRATION_REGISTRY_INVALID"
            raise _error(code, "migration compatibility graph is not usable") from None
        if not isinstance(plan, MigrationPlan):
            raise _error("FMEA_MIGRATION_REGISTRY_INVALID", "migration compatibility graph returned an invalid plan")
        return plan

    def _apply(  # noqa: C901
        self,
        source: FmeaRevision,
        plan: MigrationPlan,
        target_identity: tuple[str, str, str],
    ) -> MigrationCandidate:
        mapped: list[str] = []
        dropped: list[str] = []
        unresolved: list[str] = []
        warnings: list[str] = []
        current = source

        def add_unique(destination: list[str], values: tuple[str, ...]) -> None:
            for value in values:
                if value not in destination:
                    destination.append(value)

        for step in plan.steps:
            if current.domain_pack_identity[:2] != step.source:
                raise _error(
                    "FMEA_MIGRATION_ADAPTER_INVALID",
                    "migration adapter source does not match the registered edge",
                )
            try:
                adapter = self._migration_registry.adapter_for(step)
            except Exception as exc:
                code = _registry_code(exc) or "FMEA_MIGRATION_REGISTRY_INVALID"
                raise _error(code, "migration adapter is not registered") from None
            if not callable(getattr(adapter, "migrate", None)):
                raise _error("FMEA_MIGRATION_ADAPTER_INVALID", "migration adapter is invalid")
            try:
                candidate = adapter.migrate(current)
            except Exception:
                raise _error(
                    "FMEA_MIGRATION_ADAPTER_FAILED", "migration adapter execution failed", retryable=True
                ) from None
            if not isinstance(candidate, MigrationCandidate):
                raise _error("FMEA_MIGRATION_ADAPTER_INVALID", "migration adapter returned an invalid candidate")
            target_revision = candidate.target_revision
            if not isinstance(target_revision, FmeaRevision):
                raise _error("FMEA_MIGRATION_ADAPTER_INVALID", "migration adapter target revision is invalid")
            try:
                computed_hash = revision_content_hash(target_revision)
            except Exception:
                raise _error("FMEA_MIGRATION_ADAPTER_INVALID", "migration adapter target revision is invalid") from None
            if _digest(computed_hash) != _digest(target_revision.revision_hash):
                raise _error("FMEA_MIGRATION_ADAPTER_INVALID", "migration adapter target revision hash is invalid")
            if (
                target_revision.workspace_id != source.workspace_id
                or target_revision.analysis_id != source.analysis_id
                or target_revision.domain_pack_identity[:2] != step.target
            ):
                raise _error(
                    "FMEA_MIGRATION_ADAPTER_INVALID", "migration adapter target does not match the registered edge"
                )
            registered_target = self._load_pack_identity(
                step.target[0],
                step.target[1],
                missing_code="FMEA_MIGRATION_ADAPTER_INVALID",
                invalid_code="FMEA_MIGRATION_ADAPTER_INVALID",
                label="adapter target",
            )
            if registered_target[:2] != target_revision.domain_pack_identity[:2] or _digest(
                registered_target[2]
            ) != _digest(target_revision.domain_pack_identity[2]):
                raise _error(
                    "FMEA_MIGRATION_ADAPTER_INVALID",
                    "migration adapter target does not match the registered domain pack",
                )
            current = target_revision
            add_unique(mapped, candidate.mapped_fields)
            add_unique(dropped, candidate.dropped_fields)
            add_unique(unresolved, candidate.unresolved_fields)
            add_unique(warnings, candidate.warnings)
        if (
            current is source
            or current.domain_pack_identity[:2] != target_identity[:2]
            or _digest(current.domain_pack_identity[2]) != _digest(target_identity[2])
        ):
            raise _error(
                "FMEA_MIGRATION_ADAPTER_INVALID",
                "final migration adapter target does not match the requested domain pack",
            )
        try:
            return MigrationCandidate(
                target_revision=current,
                mapped_fields=tuple(mapped),
                dropped_fields=tuple(dropped),
                unresolved_fields=tuple(unresolved),
                warnings=tuple(warnings),
            )
        except ValueError:
            raise _error("FMEA_MIGRATION_ADAPTER_INVALID", "migration adapter output is invalid") from None

    def _build_record(self, command: MigrationCommand, actor: ActorContext) -> _DryRunRecord:
        source, source_record_version = self._load_source(command, actor)
        target = self._load_target(command)
        plan = self._resolve(source.domain_pack_identity[:2], target[:2])
        candidate = self._apply(source, plan, target)
        try:
            report = MigrationReport(
                migration_id=command.migration_id,
                plan=plan,
                source_revision_id=source.revision_id,
                source_revision_hash=source.revision_hash,
                source_domain_pack_identity=source.domain_pack_identity,
                target_domain_pack_identity=target,
                target_revision_hash=candidate.target_revision.revision_hash,
                status=MigrationReportStatus.DRY_RUN,
                mapped_fields=candidate.mapped_fields,
                dropped_fields=candidate.dropped_fields,
                unresolved_fields=candidate.unresolved_fields,
                warnings=candidate.warnings,
                created_at=self._clock(),
            )
        except Exception:
            raise _error("FMEA_MIGRATION_REPORT_INVALID", "migration report could not be created") from None
        return _DryRunRecord(command, source, source_record_version, plan, candidate, report)

    def _stored_report(self, command: MigrationCommand, workspace_id: str) -> MigrationReport | None:
        getter = getattr(self._repository, "get_migration_report", None)
        if getter is None:
            return None
        if not callable(getter):
            raise _error(
                "FMEA_MIGRATION_STORAGE_UNAVAILABLE", "migration report storage is unavailable", retryable=True
            )
        try:
            report = getter(command.migration_id, workspace_id, command=command)
        except MigrationReportRequestConflict:
            raise _error(
                "FMEA_MIGRATION_IDEMPOTENCY_CONFLICT",
                "migration request identity conflicts with the stored dry run",
            ) from None
        except Exception:
            raise _error(
                "FMEA_MIGRATION_STORAGE_UNAVAILABLE", "migration report storage is unavailable", retryable=True
            ) from None
        if report is not None and not isinstance(report, MigrationReport):
            raise _error("FMEA_MIGRATION_REPORT_INVALID", "stored migration report is invalid")
        return report

    def dry_run(self, command: MigrationCommand, actor: ActorContext) -> MigrationReport:  # noqa: C901
        self._authorize(actor)
        if not isinstance(command, MigrationCommand):
            raise _error("FMEA_MIGRATION_REQUEST_INVALID", "migration dry-run request is invalid")
        cache_key = (actor.workspace_id, command.migration_id)
        cached = self._dry_runs.get(cache_key)
        if cached is not None:
            if cached.command != command:
                raise _error(
                    "FMEA_MIGRATION_IDEMPOTENCY_CONFLICT",
                    "migration request identity conflicts with the stored dry run",
                )
            source, _ = self._load_source(command, actor)
            target = self._load_target(command)
            plan = self._resolve(source.domain_pack_identity[:2], target[:2])
            if plan != cached.plan:
                raise _error("FMEA_MIGRATION_REPORT_STALE", "stored migration report is stale")
            stored = self._stored_report(command, actor.workspace_id)
            if stored is not None and stored.report_hash != cached.report.report_hash:
                raise _error("FMEA_MIGRATION_REPORT_STALE", "stored migration report hash is stale")
            return cached.report if stored is None else stored

        stored = self._stored_report(command, actor.workspace_id)
        record = self._build_record(command, actor)
        if stored is not None:
            if stored.status is not MigrationReportStatus.DRY_RUN or stored.report_hash != record.report.report_hash:
                raise _error(
                    "FMEA_MIGRATION_REPORT_STALE", "stored migration report does not match the deterministic dry run"
                )
            record = _DryRunRecord(
                record.command,
                record.source,
                record.source_record_version,
                record.plan,
                record.candidate,
                stored,
            )
            self._dry_runs[cache_key] = record
            return stored
        saver = getattr(self._repository, "save_migration_report", None)
        if not callable(saver):
            raise _error(
                "FMEA_MIGRATION_STORAGE_UNAVAILABLE", "migration report storage is unavailable", retryable=True
            )
        try:
            saved = saver(record.report, command=command, actor=actor)
        except MigrationServiceError:
            raise
        except Exception:
            raise _error(
                "FMEA_MIGRATION_STORAGE_UNAVAILABLE", "migration report storage is unavailable", retryable=True
            ) from None
        if not isinstance(saved, MigrationReport) or saved.report_hash != record.report.report_hash:
            raise _error("FMEA_MIGRATION_REPORT_INVALID", "migration report storage returned an invalid report")
        record = _DryRunRecord(
            record.command,
            record.source,
            record.source_record_version,
            record.plan,
            record.candidate,
            saved,
        )
        self._dry_runs[cache_key] = record
        return saved

    def compatibility(
        self, command: CompatibilityCommand | MigrationCommand, actor: ActorContext
    ) -> CompatibilityReport:
        self._authorize(actor)
        if isinstance(command, CompatibilityCommand):
            source = command.source_identity
            target_command = MigrationCommand(
                migration_id="compatibility-check",
                source_revision_id="compatibility-source",
                source_revision_hash="0" * 64,
                target_domain_pack_id=command.target_domain_pack_id,
                target_domain_pack_version=command.target_domain_pack_version,
                target_domain_pack_hash=command.target_domain_pack_hash,
                idempotency_key=command.idempotency_key,
            )
        elif isinstance(command, MigrationCommand):
            source_revision, _ = self._load_source(command, actor)
            source = source_revision.domain_pack_identity[:2]
            target_command = command
        else:
            raise _error("FMEA_MIGRATION_REQUEST_INVALID", "migration compatibility request is invalid")
        target = self._load_target(target_command)
        try:
            plan = self._resolve(source, target[:2])
        except MigrationServiceError as exc:
            if exc.code not in {
                "FMEA_MIGRATION_EDGE_MISSING",
                "FMEA_MIGRATION_EDGE_AMBIGUOUS",
                "FMEA_MIGRATION_EDGE_CYCLIC",
                "FMEA_MIGRATION_REGISTRY_INVALID",
            }:
                raise
            return CompatibilityReport(
                source=source,
                target=target[:2],
                compatible=False,
                blocking_reasons=(exc.code,),
                warnings=(),
                checked_at=self._clock(),
            )
        return CompatibilityReport(
            source=plan.source,
            target=plan.target,
            compatible=True,
            blocking_reasons=(),
            warnings=(),
            checked_at=self._clock(),
        )

    def _record_for_confirmation(self, command: ConfirmMigrationCommand, actor: ActorContext) -> _DryRunRecord:
        cache_key = (actor.workspace_id, command.migration_id)
        cached = self._dry_runs.get(cache_key)
        if cached is not None and cached.command.migration_id != command.migration_id:
            cached = None
        if cached is not None:
            record = cached
            stored = self._stored_report(record.command, actor.workspace_id)
            source, source_version = self._load_source(record.command, actor)
            target = self._load_target(record.command)
            if not _same_migration_fields(record.command, command):
                raise _error("FMEA_MIGRATION_REPORT_STALE", "confirmation preconditions do not match the dry run")
            if stored is not None and stored.report_hash != record.report.report_hash:
                raise _error("FMEA_MIGRATION_REPORT_STALE", "stored migration report hash is stale")
            if command.report_hash != record.report.report_hash:
                raise _error("FMEA_MIGRATION_REPORT_STALE", "confirmation report hash is stale")
            plan = self._resolve(source.domain_pack_identity[:2], target[:2])
            if plan != record.plan:
                raise _error("FMEA_MIGRATION_REPORT_STALE", "migration compatibility path is stale")
            return _DryRunRecord(record.command, source, source_version, plan, record.candidate, record.report)
        dry_command = command.dry_run_command
        stored = self._stored_report(dry_command, actor.workspace_id)
        if stored is None:
            raise _error("FMEA_MIGRATION_REPORT_MISSING", "a stored dry-run report is required")
        if not _same_migration_fields(dry_command, command):
            raise _error("FMEA_MIGRATION_REPORT_STALE", "confirmation preconditions do not match the dry run")
        record = self._build_record(dry_command, actor)
        if (
            stored.report_hash != command.report_hash
            or stored.report_hash != record.report.report_hash
            or stored.status is not MigrationReportStatus.DRY_RUN
        ):
            raise _error("FMEA_MIGRATION_REPORT_STALE", "confirmation report is not the stored dry-run report")
        return _DryRunRecord(
            dry_command, record.source, record.source_record_version, record.plan, record.candidate, stored
        )

    def confirm(self, command: ConfirmMigrationCommand, actor: ActorContext) -> MigrationResult:  # noqa: C901
        self._authorize(actor)
        if not isinstance(command, ConfirmMigrationCommand):
            raise _error("FMEA_MIGRATION_REQUEST_INVALID", "migration confirmation request is invalid")
        if command.confirm_migration is not True:
            raise _error("FMEA_MIGRATION_CONFIRMATION_REQUIRED", "explicit migration confirmation is required")
        if command.expected_report_version != 1:
            raise _error("FMEA_VERSION_CONFLICT", "migration report version is stale")
        record = self._record_for_confirmation(command, actor)
        target = self._load_target(record.command)
        try:
            prepared = PreparedMigration(
                command=command,
                dry_run_command=record.command,
                source=record.source,
                source_record_version=record.source_record_version,
                plan=record.plan,
                candidate=record.candidate,
                report=record.report,
                target_domain_pack_identity=target,
                actor=actor,
            )
        except Exception:
            raise _error("FMEA_MIGRATION_REPORT_INVALID", "migration commit unit is invalid") from None
        committer = getattr(self._repository, "commit_migration", None)
        if not callable(committer):
            raise _error(
                "FMEA_MIGRATION_STORAGE_UNAVAILABLE", "migration commit storage is unavailable", retryable=True
            )
        try:
            result = committer(prepared)
        except MigrationServiceError:
            raise
        except ReviewError:
            raise _error(
                "FMEA_MIGRATION_FAILED", "confirmed migration could not be committed", retryable=True
            ) from None
        except Exception:
            raise _error(
                "FMEA_MIGRATION_FAILED", "confirmed migration could not be committed", retryable=True
            ) from None
        if not isinstance(result, MigrationResult):
            raise _error("FMEA_MIGRATION_FAILED", "migration repository returned an invalid result")
        if result.migration_id != command.migration_id or _digest(result.report_hash) != _digest(
            record.report.report_hash
        ):
            raise _error("FMEA_MIGRATION_FAILED", "migration repository returned a mismatched result")
        return result


__all__ = [
    "CompatibilityCommand",
    "ConfirmMigrationCommand",
    "MigrationCandidate",
    "MigrationCommand",
    "MigrationResult",
    "MigrationService",
    "MigrationServiceError",
    "PreparedMigration",
]
