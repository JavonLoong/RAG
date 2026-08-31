"""Application-layer commands and atomic handoffs for FMEA governance."""

# These contracts intentionally raise ValueError for malformed application
# input, matching the existing immutable risk/review contracts.
# ruff: noqa: TRY003, TRY004

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from core_domain.fmea.governance import (
    ApprovalDecision,
    ApprovalStatus,
    ApprovalSubmission,
    ApprovalWithdrawalRecord,
    FmeaRevision,
    PublicationManifest,
    PublicationWithdrawalRecord,
    PublishedRevision,
    SupersessionRecord,
    canonical_hash,
    canonical_json_value,
    validate_approval_binding,
    validate_supersession_binding,
)
from fmea_application.snapshot_contracts import NormalizedFmeaSnapshot

from .review_contracts import AuditEvent, IdempotencyScope, idempotency_key_hash
from .risk_contracts import OutboxEvent, outbox_payload_hash

if TYPE_CHECKING:
    from .revision_assembler import PublicationReadinessReport

_HASH = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _hash(value: object, field_name: str) -> str:
    normalized = _text(value, field_name)
    if _HASH.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hash")
    return normalized


def _positive(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


def _hash_pairs(value: object, field_name: str) -> tuple[tuple[str, str], ...]:
    if isinstance(value, str | bytes) or value is None:
        raise ValueError(f"{field_name} must be a sequence")
    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(f"{field_name} must be a sequence") from exc
    result: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, tuple | list) or len(item) != 2:
            raise ValueError(f"{field_name} must contain pairs")
        result.append((_text(item[0], field_name), _hash(item[1], field_name)))
    if len({key for key, _ in result}) != len(result):
        raise ValueError(f"{field_name} must not contain duplicate identities")
    return tuple(sorted(result))


def _optional_text(value: object, field_name: str) -> str | None:
    return None if value is None else _text(value, field_name)


def _idempotency_key(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("idempotency_key must be a canonical lowercase UUID")
    idempotency_key_hash(value)
    return value


def _validate_payload(payload_hash: str, payload: Mapping[str, object]) -> str:
    normalized = _hash(payload_hash, "payload_hash")
    expected = governance_payload_hash(payload)
    if normalized != expected:
        raise ValueError("payload hash does not match canonical payload")
    return normalized


def _validate_prepared_bindings(  # noqa: C901
    *,
    scope: IdempotencyScope,
    payload_hash: str,
    payload: Mapping[str, object],
    audit: AuditEvent,
    outbox: OutboxEvent,
    workspace_id: str,
    aggregate_id: str,
    analysis_id: str | None = None,
    resource_actor_id: str | None = None,
) -> None:
    if not isinstance(scope, IdempotencyScope):
        raise ValueError("scope must be an IdempotencyScope")
    if not isinstance(audit, AuditEvent):
        raise ValueError("audit must be an AuditEvent")
    if not isinstance(outbox, OutboxEvent):
        raise ValueError("outbox must be an OutboxEvent")
    normalized = _validate_payload(payload_hash, payload)
    if scope.workspace_id != workspace_id:
        raise ValueError("scope workspace does not match resource workspace")
    if audit.workspace_id != workspace_id or audit.actor_id != scope.actor_id:
        raise ValueError("audit actor binding is invalid")
    if analysis_id is not None and audit.analysis_id != analysis_id:
        raise ValueError("audit analysis binding is invalid")
    if audit.row_id != aggregate_id:
        raise ValueError("audit aggregate binding is invalid")
    if resource_actor_id is not None and resource_actor_id != scope.actor_id:
        raise ValueError("resource actor binding is invalid")
    if audit.command != scope.command or audit.idempotency_key_hash != scope.key_hash:
        raise ValueError("audit command binding is invalid")
    if audit.canonical_payload_hash != normalized:
        raise ValueError("audit canonical payload hash does not match payload")
    if outbox.workspace_id != workspace_id or outbox.aggregate_id != aggregate_id:
        raise ValueError("outbox aggregate binding is invalid")
    if outbox.scope_key != scope.scope_key or outbox.event_type != scope.command:
        raise ValueError("outbox command binding is invalid")
    if outbox_payload_hash(outbox.payload) != normalized:
        raise ValueError("outbox payload hash does not match payload")


def canonical_governance_payload(
    operation: str,
    command_or_value: object,
    *,
    exclude_fields: tuple[str, ...] = (),
    **objects: object,
) -> Mapping[str, object]:
    """Build one canonical, transport-free JSON payload for a governance write."""

    normalized_operation = _text(operation, "operation")
    if objects:
        raw: dict[str, object] = {"operation": normalized_operation, "command": command_or_value}
        raw.update(objects)
    else:
        raw = {"operation": normalized_operation, "value": command_or_value}
    projected = canonical_json_value(
        raw,
        exclude_fields=frozenset({"idempotency_key", *exclude_fields}),
    )
    if not isinstance(projected, Mapping):  # pragma: no cover - canonical_json_value preserves mappings.
        raise ValueError("canonical governance payload must be an object")
    return projected


def governance_payload_hash(payload: object) -> str:
    return canonical_hash(payload, prefixed=True)


canonical_payload_hash = governance_payload_hash


@dataclass(frozen=True, slots=True)
class RevisionAssemblyRequest:
    analysis_id: str
    parent_revision_id: str | None
    expected_analysis_version: int
    parent_revision_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "analysis_id", _text(self.analysis_id, "analysis_id"))
        object.__setattr__(self, "parent_revision_id", _optional_text(self.parent_revision_id, "parent_revision_id"))
        object.__setattr__(
            self, "expected_analysis_version", _positive(self.expected_analysis_version, "expected_analysis_version")
        )
        object.__setattr__(
            self,
            "parent_revision_hash",
            None if self.parent_revision_hash is None else _hash(self.parent_revision_hash, "parent_revision_hash"),
        )
        if self.parent_revision_id is None and self.parent_revision_hash is not None:
            raise ValueError("parent_revision_hash requires parent_revision_id")


