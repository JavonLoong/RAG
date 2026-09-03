from __future__ import annotations

import hashlib
from types import SimpleNamespace

from chroma_rag_poc.api import create_app
from fastapi.testclient import TestClient

from core_domain.fmea.states import ActorType
from fmea_application.delivery_contracts import ExportArtifactManifest, VerifiedExportArtifact
from fmea_application.review_contracts import ActorContext

TOKEN = "a" * 32
UUID1 = "00000000-0000-4000-8000-0000000005ab"
SNAPSHOT_HASH = "sha256:" + "d" * 64


class FakeAuth:
    def authenticate(self, bearer_token: str, remote_host: str | None) -> ActorContext:
        assert bearer_token == TOKEN
        return ActorContext(
            "human-1",
            ActorType.HUMAN,
            frozenset({"reviewer", "exporter"}),
            "ws-1",
        )


class FakeDomainPackService:
    called = False

    def accept_patch(self, command, actor):
        self.called = True
        raise AssertionError


class FakeExportService:
    def __init__(self) -> None:
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

    def suggest_narrative(self, snapshot, actor):
        return SimpleNamespace(
            envelope=SimpleNamespace(
                suggestion_id="suggestion-1",
                target_type="normalized_fmea_snapshot",
                target_id="snapshot-1",
                applied=False,
                citations=("evidence-1",),
            ),
            draft=SimpleNamespace(title="FMEA narrative", sections=(), claims=()),
        )


class FakeSnapshotService:
    def get_snapshot(self, snapshot_id: str, actor: ActorContext):
        assert snapshot_id == "snapshot-1"
        return SimpleNamespace(snapshot_id=snapshot_id, snapshot_hash=SNAPSHOT_HASH, revision_id="revision-1")


def _app() -> tuple[object, FakeDomainPackService]:
    domain_pack = FakeDomainPackService()
    runtime = SimpleNamespace(
        domain_pack_service=domain_pack,
        migration_service=SimpleNamespace(),
        export_service=FakeExportService(),
        governance_service=FakeSnapshotService(),
    )
    app = create_app(
        review_auth_provider=FakeAuth(),
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
