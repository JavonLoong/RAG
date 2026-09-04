from __future__ import annotations

import hashlib
from types import SimpleNamespace

from chroma_rag_poc.api import create_app
from fastapi.testclient import TestClient

from core_domain.fmea.states import ActorType, RunStatus
from core_domain.fmea.template_migration import (
    MigrationPlan,
    MigrationReport,
    MigrationReportStatus,
    MigrationStep,
)
from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
from fmea_application.delivery_contracts import ExportArtifactManifest, ExportRun, VerifiedExportArtifact
from fmea_application.export_service import (
    ExportNarrativeClaim,
    ExportNarrativeDraft,
    ExportNarrativeSection,
    ExportNarrativeSuggestion,
)
from fmea_application.migration_service import MigrationResult, migration_report_id
from fmea_application.review_contracts import ActorContext

TOKEN = "a" * 32
UUID1 = "00000000-0000-4000-8000-0000000005ab"
SNAPSHOT_HASH = "sha256:" + "d" * 64
UUID2 = "00000000-0000-4000-8000-0000000005ac"


class FakeAuth:
    def __init__(self, roles: frozenset[str] | None = None) -> None:
        self.roles = roles or frozenset({"reviewer", "exporter"})

    def authenticate(self, bearer_token: str, remote_host: str | None) -> ActorContext:
        assert bearer_token == TOKEN
        return ActorContext(
            "human-1",
            ActorType.HUMAN,
            self.roles,
            "ws-1",
        )


class FakeDomainPackService:
    called = False

    def accept_patch(self, command, actor):
        self.called = True
        raise AssertionError


class FakeExportService:
    def __init__(self) -> None:
        self.start_commands = []
        payload = b'{"ok":true}\n'
        manifest = ExportArtifactManifest(
            artifact_id="artifact-1",
            export_run_id="run-1",
            publication_id="publication-1",
            revision_id="revision-1",
            snapshot_hash=SNAPSHOT_HASH,
            format="json",
            media_type="application/json",
            byte_length=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            draft_preview=False,
            created_at="2026-08-30T00:00:00Z",
            snapshot_id="snapshot-1",
            filename="fmea-run-1.json",
        )
        self.artifact = VerifiedExportArtifact(
            workspace_id="ws-1",
            export_run_id="run-1",
            artifact_id="artifact-1",
            filename="fmea-run-1.json",
            payload=payload,
            manifest=manifest,
        )

    def get_artifact(self, artifact_id: str, actor: ActorContext):
        assert artifact_id == "artifact-1"
        return self.artifact

    def start(self, command, actor):
        self.start_commands.append(command)
        return ExportRun(
            export_run_id=command.export_run_id,
            workspace_id=command.workspace_id,
            revision_id=command.revision_id,
            snapshot_hash=command.snapshot_hash,
            publication_id=command.publication_id,
            format=command.format,
            draft_preview=command.draft_preview,
            status=RunStatus.QUEUED,
            created_at="2026-08-30T00:00:00Z",
            snapshot_id=command.snapshot_id,
            filename=command.filename,
        )

    def suggest_narrative_for_revision(self, revision_id, actor, **kwargs):
        assert revision_id == "revision-1"
        claim = ExportNarrativeClaim("claim-1", "Narrative claim", ("evidence-1",))
        section = ExportNarrativeSection("section-1", "Summary", "Body", (claim.claim_id,))
        draft = ExportNarrativeDraft("FMEA narrative", (section,), (claim,))
        envelope = AssistanceSuggestion(
            suggestion_id="suggestion-1",
            kind=AssistanceKind.EXPORT_NARRATIVE_DRAFT,
            workspace_id=actor.workspace_id,
            target_type="normalized_fmea_snapshot",
            target_id="snapshot-1",
            target_record_version=1,
            evidence_pack_ids=("evidence-pack",),
            payload=draft.as_json(),
            evidence_ids=("evidence-1",),
            model_hash="a" * 64,
            prompt_hash="b" * 64,
            run_id="narrative-run-1",
            trace_id="narrative-trace-1",
            record_version=1,
            created_at="2026-08-30T00:00:00Z",
        )
        return ExportNarrativeSuggestion(envelope=envelope, draft=draft)


