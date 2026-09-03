"""Provider-neutral application service for verified FMEA exports."""

# The service is deliberately independent from JSON/XLSX/DOCX implementations.
# Exporters and storage are injected through ports so C2 can add narrative
# generation without changing the durable export protocol.
# ruff: noqa: C901, TRY003, TRY004

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import isfinite
from typing import Literal, TypeVar

from core_domain.fmea.filename_policy import validate_filename
from core_domain.fmea.governance import PublicationLifecycleView, PublishedRevision, RevisionPublicationStatus
from core_domain.fmea.states import ActorType, RunStatus

from .assistance_contracts import AssistanceKind, AssistanceSuggestion
from .delivery_contracts import ExportArtifactManifest, ExportFormat, ExportRun, validate_export_binding
from .governance_contracts import ExportEligibilityRecord
from .ports import ArtifactStore, ExportNarrativeGenerator, ExportRepository, GovernanceRepository, SnapshotExporter
from .review_contracts import ActorContext
from .snapshot_contracts import NormalizedFmeaSnapshot

_HASH = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_MAX_ID = 256
_MAX_TEXT = 4096
_MEDIA_TYPES = {
    ExportFormat.JSON: "application/json",
    ExportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ExportFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_NARRATIVE_UNSAFE = re.compile(
    r"(?i)(?:https?://|file://|\\\\|(?:[a-z]:[\\/])|\b(?:api[_ -]?key|authorization|credential|password|secret|token)\b)"
)
_NARRATIVE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,127}$")
_NARRATIVE_FIELDS = (
    "function",
    "item",
    "failure_mode",
    "potential_failure_mode",
    "effect",
    "potential_effect",
    "cause",
    "potential_cause",
    "current_control",
    "current_controls",
    "detection_method",
    "recommended_action",
    "severity",
    "occurrence",
    "detection",
    "rpn",
)
_NARRATIVE_MAX_ROWS = 8
_NARRATIVE_MAX_EVIDENCE = 12
_NARRATIVE_MAX_UNRESOLVED = 8


class ExportServiceError(ValueError):
    """Stable, bounded error at the export application boundary."""

    _CODES = frozenset({
        "FMEA_EXPORT_REQUEST_INVALID",
        "FMEA_EXPORT_FORBIDDEN",
        "FMEA_EXPORT_RUN_NOT_FOUND",
        "FMEA_EXPORT_SNAPSHOT_NOT_FOUND",
        "FMEA_EXPORT_SNAPSHOT_STALE",
        "FMEA_EXPORT_PUBLICATION_NOT_FOUND",
        "FMEA_EXPORT_PUBLICATION_STALE",
        "FMEA_EXPORT_NOT_ELIGIBLE",
        "FMEA_EXPORT_FORMAT_UNSUPPORTED",
        "FMEA_EXPORT_RENDER_FAILED",
        "FMEA_EXPORT_ARTIFACT_NOT_FOUND",
        "FMEA_EXPORT_ARTIFACT_INVALID",
        "FMEA_EXPORT_IDEMPOTENCY_CONFLICT",
        "FMEA_EXPORT_STORAGE_UNAVAILABLE",
        "FMEA_EXPORT_PERSISTENCE_INVALID",
        "FMEA_EXPORT_NARRATIVE_REQUEST_INVALID",
        "FMEA_EXPORT_NARRATIVE_FORBIDDEN",
        "FMEA_EXPORT_NARRATIVE_INVALID",
        "FMEA_EXPORT_NARRATIVE_UNAVAILABLE",
    })

    def __init__(self, code: str, public_message: str, retryable: bool = False) -> None:
        if code not in self._CODES:
            raise ValueError(f"unknown export error code: {code}")
        if not isinstance(public_message, str) or not public_message.strip():
            raise ValueError("public_message must not be empty")
        if not isinstance(retryable, bool):
            raise ValueError("retryable must be a boolean")
        self.code = code
        self.public_message = public_message.strip()[:_MAX_TEXT]
        self.retryable = retryable
        super().__init__(f"{code}: {self.public_message}")


_T = TypeVar("_T")


def _boundary_call(
    operation: Callable[[], _T],
    *,
    code: str,
    message: str,
    retryable: bool = False,
    idempotency_conflict: bool = False,
) -> _T:
    """Translate every adapter exception into service-owned public policy."""

    try:
        return operation()
    except Exception as exc:
        if idempotency_conflict and type(exc) is ValueError and str(exc) == "FMEA_EXPORT_IDEMPOTENCY_CONFLICT":
            raise ExportServiceError(
                "FMEA_EXPORT_IDEMPOTENCY_CONFLICT", "idempotency key has a different payload"
            ) from None
        raise ExportServiceError(code, message, retryable) from None


def _narrative_boundary_call(operation: Callable[[], _T]) -> _T:
    """Classify generator failures by service policy, never adapter fields."""

    try:
        return operation()
    except Exception as exc:
        cause = exc.__cause__
        if (
            isinstance(exc, ValueError)
            and not isinstance(exc, ExportServiceError)
            and (cause is None or isinstance(cause, ValueError))
        ):
            raise ExportServiceError(
                "FMEA_EXPORT_NARRATIVE_INVALID", "narrative generation result is invalid"
            ) from None
        raise ExportServiceError(
            "FMEA_EXPORT_NARRATIVE_UNAVAILABLE",
            "narrative generation is temporarily unavailable",
            retryable=True,
        ) from None


