from __future__ import annotations

from hashlib import sha256

import pytest
from chroma_rag_poc.fmea_delivery_contracts import (
    ExportNarrativeRunRequest,
    ExportRunRequest,
    MigrationConfirmationRequest,
    MigrationDryRunRequest,
    TemplatePatchAcceptanceRequest,
    TemplatePatchRunRequest,
    _public_value,
    compatibility_report_data,
    export_artifact_manifest_data,
    export_run_data,
    migration_report_data,
    migration_result_data,
    narrative_data,
    template_draft_data,
    template_patch_data,
    template_patch_decision_data,
    template_registration_data,
)
from pydantic import ValidationError

from core_domain.fmea.states import ActorType, RunStatus
from core_domain.fmea.template_migration import (
    CompatibilityReport,
    MigrationPlan,
    MigrationReport,
    MigrationReportStatus,
    MigrationStep,
    ProposedFieldMapping,
    SourceStructureItem,
    TemplateDraft,
    TemplateDraftStatus,
    TemplatePatchCandidate,
    TemplatePatchStatus,
)
from core_domain.structured_output.contracts import CompiledTemplate, EvidenceBinding, TemplateMetadata
from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
from fmea_application.delivery_contracts import ExportArtifactManifest, ExportFormat, ExportRun
from fmea_application.export_service import (
    ExportNarrativeClaim,
    ExportNarrativeDraft,
    ExportNarrativeSection,
    ExportNarrativeSuggestion,
)
from fmea_application.migration_service import MigrationResult
from fmea_application.template_patch_contracts import (
    TemplatePatchDecision,
    TemplatePatchSuggestion,
    candidate_payload,
)

STAMP = "2026-09-04T00:00:00Z"
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
HASH_E = "e" * 64
HASH_F = "f" * 64


def _draft() -> TemplateDraft:
    return TemplateDraft(
        draft_id="draft-1",
        workspace_id="ws-1",
        source_filename="source.xlsx",
        source_sha256=f"sha256:{HASH_A}",
        source_type="xlsx",
        structure=(SourceStructureItem("table", "Sheet1!A1", {"nested": ("cell", 1.5)}),),
        proposed_fields=(ProposedFieldMapping("Failure Mode", "failure_mode", "Sheet1!B1", 0.75, "header match"),),
        unknown_fields=("Unknown",),
        ambiguous_fields=("Ambiguous",),
        parser_warnings=("Warning",),
        status=TemplateDraftStatus.DRAFT,
        created_at=STAMP,
        identified_fields=("failure_mode",),
    )


def _candidate() -> TemplatePatchCandidate:
    return TemplatePatchCandidate(
        patch_id="patch-1",
        draft_id="draft-1",
        input_template_version="1.0.0",
        target_template_id="fmea-template",
        target_template_version="1.0.0",
        target_template_hash=f"sha256:{HASH_B}",
        domain_pack_id="domain-pack",
        domain_pack_version="1.0.0",
        domain_pack_hash=f"sha256:{HASH_C}",
        evidence_pack_id="evidence-pack",
        evidence_pack_hash=f"sha256:{HASH_D}",
        run_id="patch-run-1",
        trace_id="patch-trace-1",
        model_version="model-1",
        prompt_version="prompt-1",
        diff=({"op": "replace", "path": "/fields/failure_mode", "value": "new"},),
        evidence_ids=("evidence-1",),
        status=TemplatePatchStatus.SUGGESTED,
        created_at=STAMP,
    )


