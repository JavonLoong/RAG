# FMEA Migration and Delivery Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete reusable DomainPack/template migration, canonical JSON/XLSX/DOCX export, thin browser workbench, multi-domain proof, and bounded scale acceptance.

**Architecture:** Imports create immutable-source `TemplateDraft` objects and model-generated patch candidates; only a human template administrator compiles/registers a new version. Explicit migration plans create child FMEA revisions through dry-run and confirmation. Every export adapter reads one `NormalizedFmeaSnapshot`; the browser workbench is a native ES-module REST client and never reads SQLite.

**Tech Stack:** Python 3.11+, frozen dataclasses, Protocol, Pydantic 2.13, FastAPI, SQLite, orjson, PyYAML, jsonschema, openpyxl 3.1.5+, python-docx 1.2+, native HTML/CSS/ES Modules, Playwright 1.50+, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-08-27-full-fmea-modular-product-design.md`

## Global Constraints

- Risk, propagation, and governance phases are complete; published revisions and normalized snapshots are immutable.
- DomainPack/template import, migration, and export never mutate a published revision in place.
- Imported Excel/Word content creates a draft only; model patches remain immutable suggestions until human acceptance.
- Templates, rule packs, mappings, and migrations are contained, hash-bound, versioned, allowlisted, and non-executable by default.
- JSON is canonical; XLSX and DOCX are presentation adapters over the exact same snapshot identity.
- Draft previews are visibly marked and cannot be confused with published artifacts.
- Export generation uses contained temporary directories, verifies artifacts, then atomically publishes them.
- The browser workbench calls REST only, uses pagination/cursors, and never imports repository/database code.
- At least fuel/combustion, electrical, and software demonstration DomainPacks prove generic-kernel reuse.
- Synthetic 10,000-row export proves bounded streaming/pagination contracts, not industrial certification.
- Default tests incur no external-model cost and do not require a browser except the explicit Playwright gate.

## File map

- `core_domain/fmea/template_migration.py`: template draft, patch, compatibility, and migration contracts.
- `fmea_application/domain_pack_service.py`: pack/template lifecycle and human patch decisions.
- `fmea_application/migration_service.py`: compatibility, dry-run, confirm, and child-revision migration.
- `fmea_application/export_service.py`: snapshot query, export run, artifact manifest, and verification orchestration.
- `fmea_application/ports.py`: importer, migration adapter, artifact store, and exporter ports.
- `fmea_infrastructure/template_import_excel.py`: safe XLSX structure extraction.
- `fmea_infrastructure/template_import_docx.py`: safe DOCX table/paragraph extraction.
- `fmea_infrastructure/template_patch_generator.py`: model-assisted mapping diff.
- `fmea_infrastructure/migration_registry.py`: explicit allowlisted migration graph.
- `fmea_infrastructure/export_json.py`: canonical JSON adapter.
- `fmea_infrastructure/export_narrative_generator.py`: bounded export-narrative assistance adapter.
- `fmea_infrastructure/export_xlsx.py`: XLSX adapter.
- `fmea_infrastructure/export_docx.py`: DOCX adapter.
- `fmea_infrastructure/artifact_store.py`: contained atomic artifact publication.
- `fmea_infrastructure/delivery_repository_sqlite.py`: draft/patch/migration/export-run persistence.
- `fmea_infrastructure/migrations/010_fmea_migration_delivery.sql`: additive delivery schema after the completed governance migration sequence `005`-`009`.
- `domain_packs/electrical-demo/` and `domain_packs/software-demo/`: structurally distinct demonstration packs.
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_delivery_contracts.py`: REST schemas.
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_delivery_v1.py`: DomainPack, migration, and export routes.
- `scripts/fmea_skill.py`: `domain-pack`, `migration`, and `export` CLI groups.
- `skills/graphrag-fmea/SKILL.md`: safe full-product Codex Skill wrapper over the JSON CLI.
- `frontend_app/current_console/fmea.html`: independent workbench entry.
- `frontend_app/current_console/fmea/`: native ES modules, styles, and view components.
- `scripts/run_fmea_full_acceptance.py` and `scripts/verify_fmea_full_acceptance.py`: final independent acceptance.

---

### Task 1: Freeze template draft, patch, compatibility, and migration contracts

**Files:**
- Create: `core_domain/fmea/template_migration.py`
- Modify: `core_domain/fmea/__init__.py`
- Create: `fmea_application/delivery_contracts.py`
- Test: `tests/unit/test_fmea_template_migration_contracts.py`

**Interfaces:**
- Consumes: `DomainPackManifest`, compiled template identity, and immutable revision contracts.
- Produces: `TemplateDraft`, `TemplatePatchCandidate`, `CompatibilityReport`, `MigrationPlan`, `MigrationReport`, `ExportRun`, and `ExportArtifactManifest`.

- [ ] **Step 1: Write strict contract tests**

```python
def test_template_draft_preserves_unknown_and_ambiguous_fields():
    draft = template_draft(unknown_fields=("Legacy Criticality",), ambiguous_fields=("Cause",))
    assert draft.status == "draft"
    assert draft.unknown_fields == ("Legacy Criticality",)
    assert draft.ambiguous_fields == ("Cause",)