def _text(value: object, name: str, *, limit: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
    value = value.strip()
    if len(value) > limit:
        raise ValueError(f"{name} exceeds maximum length {limit}")
    return value


def _hash(value: object, name: str) -> str:
    value = _text(value, name, limit=71)
    if _HASH.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 hash")
    return value


def _timestamp(value: object, name: str) -> str:
    value = _text(value, name, limit=64)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp")
    return value


def _narrative_text(value: object, name: str, *, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} is invalid")
    normalized = value.strip()
    if _NARRATIVE_UNSAFE.search(normalized):
        raise ValueError(f"{name} is not export-safe")
    return normalized


def _narrative_id(value: object, name: str) -> str:
    normalized = _narrative_text(value, name, limit=128)
    if _NARRATIVE_ID.fullmatch(normalized) is None:
        raise ValueError(f"{name} is invalid")
    return normalized


def _narrative_ids(value: object, name: str, *, maximum: int) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise ValueError(f"{name} is invalid")
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds its limit")
    normalized = tuple(_narrative_id(item, name) for item in value)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} contains duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class ExportNarrativeClaim:
    """One bounded narrative claim and its projection-local evidence references."""

    claim_id: str
    text: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", _narrative_id(self.claim_id, "claim_id"))
        object.__setattr__(self, "text", _narrative_text(self.text, "claim text", limit=1000))
        object.__setattr__(self, "evidence_ids", _narrative_ids(self.evidence_ids, "claim evidence_ids", maximum=8))


@dataclass(frozen=True, slots=True)
class ExportNarrativeSection:
    """One bounded section that can only point at claims in the same draft."""

    section_id: str
    title: str
    body: str
    claim_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "section_id", _narrative_id(self.section_id, "section_id"))
        object.__setattr__(self, "title", _narrative_text(self.title, "section title", limit=256))
        object.__setattr__(self, "body", _narrative_text(self.body, "section body", limit=2500))
        object.__setattr__(self, "claim_ids", _narrative_ids(self.claim_ids, "section claim_ids", maximum=32))


@dataclass(frozen=True, slots=True)
class ExportNarrativeDraft:
    """Immutable, review-only narrative payload for one normalized snapshot."""

    title: str
    sections: tuple[ExportNarrativeSection, ...]
    claims: tuple[ExportNarrativeClaim, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _narrative_text(self.title, "narrative title", limit=256))
        sections = tuple(self.sections)
        claims = tuple(self.claims)
        if not 1 <= len(sections) <= 8 or not 1 <= len(claims) <= 32:
            raise ValueError("narrative sections or claims exceed the bounded limit")
        if not all(isinstance(item, ExportNarrativeSection) for item in sections):
            raise ValueError("narrative sections are invalid")
        if not all(isinstance(item, ExportNarrativeClaim) for item in claims):
            raise ValueError("narrative claims are invalid")
        section_ids = tuple(item.section_id for item in sections)
        claim_ids = tuple(item.claim_id for item in claims)
        if len(section_ids) != len(set(section_ids)) or len(claim_ids) != len(set(claim_ids)):
            raise ValueError("narrative section or claim IDs contain duplicates")
        known_claims = set(claim_ids)
        referenced_claims = {claim_id for section in sections for claim_id in section.claim_ids}
        if referenced_claims != known_claims:
            raise ValueError("narrative section claim references are invalid")
        if sum(len(section.title) + len(section.body) for section in sections) + len(self.title) > 16_000:
            raise ValueError("narrative text exceeds the bounded limit")
        object.__setattr__(self, "sections", sections)
        object.__setattr__(self, "claims", claims)

    def as_json(self) -> Mapping[str, object]:
        return {
            "title": self.title,
            "sections": [
                {
                    "section_id": section.section_id,
                    "title": section.title,
                    "body": section.body,
                    "claim_ids": list(section.claim_ids),
                }
                for section in self.sections
            ],
            "claims": [
                {
                    "claim_id": claim.claim_id,
                    "text": claim.text,
                    "evidence_ids": list(claim.evidence_ids),
                }
                for claim in self.claims
            ],
        }


@dataclass(frozen=True, slots=True)
class ExportNarrativeRequest:
    """Server-side request carrying the exact snapshot and its safe model projection."""

    snapshot: NormalizedFmeaSnapshot
    projection: Mapping[str, object]
    run_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, NormalizedFmeaSnapshot):
            raise ValueError("snapshot must be a NormalizedFmeaSnapshot")
        object.__setattr__(self, "run_id", _text(self.run_id, "run_id", limit=_MAX_ID))
        if not isinstance(self.projection, Mapping):
            raise ValueError("narrative projection must be a mapping")
        object.__setattr__(self, "projection", dict(self.projection))