def _patch_suggestion() -> TemplatePatchSuggestion:
    candidate = _candidate()
    envelope = AssistanceSuggestion(
        suggestion_id="suggestion-1",
        kind=AssistanceKind.TEMPLATE_FIELD_MAPPING,
        workspace_id="ws-1",
        target_type="template_draft",
        target_id="draft-1",
        target_record_version=1,
        evidence_pack_ids=("evidence-pack",),
        payload=candidate_payload(candidate),
        evidence_ids=("evidence-1",),
        conflict_ids=("conflict-1",),
        uncertainty="bounded",
        model_hash=HASH_E,
        prompt_hash=HASH_F,
        run_id=candidate.run_id,
        trace_id=candidate.trace_id,
        domain_pack_id=candidate.domain_pack_id,
        domain_pack_version=candidate.domain_pack_version,
        template_id=candidate.target_template_id,
        template_version=candidate.target_template_version,
        record_version=2,
        created_at=STAMP,
    )
    return TemplatePatchSuggestion(candidate=candidate, envelope=envelope)


def _patch_decision() -> TemplatePatchDecision:
    candidate = _candidate()
    return TemplatePatchDecision(
        decision_id="decision-1",
        suggestion_id="suggestion-1",
        patch_id=candidate.patch_id,
        workspace_id="ws-1",
        actor_id="human-1",
        actor_type=ActorType.HUMAN,
        action="accepted",
        reason="accepted",
        base_template_id=candidate.target_template_id,
        base_template_version=candidate.target_template_version,
        base_template_hash=candidate.target_template_hash,
        candidate=candidate,
        new_template_version="1.1.0",
        created_at=STAMP,
    )


def _migration_plan() -> MigrationPlan:
    return MigrationPlan(
        source=("domain-pack", "1.0.0"),
        target=("domain-pack", "1.1.0"),
        steps=(MigrationStep(("domain-pack", "1.0.0"), ("domain-pack", "1.1.0"), "adapter-1"),),
    )


def _migration_report() -> MigrationReport:
    return MigrationReport(
        migration_id="migration-1",
        plan=_migration_plan(),
        source_revision_id="revision-1",
        source_revision_hash=f"sha256:{HASH_A}",
        source_domain_pack_identity=("domain-pack", "1.0.0", f"sha256:{HASH_B}"),
        target_domain_pack_identity=("domain-pack", "1.1.0", f"sha256:{HASH_C}"),
        target_revision_hash=f"sha256:{HASH_D}",
        status=MigrationReportStatus.DRY_RUN,
        mapped_fields=("failure_mode",),
        dropped_fields=("legacy_field",),
        unresolved_fields=("unknown_field",),
        warnings=("warning",),
        created_at=STAMP,
    )


def _export_run_and_manifest() -> tuple[ExportRun, ExportArtifactManifest]:
    payload = b'{"ok":true}\n'
    payload_hash = sha256(payload).hexdigest()
    run = ExportRun(
        export_run_id="export-run-1",
        workspace_id="ws-1",
        revision_id="revision-1",
        snapshot_hash=f"sha256:{HASH_A}",
        publication_id="publication-1",
        format=ExportFormat.JSON,
        draft_preview=False,
        status=RunStatus.SUCCEEDED,
        created_at=STAMP,
        snapshot_id="snapshot-1",
        filename="fmea-run-1.json",
        artifact_id="artifact-1",
        started_at=STAMP,
        finished_at="2026-09-04T00:01:00Z",
    )
    manifest = ExportArtifactManifest(
        artifact_id="artifact-1",
        export_run_id=run.export_run_id,
        publication_id=run.publication_id,
        revision_id=run.revision_id,
        snapshot_hash=run.snapshot_hash,
        format=run.format,
        media_type="application/json",
        byte_length=len(payload),
        sha256=payload_hash,
        draft_preview=run.draft_preview,
        created_at=STAMP,
        snapshot_id=run.snapshot_id,
        filename=run.filename,
    )
    return run, manifest