def test_migration_plan_rejects_missing_explicit_version_edge():
    with pytest.raises(FmeaDomainError, match="migration path is not explicit"):
        MigrationPlan(source=("fuel-combustion", "1.0.0"), target=("fuel-combustion", "3.0.0"), steps=())
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_template_migration_contracts.py -q`

Expected: FAIL because migration/delivery contracts are absent.

- [ ] **Step 3: Implement immutable, bounded contracts**

```python
@dataclass(frozen=True, slots=True)
class TemplateDraft:
    draft_id: str
    workspace_id: str
    source_filename: str
    source_sha256: str
    source_type: str
    structure: tuple[SourceStructureItem, ...]
    proposed_fields: tuple[ProposedFieldMapping, ...]
    unknown_fields: tuple[str, ...]
    ambiguous_fields: tuple[str, ...]
    parser_warnings: tuple[str, ...]
    status: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ExportArtifactManifest:
    artifact_id: str
    export_run_id: str
    publication_id: str | None
    revision_id: str
    snapshot_hash: str
    format: str
    media_type: str
    byte_length: int
    sha256: str
    draft_preview: bool
    created_at: str
```

Validate canonical SHA-256, finite sizes, bounded strings/collections, exact enums, unique mapping keys, explicit migration edge continuity, and published-versus-preview identity rules.

- [ ] **Step 4: Run contract and snapshot tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_template_migration_contracts.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_domain_pack.py -q`

Expected: PASS.

- [ ] **Step 5: Commit delivery contracts**

```powershell
git add core_domain/fmea/template_migration.py core_domain/fmea/__init__.py fmea_application/delivery_contracts.py tests/unit/test_fmea_template_migration_contracts.py
git commit -m "feat(fmea): define migration and delivery contracts"
```

### Task 2: Import Excel/Word templates and review model patch candidates

**Files:**
- Modify: `pyproject.toml`
- Create: `fmea_infrastructure/template_import_excel.py`
- Create: `fmea_infrastructure/template_import_docx.py`
- Create: `fmea_infrastructure/template_patch_generator.py`
- Create: `fmea_application/domain_pack_service.py`
- Modify: `fmea_application/ports.py`
- Test: `tests/unit/test_fmea_template_import_excel.py`
- Test: `tests/unit/test_fmea_template_import_docx.py`
- Test: `tests/unit/test_fmea_template_patch_generator.py`
- Test: `tests/integration/test_fmea_template_draft_lifecycle.py`

**Interfaces:**
- Consumes: Task 1 draft/patch contracts and existing `TemplateCompiler`/file registry.
- Produces: safe import ports, immutable patch suggestions, human accept/reject, compile/register lifecycle.

- [ ] **Step 1: Write malicious-file and human-authority tests**

```python
def test_excel_import_preserves_cells_merges_unknown_and_ambiguous_headers():
    draft = ExcelTemplateImporter().parse(FMEA_XLSX_BYTES, "fmea.xlsx", workspace_id="ws-1")
    assert SourceStructureItem(kind="merge", locator="Sheet1!A3:B3") in draft.structure
    assert "Legacy Criticality" in draft.unknown_fields
    assert "Cause" in draft.ambiguous_fields


def test_model_patch_cannot_register_template(service, model_actor):
    suggestion = service.suggest_patch(suggest_patch_command(), model_actor)
    patch = suggestion.payload
    assert suggestion.applied is False
    assert patch.status == "suggested"
    with pytest.raises(ReviewError, match="FMEA_TEMPLATE_ADMIN_REQUIRED"):
        service.accept_patch(accept_patch_command(suggestion.suggestion_id, patch.patch_id), model_actor)
```

- [ ] **Step 2: Add dependencies and run tests to confirm RED**

Add exact dependency: `openpyxl>=3.1.5,<4`.

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_template_import_excel.py tests/unit/test_fmea_template_import_docx.py tests/unit/test_fmea_template_patch_generator.py tests/integration/test_fmea_template_draft_lifecycle.py -q`

Expected: FAIL because importers and service are absent.

- [ ] **Step 3: Implement safe import and patch lifecycle**

```python
class TemplateImporter(Protocol):
    def parse(self, raw_bytes: bytes, filename: str, *, workspace_id: str) -> TemplateDraft: ...