@dataclass(frozen=True, slots=True)
class AssembleRevisionCommand:
    request: RevisionAssemblyRequest
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.request, RevisionAssemblyRequest):
            raise ValueError("request must be a RevisionAssemblyRequest")
        object.__setattr__(self, "idempotency_key", _idempotency_key(self.idempotency_key))


@dataclass(frozen=True, slots=True)
class SubmitApprovalCommand:
    revision_id: str
    revision_hash: str
    expected_revision_version: int
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "revision_id", _text(self.revision_id, "revision_id"))
        object.__setattr__(self, "revision_hash", _hash(self.revision_hash, "revision_hash"))
        object.__setattr__(
            self, "expected_revision_version", _positive(self.expected_revision_version, "expected_revision_version")
        )
        object.__setattr__(self, "idempotency_key", _idempotency_key(self.idempotency_key))


@dataclass(frozen=True, slots=True)
class ApprovalCommand:
    submission_id: str
    revision_id: str
    revision_hash: str
    expected_submission_version: int
    reason: str
    idempotency_key: str

    def __post_init__(self) -> None:
        for field_name in ("submission_id", "revision_id", "reason"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        object.__setattr__(self, "revision_hash", _hash(self.revision_hash, "revision_hash"))
        object.__setattr__(
            self,
            "expected_submission_version",
            _positive(self.expected_submission_version, "expected_submission_version"),
        )
        object.__setattr__(self, "idempotency_key", _idempotency_key(self.idempotency_key))


@dataclass(frozen=True, slots=True)
class ApprovalRejectionCommand(ApprovalCommand):
    pass


@dataclass(frozen=True, slots=True)
class WithdrawApprovalCommand:
    approval_id: str
    revision_hash: str
    expected_approval_version: int
    reason: str
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "approval_id", _text(self.approval_id, "approval_id"))
        object.__setattr__(self, "revision_hash", _hash(self.revision_hash, "revision_hash"))
        object.__setattr__(
            self, "expected_approval_version", _positive(self.expected_approval_version, "expected_approval_version")
        )
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        object.__setattr__(self, "idempotency_key", _idempotency_key(self.idempotency_key))


@dataclass(frozen=True, slots=True)
class PublishCommand:
    revision_id: str
    revision_hash: str
    approval_id: str
    expected_revision_version: int
    idempotency_key: str

    def __post_init__(self) -> None:
        for field_name in ("revision_id", "approval_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        object.__setattr__(self, "revision_hash", _hash(self.revision_hash, "revision_hash"))
        object.__setattr__(
            self, "expected_revision_version", _positive(self.expected_revision_version, "expected_revision_version")
        )
        object.__setattr__(self, "idempotency_key", _idempotency_key(self.idempotency_key))


@dataclass(frozen=True, slots=True)
class PersistReadinessCommand:
    revision_id: str
    revision_hash: str
    expected_revision_version: int
    readiness_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "revision_id", _text(self.revision_id, "revision_id"))
        object.__setattr__(self, "revision_hash", _hash(self.revision_hash, "revision_hash"))
        object.__setattr__(
            self, "expected_revision_version", _positive(self.expected_revision_version, "expected_revision_version")
        )
        object.__setattr__(self, "readiness_id", _text(self.readiness_id, "readiness_id"))
        object.__setattr__(self, "idempotency_key", _idempotency_key(self.idempotency_key))


