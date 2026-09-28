"""Immutable revision and publication governance contracts."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timedelta
from enum import Enum
from hashlib import sha256
from typing import Literal

from core_domain.structured_output.canonical import canonical_json
from core_domain.structured_output.contracts import StructuredOutputError
from core_domain.structured_output.policies import TemplateLimits

from .errors import FmeaDomainError

_HASH = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_SEVERITIES = frozenset({"info", "warning", "blocking", "critical"})
MAX_SUPERSESSION_TRAVERSAL = 64


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FmeaDomainError(f"{field_name} must not be empty")  # noqa: TRY003
    return value.strip()


def _hash(value: object, field_name: str) -> str:
    normalized = _text(value, field_name)
    if _HASH.fullmatch(normalized) is None:
        raise FmeaDomainError(f"{field_name} must be a lowercase SHA-256 hash")  # noqa: TRY003
    return normalized


def _positive(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise FmeaDomainError(f"{field_name} must be positive")  # noqa: TRY003
    return value


def _timestamp(value: object, field_name: str) -> str:
    normalized = _text(value, field_name)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FmeaDomainError(f"{field_name} must be an ISO-8601 UTC timestamp") from exc  # noqa: TRY003
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise FmeaDomainError(f"{field_name} must be an ISO-8601 UTC timestamp")  # noqa: TRY003
    return normalized


def _optional_text(value: object, field_name: str) -> str | None:
    return None if value is None else _text(value, field_name)


def _optional_hash(value: object, field_name: str) -> str | None:
    return None if value is None else _hash(value, field_name)


def _strings(value: object, field_name: str, *, unique: bool = False) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or value is None:
        raise FmeaDomainError(f"{field_name} must be a sequence")  # noqa: TRY003
    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise FmeaDomainError(f"{field_name} must be a sequence") from exc  # noqa: TRY003
    result = tuple(_text(item, field_name) for item in items)
    if unique and len(result) != len(set(result)):
        raise FmeaDomainError(f"{field_name} must not contain duplicates")  # noqa: TRY003
    return result


def _pairs(value: object, field_name: str, *, values_are_hashes: bool = False) -> tuple[tuple[object, object], ...]:
    if isinstance(value, str | bytes) or value is None:
        raise FmeaDomainError(f"{field_name} must be a sequence")  # noqa: TRY003
    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise FmeaDomainError(f"{field_name} must be a sequence") from exc  # noqa: TRY003
    result: list[tuple[object, object]] = []
    for item in items:
        if not isinstance(item, tuple | list) or len(item) != 2:
            raise FmeaDomainError(f"{field_name} must contain pairs")  # noqa: TRY003
        left, right = item
        result.append((_text(left, field_name), _hash(right, field_name) if values_are_hashes else right))
    if len({left for left, _ in result}) != len(result):
        raise FmeaDomainError(f"{field_name} must not contain duplicate identities")  # noqa: TRY003
    return tuple(sorted(result, key=lambda pair: str(pair[0])))


def _identity_triples(value: object, field_name: str) -> tuple[tuple[str, str, str], ...]:
    if isinstance(value, str | bytes) or value is None:
        raise FmeaDomainError(f"{field_name} must be a sequence")  # noqa: TRY003
    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise FmeaDomainError(f"{field_name} must be a sequence") from exc  # noqa: TRY003
    result: list[tuple[str, str, str]] = []
    for item in items:
        if not isinstance(item, tuple | list) or len(item) != 3:
            raise FmeaDomainError(f"{field_name} must contain id/version/hash triples")  # noqa: TRY003
        result.append((_text(item[0], field_name), _text(item[1], field_name), _hash(item[2], field_name)))
    identities = tuple((item[0], item[1]) for item in result)
    if len(identities) != len(set(identities)):
        raise FmeaDomainError(f"{field_name} must not contain duplicate identities")  # noqa: TRY003
    return tuple(sorted(result))


def _record_versions(value: object, field_name: str) -> tuple[tuple[str, int, str], ...]:
    if isinstance(value, str | bytes) or value is None:
        raise FmeaDomainError(f"{field_name} must be a sequence")  # noqa: TRY003
    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise FmeaDomainError(f"{field_name} must be a sequence") from exc  # noqa: TRY003
    result: list[tuple[str, int, str]] = []
    for item in items:
        if not isinstance(item, tuple | list) or len(item) != 3:
            raise FmeaDomainError(f"{field_name} must contain id/version/hash triples")  # noqa: TRY003
        result.append((_text(item[0], field_name), _positive(item[1], field_name), _hash(item[2], field_name)))
    if len({item[0] for item in result}) != len(result):
        raise FmeaDomainError(f"{field_name} must not contain duplicate identities")  # noqa: TRY003
    return tuple(sorted(result))


def _canonical_value(value: object, *, exclude_fields: frozenset[str] = frozenset()) -> object:
    if isinstance(value, Enum):
        return _canonical_value(value.value, exclude_fields=exclude_fields)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonical_value(getattr(value, field.name), exclude_fields=exclude_fields)
            for field in fields(value)
            if field.name not in exclude_fields
        }
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise FmeaDomainError("canonical payload object keys must be strings")  # noqa: TRY003
        return {key: _canonical_value(item, exclude_fields=exclude_fields) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_canonical_value(item, exclude_fields=exclude_fields) for item in value]
    if isinstance(value, frozenset):
        return sorted(_canonical_value(item, exclude_fields=exclude_fields) for item in value)
    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise FmeaDomainError("canonical payload contains an unsupported value")  # noqa: TRY003


def canonical_json_bytes(
    value: object,
    *,
    exclude_fields: Iterable[str] = (),
    max_array_items: int | None = None,
) -> bytes:
    """Encode a supported contract through the existing strict JSON codec."""

    projected = _canonical_value(value, exclude_fields=frozenset(exclude_fields))
    try:
        limits = None if max_array_items is None else TemplateLimits(max_array_items=max_array_items)
        return canonical_json(projected, limits=limits).encode("utf-8")
    except (ValueError, StructuredOutputError) as exc:
        raise FmeaDomainError("canonical payload cannot be encoded") from exc  # noqa: TRY003


def canonical_json_value(value: object, *, exclude_fields: Iterable[str] = ()) -> object:
    """Project one supported contract into the JSON value used for hashing."""

    return _canonical_value(value, exclude_fields=frozenset(exclude_fields))


def canonical_hash(
    value: object,
    *,
    prefixed: bool = False,
    exclude_fields: Iterable[str] = (),
    max_array_items: int | None = None,
) -> str:
    digest = sha256(
        canonical_json_bytes(value, exclude_fields=exclude_fields, max_array_items=max_array_items)
    ).hexdigest()
    return f"sha256:{digest}" if prefixed else digest


def canonical_revision_body(revision: FmeaRevision) -> Mapping[str, object]:
    if not isinstance(revision, FmeaRevision):
        raise FmeaDomainError("revision must be an FmeaRevision")  # noqa: TRY003
    return _canonical_value(revision, exclude_fields=frozenset({"revision_hash", "created_at"}))  # type: ignore[return-value]


def revision_content_hash(revision: FmeaRevision) -> str:
    return canonical_hash(canonical_revision_body(revision), max_array_items=10_000)


class ApprovalStatus(str, Enum):
    NOT_SUBMITTED = "not_submitted"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class RevisionPublicationStatus(str, Enum):
    UNPUBLISHED = "unpublished"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class RetrievalProvenanceSnapshot:
    requested_profile: str
    resolved_profile: str
    evidence_types: tuple[str, ...]
    source_counts: tuple[tuple[str, int], ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_profile", _text(self.requested_profile, "requested_profile"))
        object.__setattr__(self, "resolved_profile", _text(self.resolved_profile, "resolved_profile"))
        object.__setattr__(self, "evidence_types", _strings(self.evidence_types, "evidence_types", unique=True))
        raw_counts = _pairs(self.source_counts, "source_counts")
        counts: list[tuple[str, int]] = []
        for source_type, count in raw_counts:
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise FmeaDomainError("source_counts values must be non-negative integers")  # noqa: TRY003
            counts.append((str(source_type), count))
        object.__setattr__(self, "source_counts", tuple(counts))
        object.__setattr__(self, "warnings", _strings(self.warnings, "warnings", unique=True))


@dataclass(frozen=True, slots=True)
class ReadinessIssue:
    code: str
    severity: Literal["info", "warning", "blocking", "critical"]
    source_type: str
    source_id: str
    evidence_ids: tuple[str, ...]
    acknowledgement_decision_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _text(self.code, "code"))
        if self.severity not in _SEVERITIES:
            raise FmeaDomainError("readiness issue severity is invalid")  # noqa: TRY003
        object.__setattr__(self, "source_type", _text(self.source_type, "source_type"))
        object.__setattr__(self, "source_id", _text(self.source_id, "source_id"))
        object.__setattr__(self, "evidence_ids", _strings(self.evidence_ids, "evidence_ids", unique=True))
        object.__setattr__(
            self,
            "acknowledgement_decision_id",
            _optional_text(self.acknowledgement_decision_id, "acknowledgement_decision_id"),
        )


@dataclass(frozen=True, slots=True)
class FmeaRevision:
    revision_id: str
    workspace_id: str
    analysis_id: str
    analysis_record_version: int
    analysis_hash: str
    parent_revision_id: str | None
    parent_revision_hash: str | None
    row_versions: tuple[tuple[str, int, str], ...]
    risk_versions: tuple[tuple[str, int, str], ...]
    propagation_graph_revision_id: str | None
    propagation_graph_hash: str | None
    evidence_pack_hashes: tuple[tuple[str, str], ...]
    retrieval_provenance: RetrievalProvenanceSnapshot
    domain_pack_identity: tuple[str, str, str]
    template_identities: tuple[tuple[str, str, str], ...]
    scoring_rule_identities: tuple[tuple[str, str, str], ...]
    propagation_rule_identity: tuple[str, str, str] | None
    unresolved_items: tuple[ReadinessIssue, ...]
    revision_hash: str
    created_at: str

    def __post_init__(self) -> None:
        for field_name in ("revision_id", "workspace_id", "analysis_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        object.__setattr__(
            self, "analysis_record_version", _positive(self.analysis_record_version, "analysis_record_version")
        )
        object.__setattr__(self, "analysis_hash", _hash(self.analysis_hash, "analysis_hash"))
        parent_id = _optional_text(self.parent_revision_id, "parent_revision_id")
        parent_hash = _optional_hash(self.parent_revision_hash, "parent_revision_hash")
        if (parent_id is None) != (parent_hash is None):
            raise FmeaDomainError("parent revision identity and hash must be supplied together")  # noqa: TRY003
        object.__setattr__(self, "parent_revision_id", parent_id)
        object.__setattr__(self, "parent_revision_hash", parent_hash)
        object.__setattr__(self, "row_versions", _record_versions(self.row_versions, "row_versions"))
        object.__setattr__(self, "risk_versions", _record_versions(self.risk_versions, "risk_versions"))
        graph_id = _optional_text(self.propagation_graph_revision_id, "propagation_graph_revision_id")
        graph_hash = _optional_hash(self.propagation_graph_hash, "propagation_graph_hash")
        if (graph_id is None) != (graph_hash is None):
            raise FmeaDomainError("propagation graph identity and hash must be supplied together")  # noqa: TRY003
        object.__setattr__(self, "propagation_graph_revision_id", graph_id)
        object.__setattr__(self, "propagation_graph_hash", graph_hash)
        object.__setattr__(
            self,
            "evidence_pack_hashes",
            _pairs(self.evidence_pack_hashes, "evidence_pack_hashes", values_are_hashes=True),
        )
        if not isinstance(self.retrieval_provenance, RetrievalProvenanceSnapshot):
            raise FmeaDomainError("retrieval_provenance must be a RetrievalProvenanceSnapshot")  # noqa: TRY003
        object.__setattr__(
            self, "domain_pack_identity", self._one_identity(self.domain_pack_identity, "domain_pack_identity")
        )
        object.__setattr__(
            self, "template_identities", _identity_triples(self.template_identities, "template_identities")
        )
        object.__setattr__(
            self, "scoring_rule_identities", _identity_triples(self.scoring_rule_identities, "scoring_rule_identities")
        )
        propagation_identity = (
            None
            if self.propagation_rule_identity is None
            else self._one_identity(self.propagation_rule_identity, "propagation_rule_identity")
        )
        object.__setattr__(self, "propagation_rule_identity", propagation_identity)
        unresolved = tuple(self.unresolved_items)
        if any(not isinstance(item, ReadinessIssue) for item in unresolved):
            raise FmeaDomainError("unresolved_items must contain ReadinessIssue objects")  # noqa: TRY003
        issue_keys = tuple((item.code, item.source_type, item.source_id) for item in unresolved)
        if len(issue_keys) != len(set(issue_keys)):
            raise FmeaDomainError("unresolved_items must not contain duplicate identities")  # noqa: TRY003
        object.__setattr__(
            self,
            "unresolved_items",
            tuple(sorted(unresolved, key=lambda item: (item.code, item.source_type, item.source_id))),
        )
        object.__setattr__(self, "revision_hash", _hash(self.revision_hash, "revision_hash"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        if self.revision_hash.removeprefix("sha256:") != revision_content_hash(self):
            raise FmeaDomainError("revision hash does not match revision content")  # noqa: TRY003

    @staticmethod
    def _one_identity(value: object, field_name: str) -> tuple[str, str, str]:
        items = _identity_triples((value,), field_name)
        return items[0]


@dataclass(frozen=True, slots=True)
class ApprovalSubmission:
    submission_id: str
    workspace_id: str
    revision_id: str
    revision_hash: str
    status: ApprovalStatus
    submitter_actor_id: str
    record_version: int
    created_at: str

    def __post_init__(self) -> None:
        for field_name in ("submission_id", "workspace_id", "revision_id", "submitter_actor_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        object.__setattr__(self, "revision_hash", _hash(self.revision_hash, "revision_hash"))
        if self.status is not ApprovalStatus.PENDING:
            raise FmeaDomainError("approval submission status must be pending")  # noqa: TRY003
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    approval_id: str
    submission_id: str
    revision_id: str
    revision_hash: str
    status: ApprovalStatus
    approver_actor_id: str
    reason: str
    record_version: int
    created_at: str

    def __post_init__(self) -> None:
        for field_name in ("approval_id", "submission_id", "revision_id", "approver_actor_id", "reason"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        object.__setattr__(self, "revision_hash", _hash(self.revision_hash, "revision_hash"))
        if self.status not in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
            raise FmeaDomainError("approval decision status must be approved or rejected")  # noqa: TRY003
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))


@dataclass(frozen=True, slots=True)
class ApprovalWithdrawalRecord:
    withdrawal_id: str
    approval_id: str
    revision_id: str
    revision_hash: str
    actor_id: str
    reason: str
    created_at: str

    def __post_init__(self) -> None:
        for field_name in ("withdrawal_id", "approval_id", "revision_id", "actor_id", "reason"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        object.__setattr__(self, "revision_hash", _hash(self.revision_hash, "revision_hash"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))


@dataclass(frozen=True, slots=True)
class PublicationManifest:
    manifest_id: str
    revision_id: str
    revision_hash: str
    approval_id: str
    snapshot_id: str
    snapshot_hash: str
    version_manifest_hash: str
    previous_audit_chain_head: str | None
    export_eligible: bool
    manifest_hash: str
    created_at: str

    def __post_init__(self) -> None:
        for field_name in ("manifest_id", "revision_id", "approval_id", "snapshot_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        for field_name in ("revision_hash", "snapshot_hash", "version_manifest_hash", "manifest_hash"):
            object.__setattr__(self, field_name, _hash(getattr(self, field_name), field_name))
        object.__setattr__(
            self,
            "previous_audit_chain_head",
            _optional_hash(self.previous_audit_chain_head, "previous_audit_chain_head"),
        )
        if not isinstance(self.export_eligible, bool):
            raise FmeaDomainError("export_eligible must be a boolean")  # noqa: TRY003
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))


@dataclass(frozen=True, slots=True)
class PublishedRevision:
    publication_id: str
    workspace_id: str
    analysis_id: str
    revision_id: str
    revision_hash: str
    approval_id: str
    manifest_id: str
    manifest_hash: str
    snapshot_id: str
    snapshot_hash: str
    audit_chain_head: str
    publisher_actor_id: str
    record_version: int
    created_at: str

    def __post_init__(self) -> None:
        for field_name in (
            "publication_id",
            "workspace_id",
            "analysis_id",
            "revision_id",
            "approval_id",
            "manifest_id",
            "snapshot_id",
            "publisher_actor_id",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        for field_name in ("revision_hash", "manifest_hash", "snapshot_hash", "audit_chain_head"):
            object.__setattr__(self, field_name, _hash(getattr(self, field_name), field_name))
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))


@dataclass(frozen=True, slots=True)
class PublicationWithdrawalRecord:
    withdrawal_id: str
    publication_id: str
    replacement_publication_id: str | None
    actor_id: str
    reason: str
    created_at: str

    def __post_init__(self) -> None:
        for field_name in ("withdrawal_id", "publication_id", "actor_id", "reason"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        object.__setattr__(
            self,
            "replacement_publication_id",
            _optional_text(self.replacement_publication_id, "replacement_publication_id"),
        )
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))


@dataclass(frozen=True, slots=True)
class SupersessionRecord:
    supersession_id: str
    old_publication_id: str
    new_publication_id: str
    actor_id: str
    reason: str
    created_at: str

    def __post_init__(self) -> None:
        for field_name in ("supersession_id", "old_publication_id", "new_publication_id", "actor_id", "reason"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        if self.old_publication_id == self.new_publication_id:
            raise FmeaDomainError("supersession must link different publications")  # noqa: TRY003
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))


@dataclass(frozen=True, slots=True)
class PublicationLifecycleView:
    publication: PublishedRevision
    effective_status: RevisionPublicationStatus
    withdrawal: PublicationWithdrawalRecord | None
    supersession: SupersessionRecord | None

    def __post_init__(self) -> None:
        if not isinstance(self.publication, PublishedRevision):
            raise FmeaDomainError("publication must be a PublishedRevision")  # noqa: TRY003
        if not isinstance(self.effective_status, RevisionPublicationStatus):
            raise FmeaDomainError("effective_status must be a RevisionPublicationStatus")  # noqa: TRY003
        if self.withdrawal is not None:
            if not isinstance(self.withdrawal, PublicationWithdrawalRecord):
                raise FmeaDomainError("withdrawal must be a PublicationWithdrawalRecord")  # noqa: TRY003
            if self.withdrawal.publication_id != self.publication.publication_id:
                raise FmeaDomainError("publication withdrawal binding is invalid")  # noqa: TRY003
        if self.supersession is not None:
            if not isinstance(self.supersession, SupersessionRecord):
                raise FmeaDomainError("supersession must be a SupersessionRecord")  # noqa: TRY003
            if self.supersession.old_publication_id != self.publication.publication_id:
                raise FmeaDomainError("publication supersession binding is invalid")  # noqa: TRY003


def validate_approval_binding(decision: ApprovalDecision, revision: FmeaRevision) -> None:
    if not isinstance(decision, ApprovalDecision) or not isinstance(revision, FmeaRevision):
        raise FmeaDomainError("approval binding requires an ApprovalDecision and FmeaRevision")  # noqa: TRY003
    if decision.revision_id != revision.revision_id:
        raise FmeaDomainError("approval revision id mismatch")  # noqa: TRY003
    if decision.revision_hash != revision.revision_hash:
        raise FmeaDomainError("approval revision hash mismatch")  # noqa: TRY003


def validate_supersession_binding(  # noqa: C901
    link: SupersessionRecord,
    *,
    old: PublishedRevision,
    replacement: PublishedRevision,
    old_revision: FmeaRevision,
    replacement_revision: FmeaRevision,
) -> None:
    if not all(isinstance(item, PublishedRevision) for item in (old, replacement)):
        raise FmeaDomainError("supersession publications are invalid")  # noqa: TRY003
    if not all(isinstance(item, FmeaRevision) for item in (old_revision, replacement_revision)):
        raise FmeaDomainError("supersession revisions are invalid")  # noqa: TRY003
    if not isinstance(link, SupersessionRecord):
        raise FmeaDomainError("supersession record is invalid")  # noqa: TRY003
    if link.old_publication_id != old.publication_id or link.new_publication_id != replacement.publication_id:
        raise FmeaDomainError("supersession publication binding is invalid")  # noqa: TRY003
    if old.workspace_id != replacement.workspace_id or old.workspace_id != old_revision.workspace_id:
        raise FmeaDomainError("supersession workspace binding is invalid")  # noqa: TRY003
    if replacement.workspace_id != replacement_revision.workspace_id:
        raise FmeaDomainError("supersession workspace binding is invalid")  # noqa: TRY003
    if old.analysis_id != replacement.analysis_id:
        raise FmeaDomainError("supersession analysis binding is invalid")  # noqa: TRY003
    if old_revision.analysis_id != old.analysis_id or replacement_revision.analysis_id != replacement.analysis_id:
        raise FmeaDomainError("supersession analysis binding is invalid")  # noqa: TRY003
    if old.revision_id != old_revision.revision_id or replacement.revision_id != replacement_revision.revision_id:
        raise FmeaDomainError("supersession revision binding is invalid")  # noqa: TRY003
    if (
        old.revision_hash != old_revision.revision_hash
        or replacement.revision_hash != replacement_revision.revision_hash
    ):
        raise FmeaDomainError("supersession revision hash binding is invalid")  # noqa: TRY003
    if replacement_revision.parent_revision_id != old_revision.revision_id:
        raise FmeaDomainError("supersession parent revision binding is invalid")  # noqa: TRY003
    if replacement_revision.parent_revision_hash != old_revision.revision_hash:
        raise FmeaDomainError("supersession parent revision hash mismatch")  # noqa: TRY003


def project_publication_lifecycle(
    publication: PublishedRevision,
    *,
    withdrawal: PublicationWithdrawalRecord | None,
    supersession: SupersessionRecord | None,
) -> PublicationLifecycleView:
    if not isinstance(publication, PublishedRevision):
        raise FmeaDomainError("publication must be a PublishedRevision")  # noqa: TRY003
    if withdrawal is not None and withdrawal.publication_id != publication.publication_id:
        raise FmeaDomainError("publication withdrawal binding is invalid")  # noqa: TRY003
    if supersession is not None and supersession.old_publication_id != publication.publication_id:
        raise FmeaDomainError("publication supersession binding is invalid")  # noqa: TRY003
    status = (
        RevisionPublicationStatus.SUPERSEDED
        if supersession is not None
        else RevisionPublicationStatus.WITHDRAWN
        if withdrawal is not None
        else RevisionPublicationStatus.PUBLISHED
    )
    return PublicationLifecycleView(publication, status, withdrawal, supersession)


__all__ = [
    "ApprovalDecision",
    "ApprovalStatus",
    "ApprovalSubmission",
    "ApprovalWithdrawalRecord",
    "FmeaRevision",
    "PublicationLifecycleView",
    "PublicationManifest",
    "PublicationWithdrawalRecord",
    "PublishedRevision",
    "ReadinessIssue",
    "RetrievalProvenanceSnapshot",
    "RevisionPublicationStatus",
    "SupersessionRecord",
    "canonical_hash",
    "canonical_json_bytes",
    "canonical_json_value",
    "canonical_revision_body",
    "project_publication_lifecycle",
    "revision_content_hash",
    "validate_approval_binding",
    "validate_supersession_binding",
]
