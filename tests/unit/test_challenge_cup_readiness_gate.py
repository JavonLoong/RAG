from __future__ import annotations

import importlib.util
import json
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
    assert "package control files" in report
    assert "package evidence files" in report
    assert "claim-evidence matrix" in report
    assert "award claims" in report
    assert "special-prize rubric self-assessment" in report
    assert "expert review index" in report
    assert "defense rehearsal pack" in report
    assert "evidence integrity hashes" in report
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


def test_markdown_path_extractor_ignores_fenced_commands() -> None:
    module = load_readiness_module()
    text = "\n".join(
        [
            "`docs/challenge_cup/00_项目一页纸.md`",
            "",
            "```powershell",
            ".\\.venv\\Scripts\\python.exe scripts/check_challenge_cup_readiness.py",
            "```",
        ]
    )

    paths = module.extract_markdown_code_span_paths(text)

    assert paths == ["docs/challenge_cup/00_项目一页纸.md"]


def test_package_manifest_gate_rejects_untracked_evidence(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "question_count": 60,
                "evidence_files": ["docs/challenge_cup/untracked-evidence.md"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "nonempty", lambda path: True)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {"evaluation/system_eval_questions.jsonl"}, raising=False)

    check = module.check_package_manifest()

    assert not check.passed
    assert "untracked-evidence.md" in check.detail


def test_package_manifest_gate_rejects_dirty_evidence(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "question_count": 60,
                "evidence_files": ["docs/challenge_cup/dirty-evidence.md"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "nonempty", lambda path: True)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {"docs/challenge_cup/dirty-evidence.md"})
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: {"docs/challenge_cup/dirty-evidence.md"}, raising=False)

    check = module.check_package_manifest()

    assert not check.passed
    assert "dirty-evidence.md" in check.detail


def test_package_control_files_gate_rejects_dirty_manifest(monkeypatch) -> None:
    module = load_readiness_module()
    manifest = module.PACKAGE_MANIFEST.relative_to(module.REPO_ROOT).as_posix()
    hashes = module.EVIDENCE_HASHES.relative_to(module.REPO_ROOT).as_posix()
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {manifest, hashes})
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: {manifest})

    check = module.check_package_control_files()

    assert not check.passed
    assert "package_manifest.json" in check.detail


def test_evidence_hash_gate_rejects_mismatched_hash(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    target = "evaluation/system_eval_questions.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "question_count": 60,
                "evidence_files": [target],
                "integrity_manifest": "docs/challenge_cup/reproducibility/evidence_hashes.json",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    hashes = tmp_path / "evidence_hashes.json"
    hashes.write_text(
        json.dumps(
            {
                "algorithm": "sha256",
                "excluded_self_reports": [],
                "files": [{"path": target, "bytes": (module.REPO_ROOT / target).stat().st_size, "sha256": "0" * 64}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)

    check = module.check_evidence_hashes()

    assert not check.passed
    assert "sha256 mismatch" in check.detail
