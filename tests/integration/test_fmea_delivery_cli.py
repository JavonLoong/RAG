from __future__ import annotations

import json
from types import SimpleNamespace

from core_domain.fmea.states import ActorType
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
            get_run=lambda run_id, actor: SimpleNamespace(
                export_run_id=run_id,
                workspace_id="ws-1",
                revision_id="revision-1",
                snapshot_id="snapshot-1",
                snapshot_hash="sha256:" + "a" * 64,
                publication_id=None,
                format="json",
                draft_preview=True,
                status="queued",
                created_at="2026-08-30T00:00:00Z",
                filename="fmea-run-1.json",
                artifact_id=None,
                error=None,
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


def test_cli_rejects_repository_and_sqlite_overrides_without_echoing(capsys) -> None:
    exit_code = fmea_skill.main(["export", "status", "--run-id", "run-1", "--repository", "secret"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code != 0
    assert payload["error"]["code"] in {"FMEA_DELIVERY_REQUEST_INVALID", "FMEA_GOVERNANCE_REQUEST_INVALID"}
    assert "secret" not in json.dumps(payload)