@dataclass(frozen=True, slots=True)
class WithdrawPublicationCommand:
    publication_id: str
    expected_publication_version: int
    reason: str
    replacement_publication_id: str | None
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "publication_id", _text(self.publication_id, "publication_id"))
        object.__setattr__(
            self,
            "expected_publication_version",
            _positive(self.expected_publication_version, "expected_publication_version"),
        )
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        object.__setattr__(
            self,
            "replacement_publication_id",
            _optional_text(self.replacement_publication_id, "replacement_publication_id"),
        )
        object.__setattr__(self, "idempotency_key", _idempotency_key(self.idempotency_key))


@dataclass(frozen=True, slots=True)
class SupersedePublicationCommand:
    publication_id: str
    replacement_publication_id: str
    expected_publication_version: int
    expected_replacement_version: int
    reason: str
    idempotency_key: str

    def __post_init__(self) -> None:
        for field_name in ("publication_id", "replacement_publication_id", "reason"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        if self.publication_id == self.replacement_publication_id:
            raise ValueError("supersession publications must differ")
        object.__setattr__(
            self,
            "expected_publication_version",
            _positive(self.expected_publication_version, "expected_publication_version"),
        )
        object.__setattr__(
            self,
            "expected_replacement_version",
            _positive(self.expected_replacement_version, "expected_replacement_version"),
        )
        object.__setattr__(self, "idempotency_key", _idempotency_key(self.idempotency_key))


@dataclass(frozen=True, slots=True)
class GovernanceHistoryQuery:
    workspace_id: str
    resource_type: Literal["revision", "publication"]
    resource_id: str
    page_size: int
    cursor: str | None
    descending: bool = False

    def __post_init__(self) -> None:
        for field_name in ("workspace_id", "resource_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        if self.resource_type not in {"revision", "publication"}:
            raise ValueError("resource_type must be revision or publication")
        if isinstance(self.page_size, bool) or not 1 <= self.page_size <= 500:
            raise ValueError("page_size must be between 1 and 500")
        object.__setattr__(self, "cursor", _optional_text(self.cursor, "cursor"))
        if not isinstance(self.descending, bool):
            raise ValueError("descending must be a boolean")


@dataclass(frozen=True, slots=True)
class ReadinessReportRecord:
    readiness_id: str
    report: PublicationReadinessReport
    source_hashes: tuple[tuple[str, str], ...]
    report_hash: str
    canonical_json_hash: str
    created_at: str

    def __post_init__(self) -> None:
        from .revision_assembler import PublicationReadinessReport as _PublicationReadinessReport

        object.__setattr__(self, "readiness_id", _text(self.readiness_id, "readiness_id"))
        if not isinstance(self.report, _PublicationReadinessReport):
            raise ValueError("report must be a PublicationReadinessReport")
        object.__setattr__(self, "source_hashes", _hash_pairs(self.source_hashes, "source_hashes"))
        object.__setattr__(self, "report_hash", _hash(self.report_hash, "report_hash"))
        object.__setattr__(self, "canonical_json_hash", _hash(self.canonical_json_hash, "canonical_json_hash"))
        object.__setattr__(self, "created_at", _text(self.created_at, "created_at"))
        if self.report_hash != canonical_hash(self.report, prefixed=True):
            raise ValueError("report_hash does not match report")
        if self.canonical_json_hash != canonical_hash(
            {"readiness_id": self.readiness_id, "report": self.report, "source_hashes": self.source_hashes},
            prefixed=True,
        ):
            raise ValueError("canonical_json_hash does not match readiness record")


@dataclass(frozen=True, slots=True)
class ExportEligibilityRecord:
    eligibility_id: str
    workspace_id: str
    publication_id: str
    manifest_id: str
    eligible: bool
    source_hashes: tuple[tuple[str, str], ...]
    eligibility_hash: str
    created_at: str

    def __post_init__(self) -> None:
        for field_name in ("eligibility_id", "workspace_id", "publication_id", "manifest_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        if not isinstance(self.eligible, bool):
            raise ValueError("eligible must be a boolean")
        object.__setattr__(self, "source_hashes", _hash_pairs(self.source_hashes, "source_hashes"))
        object.__setattr__(self, "eligibility_hash", _hash(self.eligibility_hash, "eligibility_hash"))
        object.__setattr__(self, "created_at", _text(self.created_at, "created_at"))
        expected = canonical_hash(
            {
                "eligibility_id": self.eligibility_id,
                "workspace_id": self.workspace_id,
                "publication_id": self.publication_id,
                "manifest_id": self.manifest_id,
                "eligible": self.eligible,
                "source_hashes": self.source_hashes,
            },
            prefixed=True,
        )
        if self.eligibility_hash != expected:
            raise ValueError("eligibility_hash does not match eligibility record")


@dataclass(frozen=True, slots=True)
class PreparedRevision:
    scope: IdempotencyScope
    payload_hash: str
    command: AssembleRevisionCommand
    expected_analysis_version: int
    revision: FmeaRevision
    audit: AuditEvent
    outbox: OutboxEvent

    @property
    def payload(self) -> Mapping[str, object]:
        return canonical_governance_payload("revision.assemble", self.command, revision=self.revision)

    def __post_init__(self) -> None:
        if not isinstance(self.command, AssembleRevisionCommand):
            raise ValueError("command must be an AssembleRevisionCommand")
        if not isinstance(self.revision, FmeaRevision):
            raise ValueError("revision must be an FmeaRevision")
        object.__setattr__(
            self, "expected_analysis_version", _positive(self.expected_analysis_version, "expected_analysis_version")
        )
        if self.command.request.expected_analysis_version != self.expected_analysis_version:
            raise ValueError("expected analysis version does not match command")
        if self.command.request.analysis_id != self.revision.analysis_id:
            raise ValueError("revision analysis binding is invalid")
        if self.revision.analysis_record_version != self.expected_analysis_version:
            raise ValueError("revision analysis version binding is invalid")
        _validate_prepared_bindings(
            scope=self.scope,
            payload_hash=self.payload_hash,
            payload=self.payload,
            audit=self.audit,
            outbox=self.outbox,
            workspace_id=self.revision.workspace_id,
            aggregate_id=self.revision.revision_id,
            analysis_id=self.revision.analysis_id,
        )


@dataclass(frozen=True, slots=True)
class PreparedReadinessReport:
    scope: IdempotencyScope
    payload_hash: str
    command: PersistReadinessCommand
    revision_record_version: int
    readiness_id: str
    revision: FmeaRevision
    report: PublicationReadinessReport
    source_hashes: tuple[tuple[str, str], ...]
    audit: AuditEvent
    outbox: OutboxEvent

    @property
    def payload(self) -> Mapping[str, object]:
        return canonical_governance_payload(
            "revision.readiness",
            self.command,
            report=self.report,
            source_hashes=self.source_hashes,
        )

    def __post_init__(self) -> None:
        from .revision_assembler import PublicationReadinessReport as _PublicationReadinessReport

        if not isinstance(self.command, PersistReadinessCommand) or not isinstance(self.revision, FmeaRevision):
            raise ValueError("readiness prepared contract types are invalid")
        if not isinstance(self.report, _PublicationReadinessReport):
            raise ValueError("readiness report type is invalid")
        object.__setattr__(
            self, "revision_record_version", _positive(self.revision_record_version, "revision_record_version")
        )
        object.__setattr__(self, "readiness_id", _text(self.readiness_id, "readiness_id"))
        object.__setattr__(self, "source_hashes", _hash_pairs(self.source_hashes, "source_hashes"))
        if (
            self.command.revision_id != self.revision.revision_id
            or self.command.revision_hash != self.revision.revision_hash
            or self.command.expected_revision_version != self.revision_record_version
            or self.command.readiness_id != self.readiness_id
            or self.report.revision_id != self.revision.revision_id
            or self.report.workspace_id != self.revision.workspace_id
            or self.report.analysis_id != self.revision.analysis_id
            or self.report.revision_hash != self.revision.revision_hash
            or self.report.target_record_version != self.revision.analysis_record_version
            or dict(self.source_hashes).get("analysis") != self.revision.analysis_hash
            or dict(self.source_hashes).get("revision") != self.revision.revision_hash
        ):
            raise ValueError("readiness revision binding is invalid")
        _validate_prepared_bindings(
            scope=self.scope,
            payload_hash=self.payload_hash,
            payload=self.payload,
            audit=self.audit,
            outbox=self.outbox,
            workspace_id=self.revision.workspace_id,
            aggregate_id=self.readiness_id,
            analysis_id=self.revision.analysis_id,
        )


@dataclass(frozen=True, slots=True)
class PreparedApprovalSubmission:
    scope: IdempotencyScope
    payload_hash: str
    command: SubmitApprovalCommand
    revision_record_version: int
    submission: ApprovalSubmission
    audit: AuditEvent
    outbox: OutboxEvent

    @property
    def payload(self) -> Mapping[str, object]:
        return canonical_governance_payload("approval.submit", self.command, submission=self.submission)

    def __post_init__(self) -> None:
        if not isinstance(self.command, SubmitApprovalCommand) or not isinstance(self.submission, ApprovalSubmission):
            raise ValueError("approval submission prepared contract types are invalid")
        object.__setattr__(
            self, "revision_record_version", _positive(self.revision_record_version, "revision_record_version")
        )
        if (
            self.command.revision_id != self.submission.revision_id
            or self.command.revision_hash != self.submission.revision_hash
            or self.command.expected_revision_version != self.revision_record_version
        ):
            raise ValueError("approval submission revision version binding is invalid")
        _validate_prepared_bindings(
            scope=self.scope,
            payload_hash=self.payload_hash,
            payload=self.payload,
            audit=self.audit,
            outbox=self.outbox,
            workspace_id=self.submission.workspace_id,
            aggregate_id=self.submission.submission_id,
            resource_actor_id=self.submission.submitter_actor_id,
        )


@dataclass(frozen=True, slots=True)
class PreparedApproval:
    scope: IdempotencyScope
    payload_hash: str
    command: ApprovalCommand
    submission: ApprovalSubmission
    decision: ApprovalDecision
    audit: AuditEvent
    outbox: OutboxEvent

    @property
    def payload(self) -> Mapping[str, object]:
        return canonical_governance_payload(
            "approval.decide", self.command, submission=self.submission, decision=self.decision
        )

    def __post_init__(self) -> None:
        if not isinstance(self.command, ApprovalCommand):
            raise ValueError("command must be an ApprovalCommand")
        if not isinstance(self.submission, ApprovalSubmission) or not isinstance(self.decision, ApprovalDecision):
            raise ValueError("approval prepared contract types are invalid")
        if (
            self.command.submission_id != self.submission.submission_id
            or self.command.expected_submission_version != self.submission.record_version
        ):
            raise ValueError("approval submission binding is invalid")
        if (
            self.command.revision_id != self.submission.revision_id
            or self.command.revision_hash != self.submission.revision_hash
            or self.decision.submission_id != self.submission.submission_id
            or self.decision.revision_id != self.submission.revision_id
            or self.decision.revision_hash != self.submission.revision_hash
        ):
            raise ValueError("approval revision binding is invalid")
        _validate_prepared_bindings(
            scope=self.scope,
            payload_hash=self.payload_hash,
            payload=self.payload,
            audit=self.audit,
            outbox=self.outbox,
            workspace_id=self.submission.workspace_id,
            aggregate_id=self.decision.approval_id,
            resource_actor_id=self.decision.approver_actor_id,
        )


@dataclass(frozen=True, slots=True)
class PreparedApprovalWithdrawal:
    scope: IdempotencyScope
    payload_hash: str
    command: WithdrawApprovalCommand
    approval: ApprovalDecision
    withdrawal: ApprovalWithdrawalRecord
    audit: AuditEvent
    outbox: OutboxEvent

    @property
    def payload(self) -> Mapping[str, object]:
        return canonical_governance_payload(
            "approval.withdraw", self.command, approval=self.approval, withdrawal=self.withdrawal
        )

    def __post_init__(self) -> None:
        if not isinstance(self.command, WithdrawApprovalCommand) or not isinstance(self.approval, ApprovalDecision):
            raise ValueError("approval withdrawal contract types are invalid")
        if not isinstance(self.withdrawal, ApprovalWithdrawalRecord):
            raise ValueError("withdrawal must be an ApprovalWithdrawalRecord")
        if self.approval.status is not ApprovalStatus.APPROVED:
            raise ValueError("approval withdrawal requires an approved decision")
        if self.command.expected_approval_version != self.approval.record_version:
            raise ValueError("approval withdrawal version binding is invalid")
        if (
            self.command.approval_id != self.approval.approval_id
            or self.command.revision_hash != self.approval.revision_hash
        ):
            raise ValueError("approval withdrawal binding is invalid")
        if (
            self.withdrawal.approval_id != self.approval.approval_id
            or self.withdrawal.revision_hash != self.approval.revision_hash
        ):
            raise ValueError("approval withdrawal record binding is invalid")
        if self.withdrawal.revision_id != self.approval.revision_id:
            raise ValueError("approval withdrawal revision binding is invalid")
        _validate_prepared_bindings(
            scope=self.scope,
            payload_hash=self.payload_hash,
            payload=self.payload,
            audit=self.audit,
            outbox=self.outbox,
            workspace_id=self.scope.workspace_id,
            aggregate_id=self.withdrawal.withdrawal_id,
            resource_actor_id=self.withdrawal.actor_id,
        )


@dataclass(frozen=True, slots=True)
class PreparedPublication:
    scope: IdempotencyScope
    payload_hash: str
    command: PublishCommand
    revision_record_version: int
    revision: FmeaRevision
    approval: ApprovalDecision
    submission: ApprovalSubmission
    manifest: PublicationManifest
    publication: PublishedRevision
    snapshot: NormalizedFmeaSnapshot
    audit: AuditEvent
    outbox: OutboxEvent
    export_eligibility: ExportEligibilityRecord

    @property
    def payload(self) -> Mapping[str, object]:
        return canonical_governance_payload(
            "publication.publish",
            self.command,
            revision=self.revision,
            approval=self.approval,
            submission=self.submission,
            manifest=self.manifest,
            publication=self.publication,
            snapshot=self.snapshot,
            export_eligibility=self.export_eligibility,
        )

    def __post_init__(self) -> None:  # noqa: C901
        if not isinstance(self.command, PublishCommand) or not isinstance(self.revision, FmeaRevision):
            raise ValueError("publication prepared contract types are invalid")
        if not isinstance(self.approval, ApprovalDecision) or not isinstance(self.manifest, PublicationManifest):
            raise ValueError("publication approval/manifest types are invalid")
        if not isinstance(self.submission, ApprovalSubmission):
            raise ValueError("publication submission type is invalid")
        if not isinstance(self.publication, PublishedRevision) or not isinstance(self.snapshot, NormalizedFmeaSnapshot):
            raise ValueError("publication/snapshot types are invalid")
        if not isinstance(self.export_eligibility, ExportEligibilityRecord):
            raise ValueError("publication export eligibility type is invalid")
        object.__setattr__(
            self, "revision_record_version", _positive(self.revision_record_version, "revision_record_version")
        )
        if self.approval.status is not ApprovalStatus.APPROVED:
            raise ValueError("publication requires an approved revision")
        if (
            self.command.revision_id != self.revision.revision_id
            or self.command.revision_hash != self.revision.revision_hash
        ):
            raise ValueError("publication revision binding is invalid")
        if self.command.expected_revision_version != self.revision_record_version:
            raise ValueError("publication revision version binding is invalid")
        if (
            self.submission.workspace_id != self.revision.workspace_id
            or self.submission.revision_id != self.revision.revision_id
            or self.submission.revision_hash != self.revision.revision_hash
            or self.approval.submission_id != self.submission.submission_id
        ):
            raise ValueError("publication approval submission binding is invalid")
        validate_approval_binding(self.approval, self.revision)
        if self.publication.workspace_id != self.revision.workspace_id:
            raise ValueError("publication workspace binding is invalid")
        if self.publication.analysis_id != self.revision.analysis_id:
            raise ValueError("publication analysis binding is invalid")
        if self.snapshot.workspace_id != self.revision.workspace_id:
            raise ValueError("publication snapshot workspace binding is invalid")
        if self.snapshot.analysis_id != self.revision.analysis_id:
            raise ValueError("publication snapshot analysis binding is invalid")
        if self.publication.publisher_actor_id != self.scope.actor_id:
            raise ValueError("publication actor binding is invalid")
        if self.publication.approval_id != self.approval.approval_id:
            raise ValueError("publication approval binding is invalid")
        if (
            self.command.approval_id != self.approval.approval_id
            or self.manifest.revision_id != self.revision.revision_id
            or self.manifest.revision_hash != self.revision.revision_hash
            or self.manifest.approval_id != self.approval.approval_id
            or self.publication.revision_id != self.revision.revision_id
            or self.publication.revision_hash != self.revision.revision_hash
            or self.publication.manifest_id != self.manifest.manifest_id
            or self.publication.manifest_hash != self.manifest.manifest_hash
            or self.publication.snapshot_id != self.manifest.snapshot_id
            or self.publication.snapshot_hash != self.manifest.snapshot_hash
            or self.snapshot.revision_id != self.revision.revision_id
            or self.snapshot.revision_hash != self.revision.revision_hash
            or self.snapshot.snapshot_id != self.manifest.snapshot_id
            or self.snapshot.publication_id != self.publication.publication_id
            or self.snapshot.manifest_id != self.manifest.manifest_id
            or self.export_eligibility.workspace_id != self.publication.workspace_id
            or self.export_eligibility.publication_id != self.publication.publication_id
            or self.export_eligibility.manifest_id != self.manifest.manifest_id
            or self.export_eligibility.eligible is not self.manifest.export_eligible
            or dict(self.export_eligibility.source_hashes).get("revision") != self.revision.revision_hash
            or dict(self.export_eligibility.source_hashes).get("manifest") != self.manifest.manifest_hash
            or dict(self.export_eligibility.source_hashes).get("snapshot") != self.snapshot.snapshot_hash
        ):
            raise ValueError("publication snapshot lineage binding is invalid")
        _validate_prepared_bindings(
            scope=self.scope,
            payload_hash=self.payload_hash,
            payload=self.payload,
            audit=self.audit,
            outbox=self.outbox,
            workspace_id=self.publication.workspace_id,
            aggregate_id=self.publication.publication_id,
            analysis_id=self.revision.analysis_id,
        )


@dataclass(frozen=True, slots=True)
class PreparedPublicationWithdrawal:
    scope: IdempotencyScope
    payload_hash: str
    command: WithdrawPublicationCommand
    publication: PublishedRevision
    withdrawal: PublicationWithdrawalRecord
    audit: AuditEvent
    outbox: OutboxEvent

    @property
    def payload(self) -> Mapping[str, object]:
        return canonical_governance_payload(
            "publication.withdraw", self.command, publication=self.publication, withdrawal=self.withdrawal
        )

    def __post_init__(self) -> None:
        if not isinstance(self.command, WithdrawPublicationCommand) or not isinstance(
            self.publication, PublishedRevision
        ):
            raise ValueError("publication withdrawal contract types are invalid")
        if not isinstance(self.withdrawal, PublicationWithdrawalRecord):
            raise ValueError("withdrawal must be a PublicationWithdrawalRecord")
        if (
            self.command.publication_id != self.publication.publication_id
            or self.withdrawal.publication_id != self.publication.publication_id
        ):
            raise ValueError("publication withdrawal binding is invalid")
        if self.command.expected_publication_version != self.publication.record_version:
            raise ValueError("publication withdrawal version binding is invalid")
        if self.command.replacement_publication_id != self.withdrawal.replacement_publication_id:
            raise ValueError("publication replacement binding is invalid")
        _validate_prepared_bindings(
            scope=self.scope,
            payload_hash=self.payload_hash,
            payload=self.payload,
            audit=self.audit,
            outbox=self.outbox,
            workspace_id=self.publication.workspace_id,
            aggregate_id=self.withdrawal.withdrawal_id,
            resource_actor_id=self.withdrawal.actor_id,
        )


@dataclass(frozen=True, slots=True)
class PreparedSupersession:
    scope: IdempotencyScope
    payload_hash: str
    command: SupersedePublicationCommand
    old_publication: PublishedRevision
    replacement_publication: PublishedRevision
    old_revision: FmeaRevision
    replacement_revision: FmeaRevision
    supersession: SupersessionRecord
    audit: AuditEvent
    outbox: OutboxEvent

    @property
    def payload(self) -> Mapping[str, object]:
        return canonical_governance_payload(
            "publication.supersede",
            self.command,
            old=self.old_publication,
            replacement=self.replacement_publication,
            old_revision=self.old_revision,
            replacement_revision=self.replacement_revision,
            supersession=self.supersession,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.command, SupersedePublicationCommand):
            raise ValueError("command must be a SupersedePublicationCommand")
        if not isinstance(self.old_publication, PublishedRevision) or not isinstance(
            self.replacement_publication, PublishedRevision
        ):
            raise ValueError("supersession publications are invalid")
        if not isinstance(self.old_revision, FmeaRevision) or not isinstance(self.replacement_revision, FmeaRevision):
            raise ValueError("supersession revisions are invalid")
        if not isinstance(self.supersession, SupersessionRecord):
            raise ValueError("supersession must be a SupersessionRecord")
        if (
            self.command.publication_id != self.old_publication.publication_id
            or self.command.replacement_publication_id != self.replacement_publication.publication_id
            or self.supersession.old_publication_id != self.old_publication.publication_id
            or self.supersession.new_publication_id != self.replacement_publication.publication_id
        ):
            raise ValueError("supersession publication binding is invalid")
        if (
            self.command.expected_publication_version != self.old_publication.record_version
            or self.command.expected_replacement_version != self.replacement_publication.record_version
        ):
            raise ValueError("supersession publication version binding is invalid")
        if self.old_publication.workspace_id != self.replacement_publication.workspace_id:
            raise ValueError("supersession workspace binding is invalid")
        if self.supersession.actor_id != self.scope.actor_id:
            raise ValueError("supersession actor binding is invalid")
        validate_supersession_binding(
            self.supersession,
            old=self.old_publication,
            replacement=self.replacement_publication,
            old_revision=self.old_revision,
            replacement_revision=self.replacement_revision,
        )
        _validate_prepared_bindings(
            scope=self.scope,
            payload_hash=self.payload_hash,
            payload=self.payload,
            audit=self.audit,
            outbox=self.outbox,
            workspace_id=self.old_publication.workspace_id,
            aggregate_id=self.supersession.supersession_id,
            analysis_id=self.old_publication.analysis_id,
            resource_actor_id=self.supersession.actor_id,
        )


def _result_text(value: object, field_name: str) -> str:
    return _text(value, field_name)


@dataclass(frozen=True, slots=True)
class RevisionResult:
    revision_id: str
    record_version: int
    audit_event_id: str
    outbox_event_id: str
    replayed: bool = False

    def __post_init__(self) -> None:
        for field_name in ("revision_id", "audit_event_id", "outbox_event_id"):
            object.__setattr__(self, field_name, _result_text(getattr(self, field_name), field_name))
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        if not isinstance(self.replayed, bool):
            raise ValueError("replayed must be a boolean")


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    readiness_id: str
    record_version: int
    audit_event_id: str
    outbox_event_id: str
    replayed: bool = False

    def __post_init__(self) -> None:
        for field_name in ("readiness_id", "audit_event_id", "outbox_event_id"):
            object.__setattr__(self, field_name, _result_text(getattr(self, field_name), field_name))
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        if not isinstance(self.replayed, bool):
            raise ValueError("replayed must be a boolean")


@dataclass(frozen=True, slots=True)
class ApprovalSubmissionResult:
    submission_id: str
    record_version: int
    audit_event_id: str
    outbox_event_id: str
    replayed: bool = False

    def __post_init__(self) -> None:
        for field_name in ("submission_id", "audit_event_id", "outbox_event_id"):
            object.__setattr__(self, field_name, _result_text(getattr(self, field_name), field_name))
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        if not isinstance(self.replayed, bool):
            raise ValueError("replayed must be a boolean")


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    approval_id: str
    record_version: int
    audit_event_id: str
    outbox_event_id: str
    replayed: bool = False

    def __post_init__(self) -> None:
        for field_name in ("approval_id", "audit_event_id", "outbox_event_id"):
            object.__setattr__(self, field_name, _result_text(getattr(self, field_name), field_name))
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        if not isinstance(self.replayed, bool):
            raise ValueError("replayed must be a boolean")


@dataclass(frozen=True, slots=True)
class PublicationResult:
    publication_id: str
    manifest_id: str
    snapshot_id: str
    record_version: int
    audit_event_id: str
    outbox_event_id: str
    replayed: bool = False

    def __post_init__(self) -> None:
        for field_name in ("publication_id", "manifest_id", "snapshot_id", "audit_event_id", "outbox_event_id"):
            object.__setattr__(self, field_name, _result_text(getattr(self, field_name), field_name))
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        if not isinstance(self.replayed, bool):
            raise ValueError("replayed must be a boolean")


@dataclass(frozen=True, slots=True)
class PublicationWithdrawalResult:
    withdrawal_id: str
    publication_id: str
    audit_event_id: str
    outbox_event_id: str
    replayed: bool = False

    def __post_init__(self) -> None:
        for field_name in ("withdrawal_id", "publication_id", "audit_event_id", "outbox_event_id"):
            object.__setattr__(self, field_name, _result_text(getattr(self, field_name), field_name))
        if not isinstance(self.replayed, bool):
            raise ValueError("replayed must be a boolean")


@dataclass(frozen=True, slots=True)
class SupersessionResult:
    supersession_id: str
    old_publication_id: str
    new_publication_id: str
    audit_event_id: str
    outbox_event_id: str
    replayed: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "supersession_id",
            "old_publication_id",
            "new_publication_id",
            "audit_event_id",
            "outbox_event_id",
        ):
            object.__setattr__(self, field_name, _result_text(getattr(self, field_name), field_name))
        if not isinstance(self.replayed, bool):
            raise ValueError("replayed must be a boolean")


__all__ = [
    "ApprovalCommand",
    "ApprovalRejectionCommand",
    "ApprovalResult",
    "ApprovalSubmissionResult",
    "AssembleRevisionCommand",
    "ExportEligibilityRecord",
    "GovernanceHistoryQuery",
    "PersistReadinessCommand",
    "PreparedApproval",
    "PreparedApprovalSubmission",
    "PreparedApprovalWithdrawal",
    "PreparedPublication",
    "PreparedPublicationWithdrawal",
    "PreparedReadinessReport",
    "PreparedRevision",
    "PreparedSupersession",
    "PublicationResult",
    "PublicationWithdrawalResult",
    "PublishCommand",
    "ReadinessReportRecord",
    "ReadinessResult",
    "RevisionAssemblyRequest",
    "RevisionResult",
    "SubmitApprovalCommand",
    "SupersedePublicationCommand",
    "SupersessionResult",
    "WithdrawApprovalCommand",
    "WithdrawPublicationCommand",
    "canonical_governance_payload",
    "canonical_payload_hash",
    "governance_payload_hash",
]
