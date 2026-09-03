"""Strict transport contracts and path-free projections for FMEA delivery."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from math import isfinite
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator

from core_domain.fmea.template_migration import (
    CompatibilityReport,
    MigrationPlan,
    MigrationReport,
    MigrationStep,
    ProposedFieldMapping,
    SourceStructureItem,
    TemplateDraft,
    TemplatePatchCandidate,
)
from core_domain.structured_output.contracts import CompiledTemplate, TemplateMetadata
from fmea_application.assistance_contracts import AssistanceSuggestion
from fmea_application.delivery_contracts import ExportArtifactManifest, ExportRun
from fmea_application.export_service import (
    ExportNarrativeClaim,
    ExportNarrativeDraft,
    ExportNarrativeSection,
    ExportNarrativeSuggestion,
)
from fmea_application.migration_service import MigrationResult
from fmea_application.template_patch_contracts import TemplatePatchDecision, TemplatePatchSuggestion

_HASH_PATTERN = r"^(?:sha256:)?[0-9a-f]{64}$"
_ID = Field(min_length=1, max_length=256)
_OPTIONAL_ID = Field(default=None, min_length=1, max_length=256)
_HASH = Field(min_length=64, max_length=71, pattern=_HASH_PATTERN)
_VERSION = Field(min_length=1, max_length=128)
_T = TypeVar("_T")


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


def _public_mapping(value: Mapping[object, object], *, active: frozenset[int]) -> dict[str, object]:
    identity = id(value)
    if identity in active:
        raise TypeError("public projection does not support cyclic mappings")  # noqa: TRY003
    items = list(value.items())
    keys = [key for key, _ in items]
    if any(type(key) is not str for key in keys):
        raise TypeError("public projection mapping keys must be strings")  # noqa: TRY003
    if len(keys) != len(set(keys)):
        raise TypeError("public projection mapping keys must be unique")  # noqa: TRY003
    next_active = active | {identity}
    return {key: _public_value(item, _active=next_active) for key, item in sorted(items, key=lambda pair: pair[0])}


def _public_sequence(value: tuple[object, ...] | list[object], *, active: frozenset[int]) -> list[object]:
    identity = id(value)
    if identity in active:
        raise TypeError("public projection does not support cyclic sequences")  # noqa: TRY003
    next_active = active | {identity}
    return [_public_value(item, _active=next_active) for item in value]


def _public_value(value: object, *, _active: frozenset[int] = frozenset()) -> object:
    """Convert only JSON primitives and containers into deterministic public values."""

    if isinstance(value, Enum):
        return _public_value(value.value, _active=_active)
    if value is None or type(value) in {str, int, bool}:
        return value
    if type(value) is float:
        if not isfinite(value):
            raise TypeError("public projection does not support non-finite numbers")  # noqa: TRY003
        return value
    if isinstance(value, Mapping):
        return _public_mapping(value, active=_active)
    if isinstance(value, tuple | list):
        return _public_sequence(value, active=_active)
    raise TypeError(f"public projection does not support {type(value).__name__}")  # noqa: TRY003


def _require_type(value: object, expected: type[_T], field_name: str) -> _T:
    if not isinstance(value, expected):
        raise TypeError(f"{field_name} must be a {expected.__name__}")  # noqa: TRY003
    return value


def _structure_item_data(item: object) -> dict[str, object]:
    item = _require_type(item, SourceStructureItem, "structure item")
    return {
        "kind": item.kind,
        "locator": item.locator,
        "value": _public_value(item.value),
    }


def _proposed_field_data(item: object) -> dict[str, object]:
    item = _require_type(item, ProposedFieldMapping, "proposed field")
    return {
        "source_key": item.source_key,
        "target_field": item.target_field,
        "source_locator": item.source_locator,
        "confidence": _public_value(item.confidence),
        "rationale": item.rationale,
    }


def template_draft_data(draft: TemplateDraft) -> dict[str, object]:
    draft = _require_type(draft, TemplateDraft, "draft")
    return {
        "draft_id": draft.draft_id,
        "workspace_id": draft.workspace_id,
        "source_filename": draft.source_filename,
        "source_sha256": draft.source_sha256,
        "source_type": draft.source_type,
        "structure": [_structure_item_data(item) for item in draft.structure],
        "proposed_fields": [_proposed_field_data(item) for item in draft.proposed_fields],
        "unknown_fields": _public_value(draft.unknown_fields),
        "ambiguous_fields": _public_value(draft.ambiguous_fields),
        "parser_warnings": _public_value(draft.parser_warnings),
        "status": _public_value(draft.status),
        "created_at": draft.created_at,
        "identified_fields": _public_value(draft.identified_fields),
    }


def _template_patch_candidate_data(candidate: object) -> dict[str, object]:
    candidate = _require_type(candidate, TemplatePatchCandidate, "template patch candidate")
    return {
        "patch_id": candidate.patch_id,
        "draft_id": candidate.draft_id,
        "input_template_version": candidate.input_template_version,
        "target_template_id": candidate.target_template_id,
        "target_template_version": candidate.target_template_version,
        "target_template_hash": candidate.target_template_hash,
        "domain_pack_id": candidate.domain_pack_id,
        "domain_pack_version": candidate.domain_pack_version,
        "domain_pack_hash": candidate.domain_pack_hash,
        "evidence_pack_id": candidate.evidence_pack_id,
        "evidence_pack_hash": candidate.evidence_pack_hash,
        "run_id": candidate.run_id,
        "trace_id": candidate.trace_id,
        "model_version": candidate.model_version,
        "prompt_version": candidate.prompt_version,
        "diff": _public_value(candidate.diff),
        "evidence_ids": _public_value(candidate.evidence_ids),
        "status": _public_value(candidate.status),
        "created_at": candidate.created_at,
        "applied": candidate.applied,
    }


def _assistance_suggestion_data(envelope: object) -> dict[str, object]:
    envelope = _require_type(envelope, AssistanceSuggestion, "assistance envelope")
    return {
        "suggestion_id": envelope.suggestion_id,
        "kind": _public_value(envelope.kind),
        "workspace_id": envelope.workspace_id,
        "target_type": envelope.target_type,
        "target_id": envelope.target_id,
        "target_record_version": envelope.target_record_version,
        "evidence_pack_ids": _public_value(envelope.evidence_pack_ids),
        "payload": _public_value(envelope.payload),
        "evidence_ids": _public_value(envelope.evidence_ids),
        "conflict_ids": _public_value(envelope.conflict_ids),
        "uncertainty": envelope.uncertainty,
        "model_hash": envelope.model_hash,
        "prompt_hash": envelope.prompt_hash,
        "run_id": envelope.run_id,
        "trace_id": envelope.trace_id,
        "domain_pack_id": envelope.domain_pack_id,
        "domain_pack_version": envelope.domain_pack_version,
        "template_id": envelope.template_id,
        "template_version": envelope.template_version,
        "rule_pack_id": envelope.rule_pack_id,
        "rule_pack_version": envelope.rule_pack_version,
        "record_version": envelope.record_version,
        "created_at": envelope.created_at,
        "applied": envelope.applied,
        "suggestion_hash": envelope.suggestion_hash,
    }


def template_patch_data(suggestion: TemplatePatchSuggestion) -> dict[str, object]:
    suggestion = _require_type(suggestion, TemplatePatchSuggestion, "template patch suggestion")
    data = _assistance_suggestion_data(suggestion.envelope)
    data["candidate"] = _template_patch_candidate_data(suggestion.candidate)
    return data


def template_patch_decision_data(decision: TemplatePatchDecision) -> dict[str, object]:
    decision = _require_type(decision, TemplatePatchDecision, "template patch decision")
    return {
        "decision_id": decision.decision_id,
        "suggestion_id": decision.suggestion_id,
        "patch_id": decision.patch_id,
        "workspace_id": decision.workspace_id,
        "actor_id": decision.actor_id,
        "actor_type": _public_value(decision.actor_type),
        "action": decision.action,
        "reason": decision.reason,
        "base_template_id": decision.base_template_id,
        "base_template_version": decision.base_template_version,
        "base_template_hash": decision.base_template_hash,
        "candidate": _template_patch_candidate_data(decision.candidate),
        "new_template_version": decision.new_template_version,
        "created_at": decision.created_at,
    }


def template_registration_data(template: CompiledTemplate) -> dict[str, object]:
    template = _require_type(template, CompiledTemplate, "compiled template")
    metadata = _require_type(template.metadata, TemplateMetadata, "compiled template metadata")
    return {
        "template_id": metadata.template_id,
        "version": metadata.version,
        "template_hash": template.template_hash,
        "schema_dialect": metadata.schema_dialect,
    }


def _migration_step_data(step: object) -> dict[str, object]:
    step = _require_type(step, MigrationStep, "migration step")
    return {
        "source": _public_value(step.source),
        "target": _public_value(step.target),
        "adapter_id": step.adapter_id,
    }


def _migration_plan_data(plan: object) -> dict[str, object]:
    plan = _require_type(plan, MigrationPlan, "migration plan")
    return {
        "source": _public_value(plan.source),
        "target": _public_value(plan.target),
        "steps": [_migration_step_data(step) for step in plan.steps],
    }


def migration_report_data(report: MigrationReport) -> dict[str, object]:
    report = _require_type(report, MigrationReport, "migration report")
    return {
        "migration_id": report.migration_id,
        "plan": _migration_plan_data(report.plan),
        "source_revision_id": report.source_revision_id,
        "source_revision_hash": report.source_revision_hash,
        "source_domain_pack_identity": _public_value(report.source_domain_pack_identity),
        "target_domain_pack_identity": _public_value(report.target_domain_pack_identity),
        "target_revision_hash": report.target_revision_hash,
        "status": _public_value(report.status),
        "mapped_fields": _public_value(report.mapped_fields),
        "dropped_fields": _public_value(report.dropped_fields),
        "unresolved_fields": _public_value(report.unresolved_fields),
        "warnings": _public_value(report.warnings),
        "created_at": report.created_at,
        "report_hash": report.report_hash,
    }


def compatibility_report_data(report: CompatibilityReport) -> dict[str, object]:
    report = _require_type(report, CompatibilityReport, "compatibility report")
    return {
        "source": _public_value(report.source),
        "target": _public_value(report.target),
        "compatible": report.compatible,
        "blocking_reasons": _public_value(report.blocking_reasons),
        "warnings": _public_value(report.warnings),
        "checked_at": report.checked_at,
        "report_hash": report.report_hash,
    }


def migration_result_data(result: MigrationResult) -> dict[str, object]:
    result = _require_type(result, MigrationResult, "migration result")
    return {
        "migration_id": result.migration_id,
        "child_revision_id": result.child_revision_id,
        "report_hash": result.report_hash,
        "replayed": result.replayed,
    }


def export_run_data(run: ExportRun) -> dict[str, object]:
    run = _require_type(run, ExportRun, "export run")
    return {
        "export_run_id": run.export_run_id,
        "workspace_id": run.workspace_id,
        "revision_id": run.revision_id,
        "snapshot_hash": run.snapshot_hash,
        "publication_id": run.publication_id,
        "format": _public_value(run.format),
        "draft_preview": run.draft_preview,
        "status": _public_value(run.status),
        "created_at": run.created_at,
        "snapshot_id": run.snapshot_id,
        "filename": run.filename,
        "artifact_id": run.artifact_id,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "error": run.error,
    }


def export_artifact_manifest_data(manifest: ExportArtifactManifest) -> dict[str, object]:
    manifest = _require_type(manifest, ExportArtifactManifest, "export artifact manifest")
    return {
        "artifact_id": manifest.artifact_id,
        "export_run_id": manifest.export_run_id,
        "publication_id": manifest.publication_id,
        "revision_id": manifest.revision_id,
        "snapshot_hash": manifest.snapshot_hash,
        "format": _public_value(manifest.format),
        "media_type": manifest.media_type,
        "byte_length": manifest.byte_length,
        "sha256": manifest.sha256,
        "draft_preview": manifest.draft_preview,
        "created_at": manifest.created_at,
        "snapshot_id": manifest.snapshot_id,
        "filename": manifest.filename,
    }


def _narrative_claim_data(claim: object) -> dict[str, object]:
    claim = _require_type(claim, ExportNarrativeClaim, "narrative claim")
    return {
        "claim_id": claim.claim_id,
        "text": claim.text,
        "evidence_ids": _public_value(claim.evidence_ids),
    }


def _narrative_section_data(section: object) -> dict[str, object]:
    section = _require_type(section, ExportNarrativeSection, "narrative section")
    return {
        "section_id": section.section_id,
        "title": section.title,
        "body": section.body,
        "claim_ids": _public_value(section.claim_ids),
    }


def _narrative_draft_data(draft: object) -> dict[str, object]:
    draft = _require_type(draft, ExportNarrativeDraft, "narrative draft")
    return {
        "title": draft.title,
        "sections": [_narrative_section_data(section) for section in draft.sections],
        "claims": [_narrative_claim_data(claim) for claim in draft.claims],
    }


def narrative_data(suggestion: ExportNarrativeSuggestion, *, target_type: str = "fmea_revision") -> dict[str, object]:
    suggestion = _require_type(suggestion, ExportNarrativeSuggestion, "narrative suggestion")
    if type(target_type) is not str or not target_type:
        raise TypeError("target_type must be a non-empty string")  # noqa: TRY003
    data = _assistance_suggestion_data(suggestion.envelope)
    data["target_type"] = target_type
    data["draft"] = _narrative_draft_data(suggestion.draft)
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
