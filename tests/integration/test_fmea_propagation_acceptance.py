from __future__ import annotations

import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest

from scripts.run_fmea_propagation_acceptance import (
    ARTIFACT_NAMES,
    CASE_IDS,
    EVIDENCE_PROFILES,
    SCHEMA_VERSION,
    run_acceptance,
)
from scripts.verify_fmea_propagation_acceptance import verify_acceptance_directory

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CASE_IDS = {"forward", "reverse", "cycle", "conflict", "long_path"}
EXPECTED_PROFILES = {
    "rag_only",
    "graphrag_local_only",
    "graphrag_global_only",
    "graphrag_only",
    "combined",
    "auto",
    "custom",
}


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _rewrite(output: Path, name: str, mutate) -> None:
    value = json.loads((output / name).read_text(encoding="utf-8"))
    mutate(value)
    (output / name).write_bytes(_canonical(value))
    if name != "acceptance-summary.json":
        summary_path = output / "acceptance-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["artifact_hashes"][name] = "sha256:" + sha256((output / name).read_bytes()).hexdigest()
        summary_path.write_bytes(_canonical(summary))


def test_acceptance_covers_forward_reverse_cycle_conflict_and_long_path(tmp_path: Path) -> None:
    result = run_acceptance(tmp_path / "runs")

    assert result["schema_version"] == SCHEMA_VERSION == "graphrag.fmea.propagation.acceptance.v1"
    assert result["status"] == "passed"
    assert set(result["case_ids"]) == EXPECTED_CASE_IDS == set(CASE_IDS)
    assert result["invented_endpoint_count"] == 0
    assert result["model_confirmation_count"] == 0
    assert result["human_confirmation_count"] == 2
    assert result["human_review_required_count"] == 3
    assert set(result["evidence_profiles"]) == EXPECTED_PROFILES == set(EVIDENCE_PROFILES)
    assert {path.name for path in result.artifact_dir.iterdir()} == set(ARTIFACT_NAMES)
    issues = json.loads((result.artifact_dir / "issues.json").read_text(encoding="utf-8"))["issues"]
    assert {item["code"] for item in issues} >= {"cyclic", "high_risk", "external", "conflicting", "incomplete"}
    assert verify_acceptance_directory(result.artifact_dir) == result.summary


def test_acceptance_uses_all_evidence_selection_profiles(tmp_path: Path) -> None:
    result = run_acceptance(tmp_path / "runs")
    topology = json.loads((result.artifact_dir / "topology.json").read_text(encoding="utf-8"))

    profiles = topology["evidence_selection_profiles"]
    assert set(profiles) == EXPECTED_PROFILES
    assert profiles["auto"]["resolved_profile"] == "combined"
    assert profiles["rag_only"]["evidence_types"] == ["text"]
    assert profiles["graphrag_local_only"]["evidence_types"] == ["graph"]
    assert profiles["graphrag_global_only"]["evidence_types"] == ["community"]
    assert profiles["graphrag_only"]["evidence_types"] == ["graph", "community"]
    assert profiles["combined"]["evidence_types"] == ["text", "graph", "community"]
    assert profiles["custom"]["evidence_types"] == ["text", "graph"]


def test_acceptance_is_byte_deterministic(tmp_path: Path) -> None:
    first = run_acceptance(tmp_path / "first")
    second = run_acceptance(tmp_path / "second")

    assert first.artifact_bytes == second.artifact_bytes


def test_acceptance_runner_and_verifier_cli_emit_one_safe_json_object(tmp_path: Path) -> None:
    run_process = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts" / "run_fmea_propagation_acceptance.py"), "--output-root", str(tmp_path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert run_process.returncode == 0
    run_payload = json.loads(run_process.stdout)
    assert run_payload["status"] == "passed"
    assert run_process.stdout.count("\n") == 1

    verify_process = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_fmea_propagation_acceptance.py"),
            "--artifact-dir",
            run_payload["output_directory"],
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert verify_process.returncode == 0
    assert json.loads(verify_process.stdout) == {
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
    }
    assert verify_process.stdout.count("\n") == 1


def test_acceptance_failure_does_not_publish_partial_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.run_fmea_propagation_acceptance as runner

    output_root = tmp_path / "runs"
    output_root.mkdir()
    latest = output_root / "latest"
    latest.mkdir()
    (latest / "sentinel").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(runner, "_build_artifacts", lambda: (_ for _ in ()).throw(RuntimeError("fixture failure")))

    with pytest.raises(RuntimeError):
        run_acceptance(output_root)

    assert (latest / "sentinel").read_text(encoding="utf-8") == "keep"
    assert not [path for path in output_root.iterdir() if path.name.startswith(".")]