class TemplatePatchGenerator(Protocol):
    def suggest(self, request: TemplatePatchRequest) -> AssistanceSuggestion[TemplatePatchCandidate]: ...


class DomainPackService:
    def import_template(self, command: ImportTemplateCommand, actor: ActorContext) -> TemplateDraft: ...
    def suggest_patch(
        self, command: SuggestTemplatePatchCommand, actor: ActorContext
    ) -> AssistanceSuggestion[TemplatePatchCandidate]: ...
    def accept_patch(self, command: AcceptTemplatePatchCommand, actor: ActorContext) -> CompiledTemplate: ...
    def reject_patch(self, command: RejectTemplatePatchCommand, actor: ActorContext) -> TemplatePatchCandidate: ...
```

XLSX import rejects macros, external links, malformed ZIPs, formulas requiring execution, excessive sheets/cells, and path escapes. DOCX import reads paragraphs/tables/relationships without executing fields, macros, or external links. Preserve source bytes hash and structural addresses. Model output is an `AssistanceSuggestion[TemplatePatchCandidate]` containing a bounded mapping diff; reuse Flash generation plus `deepseek-v4-pro` criticism through the provider-neutral pipeline. Only human `template_admin` acceptance invokes the existing compiler and immutable registry.

- [ ] **Step 4: Run import, registry, and security tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_template_import_excel.py tests/unit/test_fmea_template_import_docx.py tests/unit/test_fmea_template_patch_generator.py tests/integration/test_fmea_template_draft_lifecycle.py tests/integration/test_output_template_skill_cli.py tests/unit/test_structured_output_file_registry.py -q`

Expected: PASS.

- [ ] **Step 5: Commit import and patch workflow**

```powershell
git add pyproject.toml fmea_infrastructure/template_import_excel.py fmea_infrastructure/template_import_docx.py fmea_infrastructure/template_patch_generator.py fmea_application/domain_pack_service.py fmea_application/ports.py tests/unit/test_fmea_template_import_excel.py tests/unit/test_fmea_template_import_docx.py tests/unit/test_fmea_template_patch_generator.py tests/integration/test_fmea_template_draft_lifecycle.py
git commit -m "feat(fmea): import and review template drafts"
```

### Task 3: Persist delivery state and execute explicit dry-run migrations

**Files:**
- Create: `fmea_infrastructure/migrations/010_fmea_migration_delivery.sql`
- Create: `fmea_infrastructure/delivery_repository_sqlite.py`
- Create: `fmea_infrastructure/migration_registry.py`
- Create: `fmea_application/migration_service.py`
- Modify: `fmea_application/ports.py`
- Modify: `fmea_infrastructure/composition.py`
- Test: `tests/integration/test_fmea_delivery_sqlite.py`
- Test: `tests/unit/test_fmea_migration_service.py`
- Test: `tests/regression/test_fmea_migration_rollback.py`

**Interfaces:**
- Consumes: immutable source revisions, DomainPack registry, explicit migration adapters, governance assembler.
- Produces: dry-run reports and human-confirmed child revisions.

- [ ] **Step 1: Write dry-run, rollback, and no-in-place-mutation tests**

```python
def test_dry_run_is_repeatable_and_does_not_create_revision(service):
    first = service.dry_run(migration_command(), template_admin())
    second = service.dry_run(migration_command(), template_admin())
    assert first.report_hash == second.report_hash
    assert repository.count_child_revisions() == 0


def test_failed_confirmed_migration_rolls_back_child_and_events(service, faulting_adapter):
    with pytest.raises(ReviewError, match="FMEA_MIGRATION_FAILED"):
        service.confirm(confirm_migration_command(), template_admin())
    assert repository.count_child_revisions() == 0
    assert repository.count_outbox_events("migration.completed") == 0
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_delivery_sqlite.py tests/unit/test_fmea_migration_service.py tests/regression/test_fmea_migration_rollback.py -q`

Expected: FAIL because migration `010`, registry, repository, and service are absent.

- [ ] **Step 3: Implement explicit migration graph and atomic child creation**

```python
class MigrationAdapter(Protocol):
    source_identity: tuple[str, str]
    target_identity: tuple[str, str]
    def migrate(self, source: FmeaRevision) -> MigrationCandidate: ...


class MigrationService:
    def compatibility(self, command: CompatibilityCommand, actor: ActorContext) -> CompatibilityReport: ...
    def dry_run(self, command: MigrationCommand, actor: ActorContext) -> MigrationReport: ...
    def confirm(self, command: ConfirmMigrationCommand, actor: ActorContext) -> MigrationResult: ...
```