def _narrative_suggestion() -> ExportNarrativeSuggestion:
    claim = ExportNarrativeClaim("claim-1", "Claim text", ("evidence-1",))
    section = ExportNarrativeSection("section-1", "Summary", "Body", (claim.claim_id,))
    draft = ExportNarrativeDraft("FMEA narrative", (section,), (claim,))
    envelope = AssistanceSuggestion(
        suggestion_id="narrative-1",
        kind=AssistanceKind.EXPORT_NARRATIVE_DRAFT,
        workspace_id="ws-1",
        target_type="normalized_fmea_snapshot",
        target_id="snapshot-1",
        target_record_version=1,
        evidence_pack_ids=("evidence-pack",),
        payload=draft.as_json(),
        evidence_ids=("evidence-1",),
        model_hash=HASH_A,
        prompt_hash=HASH_B,
        run_id="narrative-run-1",
        trace_id="narrative-trace-1",
        record_version=1,
        created_at=STAMP,
    )
    return ExportNarrativeSuggestion(envelope=envelope, draft=draft)


def test_delivery_write_contracts_are_strict_and_server_owned() -> None:
    patch = {
        "input_template_version": "1.0.0",
        "target_template_id": "fmea-template",
        "target_template_version": "2.0.0",
        "target_template_hash": "sha256:" + "a" * 64,
        "domain_pack_id": "domain-pack",
        "domain_pack_version": "1.0.0",
        "domain_pack_hash": "sha256:" + "b" * 64,
        "evidence_pack_id": "evidence-pack",
        "evidence_pack_hash": "sha256:" + "c" * 64,
    }
    with pytest.raises(ValidationError):
        TemplatePatchRunRequest.model_validate({**patch, "provider": "client-controlled"})

    export = {
        "snapshot_id": "snapshot-1",
        "snapshot_hash": "sha256:" + "d" * 64,
        "format": "json",
        "draft_preview": True,
    }
    with pytest.raises(ValidationError):
        ExportRunRequest.model_validate({**export, "artifact_root": "C:/client"})

    assert "filename" not in ExportRunRequest.model_fields
    assert "repository" not in ExportRunRequest.model_fields
    assert "adapter" not in MigrationDryRunRequest.model_fields


def test_confirmation_contracts_require_exact_confirmation_values() -> None:
    acceptance = {
        "suggestion_id": "suggestion-1",
        "patch_id": "patch-1",
        "draft_id": "draft-1",
        "draft_sha256": "sha256:" + "a" * 64,
        "target_template_version": "2.0.0",
        "target_template_hash": "sha256:" + "b" * 64,
        "new_template_version": "2.1.0",
        "domain_pack_hash": "sha256:" + "c" * 64,
        "evidence_pack_hash": "sha256:" + "d" * 64,
        "confirm_template_change": True,
    }
    assert TemplatePatchAcceptanceRequest.model_validate(acceptance).confirm_template_change is True

    with pytest.raises(ValidationError):
        MigrationConfirmationRequest.model_validate({
            "migration_id": "migration-1",
            "report_hash": "sha256:" + "a" * 64,
            "source_revision_id": "revision-1",
            "source_revision_hash": "sha256:" + "b" * 64,
            "target_domain_pack_id": "domain-pack",
            "target_domain_pack_version": "1.0.0",
            "target_domain_pack_hash": "sha256:" + "c" * 64,
            "dry_run": {
                "migration_id": "migration-1",
                "source_revision_hash": "sha256:" + "b" * 64,
                "target_domain_pack_id": "domain-pack",
                "target_domain_pack_version": "1.0.0",
                "target_domain_pack_hash": "sha256:" + "c" * 64,
            },
            "confirm_migration": False,
        })


def test_narrative_request_is_suggestion_only() -> None:
    request = ExportNarrativeRunRequest.model_validate({
        "snapshot_id": "snapshot-1",
        "snapshot_hash": "sha256:" + "a" * 64,
    })
    assert request.model_dump() == {
        "snapshot_id": "snapshot-1",
        "snapshot_hash": "sha256:" + "a" * 64,
        "publication_id": None,
    }