class FakeMigrationService:
    def __init__(self) -> None:
        self.dry_run_commands = []
        self.confirm_commands = []

    @staticmethod
    def report() -> MigrationReport:
        plan = MigrationPlan(
            source=("domain-pack", "1.0.0"),
            target=("domain-pack", "1.1.0"),
            steps=(MigrationStep(("domain-pack", "1.0.0"), ("domain-pack", "1.1.0"), "adapter-1"),),
        )
        return MigrationReport(
            migration_id="migration-1",
            plan=plan,
            source_revision_id="revision-1",
            source_revision_hash="sha256:" + "a" * 64,
            source_domain_pack_identity=("domain-pack", "1.0.0", "sha256:" + "b" * 64),
            target_domain_pack_identity=("domain-pack", "1.1.0", "sha256:" + "c" * 64),
            target_revision_hash="sha256:" + "d" * 64,
            status=MigrationReportStatus.DRY_RUN,
            mapped_fields=(),
            dropped_fields=(),
            unresolved_fields=(),
            warnings=(),
            created_at="2026-08-30T00:00:00Z",
        )

    def dry_run(self, command, actor):
        self.dry_run_commands.append(command)
        return self.report()

    def confirm(self, command, actor):
        self.confirm_commands.append(command)
        return MigrationResult("migration-1", "revision-2", command.report_hash)