Migration `010` creates template drafts, patch candidates/decisions, migration runs/reports/confirmations, export runs/artifacts, and required indexes/triggers. It is strictly additive after migrations `005`-`009` and must not rewrite their bytes or historical behavior. The service resolves an exact allowlisted edge sequence, checks source hash, runs deterministic transformations, validates target template/DomainPack, reports every mapped/dropped/unresolved field, and on human confirmation creates child rows/revision with risk and propagation statuses `invalidated`.

- [ ] **Step 4: Run migration, governance, and registry tests**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_delivery_sqlite.py tests/unit/test_fmea_migration_service.py tests/regression/test_fmea_migration_rollback.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_template_draft_lifecycle.py -q`

Expected: PASS.

- [ ] **Step 5: Commit migration workflow**

```powershell
git add fmea_infrastructure/migrations/010_fmea_migration_delivery.sql fmea_infrastructure/delivery_repository_sqlite.py fmea_infrastructure/migration_registry.py fmea_application/migration_service.py fmea_application/ports.py fmea_infrastructure/composition.py tests/integration/test_fmea_delivery_sqlite.py tests/unit/test_fmea_migration_service.py tests/regression/test_fmea_migration_rollback.py
git commit -m "feat(fmea): migrate domain packs through child revisions"
```

### Task 4: Implement canonical JSON and verified artifact storage

**Files:**
- Create: `fmea_application/export_service.py`
- Create: `fmea_infrastructure/export_json.py`
- Create: `fmea_infrastructure/export_narrative_generator.py`
- Create: `fmea_infrastructure/artifact_store.py`
- Modify: `fmea_application/ports.py`
- Modify: `fmea_infrastructure/composition.py`
- Test: `tests/unit/test_fmea_export_json.py`
- Test: `tests/unit/test_fmea_export_narrative.py`
- Test: `tests/unit/test_fmea_artifact_store.py`
- Test: `tests/integration/test_fmea_export_runs.py`

**Interfaces:**
- Consumes: immutable `NormalizedFmeaSnapshot` and delivery repository.
- Produces: canonical JSON export run, immutable export-narrative suggestions, and atomically published artifact manifest.

- [ ] **Step 1: Write canonical identity and partial-artifact tests**

```python
def test_json_export_hash_is_stable_for_same_snapshot():
    first = CanonicalJsonExporter().render(snapshot())
    second = CanonicalJsonExporter().render(snapshot())
    assert first == second
    assert sha256(first).hexdigest() == expected_json_sha256()


def test_latest_never_observes_partial_artifact(store, fault_after_write):
    with pytest.raises(ArtifactStoreError):
        store.publish(fault_after_write)
    assert store.latest("export-run-1") is None


def test_model_narrative_is_unapplied_and_cannot_mutate_published_snapshot(service):
    published = snapshot()
    suggestion = service.suggest_narrative(published, model_actor())
    assert suggestion.kind is AssistanceKind.EXPORT_NARRATIVE_DRAFT
    assert suggestion.applied is False
    assert snapshot_repository().get(published.revision_id) == published
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_export_json.py tests/unit/test_fmea_export_narrative.py tests/unit/test_fmea_artifact_store.py tests/integration/test_fmea_export_runs.py -q`

Expected: FAIL because export service and adapters are absent.

- [ ] **Step 3: Implement canonical exporter and contained atomic store**

```python
class SnapshotExporter(Protocol):
    format: str
    media_type: str
    def render(self, snapshot: NormalizedFmeaSnapshot) -> bytes: ...


class ArtifactStore(Protocol):
    def publish(self, run_id: str, filename: str, payload: bytes, manifest: ExportArtifactManifest) -> Path: ...
    def get(self, artifact_id: str, workspace_id: str) -> ExportArtifact: ...


class ExportService:
    def start(self, command: StartExportCommand, actor: ActorContext) -> ExportRun: ...
    def suggest_narrative(
        self, snapshot: NormalizedFmeaSnapshot, actor: ActorContext
    ) -> AssistanceSuggestion[ExportNarrativeDraft]: ...
    def get_run(self, run_id: str, actor: ActorContext) -> ExportRun: ...
    def get_artifact(self, artifact_id: str, actor: ActorContext) -> ExportArtifact: ...
