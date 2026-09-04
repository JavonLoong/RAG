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
from fmea_application import ExportArtifactManifest, ExportFormat, ExportRun, bind_export_artifact
from fmea_application.delivery_contracts import validate_export_binding

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
        "target_template_id": "template-1",
        "target_template_version": "1.0.0",
        "target_template_hash": HASH,
        "domain_pack_id": "generic-domain",
        "domain_pack_version": "1.0.0",
        "domain_pack_hash": HASH,
        "evidence_pack_id": "evidence-pack-1",
        "evidence_pack_hash": HASH,
        "run_id": "run-1",
        "trace_id": "trace-1",
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


def _run(**overrides: object) -> ExportRun:
    values: dict[str, object] = {
        "export_run_id": "run-1",
        "workspace_id": "ws-1",
        "revision_id": "revision-1",
        "snapshot_hash": HASH,
        "publication_id": "publication-1",
        "format": ExportFormat.JSON,
        "draft_preview": False,
        "status": "succeeded",
        "created_at": TIMESTAMP,
        "snapshot_id": "snapshot-1",
        "filename": "report.json",
        "artifact_id": "artifact-1",
        "started_at": TIMESTAMP,
        "finished_at": "2026-08-27T12:01:00Z",
    }
    values.update(overrides)
    return ExportRun(**values)


def _manifest(**overrides: object) -> ExportArtifactManifest:
    values: dict[str, object] = {
        "artifact_id": "artifact-1",
        "export_run_id": "run-1",
        "publication_id": "publication-1",
        "revision_id": "revision-1",
        "snapshot_hash": HASH,
        "format": ExportFormat.JSON,
        "media_type": "application/json",
        "byte_length": 12,
        "sha256": HASH,
        "draft_preview": False,
        "created_at": TIMESTAMP,
        "snapshot_id": "snapshot-1",
        "filename": "report.json",
    }
    values.update(overrides)
    return ExportArtifactManifest(**values)


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


