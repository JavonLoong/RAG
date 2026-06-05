from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
PACKAGE_DIR = REPO_ROOT / "docs" / "challenge_cup"


REQUIRED_DATASET_FIELDS = {
    "id",
    "question",
    "reference_answer",
    "expected_evidence_keywords",
    "task_type",
    "source_scope",
    "expected_modes",
    "grading_notes",
}


REQUIRED_PACKAGE_FILES = [
    "README_先看这里.md",
    "00_项目一页纸.md",
    "01_挑战杯项目书.md",
    "02_技术白皮书.md",
    "03_实验评测报告.md",
    "04_系统演示脚本.md",
    "05_答辩问答手册.md",
    "06_结项验收清单.md",
    "07_评审主张证据矩阵.md",
    "reproducibility/runbook.md",
    "reproducibility/dataset_manifest.md",
    "reproducibility/command_log.md",
]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_challenge_cup_eval_dataset_has_60_schema_complete_records() -> None:
    rows = read_jsonl(DATASET)
    assert len(rows) == 60
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))
    for row in rows:
        assert REQUIRED_DATASET_FIELDS <= set(row)
        assert isinstance(row["expected_evidence_keywords"], list)
        assert row["expected_evidence_keywords"]
        assert isinstance(row["expected_modes"], list)
        assert row["expected_modes"]


def test_build_challenge_cup_package_outputs_required_files() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_challenge_cup_package.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert "docs/challenge_cup" in result.stdout
    for relative in REQUIRED_PACKAGE_FILES:
        path = PACKAGE_DIR / relative
        assert path.exists(), relative
        text = path.read_text(encoding="utf-8")
        forbidden = ("TO" + "DO", "T" + "BD")
        assert not any(marker in text for marker in forbidden)
    one_page = (PACKAGE_DIR / "00_项目一页纸.md").read_text(encoding="utf-8")
    assert "9080" in one_page
    assert "27" in one_page
    assert "GraphRAG" in one_page
    readme = (PACKAGE_DIR / "README_先看这里.md").read_text(encoding="utf-8")
    assert "07_评审主张证据矩阵.md" in readme
    assert "reproducibility/readiness_gate_report.md" in readme
    claim_matrix = (PACKAGE_DIR / "07_评审主张证据矩阵.md").read_text(encoding="utf-8")
    for phrase in ["创新性", "工程闭环", "科学评测", "可复现", "应用边界"]:
        assert phrase in claim_matrix
    for evidence in [
        "evaluation/system_eval_questions.jsonl",
        "browser_demo_smoke_report.md",
        "readiness_gate_report.md",
    ]:
        assert evidence in claim_matrix
    eval_report = (PACKAGE_DIR / "03_实验评测报告.md").read_text(encoding="utf-8")
    assert "GraphRAG 同题子集" in eval_report
    assert "challenge_cup_graphrag_same_question_report.md" in eval_report
    runbook = (PACKAGE_DIR / "reproducibility" / "runbook.md").read_text(encoding="utf-8")
    assert "run_challenge_cup_live_demo_smoke.py" in runbook
    assert "run_challenge_cup_browser_demo_smoke.mjs" in runbook
    assert "check_challenge_cup_readiness.py" in runbook
    manifest = (PACKAGE_DIR / "reproducibility" / "dataset_manifest.md").read_text(encoding="utf-8")
    assert "live_demo_smoke_report.md" in manifest
    assert "browser_demo_smoke_report.md" in manifest
    assert "readiness_gate_report.md" in manifest
    assert "browser_demo_smoke_report.json" in manifest
    assert "desktop_overview.png" in manifest
    assert "desktop_search_results.png" in manifest
    assert "desktop_kg_artifacts.png" in manifest
    assert "mobile_overview.png" in manifest
    command_log = (PACKAGE_DIR / "reproducibility" / "command_log.md").read_text(encoding="utf-8")
    assert "run_challenge_cup_browser_demo_smoke.mjs" in command_log
    assert "browser_demo_smoke_report.json" in command_log
    package_manifest = json.loads((PACKAGE_DIR / "package_manifest.json").read_text(encoding="utf-8"))
    evidence_files = package_manifest["evidence_files"]
    assert "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/browser_demo_smoke_report.json" in evidence_files
    assert "docs/challenge_cup/07_评审主张证据矩阵.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/readiness_gate_report.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/browser_screenshots/desktop_overview.png" in evidence_files
    assert "docs/challenge_cup/reproducibility/browser_screenshots/desktop_kg_artifacts.png" in evidence_files


def test_build_challenge_cup_package_is_idempotent() -> None:
    command = [sys.executable, "scripts/build_challenge_cup_package.py"]
    subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tracked = [
        PACKAGE_DIR / "README_先看这里.md",
        PACKAGE_DIR / "03_实验评测报告.md",
        PACKAGE_DIR / "reproducibility" / "command_log.md",
        PACKAGE_DIR / "package_manifest.json",
    ]
    before = {path: path.read_text(encoding="utf-8") for path in tracked}
    subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    after = {path: path.read_text(encoding="utf-8") for path in tracked}
    assert after == before


def test_build_challenge_cup_package_uses_report_timestamp() -> None:
    subprocess.run(
        [sys.executable, "scripts/build_challenge_cup_package.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    manifest = json.loads((PACKAGE_DIR / "package_manifest.json").read_text(encoding="utf-8"))
    assert manifest["generated_at"] == "2026-06-05 21:06"


def test_browser_smoke_json_is_not_ignored_by_repo_rules() -> None:
    tracked_json_entries = [
        "package.json",
        "docs/challenge_cup/package_manifest.json",
        "docs/challenge_cup/reproducibility/browser_demo_smoke_report.json",
    ]
    for target in tracked_json_entries:
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", "--", target],
            cwd=REPO_ROOT,
        )
        assert result.returncode != 0, target