def _app(
    *,
    roles: frozenset[str] | None = None,
    migration_service: object | None = None,
    export_service: FakeExportService | None = None,
) -> tuple[object, FakeDomainPackService]:
    domain_pack = FakeDomainPackService()
    runtime = SimpleNamespace(
        domain_pack_service=domain_pack,
        migration_service=migration_service or SimpleNamespace(),
        export_service=export_service or FakeExportService(),
    )
    app = create_app(
        review_auth_provider=FakeAuth(roles),
        delivery_runtime_factory=lambda _workspace: runtime,
    )
    app.state.workspace_registry = SimpleNamespace(get=lambda workspace_id: SimpleNamespace(workspace_id=workspace_id))
    return app, domain_pack


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_template_accept_requires_template_admin_before_service_call() -> None:
    app, service = _app()
    body = {
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
    response = TestClient(app).post(
        "/api/v1/fmea/template-patches/patch-1/acceptance",
        headers={**_headers(), "If-Match": '"1"', "Idempotency-Key": UUID1},
        json=body,
    )
    assert response.status_code == 403
    assert service.called is False


def test_artifact_download_returns_verified_manifest_length_and_hash() -> None:
    app, _ = _app()
    response = TestClient(app).get("/api/v1/fmea/export-artifacts/artifact-1", headers=_headers())
    assert response.status_code == 200
    assert response.content == b'{"ok":true}\n'
    assert response.headers["content-length"] == str(len(response.content))
    assert response.headers["etag"] == '"' + hashlib.sha256(response.content).hexdigest() + '"'
    assert response.headers["content-disposition"] == 'attachment; filename="fmea-run-1.json"'


def test_export_start_forwards_if_match_without_fabricating_run_etag() -> None:
    export = FakeExportService()
    app, _ = _app(export_service=export)
    response = TestClient(app).post(
        "/api/v1/fmea/revisions/revision-1/export-runs",
        headers={**_headers(), "If-Match": '"7"', "Idempotency-Key": UUID1},
        json={
            "snapshot_id": "snapshot-1",
            "snapshot_hash": SNAPSHOT_HASH,
            "format": "json",
            "draft_preview": True,
        },
    )
    assert response.status_code == 202
    assert export.start_commands[0].expected_revision_version == 7
    assert "etag" not in response.headers


def test_rest_patch_lifecycle_uses_sqlite_after_service_restart(
    tmp_path,
    fixture_review_bundle,
    fixture_system_actor,
) -> None:
    """Exercise the transport against durable DomainPackService state."""

    from fmea_application.domain_pack_service import DomainPackService
    from fmea_infrastructure.composition import _RepositoryTemplateEvidenceProvider
    from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository
    from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository
    from fmea_infrastructure.template_import_excel import ExcelTemplateImporter
    from fmea_infrastructure.template_patch_generator import TemplatePatchGenerator
    from structured_output_application import TemplateCompiler
    from structured_output_infrastructure import Draft202012SchemaAdapter, FileTemplateRegistry, load_template_source
    from tests.integration.test_fmea_template_draft_lifecycle import _FakeGateway, _xlsx

    delivery_path = tmp_path / "delivery.sqlite3"
    evidence_path = tmp_path / "evidence.sqlite3"
    evidence_repository = SqliteFmeaRepository(evidence_path)
    evidence_repository.initialize()
    evidence_repository.save_review_candidate_bundle(fixture_review_bundle, fixture_system_actor)

    def service() -> DomainPackService:
        workflow_repository = SqliteFmeaDeliveryRepository(delivery_path)
        workflow_repository.initialize()
        return DomainPackService(
            importers={"xlsx": ExcelTemplateImporter(clock=lambda: "2026-08-30T00:00:00Z")},
            patch_generator=TemplatePatchGenerator(_FakeGateway(), clock=lambda: "2026-08-30T00:00:00Z"),
            evidence_provider=_RepositoryTemplateEvidenceProvider(SqliteFmeaRepository(evidence_path)),
            compiler=TemplateCompiler(
                schema_validator=Draft202012SchemaAdapter(),
                source_loader=load_template_source,
            ),
            registry=FileTemplateRegistry(tmp_path / "template-registry"),
            workflow_repository=workflow_repository,
            clock=lambda: "2026-08-30T00:00:00Z",
        )

    def app_for(service_instance: DomainPackService):
        runtime = SimpleNamespace(
            domain_pack_service=service_instance,
            migration_service=SimpleNamespace(),
            export_service=FakeExportService(),
        )
        app = create_app(
            persist_dir=tmp_path / "persist",
            upload_dir=tmp_path / "uploads",
            log_dir=tmp_path / "logs",
            review_auth_provider=FakeAuth(frozenset({"template_admin", "reviewer", "exporter"})),
            delivery_runtime_factory=lambda _workspace: runtime,
        )
        app.state.workspace_registry = SimpleNamespace(
            get=lambda workspace_id: SimpleNamespace(workspace_id=workspace_id)
        )
        return app

    import_key = "00000000-0000-4000-8000-000000000701"
    suggest_key = "00000000-0000-4000-8000-000000000702"
    reject_key = "00000000-0000-4000-8000-000000000703"

    with TestClient(app_for(service())) as client:
        imported = client.post(
            "/api/v1/fmea/template-drafts",
            headers={**_headers(), "Idempotency-Key": import_key},
            files={"file": ("fmea.xlsx", _xlsx(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert imported.status_code == 201
        draft = imported.json()["data"]

        suggested = client.post(
            f"/api/v1/fmea/template-drafts/{draft['draft_id']}/patch-runs",
            headers={**_headers(), "If-Match": '"1"', "Idempotency-Key": suggest_key},
            json={
                "input_template_version": "1.0.0",
                "target_template_id": "fmea-row-review",
                "target_template_version": "1.0.0",
                "target_template_hash": "sha256:" + "a" * 64,
                "domain_pack_id": "generic-domain",
                "domain_pack_version": "1.0.0",
                "domain_pack_hash": "sha256:" + "b" * 64,
                "evidence_pack_id": fixture_review_bundle.evidence_pack.pack_id,
                "evidence_pack_hash": "sha256:" + fixture_review_bundle.evidence_pack.pack_hash,
            },
        )
        assert suggested.status_code == 202
        provisional = suggested.json()["data"]
        patch_id = provisional["candidate"]["patch_id"]
        suggestion_id = provisional["suggestion_id"]
        assert suggested.headers["etag"] == '"1"'
        assert provisional["candidate"]["status"] == "suggested"

    with TestClient(app_for(service())) as client:
        reloaded = client.get(f"/api/v1/fmea/template-patches/{patch_id}", headers=_headers())
        assert reloaded.status_code == 200
        assert reloaded.headers["etag"] == '"1"'
        assert reloaded.json()["resource_type"] == "fmea_template_patch"
        assert reloaded.json()["data"]["candidate"]["status"] == "suggested"

        rejected = client.post(
            f"/api/v1/fmea/template-patches/{patch_id}/rejection",
            headers={**_headers(), "If-Match": '"1"', "Idempotency-Key": reject_key},
            json={"suggestion_id": suggestion_id, "patch_id": patch_id, "reason": "reviewed"},
        )
        assert rejected.status_code == 201
        assert rejected.headers["etag"] == '"2"'
        assert rejected.json()["data"]["action"] == "rejected"

        decided = client.get(f"/api/v1/fmea/template-patches/{patch_id}", headers=_headers())
        assert decided.status_code == 200
        assert decided.headers["etag"] == '"2"'
        assert decided.json()["resource_type"] == "fmea_template_patch_decision"
        assert decided.json()["data"]["action"] == "rejected"


def test_migration_dry_run_forwards_source_version_and_reports_etag() -> None:
    migration = FakeMigrationService()
    app, _ = _app(roles=frozenset({"template_admin"}), migration_service=migration)
    response = TestClient(app).post(
        "/api/v1/fmea/revisions/revision-1/migration-dry-runs",
        headers={
            **_headers(),
            "If-Match": '"7"',
            "Idempotency-Key": UUID1,
        },
        json={
            "migration_id": "migration-1",
            "source_revision_hash": "sha256:" + "a" * 64,
            "target_domain_pack_id": "domain-pack",
            "target_domain_pack_version": "1.1.0",
            "target_domain_pack_hash": "sha256:" + "c" * 64,
        },
    )
    assert response.status_code == 202
    assert migration.dry_run_commands[0].expected_source_version == 7
    assert response.headers["etag"] == '"1"'


def test_migration_confirmation_preserves_original_dry_run_identity() -> None:
    migration = FakeMigrationService()
    app, _ = _app(roles=frozenset({"template_admin"}), migration_service=migration)
    report = migration.report()
    response = TestClient(app).post(
        f"/api/v1/fmea/migration-reports/{migration_report_id('ws-1', 'migration-1')}/confirmations",
        headers={**_headers(), "If-Match": '"1"', "Idempotency-Key": UUID1},
        json={
            "migration_id": "migration-1",
            "report_hash": report.report_hash,
            "source_revision_id": "revision-1",
            "source_revision_hash": "sha256:" + "a" * 64,
            "target_domain_pack_id": "domain-pack",
            "target_domain_pack_version": "1.1.0",
            "target_domain_pack_hash": "sha256:" + "c" * 64,
            "dry_run": {
                "migration_id": "migration-1",
                "source_revision_hash": "sha256:" + "a" * 64,
                "target_domain_pack_id": "domain-pack",
                "target_domain_pack_version": "1.1.0",
                "target_domain_pack_hash": "sha256:" + "c" * 64,
            },
            "dry_run_idempotency_key": UUID2,
            "dry_run_source_version": 7,
            "confirm_migration": True,
        },
    )
    assert response.status_code == 201
    command = migration.confirm_commands[0]
    assert command.idempotency_key == UUID1
    assert command.expected_report_version == 1
    assert command.dry_run_command.idempotency_key == UUID2
    assert command.dry_run_command.expected_source_version == 7
    assert response.headers["etag"] == '"1"'


def test_narrative_endpoint_is_accepted_as_unapplied_revision_suggestion() -> None:
    app, _ = _app()
    response = TestClient(app).post(
        "/api/v1/fmea/revisions/revision-1/export-narrative-runs",
        headers={**_headers(), "Idempotency-Key": UUID1},
        json={"snapshot_id": "snapshot-1", "snapshot_hash": SNAPSHOT_HASH},
    )
    assert response.status_code == 202
    assert response.json()["data"]["applied"] is False
    assert response.json()["data"]["target_type"] == "fmea_revision"


def test_delivery_rejects_client_owned_transport_overrides() -> None:
    app, _ = _app()
    response = TestClient(app).post(
        "/api/v1/fmea/revisions/revision-1/export-runs",
        headers={**_headers(), "If-Match": '"1"', "Idempotency-Key": UUID1},
        json={
            "snapshot_id": "snapshot-1",
            "snapshot_hash": SNAPSHOT_HASH,
            "format": "json",
            "draft_preview": True,
            "artifact_root": "C:/attacker",
        },
    )
    assert response.status_code == 400


def test_delivery_problem_details_preserve_request_and_trace_identity() -> None:
    app, _ = _app()
    response = TestClient(app).post(
        "/api/v1/fmea/revisions/revision-1/export-runs",
        headers={
            **_headers(),
            "X-Request-ID": "request-123",
            "X-Trace-ID": "trace-456",
        },
        json={
            "snapshot_id": "snapshot-1",
            "snapshot_hash": SNAPSHOT_HASH,
            "format": "json",
            "draft_preview": True,
        },
    )
    payload = response.json()
    assert response.status_code == 428
    assert payload["request_id"] == "request-123"
    assert payload["trace_id"] == "trace-456"
    assert payload["error"]["trace_id"] == "trace-456"