def test_template_draft_projection_preserves_real_nested_contract_fields() -> None:
    assert template_draft_data(_draft()) == {
        "draft_id": "draft-1",
        "workspace_id": "ws-1",
        "source_filename": "source.xlsx",
        "source_sha256": f"sha256:{HASH_A}",
        "source_type": "xlsx",
        "structure": [{"kind": "table", "locator": "Sheet1!A1", "value": {"nested": ["cell", 1.5]}}],
        "proposed_fields": [
            {
                "source_key": "Failure Mode",
                "target_field": "failure_mode",
                "source_locator": "Sheet1!B1",
                "confidence": 0.75,
                "rationale": "header match",
            }
        ],
        "unknown_fields": ["Unknown"],
        "ambiguous_fields": ["Ambiguous"],
        "parser_warnings": ["Warning"],
        "status": "draft",
        "created_at": STAMP,
        "identified_fields": ["failure_mode"],
    }


def test_template_patch_projections_preserve_real_suggestion_and_decision_fields() -> None:
    suggestion = _patch_suggestion()
    suggestion_data = template_patch_data(suggestion)
    assert suggestion_data["evidence_ids"] == ["evidence-1"]
    assert suggestion_data["conflict_ids"] == ["conflict-1"]
    assert suggestion_data["uncertainty"] == "bounded"
    assert suggestion_data["record_version"] == 2
    assert suggestion_data["candidate"] == {
        "patch_id": "patch-1",
        "draft_id": "draft-1",
        "input_template_version": "1.0.0",
        "target_template_id": "fmea-template",
        "target_template_version": "1.0.0",
        "target_template_hash": f"sha256:{HASH_B}",
        "domain_pack_id": "domain-pack",
        "domain_pack_version": "1.0.0",
        "domain_pack_hash": f"sha256:{HASH_C}",
        "evidence_pack_id": "evidence-pack",
        "evidence_pack_hash": f"sha256:{HASH_D}",
        "run_id": "patch-run-1",
        "trace_id": "patch-trace-1",
        "model_version": "model-1",
        "prompt_version": "prompt-1",
        "diff": [{"op": "replace", "path": "/fields/failure_mode", "value": "new"}],
        "evidence_ids": ["evidence-1"],
        "status": "suggested",
        "created_at": STAMP,
        "applied": False,
    }

    assert template_patch_decision_data(_patch_decision()) == {
        "decision_id": "decision-1",
        "suggestion_id": "suggestion-1",
        "patch_id": "patch-1",
        "workspace_id": "ws-1",
        "actor_id": "human-1",
        "actor_type": "human",
        "action": "accepted",
        "reason": "accepted",
        "base_template_id": "fmea-template",
        "base_template_version": "1.0.0",
        "base_template_hash": f"sha256:{HASH_B}",
        "candidate": suggestion_data["candidate"],
        "new_template_version": "1.1.0",
        "created_at": STAMP,
    }


def test_migration_projections_preserve_real_reports_and_nested_plan() -> None:
    plan = _migration_plan()
    compatibility = CompatibilityReport(
        source=plan.source,
        target=plan.target,
        compatible=True,
        blocking_reasons=(),
        warnings=("warning",),
        checked_at=STAMP,
    )
    assert compatibility_report_data(compatibility) == {
        "source": ["domain-pack", "1.0.0"],
        "target": ["domain-pack", "1.1.0"],
        "compatible": True,
        "blocking_reasons": [],
        "warnings": ["warning"],
        "checked_at": STAMP,
        "report_hash": compatibility.report_hash,
    }

    report = _migration_report()
    assert migration_report_data(report) == {
        "migration_id": "migration-1",
        "plan": {
            "source": ["domain-pack", "1.0.0"],
            "target": ["domain-pack", "1.1.0"],
            "steps": [
                {
                    "source": ["domain-pack", "1.0.0"],
                    "target": ["domain-pack", "1.1.0"],
                    "adapter_id": "adapter-1",
                }
            ],
        },
        "source_revision_id": "revision-1",
        "source_revision_hash": f"sha256:{HASH_A}",
        "source_domain_pack_identity": ["domain-pack", "1.0.0", f"sha256:{HASH_B}"],
        "target_domain_pack_identity": ["domain-pack", "1.1.0", f"sha256:{HASH_C}"],
        "target_revision_hash": f"sha256:{HASH_D}",
        "status": "dry_run",
        "mapped_fields": ["failure_mode"],
        "dropped_fields": ["legacy_field"],
        "unresolved_fields": ["unknown_field"],
        "warnings": ["warning"],
        "created_at": STAMP,
        "report_hash": report.report_hash,
    }

    assert migration_result_data(MigrationResult("migration-1", "revision-2", HASH_E, replayed=True)) == {
        "migration_id": "migration-1",
        "child_revision_id": "revision-2",
        "report_hash": HASH_E,
        "replayed": True,
    }