```

Canonical JSON uses sorted keys, finite values, UTF-8, one newline, and schema `graphrag.fmea.export.v1`. Narrative generation receives a bounded snapshot projection and returns the shared `AssistanceSuggestion` envelope through Flash generation plus `deepseek-v4-pro` criticism; adopting or editing it creates a new draft/child revision and never mutates a published snapshot. The store resolves only server-owned filenames under a workspace artifact root, writes and fsyncs a sibling temporary directory, verifies byte length/hash/manifest, atomically renames, and only then completes the export run.

- [ ] **Step 4: Run JSON, store, snapshot, and governance tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_export_json.py tests/unit/test_fmea_export_narrative.py tests/unit/test_fmea_artifact_store.py tests/integration/test_fmea_export_runs.py tests/unit/test_fmea_snapshot_contracts.py tests/integration/test_fmea_governance_lifecycle.py -q`

Expected: PASS.

- [ ] **Step 5: Commit canonical export boundary**

```powershell
git add fmea_application/export_service.py fmea_infrastructure/export_json.py fmea_infrastructure/export_narrative_generator.py fmea_infrastructure/artifact_store.py fmea_application/ports.py fmea_infrastructure/composition.py tests/unit/test_fmea_export_json.py tests/unit/test_fmea_export_narrative.py tests/unit/test_fmea_artifact_store.py tests/integration/test_fmea_export_runs.py
git commit -m "feat(fmea): export canonical snapshots atomically"
```

### Task 5: Add XLSX and DOCX adapters with cross-format consistency

**Files:**
- Create: `fmea_infrastructure/export_xlsx.py`
- Create: `fmea_infrastructure/export_docx.py`
- Test: `tests/unit/test_fmea_export_xlsx.py`
- Test: `tests/unit/test_fmea_export_docx.py`
- Test: `tests/integration/test_fmea_export_consistency.py`

**Interfaces:**
- Consumes: `SnapshotExporter` and `NormalizedFmeaSnapshot`.
- Produces: verified XLSX and DOCX bytes with the same semantic identity as canonical JSON.

- [ ] **Step 1: Write cross-format semantic comparison tests**

```python
def test_json_xlsx_docx_share_revision_snapshot_rows_and_evidence():
    snap = snapshot()
    json_view = parse_json_export(CanonicalJsonExporter().render(snap))
    xlsx_view = parse_xlsx_export(XlsxFmeaExporter().render(snap))
    docx_view = parse_docx_export(DocxFmeaExporter().render(snap))
    assert semantic_projection(json_view) == semantic_projection(xlsx_view) == semantic_projection(docx_view)


def test_draft_preview_has_visible_marker_in_every_format():
    snap = preview_snapshot()
    assert all(view.preview_marker == "DRAFT PREVIEW — NOT PUBLISHED" for view in render_and_parse_all(snap))
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_export_xlsx.py tests/unit/test_fmea_export_docx.py tests/integration/test_fmea_export_consistency.py -q`

Expected: FAIL because office adapters are absent.

- [ ] **Step 3: Implement presentation-only adapters**

XLSX creates sheets `Manifest`, `FMEA`, `Risk`, `Propagation`, `Evidence`, `Decisions`, and `Unresolved`; freezes headers, applies bounded widths, writes text values without formula interpretation, and stores revision/snapshot hashes in `Manifest`. DOCX creates title/manifest, FMEA tables, risk and propagation sections, evidence references, decisions, unresolved items, and footer identity. Sanitize control characters and formula-leading Excel strings. Neither adapter queries repositories or changes semantic values.

- [ ] **Step 4: Run office and canonical export tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_export_json.py tests/unit/test_fmea_export_xlsx.py tests/unit/test_fmea_export_docx.py tests/integration/test_fmea_export_consistency.py -q`

Expected: PASS.

- [ ] **Step 5: Commit office exports**

```powershell
git add fmea_infrastructure/export_xlsx.py fmea_infrastructure/export_docx.py tests/unit/test_fmea_export_xlsx.py tests/unit/test_fmea_export_docx.py tests/integration/test_fmea_export_consistency.py
git commit -m "feat(fmea): export consistent xlsx and docx"
```

### Task 6: Publish DomainPack, migration, and export REST/CLI contracts

**Files:**
- Create: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_delivery_contracts.py`
- Create: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_delivery_v1.py`
- Create: `skills/graphrag-fmea/SKILL.md`
- Modify: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py`
- Modify: `scripts/fmea_skill.py`
- Modify: `fmea_infrastructure/local_auth.py`
- Test: `tests/unit/test_fmea_delivery_api_contracts.py`
- Test: `tests/unit/test_fmea_codex_skill.py`
- Test: `tests/integration/test_fmea_delivery_api_v1.py`
- Test: `tests/integration/test_fmea_delivery_cli.py`

**Interfaces:**
- Consumes: DomainPack, migration, export, and export-narrative assistance services.
- Produces: matching REST/CLI operations and a safe Codex Skill wrapper with template-admin and export permissions while keeping narrative suggestions non-authoritative.

