from __future__ import annotations

import re
from dataclasses import FrozenInstanceError, replace

import pytest

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.template_migration import (
    CompatibilityReport,
    MigrationPlan,
    MigrationReport,
    MigrationStep,
    ProposedFieldMapping,
    SourceStructureItem,
    TemplateDraft,
    TemplateDraftStatus,
    TemplatePatchCandidate,
    TemplatePatchStatus,
)
from fmea_application.delivery_contracts import (
    ExportArtifactManifest,
    ExportFormat,
    ExportRun,
)

TIMESTAMP = "2026-08-27T12:00:00Z"
HASH = "a" * 64


def _draft(**overrides: object) -> TemplateDraft:
    values: dict[str, object] = {
        "draft_id": "draft-1",
        "workspace_id": "ws-1",
        "source_filename": "source.xlsx",
        "source_sha256": HASH,
        "source_type": "xlsx",
        "structure": (
            SourceStructureItem(kind="sheet", locator="Sheet1"),
            SourceStructureItem(kind="merge", locator="Sheet1!A3:B3"),
        ),
        "proposed_fields": (
            ProposedFieldMapping(
                source_key="Failure Mode",
                target_field="failure_mode",
                source_locator="Sheet1!B2",
            ),
        ),
        "unknown_fields": ("Legacy Criticality",),
        "ambiguous_fields": ("Cause",),
        "parser_warnings": ("formula was not evaluated",),
        "status": TemplateDraftStatus.DRAFT,
        "created_at": TIMESTAMP,
    }
    values.update(overrides)
    return TemplateDraft(**values)


def _patch(**overrides: object) -> TemplatePatchCandidate:
    values: dict[str, object] = {
        "patch_id": "patch-1",
        "draft_id": "draft-1",
        "input_template_version": "1.0.0",
        "model_version": "model-1",
        "prompt_version": "prompt-1",
        "diff": (
            {
                "op": "replace",
                "path": "/fields/failure_mode",
                "value": "failure_mode",
            },
        ),
        "evidence_ids": ("evidence-1",),
        "status": TemplatePatchStatus.SUGGESTED,
        "created_at": TIMESTAMP,
    }
    values.update(overrides)
    return TemplatePatchCandidate(**values)


def _edge(source_version: str, target_version: str, adapter_id: str = "adapter-1") -> MigrationStep:
    return MigrationStep(
        source=("generic-domain", source_version),
        target=("generic-domain", target_version),
        adapter_id=adapter_id,
    )


def _plan(**overrides: object) -> MigrationPlan:
    values: dict[str, object] = {
        "source": ("generic-domain", "1.0.0"),
        "target": ("generic-domain", "3.0.0"),
        "steps": (_edge("1.0.0", "2.0.0"), _edge("2.0.0", "3.0.0")),
    }
    values.update(overrides)
    return MigrationPlan(**values)


def test_template_draft_preserves_unknown_and_ambiguous_fields() -> None:
    draft = _draft()
    assert draft.status == "draft"
    assert draft.unknown_fields == ("Legacy Criticality",)
    assert draft.ambiguous_fields == ("Cause",)
    assert draft.structure[1] == SourceStructureItem(kind="merge", locator="Sheet1!A3:B3")


def test_template_draft_keeps_identified_fields_as_an_immutable_collection() -> None:
    draft = _draft(identified_fields=("failure_mode", "causes"))
    assert draft.identified_fields == ("failure_mode", "causes")


def test_template_draft_preserves_repeated_source_labels_and_parser_warnings() -> None:
    draft = _draft(
        unknown_fields=("Legacy Column", "Legacy Column"),
        ambiguous_fields=("Cause", "Cause"),
        parser_warnings=("formula was not evaluated", "formula was not evaluated"),
    )
    assert draft.unknown_fields == ("Legacy Column", "Legacy Column")
    assert draft.ambiguous_fields == ("Cause", "Cause")
    assert draft.parser_warnings == ("formula was not evaluated", "formula was not evaluated")