@dataclass(frozen=True, slots=True)
class ExportNarrativeGenerationResult:
    """Validated generator result before the application builds the shared envelope."""

    draft: ExportNarrativeDraft
    model_hash: str
    prompt_hash: str
    run_id: str
    trace_id: str
    status: Literal["succeeded", "needs_review"]
    repair_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.draft, ExportNarrativeDraft):
            raise ValueError("narrative draft is invalid")
        object.__setattr__(self, "model_hash", _hash(self.model_hash, "model_hash"))
        object.__setattr__(self, "prompt_hash", _hash(self.prompt_hash, "prompt_hash"))
        object.__setattr__(self, "run_id", _text(self.run_id, "run_id", limit=_MAX_ID))
        object.__setattr__(self, "trace_id", _text(self.trace_id, "trace_id", limit=_MAX_ID))
        if self.status not in {"succeeded", "needs_review"}:
            raise ValueError("narrative pipeline status is invalid")
        if isinstance(self.repair_count, bool) or self.repair_count not in {0, 1}:
            raise ValueError("narrative repair count is invalid")


@dataclass(frozen=True, slots=True)
class ExportNarrativeSuggestion:
    """Typed view over the shared immutable AssistanceSuggestion envelope."""

    envelope: AssistanceSuggestion[Mapping[str, object]]
    draft: ExportNarrativeDraft

    @property
    def payload(self) -> ExportNarrativeDraft:
        return self.draft

    def __getattr__(self, name: str) -> object:
        return getattr(self.envelope, name)


def _narrative_alias(prefix: str, value: object) -> str:
    return f"{prefix}-{sha256(str(value).encode('utf-8')).hexdigest()[:16]}"


def _safe_projection_text(value: object, *, limit: int = 512) -> str | None:
    if not isinstance(value, str) or not value.strip() or len(value) > 16_384:
        return None
    normalized = value.strip()
    if _NARRATIVE_UNSAFE.search(normalized):
        return None
    return normalized[:limit]