def test_template_patch_candidate_records_exact_target_and_provenance() -> None:
    candidate = _patch()
    assert candidate.target_template_id == "template-1"
    assert candidate.target_template_version == "1.0.0"
    assert candidate.target_template_hash == HASH
    assert candidate.domain_pack_id == "generic-domain"
    assert candidate.domain_pack_version == "1.0.0"
    assert candidate.domain_pack_hash == HASH
    assert candidate.evidence_pack_id == "evidence-pack-1"
    assert candidate.evidence_pack_hash == HASH
    assert candidate.run_id == "run-1"
    assert candidate.trace_id == "trace-1"


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("target_template_id", ""),
        ("target_template_version", "not-semver"),
        ("target_template_hash", "b" * 63),
        ("domain_pack_id", "bad id"),
        ("domain_pack_version", "not-semver"),
        ("domain_pack_hash", "b" * 63),
        ("evidence_pack_id", ""),
        ("evidence_pack_hash", "b" * 63),
        ("run_id", ""),
        ("trace_id", ""),
    ),
)
def test_template_patch_candidate_rejects_perturbed_provenance(
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(FmeaDomainError, match=field_name.split("_")[0]):
        _patch(**{field_name: value})


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


def test_compatibility_report_hash_detects_semantic_change_but_excludes_timestamp() -> None:
    report = CompatibilityReport(
        source=("generic-domain", "1.0.0"),
        target=("generic-domain", "2.0.0"),
        compatible=True,
        blocking_reasons=(),
        warnings=("stable",),
        checked_at=TIMESTAMP,
    )
    assert replace(report, warnings=("changed",), report_hash=None).report_hash != report.report_hash
    assert replace(report, checked_at="2026-08-27T12:01:00Z", report_hash=None).report_hash == report.report_hash


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


def test_migration_plan_rejects_equal_endpoints_and_cycles() -> None:
    with pytest.raises(FmeaDomainError, match="differ"):
        _plan(
            source=("generic-domain", "1.0.0"),
            target=("generic-domain", "1.0.0"),
            steps=(_edge("1.0.0", "2.0.0"), _edge("2.0.0", "1.0.0")),
        )
    with pytest.raises(FmeaDomainError, match="repeated|cycle"):
        _plan(
            target=("generic-domain", "4.0.0"),
            steps=(
                _edge("1.0.0", "2.0.0"),
                _edge("2.0.0", "3.0.0"),
                _edge("3.0.0", "2.0.0"),
                _edge("2.0.0", "4.0.0"),
            ),
        )


def test_migration_plan_rejects_duplicate_edge_identity() -> None:
    with pytest.raises(FmeaDomainError, match="duplicate edges"):
        _plan(
            target=("generic-domain", "5.0.0"),
            steps=(
                _edge("1.0.0", "2.0.0"),
                _edge("2.0.0", "3.0.0"),
                _edge("3.0.0", "4.0.0"),
                _edge("4.0.0", "3.0.0"),
                _edge("3.0.0", "4.0.0"),
                _edge("4.0.0", "5.0.0"),
            ),
        )


def test_migration_report_is_immutable_and_requires_matching_plan_endpoints() -> None:
    plan = _plan()
    report = MigrationReport(
        migration_id="migration-1",
        plan=plan,
        source_revision_id="revision-1",
        source_revision_hash=HASH,
        source_domain_pack_identity=(*plan.source, HASH),
        target_domain_pack_identity=(*plan.target, "b" * 64),
        target_revision_hash="c" * 64,
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
    with pytest.raises(FmeaDomainError, match="identity|endpoints|plan"):
        replace(report, target_domain_pack_identity=("other-domain", "3.0.0", "b" * 64), report_hash=None)


def test_migration_report_hash_detects_semantic_change_but_excludes_timestamp() -> None:
    report = MigrationReport(
        migration_id="migration-1",
        plan=_plan(),
        source_revision_id="revision-1",
        source_revision_hash=HASH,
        source_domain_pack_identity=(*_plan().source, HASH),
        target_domain_pack_identity=(*_plan().target, "b" * 64),
        target_revision_hash="c" * 64,
        status="dry_run",
        mapped_fields=("failure_mode",),
        dropped_fields=(),
        unresolved_fields=("legacy_field",),
        warnings=(),
        created_at=TIMESTAMP,
    )
    assert replace(report, warnings=("changed",), report_hash=None).report_hash != report.report_hash
    assert replace(report, target_revision_hash="d" * 64, report_hash=None).report_hash != report.report_hash
    assert replace(report, created_at="2026-08-27T12:01:00Z", report_hash=None).report_hash == report.report_hash


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
    ("field_name", "value"),
    (
        ("started_at", None),
        ("finished_at", None),
        ("artifact_id", None),
        ("error", "failed"),
    ),
)
def test_export_run_completed_lifecycle_requires_coherent_terminal_fields(field_name: str, value: object) -> None:
    with pytest.raises(FmeaDomainError, match="lifecycle|completed|succeeded"):
        _run(**{field_name: value})


def test_export_run_lifecycle_accepts_pending_running_completed_and_failed_shapes() -> None:
    pending = _run(status="queued", started_at=None, finished_at=None, artifact_id=None, filename=None)
    running = _run(status="running", started_at=TIMESTAMP, finished_at=None, artifact_id=None, filename=None)
    completed = _run(status="succeeded")
    failed = _run(
        status="failed",
        finished_at="2026-08-27T12:01:00Z",
        artifact_id=None,
        filename=None,
        error="export generation failed",
    )
    assert (pending.status, running.status, completed.status, failed.status) == (
        "queued",
        "running",
        "succeeded",
        "failed",
    )


def test_export_run_lifecycle_accepts_cancelling_and_cancelled_shapes() -> None:
    cancelling = _run(status="cancelling", finished_at=None, artifact_id=None, filename=None, error=None)
    cancelled = _run(
        status="cancelled",
        finished_at="2026-08-27T12:01:00Z",
        artifact_id=None,
        filename=None,
        error=None,
    )
    assert (cancelling.status, cancelled.status) == ("cancelling", "cancelled")


def test_export_run_rejects_unsupported_status_and_impossible_timestamps() -> None:
    with pytest.raises(FmeaDomainError, match="status|lifecycle"):
        _run(status="unknown", started_at=None, finished_at=None, artifact_id=None, filename=None)
    with pytest.raises(FmeaDomainError, match="finished_at"):
        _run(started_at="2026-08-27T12:01:00Z", finished_at=TIMESTAMP)
    with pytest.raises(FmeaDomainError, match="lifecycle|started_at"):
        _run(status="failed", started_at=None, finished_at="2026-08-27T12:01:00Z", error="failed", artifact_id=None)
    with pytest.raises(FmeaDomainError, match="created_at"):
        _run(created_at="2026-08-27T12:01:00Z")


@pytest.mark.parametrize(
    ("status", "overrides"),
    (
        ("cancelling", {"started_at": None}),
        ("cancelling", {"finished_at": "2026-08-27T12:01:00Z"}),
        ("cancelling", {"artifact_id": "artifact-1"}),
        ("cancelling", {"error": "cancelled"}),
        ("cancelled", {"started_at": None}),
        ("cancelled", {"finished_at": None}),
        ("cancelled", {"artifact_id": "artifact-1"}),
        ("cancelled", {"error": "cancelled"}),
    ),
)
def test_export_run_rejects_cancellation_lifecycle_perturbations(
    status: str,
    overrides: dict[str, object],
) -> None:
    with pytest.raises(FmeaDomainError, match="lifecycle|cancelling|cancelled"):
        _run(status=status, **overrides)


@pytest.mark.parametrize(
    ("status", "overrides"),
    (
        ("queued", {"started_at": TIMESTAMP}),
        ("queued", {"finished_at": TIMESTAMP}),
        ("queued", {"artifact_id": "artifact-1"}),
        ("running", {"started_at": None}),
        ("running", {"finished_at": TIMESTAMP}),
        ("running", {"error": "unexpected"}),
        ("succeeded", {"finished_at": None}),
        ("failed", {"finished_at": None, "error": "failed"}),
        ("failed", {"error": None}),
        ("failed", {"artifact_id": "artifact-1"}),
    ),
)
def test_export_run_rejects_lifecycle_perturbations(status: str, overrides: dict[str, object]) -> None:
    with pytest.raises(FmeaDomainError, match="lifecycle|pending|running|completed|failed"):
        _run(status=status, **overrides)


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


@pytest.mark.parametrize(
    "filename",
    (
        "CON.xlsx",
        "nul.docx",
        "CON.backup.xlsx",
        "NUL.tar.json",
        "CON .xlsx",
        "bad\x01.xlsx",
        "trailing.xlsx ",
        "trailing.xlsx.",
    ),
)
def test_filename_policy_rejects_windows_unsafe_names_in_draft_and_delivery(filename: str) -> None:
    with pytest.raises(FmeaDomainError, match="filename"):
        _draft(source_filename=filename)
    with pytest.raises(FmeaDomainError, match="filename"):
        _manifest(filename=filename)


def test_filename_policy_retains_valid_multi_dot_names() -> None:
    assert _draft(source_filename="report.v1.xlsx").source_filename == "report.v1.xlsx"
    assert _manifest(filename="report.v1.json").filename == "report.v1.json"


@pytest.mark.parametrize(
    ("source_type", "filename"),
    (("xlsx", "source.docx"), ("docx", "source.xlsx"), ("xlsx", "source")),
)
def test_template_draft_requires_source_type_matching_filename_extension(source_type: str, filename: str) -> None:
    with pytest.raises(FmeaDomainError, match="source_type|extension"):
        _draft(source_type=source_type, source_filename=filename)


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("export_run_id", "other-run"),
        ("revision_id", "other-revision"),
        ("snapshot_id", "other-snapshot"),
        ("snapshot_hash", "b" * 64),
        ("publication_id", "other-publication"),
        ("draft_preview", True),
        ("format", ExportFormat.XLSX),
        ("filename", "other.json"),
        ("artifact_id", "other-artifact"),
    ),
)
def test_export_binding_rejects_every_shared_identity_and_artifact_perturbation(
    field_name: str,
    value: object,
) -> None:
    manifest_overrides: dict[str, object] = {field_name: value}
    if field_name == "format":
        manifest_overrides["media_type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        manifest_overrides["filename"] = "report.xlsx"
    if field_name == "draft_preview":
        manifest_overrides["publication_id"] = None
    with pytest.raises(FmeaDomainError, match="binding|mismatch"):
        validate_export_binding(_run(), _manifest(**manifest_overrides))


def test_export_binding_requires_completed_run_and_returns_immutable_manifest() -> None:
    bound = bind_export_artifact(_run(), _manifest())
    assert bound == _manifest()
    with pytest.raises(FmeaDomainError, match="binding|completed"):
        bind_export_artifact(_run(status="running", finished_at=None, artifact_id=None, filename=None), _manifest())


def test_application_package_reexports_delivery_contracts() -> None:
    from fmea_application import ExportArtifactManifest as RootManifest
    from fmea_application import ExportFormat as RootFormat
    from fmea_application import ExportRun as RootRun

    assert (RootRun, RootManifest, RootFormat) == (ExportRun, ExportArtifactManifest, ExportFormat)
