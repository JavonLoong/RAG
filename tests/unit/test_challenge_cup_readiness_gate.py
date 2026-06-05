from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "readiness_gate_report.md"
READINESS_SCRIPT = REPO_ROOT / "scripts" / "check_challenge_cup_readiness.py"


def load_readiness_module():
    spec = importlib.util.spec_from_file_location("check_challenge_cup_readiness", READINESS_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def test_claim_matrix_gate_rejects_missing_evidence_paths(tmp_path, monkeypatch) -> None:
    module = load_readiness_module()
    matrix = tmp_path / "claim_matrix.md"
    matrix.write_text(
        "\n".join(
            [
                "# 评审主张证据矩阵",
                "| 评审维度 | 直接证据 |",
                "| --- | --- |",
                "| 创新性 | `docs/challenge_cup/02_技术白皮书.md`; `docs/challenge_cup/missing-evidence.md` |",
                "| 工程闭环 | `docs/challenge_cup/reproducibility/dataset_manifest.md` |",
                "| 科学评测 | `evaluation/system_eval_questions.jsonl` |",
                "| 可复现 | `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`; `docs/challenge_cup/reproducibility/readiness_gate_report.md` |",
                "| 应用边界 | `docs/challenge_cup/05_答辩问答手册.md` |",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "CLAIM_MATRIX", matrix)

    check = module.check_claim_evidence_matrix()

    assert not check.passed
    assert "missing-evidence.md" in check.detail