- [ ] **Step 1: Write authority, artifact, and parity tests**

```python
def test_template_patch_accept_requires_template_admin(client_without_template_admin):
    response = client_without_template_admin.post(
        "/api/v1/fmea/template-patches/patch-1/acceptance",
        headers={"If-Match": '"1"', "Idempotency-Key": UUID1},
        json={"confirm_template_change": True},
    )
    assert response.status_code == 403


def test_export_artifact_bytes_match_manifest(client):
    artifact = download_completed_export(client)
    assert len(artifact.body) == artifact.manifest["byte_length"]
    assert sha256(artifact.body).hexdigest() == artifact.manifest["sha256"]


def test_export_narrative_suggestion_is_never_published_automatically(client):
    response = client.post("/api/v1/fmea/revisions/rev-1/export-narrative-runs", json={})
    assert response.status_code == 202
    assert response.json()["data"]["applied"] is False
    assert response.json()["data"]["target_type"] == "fmea_revision"


def test_codex_skill_is_cli_only_read_only_by_default_and_requires_confirmation():
    text = Path("skills/graphrag-fmea/SKILL.md").read_text(encoding="utf-8")
    assert "fmea_skill.py" in text
    assert "repository_sqlite" not in text
    assert "sqlite3" not in text
    assert "read-only by default" in text
    assert "--confirm-human-assistance-decision" in text
    assert "--confirm-publication" in text
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_delivery_api_contracts.py tests/unit/test_fmea_codex_skill.py tests/integration/test_fmea_delivery_api_v1.py tests/integration/test_fmea_delivery_cli.py -q`

Expected: FAIL because delivery transports are absent.

- [ ] **Step 3: Implement strict routes and CLI**

REST resources:

```text
POST /api/v1/fmea/template-drafts
POST /api/v1/fmea/template-drafts/{draft_id}/patch-runs
GET  /api/v1/fmea/template-patches/{patch_id}
POST /api/v1/fmea/template-patches/{patch_id}/acceptance
POST /api/v1/fmea/template-patches/{patch_id}/rejection
POST /api/v1/fmea/revisions/{revision_id}/migration-dry-runs
POST /api/v1/fmea/migration-reports/{report_id}/confirmations
POST /api/v1/fmea/revisions/{revision_id}/export-runs
POST /api/v1/fmea/revisions/{revision_id}/export-narrative-runs
GET  /api/v1/fmea/export-runs/{run_id}
GET  /api/v1/fmea/export-artifacts/{artifact_id}
```

CLI groups `domain-pack`, `migration`, and `export` mirror the resources, including `export narrative-suggest`. File input is read as bounded bytes by CLI/server; clients cannot supply output paths, model IDs, provider URLs, migration adapters, or filenames. Add local roles `template_admin` and `exporter` while retaining separate explicit confirmations.

Use `superpowers:writing-skills` when implementing `skills/graphrag-fmea/SKILL.md`. The Skill invokes `scripts/fmea_skill.py` only, never imports repositories or reads SQLite, defaults to query/status/export-preview operations, explains all orthogonal states, preserves EvidencePack citations, and requires the exact human confirmation flag for assistance adoption, field review, risk confirmation, propagation review, approval, publication, withdrawal, template registration, or migration. It must not infer confirmation from conversational wording and must surface safe CLI errors unchanged.

