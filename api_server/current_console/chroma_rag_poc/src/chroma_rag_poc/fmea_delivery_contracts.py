"""Strict transport contracts and path-free projections for FMEA delivery."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator

_HASH_PATTERN = r"^(?:sha256:)?[0-9a-f]{64}$"
_ID = Field(min_length=1, max_length=256)
_OPTIONAL_ID = Field(default=None, min_length=1, max_length=256)
_HASH = Field(min_length=64, max_length=71, pattern=_HASH_PATTERN)
_VERSION = Field(min_length=1, max_length=128)


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class TemplatePatchRunRequest(_StrictRequest):
    input_template_version: StrictStr = _VERSION
    target_template_id: StrictStr = _ID
    target_template_version: StrictStr = _VERSION
    target_template_hash: StrictStr = _HASH
    domain_pack_id: StrictStr = _ID
    domain_pack_version: StrictStr = _VERSION
    domain_pack_hash: StrictStr = _HASH
    evidence_pack_id: StrictStr = _ID
    evidence_pack_hash: StrictStr = _HASH


class TemplatePatchAcceptanceRequest(_StrictRequest):
    suggestion_id: StrictStr = _ID
    patch_id: StrictStr = _ID
    draft_id: StrictStr = _ID
    draft_sha256: StrictStr = _HASH
    target_template_version: StrictStr = _VERSION
    target_template_hash: StrictStr = _HASH
    new_template_version: StrictStr = _VERSION
    domain_pack_hash: StrictStr = _HASH
    evidence_pack_hash: StrictStr = _HASH
    confirm_template_change: StrictBool

    @field_validator("confirm_template_change")
    @classmethod
    def _must_confirm(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError from None
        return value


class TemplatePatchRejectionRequest(_StrictRequest):
    suggestion_id: StrictStr = _ID
    patch_id: StrictStr = _ID
    reason: StrictStr = Field(min_length=1, max_length=4096)


class MigrationDryRunRequest(_StrictRequest):
    migration_id: StrictStr = _ID
    source_revision_hash: StrictStr = _HASH
    target_domain_pack_id: StrictStr = _ID
    target_domain_pack_version: StrictStr = _VERSION
    target_domain_pack_hash: StrictStr = _HASH


class MigrationConfirmationRequest(_StrictRequest):
    migration_id: StrictStr = _ID
    report_hash: StrictStr = _HASH
    source_revision_id: StrictStr = _ID
    source_revision_hash: StrictStr = _HASH
    target_domain_pack_id: StrictStr = _ID
    target_domain_pack_version: StrictStr = _VERSION
    target_domain_pack_hash: StrictStr = _HASH
    dry_run: MigrationDryRunRequest
    confirm_migration: StrictBool

    @field_validator("confirm_migration")
    @classmethod
    def _must_confirm(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError from None
        return value


class ExportRunRequest(_StrictRequest):
    snapshot_id: StrictStr = _ID
    snapshot_hash: StrictStr = _HASH
    format: Literal["json", "xlsx", "docx"]
    publication_id: StrictStr | None = _OPTIONAL_ID
    draft_preview: StrictBool = False
    confirm_publication: StrictBool = False


class ExportNarrativeRunRequest(_StrictRequest):
    snapshot_id: StrictStr | None = _OPTIONAL_ID
    snapshot_hash: StrictStr | None = Field(default=None, min_length=64, max_length=71, pattern=_HASH_PATTERN)
    publication_id: StrictStr | None = _OPTIONAL_ID


def _public_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, str | int | bool) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): _public_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_public_value(item) for item in value]
    return None


def _attrs(value: object, names: tuple[str, ...]) -> dict[str, object]:
    return {name: _public_value(getattr(value, name, None)) for name in names}


def template_draft_data(draft: object) -> dict[str, object]:
    return _attrs(
        draft,
        (
            "draft_id",
            "workspace_id",
            "filename",
            "source_sha256",
            "template_id",
            "template_version",
            "status",
            "created_at",
            "record_version",
        ),
    )


def template_patch_data(suggestion: object) -> dict[str, object]:
    envelope = getattr(suggestion, "envelope", suggestion)
    candidate = getattr(suggestion, "candidate", getattr(suggestion, "payload", None))
    data = _attrs(
        envelope,
        ("suggestion_id", "patch_id", "draft_id", "run_id", "trace_id", "target_type", "applied", "citations"),
    )
    data["candidate"] = _attrs(
        candidate,
        (
            "patch_id",
            "draft_id",
            "input_template_version",
            "target_template_id",
            "target_template_version",
            "target_template_hash",
            "domain_pack_id",
            "domain_pack_version",
            "domain_pack_hash",
            "evidence_pack_id",
            "evidence_pack_hash",
            "operations",
            "rationale",
        ),
    )
    return data


def template_patch_decision_data(decision: object) -> dict[str, object]:
    return _attrs(
        decision,
        (
            "decision_id",
            "suggestion_id",
            "patch_id",
            "draft_id",
            "decision",
            "reason",
            "new_template_version",
            "created_at",
            "record_version",
            "replayed",
        ),
    )


def template_registration_data(template: object) -> dict[str, object]:
    metadata = getattr(template, "metadata", None)
    return {
        "template_id": getattr(metadata, "template_id", getattr(template, "template_id", None)),
        "version": getattr(metadata, "version", getattr(template, "version", None)),
        "template_hash": _public_value(getattr(template, "template_hash", None)),
        "schema_dialect": _public_value(getattr(metadata, "schema_dialect", None)),
    }


def migration_report_data(report: object) -> dict[str, object]:
    return _attrs(
        report,
        (
            "migration_id",
            "status",
            "report_hash",
            "source_revision_id",
            "source_revision_hash",
            "source_domain_pack_identity",
            "target_domain_pack_identity",
            "target_revision_hash",
            "mapped_fields",
            "dropped_fields",
            "unresolved_fields",
            "warnings",
            "created_at",
        ),
    )


def compatibility_report_data(report: object) -> dict[str, object]:
    return _attrs(
        report,
        (
            "source_domain_pack_identity",
            "target_domain_pack_identity",
            "compatible",
            "plan",
            "report_hash",
            "created_at",
        ),
    )


def migration_result_data(result: object) -> dict[str, object]:
    return _attrs(result, ("migration_id", "child_revision_id", "report_hash", "replayed"))


def export_run_data(run: object) -> dict[str, object]:
    return _attrs(
        run,
        (
            "export_run_id",
            "workspace_id",
            "revision_id",
            "snapshot_id",
            "snapshot_hash",
            "publication_id",
            "format",
            "draft_preview",
            "status",
            "created_at",
            "filename",
            "artifact_id",
            "started_at",
            "finished_at",
            "error",
        ),
    )


def export_artifact_manifest_data(manifest: object) -> dict[str, object]:
    return _attrs(
        manifest,
        (
            "artifact_id",
            "export_run_id",
            "publication_id",
            "revision_id",
            "snapshot_id",
            "snapshot_hash",
            "format",
            "media_type",
            "byte_length",
            "sha256",
            "draft_preview",
            "created_at",
            "filename",
        ),
    )


def narrative_data(suggestion: object, *, target_type: str = "fmea_revision") -> dict[str, object]:
    envelope = getattr(suggestion, "envelope", suggestion)
    draft = getattr(suggestion, "draft", getattr(suggestion, "payload", None))
    data = _attrs(envelope, ("suggestion_id", "target_id", "run_id", "trace_id", "applied", "citations"))
    data["target_type"] = target_type
    data["draft"] = _public_value(getattr(draft, "as_json", lambda: draft)()) if draft is not None else None
    return data


__all__ = [
    "ExportNarrativeRunRequest",
    "ExportRunRequest",
    "MigrationConfirmationRequest",
    "MigrationDryRunRequest",
    "TemplatePatchAcceptanceRequest",
    "TemplatePatchRejectionRequest",
    "TemplatePatchRunRequest",
    "compatibility_report_data",
    "export_artifact_manifest_data",
    "export_run_data",
    "migration_report_data",
    "migration_result_data",
    "narrative_data",
    "template_draft_data",
    "template_patch_data",
    "template_patch_decision_data",
    "template_registration_data",
]