def test_export_and_narrative_projections_preserve_real_contract_fields() -> None:
    run, manifest = _export_run_and_manifest()
    assert export_run_data(run) == {
        "export_run_id": "export-run-1",
        "workspace_id": "ws-1",
        "revision_id": "revision-1",
        "snapshot_hash": f"sha256:{HASH_A}",
        "publication_id": "publication-1",
        "format": "json",
        "draft_preview": False,
        "status": "succeeded",
        "created_at": STAMP,
        "snapshot_id": "snapshot-1",
        "filename": "fmea-run-1.json",
        "artifact_id": "artifact-1",
        "started_at": STAMP,
        "finished_at": "2026-09-04T00:01:00Z",
        "error": None,
    }
    assert export_artifact_manifest_data(manifest) == {
        "artifact_id": "artifact-1",
        "export_run_id": "export-run-1",
        "publication_id": "publication-1",
        "revision_id": "revision-1",
        "snapshot_hash": f"sha256:{HASH_A}",
        "format": "json",
        "media_type": "application/json",
        "byte_length": 12,
        "sha256": sha256(b'{"ok":true}\n').hexdigest(),
        "draft_preview": False,
        "created_at": STAMP,
        "snapshot_id": "snapshot-1",
        "filename": "fmea-run-1.json",
    }

    suggestion = _narrative_suggestion()
    narrative = narrative_data(suggestion)
    assert narrative["evidence_ids"] == ["evidence-1"]
    assert narrative["target_type"] == "fmea_revision"
    assert narrative["draft"] == {
        "title": "FMEA narrative",
        "sections": [
            {
                "section_id": "section-1",
                "title": "Summary",
                "body": "Body",
                "claim_ids": ["claim-1"],
            }
        ],
        "claims": [
            {
                "claim_id": "claim-1",
                "text": "Claim text",
                "evidence_ids": ["evidence-1"],
            }
        ],
    }


def test_template_registration_projection_uses_the_real_compiled_template() -> None:
    template = CompiledTemplate(
        metadata=TemplateMetadata(
            template_id="fmea-template",
            version="1.0.0",
            title="FMEA",
            description="FMEA template",
            domain_tags=("fmea",),
            schema_dialect="https://json-schema.org/draft/2020-12/schema",
        ),
        output_schema={"type": "object", "properties": {"failure_mode": {"type": "string"}}},
        evidence_bindings=(EvidenceBinding("failure_mode", "optional"),),
        template_hash=HASH_A,
        canonical_json="{}",
        source_mappings={"failure_mode": "failure_mode"},
    )
    assert template_registration_data(template) == {
        "template_id": "fmea-template",
        "version": "1.0.0",
        "template_hash": HASH_A,
        "schema_dialect": "https://json-schema.org/draft/2020-12/schema",
    }


@pytest.mark.parametrize(
    "serializer",
    (
        template_draft_data,
        template_patch_data,
        template_patch_decision_data,
        template_registration_data,
        migration_report_data,
        compatibility_report_data,
        export_run_data,
        export_artifact_manifest_data,
        narrative_data,
    ),
)
def test_delivery_projections_reject_wrong_contract_types(serializer) -> None:
    with pytest.raises(TypeError):
        serializer(object())


def test_public_value_rejects_unsupported_nested_values_instead_of_returning_null() -> None:
    with pytest.raises(TypeError):
        _public_value({"nested": object()})
