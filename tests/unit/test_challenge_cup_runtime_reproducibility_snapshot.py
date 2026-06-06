from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_runtime_reproducibility_snapshot.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_runtime_reproducibility_snapshot", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_reproducibility_snapshot_records_environment_without_overclaiming(tmp_path, monkeypatch) -> None:
    module = load_module()
    output_json = tmp_path / "runtime_reproducibility_snapshot.json"
    output_md = tmp_path / "runtime_reproducibility_snapshot.md"
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "OUTPUT_JSON", output_json)
    monkeypatch.setattr(module, "OUTPUT_MD", output_md)

    (tmp_path / ".venv" / "Scripts").mkdir(parents=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").write_text("python", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "docs" / "challenge_cup" / "reproducibility").mkdir(parents=True)
    (tmp_path / "docs" / "challenge_cup" / "reproducibility" / "browser_demo_smoke_report.json").write_text(
        json.dumps(
            {
                "browser": {
                    "playwright_source": "C:/tools/playwright",
                    "frontend_url": "http://127.0.0.1:8000",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "run_command", lambda command, timeout=10: "v1.2.3" if command[0] == "node" else "ok")

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_runtime_reproducibility_snapshot"
    assert payload["status"] == "runtime_snapshot_ready_no_environment_portability_claim"
    assert payload["completion_claim_allowed"] is False
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["external_validation_claimed"] is False
    assert payload["runtime_scope"] == "local challenge-cup package reproduction environment"
    assert payload["python"]["project_venv_present"] is True
    assert payload["python"]["project_python"] == ".venv/Scripts/python.exe"
    assert payload["node"]["node_available"] is True
    assert payload["node"]["node_version"] == "v1.2.3"
    assert payload["node"]["package_lock_present"] is True
    assert payload["browser_automation"]["playwright_source"] == "C:/tools/playwright"
    assert payload["browser_automation"]["frontend_url"] == "http://127.0.0.1:8000"
    assert {
        ".\\.venv\\Scripts\\python.exe scripts/check_challenge_cup_readiness.py",
        ".\\.venv\\Scripts\\python.exe docs/challenge_cup/reproducibility/verify_submission_package.py --root .",
    } <= set(payload["verification_commands"])
    assert "not a production deployment certification" in payload["boundary"]
    assert "does not guarantee a special-prize result" in payload["boundary"]
    assert "does not replace real expert feedback or real timed rehearsal evidence" in payload["boundary"]
    assert payload["output_files"] == [
        "docs/challenge_cup/reproducibility/runtime_reproducibility_snapshot.md",
        "docs/challenge_cup/reproducibility/runtime_reproducibility_snapshot.json",
    ]

    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    markdown = output_md.read_text(encoding="utf-8")
    assert "Runtime Reproducibility Snapshot" in markdown
    assert ".venv/Scripts/python.exe" in markdown
    assert "package-lock.json" in markdown
    assert "C:/tools/playwright" in markdown
    assert "not a production deployment certification" in markdown
