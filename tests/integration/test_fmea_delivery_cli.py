from __future__ import annotations

import json
from types import SimpleNamespace

from core_domain.fmea.states import ActorType, RunStatus
from fmea_application.delivery_contracts import ExportFormat, ExportRun
from fmea_application.migration_service import MigrationResult
from fmea_application.review_contracts import ActorContext
from scripts import fmea_skill

TOKEN = "a" * 32
UUID1 = "00000000-0000-4000-8000-0000000005ab"


def test_cli_published_export_requires_exact_confirmation_before_runtime(capsys, monkeypatch) -> None:
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: (_ for _ in ()).throw(AssertionError("runtime")))
    exit_code = fmea_skill.main([
        "export",
        "start",
        "--revision-id",
        "revision-1",
        "--snapshot-id",
        "snapshot-1",
        "--snapshot-hash",
        "sha256:" + "a" * 64,
        "--format",
        "json",
        "--publication-id",
        "publication-1",
        "--record-version",
        "1",
        "--idempotency-key",
        UUID1,
    ])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code != 0
    assert payload["error"]["code"] == "FMEA_EXPORT_PUBLICATION_CONFIRMATION_REQUIRED"


def test_cli_status_is_read_only_and_emits_one_supported_json_object(capsys, monkeypatch) -> None:
    runtime = SimpleNamespace(
        actor=ActorContext("human-1", ActorType.HUMAN, frozenset({"exporter"}), "ws-1"),
        close=lambda: None,
        export_service=SimpleNamespace(
            get_run=lambda run_id, actor: ExportRun(
                export_run_id=run_id,
                workspace_id="ws-1",
                revision_id="revision-1",
                snapshot_id="snapshot-1",
                snapshot_hash="sha256:" + "a" * 64,
                publication_id=None,
                format=ExportFormat.JSON,
                draft_preview=True,
                status=RunStatus.QUEUED,
                created_at="2026-08-30T00:00:00Z",
                filename="fmea-run-1.json",
            )
        ),
    )
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: runtime)
    exit_code = fmea_skill.main(["export", "status", "--run-id", "run-1"])
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == 0
    assert output.count("\n") == 1
    assert payload["data"]["draft_preview"] is True


def test_cli_migration_confirm_keeps_dry_run_key_and_source_version(capsys, monkeypatch) -> None:
    commands = []

    class MigrationService:
        def confirm(self, command, actor):
            commands.append(command)
            return MigrationResult("migration-1", "revision-2", command.report_hash)

    runtime = SimpleNamespace(
        actor=ActorContext("human-1", ActorType.HUMAN, frozenset({"template_admin"}), "ws-1"),
        close=lambda: None,
        migration_service=MigrationService(),
    )
    request = {
        "migration_id": "migration-1",
        "report_hash": "sha256:" + "a" * 64,
        "source_revision_id": "revision-1",
        "source_revision_hash": "sha256:" + "b" * 64,
        "target_domain_pack_id": "domain-pack",
        "target_domain_pack_version": "1.1.0",
        "target_domain_pack_hash": "sha256:" + "c" * 64,
        "dry_run": {
            "migration_id": "migration-1",
            "source_revision_hash": "sha256:" + "b" * 64,
            "target_domain_pack_id": "domain-pack",
            "target_domain_pack_version": "1.1.0",
            "target_domain_pack_hash": "sha256:" + "c" * 64,
        },
        "dry_run_idempotency_key": "00000000-0000-4000-8000-0000000005ac",
        "dry_run_source_version": 7,
        "confirm_migration": True,
    }
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: runtime)
    monkeypatch.setattr(fmea_skill, "load_json_request", lambda _path: request)
    exit_code = fmea_skill.main([
        "migration",
        "confirm",
        "--request-file",
        "request.json",
        "--confirm-migration",
        "--record-version",
        "9",
        "--idempotency-key",
        UUID1,
    ])
    json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert commands[0].idempotency_key == UUID1
    assert commands[0].expected_report_version == 9
    assert commands[0].dry_run_command.idempotency_key == "00000000-0000-4000-8000-0000000005ac"
    assert commands[0].dry_run_command.expected_source_version == 7


def test_cli_export_start_forwards_record_version(capsys, monkeypatch) -> None:
    commands = []

    class ExportService:
        def start(self, command, actor):
            commands.append(command)
            return ExportRun(
                export_run_id=command.export_run_id,
                workspace_id=command.workspace_id,
                revision_id=command.revision_id,
                snapshot_id=command.snapshot_id,
                snapshot_hash=command.snapshot_hash,
                publication_id=None,
                format=command.format,
                draft_preview=True,
                status=RunStatus.QUEUED,
                created_at="2026-08-30T00:00:00Z",
                filename=command.filename,
            )

    runtime = SimpleNamespace(
        actor=ActorContext("human-1", ActorType.HUMAN, frozenset({"exporter"}), "ws-1"),
        close=lambda: None,
        export_service=ExportService(),
    )
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: runtime)
    exit_code = fmea_skill.main([
        "export",
        "start",
        "--revision-id",
        "revision-1",
        "--snapshot-id",
        "snapshot-1",
        "--snapshot-hash",
        "sha256:" + "a" * 64,
        "--format",
        "json",
        "--draft-preview",
        "--record-version",
        "7",
        "--idempotency-key",
        UUID1,
    ])
    json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert commands[0].expected_revision_version == 7


def test_cli_delivery_error_does_not_import_rest_transport(monkeypatch) -> None:
    original = fmea_skill.import_module

    def guarded_import(name):
        if name == "chroma_rag_poc.routes_fmea_delivery_v1":
            raise AssertionError
        return original(name)

    monkeypatch.setattr(fmea_skill, "import_module", guarded_import)
    error = fmea_skill._delivery_error("FMEA_DELIVERY_REQUEST_INVALID", "invalid")
    assert error.code == "FMEA_DELIVERY_REQUEST_INVALID"


def test_cli_rejects_repository_and_sqlite_overrides_without_echoing(capsys) -> None:
    exit_code = fmea_skill.main(["export", "status", "--run-id", "run-1", "--repository", "secret"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code != 0
    assert payload["error"]["code"] in {"FMEA_DELIVERY_REQUEST_INVALID", "FMEA_GOVERNANCE_REQUEST_INVALID"}
    assert "secret" not in json.dumps(payload)