def test_template_draft_is_immutable_and_freezes_nested_source_values() -> None:
    draft = _draft(
        structure=(SourceStructureItem(kind="cell", locator="Sheet1!A1", value={"raw": ["kept"]}),),
    )
    with pytest.raises(FrozenInstanceError):
        draft.status = "registered"  # type: ignore[misc]
    with pytest.raises(TypeError):
        draft.structure[0].value["raw"] = ("changed",)  # type: ignore[index]


def test_source_structure_kind_is_bounded_without_domain_specific_allowlist() -> None:
    item = SourceStructureItem(kind="custom-annotation", locator="document#annotation-1")
    assert item.kind == "custom-annotation"


def test_template_draft_rejects_duplicate_mapping_keys_and_non_draft_status() -> None:
    mapping = ProposedFieldMapping(source_key="Cause", target_field="causes", source_locator="Sheet1!A1")
    with pytest.raises(FmeaDomainError, match="mapping keys"):
        _draft(proposed_fields=(mapping, replace(mapping, source_locator="Sheet1!B1")))
    with pytest.raises(FmeaDomainError, match="status"):
        _draft(status="registered")


def test_template_patch_candidate_is_a_suggestion_until_human_workflow_accepts_it() -> None:
    candidate = _patch()
    assert candidate.status == "suggested"
    assert candidate.applied is False
    assert candidate.diff[0]["op"] == "replace"

    with pytest.raises(FmeaDomainError, match="applied"):
        _patch(applied=True)
    with pytest.raises(FmeaDomainError, match="status"):
        _patch(status="published")


def test_template_patch_candidate_rejects_duplicate_diff_paths_and_unbounded_values() -> None:
    duplicate_path = (
        {"op": "add", "path": "/fields/cause", "value": "causes"},
        {"op": "replace", "path": "/fields/cause", "value": "mechanisms"},
    )
    with pytest.raises(FmeaDomainError, match="diff paths"):
        _patch(diff=duplicate_path)
    with pytest.raises(FmeaDomainError, match="canonical"):
        _patch(diff=({"op": "add", "path": "/fields/x", "value": object()},))


def test_compatibility_report_requires_reasons_for_incompatibility_and_is_deterministic() -> None:
    report = CompatibilityReport(
        source=("generic-domain", "1.0.0"),
        target=("generic-domain", "2.0.0"),
        compatible=False,
        blocking_reasons=("required field cannot be mapped",),
        warnings=("legacy label retained",),
        checked_at=TIMESTAMP,
    )
    assert (
        report.report_hash
        == CompatibilityReport(
            source=report.source,
            target=report.target,
            compatible=report.compatible,
            blocking_reasons=report.blocking_reasons,
            warnings=report.warnings,
            checked_at=report.checked_at,
        ).report_hash
    )
    with pytest.raises(FmeaDomainError, match="blocking"):
        CompatibilityReport(
            source=report.source,
            target=report.target,
            compatible=False,
            blocking_reasons=(),
            warnings=(),
            checked_at=TIMESTAMP,
        )

    assert replace(report, report_hash=f"sha256:{report.report_hash}").report_hash == report.report_hash


def test_migration_plan_rejects_missing_explicit_version_edge() -> None:
    with pytest.raises(FmeaDomainError, match="migration path is not explicit"):
        MigrationPlan(source=("fuel-combustion", "1.0.0"), target=("fuel-combustion", "3.0.0"), steps=())


def test_migration_plan_requires_continuous_bounded_edges() -> None:
    with pytest.raises(FmeaDomainError, match="continuous"):
        _plan(steps=(_edge("1.0.0", "2.0.0"), _edge("2.1.0", "3.0.0")))
    with pytest.raises(FmeaDomainError, match="source and target"):
        _plan(source=("generic-domain", "1.0.0"), target=("other-domain", "3.0.0"))
    with pytest.raises(FmeaDomainError, match="maximum"):
        _plan(steps=tuple(_edge(f"{index}.0.0", f"{index + 1}.0.0") for index in range(65)))