- [ ] **Step 4: Run delivery and governance transport matrices**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_delivery_api_contracts.py tests/unit/test_fmea_codex_skill.py tests/integration/test_fmea_delivery_api_v1.py tests/integration/test_fmea_delivery_cli.py tests/integration/test_fmea_governance_api_v1.py tests/integration/test_fmea_governance_cli.py tests/unit/test_fmea_local_auth.py -q`

Expected: PASS.

- [ ] **Step 5: Commit delivery transports**

```powershell
git add api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_delivery_contracts.py api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_delivery_v1.py api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py scripts/fmea_skill.py skills/graphrag-fmea/SKILL.md fmea_infrastructure/local_auth.py tests/unit/test_fmea_delivery_api_contracts.py tests/unit/test_fmea_codex_skill.py tests/integration/test_fmea_delivery_api_v1.py tests/integration/test_fmea_delivery_cli.py tests/unit/test_fmea_local_auth.py
git commit -m "feat(fmea): expose migration and export interfaces"
```

### Task 7: Build the thin FMEA browser workbench

**Files:**
- Create: `frontend_app/current_console/fmea.html`
- Create: `frontend_app/current_console/fmea/styles.css`
- Create: `frontend_app/current_console/fmea/api-client.js`
- Create: `frontend_app/current_console/fmea/store.js`
- Create: `frontend_app/current_console/fmea/app.js`
- Create: `frontend_app/current_console/fmea/views/analysis.js`
- Create: `frontend_app/current_console/fmea/views/evidence.js`
- Create: `frontend_app/current_console/fmea/views/review.js`
- Create: `frontend_app/current_console/fmea/views/risk.js`
- Create: `frontend_app/current_console/fmea/views/propagation.js`
- Create: `frontend_app/current_console/fmea/views/governance.js`
- Create: `frontend_app/current_console/fmea/views/templates.js`
- Create: `frontend_app/current_console/fmea/views/exports.js`
- Modify: `pyproject.toml`
- Test: `tests/browser/test_fmea_workbench.py`
- Test: `tests/unit/test_fmea_frontend_contract.py`

**Interfaces:**
- Consumes: REST APIs only.
- Produces: accessible, paginated, event-driven workbench with explicit model/human/publication states.

- [ ] **Step 1: Add Playwright dependencies and failing main-chain tests**

Add dev dependencies: `playwright>=1.50,<2` and `pytest-playwright>=0.7,<1`.

```python
def test_workbench_main_chain(page, fmea_server):
    page.goto(f"{fmea_server}/static/fmea.html")
    page.get_by_role("link", name="证据").click()
    page.get_by_role("link", name="风险评分").click()
    page.get_by_role("button", name="确认评分").click()
    page.get_by_role("link", name="传播分析").click()
    page.get_by_role("link", name="批准发布").click()
    expect(page.get_by_text("模型建议不是人工结论")).to_be_visible()


def test_model_suggestion_never_uses_confirmed_state_class():
    source_root = Path("frontend_app/current_console/fmea")
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(source_root.rglob("*.js"))
    )
    assert 'data-authority="model-suggestion"' in source
    assert 'data-authority="human-confirmed"' in source
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_frontend_contract.py tests/browser/test_fmea_workbench.py -q`

Expected: FAIL because the workbench does not exist.

- [ ] **Step 3: Implement shell, state store, API client, and focused views**

`api-client.js` owns auth header, ETag capture, canonical idempotency key generation, cursor pagination, safe problem details, and cancellation. `store.js` owns selected analysis/revision, current resources, run states, and conflict refresh. Views render semantic data and dispatch commands; they never calculate risk, infer propagation, alter approval readiness, or access SQLite.

Provide keyboard navigation, visible focus, status text plus icons, responsive table/detail layout, evidence side panel, read-only propagation SVG, explicit draft/published banners, and confirmation dialogs naming the revision and action. Do not add a frontend framework or duplicate the existing general console.

- [ ] **Step 4: Run browser, API, and static contract tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_frontend_contract.py tests/browser/test_fmea_workbench.py tests/integration/test_fmea_delivery_api_v1.py tests/integration/test_fmea_governance_api_v1.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the workbench**

```powershell
git add pyproject.toml frontend_app/current_console/fmea.html frontend_app/current_console/fmea tests/unit/test_fmea_frontend_contract.py tests/browser/test_fmea_workbench.py
git commit -m "feat(fmea): add full workflow workbench"
```

### Task 8: Prove multi-domain portability, bounded scale, and final acceptance

**Files:**
- Create: `domain_packs/electrical-demo/`
- Create: `domain_packs/software-demo/`
- Create: `examples/fmea/full-acceptance/`
- Create: `scripts/run_fmea_full_acceptance.py`
- Create: `scripts/verify_fmea_full_acceptance.py`
- Create: `tests/integration/test_fmea_cross_domain_acceptance.py`
- Create: `tests/integration/test_fmea_full_acceptance.py`
- Create: `tests/performance/test_fmea_10000_row_export.py`
- Create: `tests/regression/test_fmea_delivery_security.py`
- Create: `docs/handoff/full-fmea-product.md`

**Interfaces:**
- Consumes: every completed phase.
- Produces: `graphrag.fmea.full.acceptance.v1` and an independent verifier covering the full product.

- [ ] **Step 1: Write cross-domain, scale, and P0 tests**

```python
@pytest.mark.parametrize("pack_id", ["fuel-combustion", "electrical-demo", "software-demo"])
def test_domain_pack_uses_same_kernel_without_domain_imports(pack_id):
    result = run_domain_fixture(pack_id)
    assert result.kernel_schema_id == "graphrag.fmea.v1"
    assert result.generic_core_imported_domain_modules == ()


def test_10000_row_export_streams_and_preserves_identity(export_large_fixture):
    result = export_large_fixture(row_count=10_000)
    assert result.row_count == 10_000
    assert result.max_api_page_size <= 100
    assert result.json_snapshot_hash == result.xlsx_snapshot_hash == result.docx_snapshot_hash


