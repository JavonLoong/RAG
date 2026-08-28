from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.run_fmea_risk_acceptance import ARTIFACT_NAMES, RETRIEVAL_MODES, run_acceptance
from scripts.verify_fmea_risk_acceptance import verify_acceptance_directory

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CASES = ["analysis_scope", "confirmed", "unknown", "conflict", "invalidated"]


def test_acceptance_covers_confirmed_unknown_conflict_and_invalidation(tmp_path: Path) -> None:
    result = run_acceptance(tmp_path / "runs")

    assert result["schema_version"] == "graphrag.fmea.risk.acceptance.v1"
    assert result["status"] == "passed"
    assert result["cases"] == EXPECTED_CASES
    assert result["model_confirmation_count"] == 0
    assert {path.name for path in result.artifact_dir.iterdir()} == set(ARTIFACT_NAMES)
    assert verify_acceptance_directory(result.artifact_dir) == result.summary


@pytest.mark.parametrize("retrieval_mode", RETRIEVAL_MODES)
def test_acceptance_consumes_every_supported_evidence_mode_through_one_contract(
    tmp_path: Path,
    retrieval_mode: str,
) -> None:
    result = run_acceptance(tmp_path / retrieval_mode, retrieval_mode=retrieval_mode)

    assert result["evidence_pack"]["retrieval_mode"] == retrieval_mode
    assert result["fmea_backend_import_count"] == 0
    assert result["fmea_backend_imports"] == []
    assert result["risk"]["confirmed_rpn"] == 108
    assert result["risk"]["unknown_rpn"] is None
    assert result["risk"]["conflict_rpn"] is None
    assert result["risk"]["rule_applicable"] is True


def test_acceptance_is_byte_deterministic_for_the_same_mode(tmp_path: Path) -> None:
    first = run_acceptance(tmp_path / "first", retrieval_mode="combined")
    second = run_acceptance(tmp_path / "second", retrieval_mode="combined")

    assert first.artifact_bytes == second.artifact_bytes


def test_acceptance_runner_and_verifier_cli_emit_one_safe_json_object(tmp_path: Path) -> None:
    run_process = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(ROOT / "scripts" / "run_fmea_risk_acceptance.py"),
            "--output-root",
            str(tmp_path / "cli"),
            "--retrieval-mode",
            "rag_only",
        ],
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
            str(ROOT / "scripts" / "verify_fmea_risk_acceptance.py"),
            "--artifact-dir",
            run_payload["output_directory"],
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert verify_process.returncode == 0
    verify_payload = json.loads(verify_process.stdout)
    assert verify_payload == {
        "fmea_module_import_count": 0,
        "schema_version": "graphrag.fmea.risk.acceptance.v1",
        "status": "passed",
    }
    assert verify_process.stdout.count("\n") == 1