def test_migration_report_is_immutable_and_requires_matching_plan_endpoints() -> None:
    plan = _plan()
    report = MigrationReport(
        migration_id="migration-1",
        plan=plan,
        source_revision_id="revision-1",
        source_revision_hash=HASH,
        status="dry_run",
        mapped_fields=("failure_mode",),
        dropped_fields=(),
        unresolved_fields=("legacy_field",),
        warnings=(),
        created_at=TIMESTAMP,
    )
    assert re.fullmatch(r"[0-9a-f]{64}", report.report_hash)
    with pytest.raises(FrozenInstanceError):
        report.status = "confirmed"  # type: ignore[misc]
    with pytest.raises(FmeaDomainError, match="status"):
        replace(report, status="published")


def test_export_run_binds_snapshot_and_publication_or_explicit_draft_preview() -> None:
    published = ExportRun(
        export_run_id="run-1",
        workspace_id="ws-1",
        revision_id="revision-1",
        snapshot_hash=HASH,
        publication_id="publication-1",
        format=ExportFormat.JSON,
        draft_preview=False,
        status="queued",
        created_at=TIMESTAMP,
    )
    preview = replace(published, export_run_id="run-2", publication_id=None, draft_preview=True)
    assert published.publication_id == "publication-1"
    assert preview.draft_preview is True
    with pytest.raises(FmeaDomainError, match="publication"):
        replace(published, publication_id=None)
    with pytest.raises(FmeaDomainError, match="preview"):
        replace(preview, publication_id="publication-2")


@pytest.mark.parametrize(
    ("export_format", "media_type"),
    (
        ("json", "application/json"),
        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ),
)
def test_artifact_manifest_enforces_exact_format_media_type_and_identity(
    export_format: str,
    media_type: str,
) -> None:
    manifest = ExportArtifactManifest(
        artifact_id="artifact-1",
        export_run_id="run-1",
        publication_id="publication-1",
        revision_id="revision-1",
        snapshot_hash=HASH,
        format=export_format,
        media_type=media_type,
        byte_length=12,
        sha256=HASH,
        draft_preview=False,
        created_at=TIMESTAMP,
    )
    assert manifest.format == export_format
    with pytest.raises(FmeaDomainError, match="media_type"):
        replace(manifest, media_type="application/octet-stream")
    with pytest.raises(FmeaDomainError, match="published"):
        replace(manifest, publication_id=None)


def test_preview_artifact_has_no_publication_and_rejects_bad_filename_size_hash_or_timestamp() -> None:
    with pytest.raises(FmeaDomainError, match="publication"):
        ExportArtifactManifest(
            artifact_id="artifact-1",
            export_run_id="run-1",
            publication_id="publication-1",
            revision_id="revision-1",
            snapshot_hash=HASH,
            format="json",
            media_type="application/json",
            byte_length=0,
            sha256=HASH,
            draft_preview=True,
            created_at=TIMESTAMP,
        )
    valid = ExportArtifactManifest(
        artifact_id="artifact-1",
        export_run_id="run-1",
        publication_id=None,
        revision_id="revision-1",
        snapshot_hash=HASH,
        format="json",
        media_type="application/json",
        byte_length=0,
        sha256=HASH,
        draft_preview=True,
        created_at=TIMESTAMP,
        filename="preview.json",
    )
    with pytest.raises(FmeaDomainError, match="filename"):
        replace(valid, filename="../preview.json")
    with pytest.raises(FmeaDomainError, match="byte_length"):
        replace(valid, byte_length=-1)
    with pytest.raises(FmeaDomainError, match="SHA-256"):
        replace(valid, sha256="A" * 64)
    with pytest.raises(FmeaDomainError, match="timestamp"):
        replace(valid, created_at="2026-08-27T12:00:00")