def _safe_projection_value(value: object) -> object | None:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if isfinite(value) else None
    if isinstance(value, str):
        return _safe_projection_text(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        bounded = tuple(_safe_projection_text(item, limit=256) for item in value[:4])
        return [item for item in bounded if item is not None]
    return None


def build_export_narrative_projection(snapshot: NormalizedFmeaSnapshot) -> Mapping[str, object]:
    """Build a bounded projection without exposing workspace or source-document identities."""

    if not isinstance(snapshot, NormalizedFmeaSnapshot):
        raise ValueError("snapshot must be a NormalizedFmeaSnapshot")
    raw_evidence: list[tuple[str, str, str]] = []

    def add_evidence(raw_id: object, kind: str, excerpt: object) -> None:
        if not isinstance(raw_id, str) or not raw_id.strip() or any(item[0] == raw_id for item in raw_evidence):
            return
        raw_evidence.append((raw_id.strip(), kind, _safe_projection_text(excerpt) or ""))

    for item in snapshot.evidence_summary:
        pack_id = item.get("pack_id")
        raw_ids = item.get("evidence_ids")
        if isinstance(raw_ids, Sequence) and not isinstance(raw_ids, str | bytes):
            for raw_id in raw_ids:
                add_evidence(raw_id, "evidence-summary", item.get("excerpt", item.get("summary", "")))
        elif isinstance(item.get("evidence_id"), str):
            add_evidence(item["evidence_id"], "evidence-summary", item.get("excerpt", ""))
        else:
            add_evidence(pack_id, "pack-summary", item.get("summary", ""))
    for item in snapshot.unresolved_items:
        evidence_ids = item.get("evidence_ids")
        if isinstance(evidence_ids, Sequence) and not isinstance(evidence_ids, str | bytes):
            for raw_id in evidence_ids:
                add_evidence(raw_id, "unresolved", "")

    raw_evidence = raw_evidence[:_NARRATIVE_MAX_EVIDENCE]
    evidence_aliases = {raw_id: f"evidence-{index:03d}" for index, (raw_id, _, _) in enumerate(raw_evidence, start=1)}
    evidence = [
        {"ref": evidence_aliases[raw_id], "kind": kind, "excerpt": excerpt} for raw_id, kind, excerpt in raw_evidence
    ]

    row_items = sorted(snapshot.rows, key=lambda item: str(item.get("row_id", "")))[:_NARRATIVE_MAX_ROWS]
    rows: list[dict[str, object]] = []
    for row in row_items:
        fields: dict[str, object] = {}
        for field_name in _NARRATIVE_FIELDS:
            if field_name not in row:
                continue
            value = _safe_projection_value(row[field_name])
            if value is not None:
                fields[field_name] = value
        rows.append({"row_alias": _narrative_alias("row", row.get("row_id", len(rows))), "fields": fields})

    unresolved: list[dict[str, object]] = []
    for index, item in enumerate(snapshot.unresolved_items[:_NARRATIVE_MAX_UNRESOLVED], start=1):
        item_evidence = item.get("evidence_ids")
        refs = tuple(
            evidence_aliases[raw_id]
            for raw_id in item_evidence
            if isinstance(item_evidence, Sequence)
            and not isinstance(item_evidence, str | bytes)
            and raw_id in evidence_aliases
        )
        unresolved.append({
            "issue_alias": f"issue-{index:03d}",
            "code": _safe_projection_text(item.get("code"), limit=128) or "unknown",
            "severity": _safe_projection_text(item.get("severity"), limit=32) or "unknown",
            "evidence_refs": list(refs),
        })
    return {
        "snapshot_alias": _narrative_alias("snapshot", snapshot.snapshot_id),
        "revision_alias": _narrative_alias("revision", snapshot.revision_id),
        "summary": {
            "row_count": snapshot.row_count,
            "risk_record_count": len(snapshot.risk_records),
            "evidence_pack_count": len(snapshot.evidence_summary),
            "decision_count": len(snapshot.decision_summary),
            "unresolved_count": len(snapshot.unresolved_items),
            "propagation_present": snapshot.propagation is not None,
        },
        "rows": rows,
        "evidence": evidence,
        "unresolved": unresolved,
    }


@dataclass(frozen=True, slots=True)
class StartExportCommand:
    """Immutable request whose filename is already server-owned."""

    export_run_id: str
    workspace_id: str
    revision_id: str
    snapshot_id: str
    snapshot_hash: str
    publication_id: str | None
    format: ExportFormat | str
    draft_preview: bool
    idempotency_key: str
    filename: str | None = None
    filename_token: str | None = None

    def __post_init__(self) -> None:
        for name in ("export_run_id", "workspace_id", "revision_id", "snapshot_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name, limit=_MAX_ID))
        object.__setattr__(self, "snapshot_hash", _hash(self.snapshot_hash, "snapshot_hash"))
        if self.publication_id is not None:
            object.__setattr__(self, "publication_id", _text(self.publication_id, "publication_id", limit=_MAX_ID))
        if not isinstance(self.draft_preview, bool):
            raise ValueError("draft_preview must be a boolean")
        if self.draft_preview and self.publication_id is not None:
            raise ValueError("draft preview must not contain a publication identity")
        if not self.draft_preview and self.publication_id is None:
            raise ValueError("published export requires a publication identity")
        try:
            export_format = self.format if isinstance(self.format, ExportFormat) else ExportFormat(self.format)
        except (TypeError, ValueError) as exc:
            raise ValueError("format is unsupported") from exc
        object.__setattr__(self, "format", export_format)
        object.__setattr__(self, "idempotency_key", _text(self.idempotency_key, "idempotency_key", limit=256))
        if self.filename is not None and self.filename_token is not None:
            raise ValueError("filename and filename_token are mutually exclusive")
        if self.filename_token is not None:
            token = _text(self.filename_token, "filename_token", limit=128)
            object.__setattr__(self, "filename_token", token)
            filename = f"{token}.{export_format.value}"
        elif self.filename is not None:
            filename = _text(self.filename, "filename", limit=255)
        else:
            filename = f"fmea-{self.export_run_id}.{export_format.value}"
        filename = validate_filename(filename, "filename", expected_extension=export_format.value)
        object.__setattr__(self, "filename", filename)


def _command_value(command: StartExportCommand) -> dict[str, object]:
    return {
        "export_run_id": command.export_run_id,
        "workspace_id": command.workspace_id,
        "revision_id": command.revision_id,
        "snapshot_id": command.snapshot_id,
        "snapshot_hash": command.snapshot_hash,
        "publication_id": command.publication_id,
        "format": command.format.value,
        "draft_preview": command.draft_preview,
        "filename": command.filename,
        "idempotency_key": command.idempotency_key,
    }


def _canonical(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _request_hash(command: StartExportCommand) -> tuple[str, str]:
    payload = _canonical(_command_value(command))
    return payload, "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


def _artifact_id(workspace_id: str, export_run_id: str) -> str:
    return "artifact-" + sha256(f"{workspace_id}:{export_run_id}".encode()).hexdigest()[:40]


class ExportService:
    """Coordinate snapshot validation, rendering, immutable publication and persistence."""

    def __init__(
        self,
        governance_repository: GovernanceRepository,
        export_repository: ExportRepository,
        artifact_store: ArtifactStore,
        exporters: Mapping[str | ExportFormat, SnapshotExporter] | Iterable[SnapshotExporter],
        *,
        clock: Callable[[], str] | None = None,
        narrative_generator: ExportNarrativeGenerator | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self.governance_repository = governance_repository
        self.export_repository = export_repository
        self.artifact_store = artifact_store
        candidates = tuple(exporters.values()) if isinstance(exporters, Mapping) else tuple(exporters)
        selected: dict[str, SnapshotExporter] = {}
        for exporter in candidates:
            try:
                format_value = getattr(exporter, "format", None)
                key = format_value.value if isinstance(format_value, ExportFormat) else str(format_value)
                ExportFormat(key)
            except Exception:
                raise ValueError("exporter format is invalid") from None
            if key in selected:
                raise ValueError("exporter format is duplicated")
            selected[key] = exporter
        self._exporters = selected
        self._clock = clock or (
            lambda: datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        )
        self._narrative_generator = narrative_generator
        self._id_factory = id_factory

    @staticmethod
    def _authorize(actor: ActorContext) -> None:
        if not isinstance(actor, ActorContext):
            raise ExportServiceError("FMEA_EXPORT_FORBIDDEN", "a human export actor is required")
        if actor.actor_type is not ActorType.HUMAN or not ({"exporter", "publisher", "admin"} & actor.roles):
            raise ExportServiceError("FMEA_EXPORT_FORBIDDEN", "actor is not allowed to export")

    @staticmethod
    def _validate_run_binding(run: object, command: StartExportCommand, actor: ActorContext) -> ExportRun:
        if not isinstance(run, ExportRun):
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "export run persistence is invalid")
        if (
            run.export_run_id != command.export_run_id
            or run.workspace_id != actor.workspace_id
            or run.revision_id != command.revision_id
            or run.snapshot_id != command.snapshot_id
            or run.snapshot_hash != command.snapshot_hash
            or run.publication_id != command.publication_id
            or run.format != command.format
            or run.draft_preview != command.draft_preview
            or run.filename != command.filename
        ):
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "export run binding is invalid")
        return run

    def _load_snapshot(self, command: StartExportCommand):
        lookup_id = command.publication_id or command.snapshot_id
        snapshot = _boundary_call(
            lambda: self.governance_repository.get_snapshot(lookup_id, command.workspace_id),
            code="FMEA_EXPORT_PERSISTENCE_INVALID",
            message="snapshot persistence is invalid",
        )
        if snapshot is None:
            raise ExportServiceError("FMEA_EXPORT_SNAPSHOT_NOT_FOUND", "exact export snapshot was not found")
        if not isinstance(snapshot, NormalizedFmeaSnapshot):
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "snapshot persistence is invalid")
        if (
            snapshot.workspace_id != command.workspace_id
            or snapshot.snapshot_id != command.snapshot_id
            or snapshot.revision_id != command.revision_id
            or snapshot.snapshot_hash != command.snapshot_hash
        ):
            raise ExportServiceError("FMEA_EXPORT_SNAPSHOT_STALE", "export snapshot binding is stale")
        if not command.draft_preview:
            publication = _boundary_call(
                lambda: self.governance_repository.get_publication(command.publication_id, command.workspace_id),
                code="FMEA_EXPORT_PERSISTENCE_INVALID",
                message="publication persistence is invalid",
            )
            lifecycle = _boundary_call(
                lambda: self.governance_repository.get_publication_lifecycle(
                    command.publication_id, command.workspace_id
                ),
                code="FMEA_EXPORT_PERSISTENCE_INVALID",
                message="publication persistence is invalid",
            )
            if publication is None or lifecycle is None:
                raise ExportServiceError("FMEA_EXPORT_PUBLICATION_NOT_FOUND", "publication was not found")
            if not isinstance(publication, PublishedRevision) or not isinstance(lifecycle, PublicationLifecycleView):
                raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "publication persistence is invalid")
            if (
                publication.workspace_id != command.workspace_id
                or publication.publication_id != command.publication_id
                or lifecycle.publication != publication
            ):
                raise ExportServiceError("FMEA_EXPORT_PUBLICATION_STALE", "publication binding is stale")
            if lifecycle.effective_status is not RevisionPublicationStatus.PUBLISHED:
                raise ExportServiceError("FMEA_EXPORT_NOT_ELIGIBLE", "publication is not currently exportable")
            if (
                publication.revision_id != command.revision_id
                or publication.revision_hash != snapshot.revision_hash
                or publication.snapshot_id != command.snapshot_id
                or publication.snapshot_hash != command.snapshot_hash
                or snapshot.publication_id != command.publication_id
                or snapshot.manifest_id != publication.manifest_id
                or snapshot.analysis_id != publication.analysis_id
            ):
                raise ExportServiceError("FMEA_EXPORT_PUBLICATION_STALE", "publication binding is stale")
            eligibility = _boundary_call(
                lambda: self.governance_repository.get_export_eligibility(command.publication_id, command.workspace_id),
                code="FMEA_EXPORT_PERSISTENCE_INVALID",
                message="export eligibility persistence is invalid",
            )
            if eligibility is not None and not isinstance(eligibility, ExportEligibilityRecord):
                raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "export eligibility persistence is invalid")
            if eligibility is None or not eligibility.eligible:
                raise ExportServiceError("FMEA_EXPORT_NOT_ELIGIBLE", "publication is not eligible for export")
            if (
                eligibility.workspace_id != command.workspace_id
                or eligibility.publication_id != command.publication_id
                or eligibility.manifest_id != publication.manifest_id
                or dict(eligibility.source_hashes).get("revision") != publication.revision_hash
                or dict(eligibility.source_hashes).get("snapshot") != command.snapshot_hash
            ):
                raise ExportServiceError("FMEA_EXPORT_PUBLICATION_STALE", "export eligibility binding is stale")
        return snapshot

    @staticmethod
    def _verify_store(stored: object, manifest: ExportArtifactManifest, payload: bytes | None = None) -> None:
        try:
            stored_manifest = getattr(stored, "manifest", None)
            stored_payload = getattr(stored, "payload", None)
        except Exception:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "published artifact verification failed") from None
        if stored is None or stored_manifest != manifest:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "published artifact verification failed")
        if not isinstance(stored_payload, bytes):
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "published artifact payload is invalid")
        if payload is not None and stored_payload != payload:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "published artifact payload changed")
        if len(stored_payload) != manifest.byte_length:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "published artifact length is invalid")
        if "sha256:" + sha256(stored_payload).hexdigest() != manifest.sha256:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "published artifact hash is invalid")

    def _verify_completed(self, run: ExportRun, actor: ActorContext) -> ExportRun:
        if not isinstance(run, ExportRun) or run.workspace_id != actor.workspace_id or run.artifact_id is None:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "succeeded export has no artifact")
        verified_run, manifest = _boundary_call(
            lambda: self.export_repository.verify_export_delivery(run.export_run_id, actor.workspace_id),
            code="FMEA_EXPORT_PERSISTENCE_INVALID",
            message="export delivery persistence is invalid",
        )
        if (
            not isinstance(verified_run, ExportRun)
            or not isinstance(manifest, ExportArtifactManifest)
            or verified_run != run
            or verified_run.workspace_id != actor.workspace_id
            or manifest.artifact_id != run.artifact_id
        ):
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "export delivery binding is corrupted")
        try:
            validate_export_binding(run, manifest)
        except ValueError:
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "export binding is corrupted") from None
        stored = _boundary_call(
            lambda: self.artifact_store.get(run.artifact_id, actor.workspace_id),
            code="FMEA_EXPORT_ARTIFACT_INVALID",
            message="succeeded export file is unavailable",
        )
        self._verify_store(stored, manifest)
        return run

    def _fail_run(self, run: ExportRun, error: str, actor: ActorContext) -> ExportRun:
        failed = _boundary_call(
            lambda: self.export_repository.fail_export(
                run.export_run_id,
                actor.workspace_id,
                error[:512],
                self._clock(),
            ),
            code="FMEA_EXPORT_STORAGE_UNAVAILABLE",
            message="export failure could not be persisted",
            retryable=True,
        )
        if (
            not isinstance(failed, ExportRun)
            or failed.export_run_id != run.export_run_id
            or failed.workspace_id != actor.workspace_id
            or failed.revision_id != run.revision_id
            or failed.snapshot_id != run.snapshot_id
            or failed.snapshot_hash != run.snapshot_hash
            or failed.publication_id != run.publication_id
            or failed.format != run.format
            or failed.draft_preview != run.draft_preview
            or failed.filename != run.filename
        ):
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "failed export persistence is invalid")
        return failed

    def start(self, command: StartExportCommand, actor: ActorContext) -> ExportRun:
        self._authorize(actor)
        if not isinstance(command, StartExportCommand) or command.workspace_id != actor.workspace_id:
            raise ExportServiceError("FMEA_EXPORT_REQUEST_INVALID", "export request is invalid")
        request_json, request_hash = _request_hash(command)
        existing = _boundary_call(
            lambda: self.export_repository.get_export_run(command.export_run_id, actor.workspace_id),
            code="FMEA_EXPORT_PERSISTENCE_INVALID",
            message="export run persistence is invalid",
        )
        if existing is not None and (
            not isinstance(existing, ExportRun)
            or existing.workspace_id != actor.workspace_id
            or existing.export_run_id != command.export_run_id
        ):
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "export run persistence is invalid")
        if existing is not None:
            existing = _boundary_call(
                lambda: self.export_repository.reserve_export_run(
                    command, actor, request_json, request_hash, self._clock()
                ),
                code="FMEA_EXPORT_STORAGE_UNAVAILABLE",
                message="export replay lookup failed",
                retryable=True,
                idempotency_conflict=True,
            )
            existing = self._validate_run_binding(existing, command, actor)
            if existing.status is RunStatus.SUCCEEDED:
                return self._verify_completed(existing, actor)
            if existing.status is RunStatus.FAILED:
                return existing

        snapshot = self._load_snapshot(command)
        exporter = self._exporters.get(command.format.value)
        if exporter is None:
            raise ExportServiceError("FMEA_EXPORT_FORMAT_UNSUPPORTED", "requested export format is not enabled")
        exporter_format = _boundary_call(
            lambda: getattr(exporter, "format", None),
            code="FMEA_EXPORT_FORMAT_UNSUPPORTED",
            message="exporter format binding is invalid",
        )
        media_type = _boundary_call(
            lambda: getattr(exporter, "media_type", None),
            code="FMEA_EXPORT_FORMAT_UNSUPPORTED",
            message="exporter media type binding is invalid",
        )
        if exporter_format not in {command.format, command.format.value}:
            raise ExportServiceError("FMEA_EXPORT_FORMAT_UNSUPPORTED", "exporter format binding is invalid")
        if media_type != _MEDIA_TYPES[command.format]:
            raise ExportServiceError("FMEA_EXPORT_FORMAT_UNSUPPORTED", "exporter media type binding is invalid")

        if existing is None:
            run = _boundary_call(
                lambda: self.export_repository.reserve_export_run(
                    command, actor, request_json, request_hash, self._clock()
                ),
                code="FMEA_EXPORT_STORAGE_UNAVAILABLE",
                message="export run reservation failed",
                retryable=True,
                idempotency_conflict=True,
            )
        else:
            run = existing
        run = self._validate_run_binding(run, command, actor)
        if run.status is RunStatus.SUCCEEDED:
            return self._verify_completed(run, actor)
        if run.status is RunStatus.FAILED:
            return run
        if run.status is RunStatus.QUEUED:
            run = _boundary_call(
                lambda: self.export_repository.mark_export_running(
                    run.export_run_id, actor.workspace_id, self._clock()
                ),
                code="FMEA_EXPORT_STORAGE_UNAVAILABLE",
                message="export run could not start",
                retryable=True,
            )
        run = self._validate_run_binding(run, command, actor)
        if run.status is not RunStatus.RUNNING:
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "running export persistence is invalid")

        artifact_id = _artifact_id(actor.workspace_id, run.export_run_id)
        try:
            existing_store_artifact = _boundary_call(
                lambda: self.artifact_store.latest(run.export_run_id),
                code="FMEA_EXPORT_ARTIFACT_INVALID",
                message="artifact store lookup failed",
            )
        except ExportServiceError:
            return self._fail_run(run, "artifact store lookup failed", actor)
        if existing_store_artifact is not None:
            manifest = _boundary_call(
                lambda: getattr(existing_store_artifact, "manifest", None),
                code="FMEA_EXPORT_ARTIFACT_INVALID",
                message="reconciled artifact binding is invalid",
            )
            if not isinstance(manifest, ExportArtifactManifest) or (
                manifest.artifact_id != artifact_id or manifest.export_run_id != run.export_run_id
            ):
                raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "reconciled artifact binding is invalid")
            if (
                manifest.revision_id != command.revision_id
                or manifest.snapshot_id != command.snapshot_id
                or manifest.snapshot_hash != command.snapshot_hash
                or manifest.publication_id != command.publication_id
                or manifest.draft_preview != command.draft_preview
                or manifest.format != command.format
                or manifest.filename != command.filename
            ):
                raise ExportServiceError("FMEA_EXPORT_IDEMPOTENCY_CONFLICT", "stored artifact binding conflicts")
            verified = _boundary_call(
                lambda: self.artifact_store.get(artifact_id, actor.workspace_id),
                code="FMEA_EXPORT_STORAGE_UNAVAILABLE",
                message="export reconciliation failed",
                retryable=True,
            )
            self._verify_store(verified, manifest)
            completed = _boundary_call(
                lambda: self.export_repository.complete_export(
                    run, manifest, actor, request_json, request_hash, self._clock()
                ),
                code="FMEA_EXPORT_STORAGE_UNAVAILABLE",
                message="export reconciliation failed",
                retryable=True,
            )
            completed = self._validate_run_binding(completed, command, actor)
            return self._verify_completed(completed, actor)

        try:
            payload = _boundary_call(
                lambda: exporter.render(snapshot),
                code="FMEA_EXPORT_RENDER_FAILED",
                message="exporter failed",
            )
        except ExportServiceError:
            return self._fail_run(run, "exporter failed", actor)
        if not isinstance(payload, bytes):
            return self._fail_run(run, "exporter returned invalid bytes", actor)
        payload_hash = "sha256:" + sha256(payload).hexdigest()
        manifest = ExportArtifactManifest(
            artifact_id=artifact_id,
            export_run_id=run.export_run_id,
            publication_id=command.publication_id,
            revision_id=command.revision_id,
            snapshot_id=command.snapshot_id,
            snapshot_hash=command.snapshot_hash,
            format=command.format,
            media_type=media_type,
            byte_length=len(payload),
            sha256=payload_hash,
            draft_preview=command.draft_preview,
            created_at=self._clock(),
            filename=command.filename,
        )
        try:
            stored = _boundary_call(
                lambda: self.artifact_store.publish(run.export_run_id, command.filename, payload, manifest),
                code="FMEA_EXPORT_ARTIFACT_INVALID",
                message="artifact publication failed",
            )
            verified = _boundary_call(
                lambda: self.artifact_store.get(artifact_id, actor.workspace_id),
                code="FMEA_EXPORT_ARTIFACT_INVALID",
                message="artifact publication verification failed",
            )
        except ExportServiceError:
            return self._fail_run(run, "artifact publication failed", actor)
        self._verify_store(stored, manifest, payload)
        self._verify_store(verified, manifest, payload)
        completed = _boundary_call(
            lambda: self.export_repository.complete_export(
                run, manifest, actor, request_json, request_hash, self._clock()
            ),
            code="FMEA_EXPORT_STORAGE_UNAVAILABLE",
            message="export completion is retryable",
            retryable=True,
        )
        completed = self._validate_run_binding(completed, command, actor)
        return self._verify_completed(completed, actor)

    def suggest_narrative(
        self,
        snapshot: NormalizedFmeaSnapshot,
        actor: ActorContext,
    ) -> ExportNarrativeSuggestion:
        """Generate a provisional narrative without touching durable export state."""

        if not isinstance(snapshot, NormalizedFmeaSnapshot):
            raise ExportServiceError("FMEA_EXPORT_NARRATIVE_REQUEST_INVALID", "narrative snapshot is invalid")
        if not isinstance(actor, ActorContext) or actor.actor_type is not ActorType.MODEL:
            raise ExportServiceError("FMEA_EXPORT_NARRATIVE_FORBIDDEN", "narrative suggestions require a model actor")
        if actor.workspace_id != snapshot.workspace_id:
            raise ExportServiceError("FMEA_EXPORT_NARRATIVE_FORBIDDEN", "narrative workspace binding is invalid")
        if self._narrative_generator is None:
            raise ExportServiceError(
                "FMEA_EXPORT_NARRATIVE_UNAVAILABLE", "narrative generation is not configured", retryable=True
            )
        request = ExportNarrativeRequest(
            snapshot=snapshot,
            projection=build_export_narrative_projection(snapshot),
            run_id="export-narrative-" + sha256(snapshot.snapshot_hash.encode("ascii")).hexdigest()[:32],
        )
        result = _narrative_boundary_call(lambda: self._narrative_generator.generate(request))
        if not isinstance(result, ExportNarrativeGenerationResult) or result.run_id != request.run_id:
            raise ExportServiceError("FMEA_EXPORT_NARRATIVE_INVALID", "narrative generation result is invalid")
        try:
            evidence_pack_ids = tuple(
                item["pack_id"]
                for item in snapshot.evidence_summary
                if isinstance(item.get("pack_id"), str) and item["pack_id"].strip()
            ) or ("snapshot-evidence",)
            evidence_values: list[str] = []
            for claim in result.draft.claims:
                for evidence_id in claim.evidence_ids:
                    if evidence_id not in evidence_values:
                        evidence_values.append(evidence_id)
            evidence_ids = tuple(evidence_values)
            envelope = AssistanceSuggestion(
                suggestion_id="export-narrative-suggestion-"
                + sha256(f"{snapshot.snapshot_id}:{snapshot.snapshot_hash}".encode()).hexdigest()[:32],
                kind=AssistanceKind.EXPORT_NARRATIVE_DRAFT,
                workspace_id=snapshot.workspace_id,
                target_type="normalized_fmea_snapshot",
                target_id=snapshot.snapshot_id,
                target_record_version=1,
                evidence_pack_ids=evidence_pack_ids,
                payload=result.draft.as_json(),
                evidence_ids=evidence_ids,
                model_hash=result.model_hash,
                prompt_hash=result.prompt_hash,
                run_id=result.run_id,
                trace_id=result.trace_id,
                domain_pack_id=None,
                domain_pack_version=None,
                template_id=None,
                template_version=None,
                rule_pack_id=None,
                rule_pack_version=None,
                created_at=self._clock(),
                applied=False,
            )
        except (TypeError, ValueError) as exc:
            raise ExportServiceError(
                "FMEA_EXPORT_NARRATIVE_INVALID", "narrative suggestion contract is invalid"
            ) from exc
        return ExportNarrativeSuggestion(envelope=envelope, draft=result.draft)

    def get_run(self, export_run_id: str, actor: ActorContext) -> ExportRun:
        self._authorize(actor)
        run = _boundary_call(
            lambda: self.export_repository.get_export_run(export_run_id, actor.workspace_id),
            code="FMEA_EXPORT_PERSISTENCE_INVALID",
            message="export run persistence is invalid",
        )
        if run is None:
            raise ExportServiceError("FMEA_EXPORT_RUN_NOT_FOUND", "export run was not found")
        if (
            not isinstance(run, ExportRun)
            or run.workspace_id != actor.workspace_id
            or run.export_run_id != export_run_id
        ):
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "export run persistence is invalid")
        return self._verify_completed(run, actor) if run.status is RunStatus.SUCCEEDED else run

    def get_artifact(self, artifact_id: str, actor: ActorContext):
        self._authorize(actor)
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise ExportServiceError("FMEA_EXPORT_REQUEST_INVALID", "artifact identity is invalid")
        manifest = _boundary_call(
            lambda: self.export_repository.get_export_artifact(artifact_id, actor.workspace_id),
            code="FMEA_EXPORT_PERSISTENCE_INVALID",
            message="export artifact persistence is invalid",
        )
        if manifest is None:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_NOT_FOUND", "artifact was not found")
        if not isinstance(manifest, ExportArtifactManifest) or manifest.artifact_id != artifact_id:
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "export artifact persistence is invalid")
        run, verified_manifest = _boundary_call(
            lambda: self.export_repository.verify_export_delivery(manifest.export_run_id, actor.workspace_id),
            code="FMEA_EXPORT_PERSISTENCE_INVALID",
            message="export delivery persistence is invalid",
        )
        if (
            not isinstance(run, ExportRun)
            or not isinstance(verified_manifest, ExportArtifactManifest)
            or run.workspace_id != actor.workspace_id
            or verified_manifest != manifest
        ):
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "export delivery binding is corrupted")
        try:
            validate_export_binding(run, manifest)
        except ValueError:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "artifact verification failed") from None
        stored = _boundary_call(
            lambda: self.artifact_store.get(artifact_id, actor.workspace_id),
            code="FMEA_EXPORT_ARTIFACT_INVALID",
            message="artifact verification failed",
        )
        self._verify_store(stored, manifest)
        return stored


__all__ = [
    "ExportNarrativeClaim",
    "ExportNarrativeDraft",
    "ExportNarrativeGenerationResult",
    "ExportNarrativeRequest",
    "ExportNarrativeSection",
    "ExportNarrativeSuggestion",
    "ExportService",
    "ExportServiceError",
    "StartExportCommand",
    "build_export_narrative_projection",
]