def test_p0_authority_and_evidence_counts_are_zero(full_acceptance):
    assert full_acceptance.model_approval_count == 0
    assert full_acceptance.known_without_evidence_count == 0
    assert full_acceptance.confirmed_invalid_score_count == 0
    assert full_acceptance.accepted_high_risk_evidence_free_edge_count == 0
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_cross_domain_acceptance.py tests/integration/test_fmea_full_acceptance.py tests/performance/test_fmea_10000_row_export.py tests/regression/test_fmea_delivery_security.py -q`

Expected: FAIL because demonstration packs and final acceptance are absent.

- [ ] **Step 3: Add structurally distinct packs and independent full verifier**

Electrical demo adds voltage/current/isolation fields and a different scoring anchor set. Software demo adds software function, hazardous behavior, trigger, detection mechanism, and no physical-unit propagation requirement. Both use DomainPack/template/rule/migration contracts without imports from generic core.

The runner executes evidence selection, candidate generation with deterministic fake, field review, risk proposal/confirmation, propagation proposal/review where applicable, revision assembly, approval, publication, JSON/XLSX/DOCX export, template import draft, migration dry-run/confirmation, withdrawal/supersession, and audit/outbox replay. The verifier independently recomputes all identities and rejects extra/missing files, duplicate cases/events, partial artifacts, private markers, authority violations, or cross-format semantic drift.

- [ ] **Step 4: Run the final product gate**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_template_migration_contracts.py tests/unit/test_fmea_template_import_excel.py tests/unit/test_fmea_template_import_docx.py tests/unit/test_fmea_template_patch_generator.py tests/unit/test_fmea_migration_service.py tests/unit/test_fmea_export_json.py tests/unit/test_fmea_export_narrative.py tests/unit/test_fmea_export_xlsx.py tests/unit/test_fmea_export_docx.py tests/unit/test_fmea_artifact_store.py tests/unit/test_fmea_delivery_api_contracts.py tests/unit/test_fmea_codex_skill.py tests/unit/test_fmea_frontend_contract.py tests/integration/test_fmea_template_draft_lifecycle.py tests/integration/test_fmea_delivery_sqlite.py tests/integration/test_fmea_export_runs.py tests/integration/test_fmea_export_consistency.py tests/integration/test_fmea_delivery_api_v1.py tests/integration/test_fmea_delivery_cli.py tests/integration/test_fmea_cross_domain_acceptance.py tests/integration/test_fmea_full_acceptance.py tests/performance/test_fmea_10000_row_export.py tests/regression/test_fmea_migration_rollback.py tests/regression/test_fmea_delivery_security.py -q
.venv\Scripts\python.exe -m pytest tests/browser/test_fmea_workbench.py -q
.venv\Scripts\python.exe scripts/run_fmea_full_acceptance.py
.venv\Scripts\python.exe scripts/verify_fmea_full_acceptance.py --latest
.venv\Scripts\python.exe -m compileall -q core_domain fmea_application fmea_infrastructure scripts
.venv\Scripts\ruff.exe check core_domain/fmea fmea_application fmea_infrastructure scripts/fmea_skill.py scripts/run_fmea_full_acceptance.py scripts/verify_fmea_full_acceptance.py tests/unit/test_fmea_*.py tests/integration/test_fmea_*.py tests/regression/test_fmea_*.py
git diff --check
```

Expected: every command exits 0. Paid live DeepSeek validation remains a separately authorized, non-default smoke gate.

- [ ] **Step 5: Commit final portability and acceptance**

```powershell
git add domain_packs/electrical-demo domain_packs/software-demo examples/fmea/full-acceptance scripts/run_fmea_full_acceptance.py scripts/verify_fmea_full_acceptance.py tests/integration/test_fmea_cross_domain_acceptance.py tests/integration/test_fmea_full_acceptance.py tests/performance/test_fmea_10000_row_export.py tests/regression/test_fmea_delivery_security.py docs/handoff/full-fmea-product.md
git commit -m "test(fmea): close full product acceptance"
```

## Phase 4 completion checklist

- [ ] Excel/Word imports create drafts and preserve source structure/hash.
- [ ] Model patches cannot register templates or DomainPacks.
- [ ] Explicit dry-run migrations create child revisions and invalidate dependent risk/propagation.
- [ ] JSON/XLSX/DOCX derive from one snapshot and pass semantic/hash verification.
- [ ] Workbench uses REST only and distinguishes model, human, draft, approved, and published states.
- [ ] Three structurally distinct DomainPacks use the same generic kernel.
- [ ] 10,000-row export remains paginated/streamed and bounded.
- [ ] Final independent acceptance reports every P0 authority/evidence violation count as zero.
