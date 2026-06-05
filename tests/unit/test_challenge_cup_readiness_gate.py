from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "readiness_gate_report.md"


def test_challenge_cup_readiness_gate_passes_and_writes_review_report() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_challenge_cup_readiness.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert "readiness_gate_report.md" in result.stdout
    report = REPORT.read_text(encoding="utf-8")
    assert "# Challenge Cup Readiness Gate" in report
    assert "Status: `pass`" in report
    assert "package evidence files" in report
    assert "claim-evidence matrix" in report
    assert "award claims" in report
    assert "browser smoke checks" in report
    assert "KG artifact links" in report
    assert "mobile console health" in report
    assert "60 evaluation questions" in report


def test_challenge_cup_readiness_gate_bootstraps_its_own_report() -> None:
    REPORT.unlink(missing_ok=True)

    result = subprocess.run(
        [sys.executable, "scripts/check_challenge_cup_readiness.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert "Status: pass" in result.stdout
    assert REPORT.exists()
