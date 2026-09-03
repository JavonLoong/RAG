"""Provider-neutral application service for verified FMEA exports."""

# The service is deliberately independent from JSON/XLSX/DOCX implementations.
# Exporters and storage are injected through ports so C2 can add narrative
# generation without changing the durable export protocol.
# ruff: noqa: C901, TRY003, TRY004

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from core_domain.fmea.filename_policy import validate_filename
from core_domain.fmea.governance import RevisionPublicationStatus
from core_domain.fmea.states import ActorType, RunStatus

from .delivery_contracts import ExportArtifactManifest, ExportFormat, ExportRun, validate_export_binding
from .ports import ArtifactStore, ExportRepository, GovernanceRepository, SnapshotExporter
from .review_contracts import ActorContext

_HASH = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_MAX_ID = 256
_MAX_TEXT = 4096
_MEDIA_TYPES = {
    ExportFormat.JSON: "application/json",
    ExportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ExportFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


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
    ) -> None:
        self.governance_repository = governance_repository
        self.export_repository = export_repository
        self.artifact_store = artifact_store
        candidates = tuple(exporters.values()) if isinstance(exporters, Mapping) else tuple(exporters)
        selected: dict[str, SnapshotExporter] = {}
        for exporter in candidates:
            format_value = getattr(exporter, "format", None)
            try:
                key = format_value.value if isinstance(format_value, ExportFormat) else str(format_value)
                ExportFormat(key)
            except (TypeError, ValueError) as exc:
                raise ValueError("exporter format is invalid") from exc
            if key in selected:
                raise ValueError("exporter format is duplicated")
            selected[key] = exporter
        self._exporters = selected
        self._clock = clock or (
            lambda: datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        )

    @staticmethod
    def _authorize(actor: ActorContext) -> None:
        if not isinstance(actor, ActorContext):
            raise ExportServiceError("FMEA_EXPORT_FORBIDDEN", "a human export actor is required")
        if actor.actor_type is not ActorType.HUMAN or not ({"exporter", "publisher", "admin"} & actor.roles):
            raise ExportServiceError("FMEA_EXPORT_FORBIDDEN", "actor is not allowed to export")

    def _load_snapshot(self, command: StartExportCommand):
        lookup_id = command.publication_id or command.snapshot_id
        try:
            snapshot = self.governance_repository.get_snapshot(lookup_id, command.workspace_id)
        except ExportServiceError:
            raise
        except Exception as exc:
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "snapshot persistence is invalid") from exc
        if snapshot is None:
            raise ExportServiceError("FMEA_EXPORT_SNAPSHOT_NOT_FOUND", "exact export snapshot was not found")
        if (
            snapshot.workspace_id != command.workspace_id
            or snapshot.snapshot_id != command.snapshot_id
            or snapshot.revision_id != command.revision_id
            or snapshot.snapshot_hash != command.snapshot_hash
        ):
            raise ExportServiceError("FMEA_EXPORT_SNAPSHOT_STALE", "export snapshot binding is stale")
        if not command.draft_preview:
            publication = self.governance_repository.get_publication(command.publication_id, command.workspace_id)
            lifecycle = self.governance_repository.get_publication_lifecycle(
                command.publication_id, command.workspace_id
            )
            if publication is None or lifecycle is None:
                raise ExportServiceError("FMEA_EXPORT_PUBLICATION_NOT_FOUND", "publication was not found")
            if lifecycle.effective_status is not RevisionPublicationStatus.PUBLISHED:
                raise ExportServiceError("FMEA_EXPORT_NOT_ELIGIBLE", "publication is not currently exportable")
            if (
                publication.revision_id != command.revision_id
                or publication.snapshot_id != command.snapshot_id
                or publication.snapshot_hash != command.snapshot_hash
                or snapshot.publication_id != command.publication_id
            ):
                raise ExportServiceError("FMEA_EXPORT_PUBLICATION_STALE", "publication binding is stale")
            eligibility = self.governance_repository.get_export_eligibility(
                command.publication_id, command.workspace_id
            )
            if eligibility is None or not eligibility.eligible:
                raise ExportServiceError("FMEA_EXPORT_NOT_ELIGIBLE", "publication is not eligible for export")
            if (
                eligibility.publication_id != command.publication_id
                or eligibility.manifest_id != publication.manifest_id
                or dict(eligibility.source_hashes).get("revision") != publication.revision_hash
                or dict(eligibility.source_hashes).get("snapshot") != command.snapshot_hash
            ):
                raise ExportServiceError("FMEA_EXPORT_PUBLICATION_STALE", "export eligibility binding is stale")
        return snapshot

    @staticmethod
    def _verify_store(stored: object, manifest: ExportArtifactManifest, payload: bytes | None = None) -> None:
        if stored is None or getattr(stored, "manifest", None) != manifest:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "published artifact verification failed")
        stored_payload = getattr(stored, "payload", None)
        if not isinstance(stored_payload, bytes):
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "published artifact payload is invalid")
        if payload is not None and stored_payload != payload:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "published artifact payload changed")
        if len(stored_payload) != manifest.byte_length:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "published artifact length is invalid")
        if "sha256:" + sha256(stored_payload).hexdigest() != manifest.sha256:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "published artifact hash is invalid")

    def _verify_completed(self, run: ExportRun, actor: ActorContext) -> ExportRun:
        if run.artifact_id is None:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "succeeded export has no artifact")
        try:
            manifest = self.export_repository.get_export_artifact(run.artifact_id, actor.workspace_id)
        except Exception as exc:
            raise ExportServiceError(
                "FMEA_EXPORT_PERSISTENCE_INVALID", "export artifact persistence is invalid"
            ) from exc
        if manifest is None:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_NOT_FOUND", "succeeded export artifact was not found")
        try:
            validate_export_binding(run, manifest)
        except ValueError as exc:
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "export binding is corrupted") from exc
        try:
            stored = self.artifact_store.get(run.artifact_id, actor.workspace_id)
        except Exception as exc:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "succeeded export file is unavailable") from exc
        self._verify_store(stored, manifest)
        return run

    def _fail_run(self, run: ExportRun, error: str, actor: ActorContext) -> ExportRun:
        try:
            return self.export_repository.fail_export(
                run.export_run_id,
                actor.workspace_id,
                error[:512],
                self._clock(),
            )
        except Exception as exc:
            raise ExportServiceError(
                "FMEA_EXPORT_STORAGE_UNAVAILABLE", "export failure could not be persisted", retryable=True
            ) from exc

    def start(self, command: StartExportCommand, actor: ActorContext) -> ExportRun:
        self._authorize(actor)
        if not isinstance(command, StartExportCommand) or command.workspace_id != actor.workspace_id:
            raise ExportServiceError("FMEA_EXPORT_REQUEST_INVALID", "export request is invalid")
        request_json, request_hash = _request_hash(command)
        try:
            existing = self.export_repository.get_export_run(command.export_run_id, actor.workspace_id)
        except Exception as exc:
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "export run persistence is invalid") from exc
        if existing is not None:
            try:
                existing = self.export_repository.reserve_export_run(
                    command, actor, request_json, request_hash, self._clock()
                )
            except Exception as exc:
                if "IDEMPOTENCY_CONFLICT" in str(exc):
                    raise ExportServiceError(
                        "FMEA_EXPORT_IDEMPOTENCY_CONFLICT", "idempotency key has a different payload"
                    ) from exc
                raise ExportServiceError(
                    "FMEA_EXPORT_STORAGE_UNAVAILABLE", "export replay lookup failed", True
                ) from exc
            if existing.status is RunStatus.SUCCEEDED:
                return self._verify_completed(existing, actor)
            if existing.status is RunStatus.FAILED:
                return existing

        snapshot = self._load_snapshot(command)
        exporter = self._exporters.get(command.format.value)
        if exporter is None:
            raise ExportServiceError("FMEA_EXPORT_FORMAT_UNSUPPORTED", "requested export format is not enabled")
        if getattr(exporter, "format", None) not in {command.format, command.format.value}:
            raise ExportServiceError("FMEA_EXPORT_FORMAT_UNSUPPORTED", "exporter format binding is invalid")
        if getattr(exporter, "media_type", None) != _MEDIA_TYPES[command.format]:
            raise ExportServiceError("FMEA_EXPORT_FORMAT_UNSUPPORTED", "exporter media type binding is invalid")

        try:
            if existing is None:
                run = self.export_repository.reserve_export_run(
                    command, actor, request_json, request_hash, self._clock()
                )
            else:
                run = existing
        except Exception as exc:
            if "IDEMPOTENCY_CONFLICT" in str(exc):
                raise ExportServiceError(
                    "FMEA_EXPORT_IDEMPOTENCY_CONFLICT", "idempotency key has a different payload"
                ) from exc
            raise ExportServiceError("FMEA_EXPORT_STORAGE_UNAVAILABLE", "export run reservation failed", True) from exc
        if run.status is RunStatus.SUCCEEDED:
            return self._verify_completed(run, actor)
        if run.status is RunStatus.FAILED:
            return run
        try:
            if run.status is RunStatus.QUEUED:
                run = self.export_repository.mark_export_running(run.export_run_id, actor.workspace_id, self._clock())
        except Exception as exc:
            raise ExportServiceError("FMEA_EXPORT_STORAGE_UNAVAILABLE", "export run could not start", True) from exc

        artifact_id = _artifact_id(actor.workspace_id, run.export_run_id)
        try:
            existing_store_artifact = self.artifact_store.latest(run.export_run_id)
        except Exception:
            return self._fail_run(run, "artifact store lookup failed", actor)
        if existing_store_artifact is not None:
            manifest = getattr(existing_store_artifact, "manifest", None)
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
            try:
                verified = self.artifact_store.get(artifact_id, actor.workspace_id)
                self._verify_store(verified, manifest)
                return self.export_repository.complete_export(
                    run, manifest, actor, request_json, request_hash, self._clock()
                )
            except ExportServiceError:
                raise
            except Exception as exc:
                raise ExportServiceError(
                    "FMEA_EXPORT_STORAGE_UNAVAILABLE", "export reconciliation failed", True
                ) from exc

        try:
            payload = exporter.render(snapshot)
        except Exception:
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
            media_type=exporter.media_type,
            byte_length=len(payload),
            sha256=payload_hash,
            draft_preview=command.draft_preview,
            created_at=self._clock(),
            filename=command.filename,
        )
        try:
            stored = self.artifact_store.publish(run.export_run_id, command.filename, payload, manifest)
            verified = self.artifact_store.get(artifact_id, actor.workspace_id)
            self._verify_store(stored, manifest, payload)
            self._verify_store(verified, manifest, payload)
        except Exception:
            return self._fail_run(run, "artifact publication failed", actor)
        try:
            return self.export_repository.complete_export(
                run, manifest, actor, request_json, request_hash, self._clock()
            )
        except ExportServiceError:
            raise
        except Exception as exc:
            raise ExportServiceError("FMEA_EXPORT_STORAGE_UNAVAILABLE", "export completion is retryable", True) from exc

    def get_run(self, export_run_id: str, actor: ActorContext) -> ExportRun:
        self._authorize(actor)
        try:
            run = self.export_repository.get_export_run(export_run_id, actor.workspace_id)
        except Exception as exc:
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "export run persistence is invalid") from exc
        if run is None:
            raise ExportServiceError("FMEA_EXPORT_RUN_NOT_FOUND", "export run was not found")
        return self._verify_completed(run, actor) if run.status is RunStatus.SUCCEEDED else run

    def get_artifact(self, artifact_id: str, actor: ActorContext):
        self._authorize(actor)
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise ExportServiceError("FMEA_EXPORT_REQUEST_INVALID", "artifact identity is invalid")
        try:
            manifest = self.export_repository.get_export_artifact(artifact_id, actor.workspace_id)
        except Exception as exc:
            raise ExportServiceError(
                "FMEA_EXPORT_PERSISTENCE_INVALID", "export artifact persistence is invalid"
            ) from exc
        if manifest is None:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_NOT_FOUND", "artifact was not found")
        try:
            run = self.export_repository.get_export_run(manifest.export_run_id, actor.workspace_id)
        except Exception as exc:
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "export run persistence is invalid") from exc
        if run is None:
            raise ExportServiceError("FMEA_EXPORT_PERSISTENCE_INVALID", "artifact run is missing")
        try:
            validate_export_binding(run, manifest)
            stored = self.artifact_store.get(artifact_id, actor.workspace_id)
            self._verify_store(stored, manifest)
        except ExportServiceError:
            raise
        except Exception as exc:
            raise ExportServiceError("FMEA_EXPORT_ARTIFACT_INVALID", "artifact verification failed") from exc
        return stored


__all__ = ["ExportService", "ExportServiceError", "StartExportCommand"]
