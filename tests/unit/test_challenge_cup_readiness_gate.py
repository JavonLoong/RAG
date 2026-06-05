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
    assert "acceptance checklist" in report
    assert "numeric consistency" in report
    assert "special-prize rubric self-assessment" in report
    assert "expert review index" in report
    assert "defense rehearsal pack" in report
    assert "evidence integrity hashes" in report
    assert "browser smoke checks" in report
    assert "KG artifact links" in report
    assert "mobile console health" in report
    assert "search results visible" in report
    assert "60 evaluation questions" in report
    assert "evaluation coverage profile" in report
    assert "application validation evidence" in report
    assert "scenario demo evidence" in report
    assert "scenario walkthrough script" in report
    assert "expert feedback protocol" in report


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


def test_evaluation_coverage_profile_gate_rejects_count_mismatch(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    dataset = tmp_path / "system_eval_questions.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "q001",
                "question": "sample",
                "reference_answer": "sample",
                "expected_evidence_keywords": ["sample"],
                "task_type": "standard_rag_fact",
                "source_scope": "sample_scope",
                "expected_modes": ["keyword"],
                "grading_notes": "sample",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    profile = tmp_path / "evaluation_coverage_profile.json"
    profile.write_text(
        json.dumps(
            {
                "generated_from": "evaluation/system_eval_questions.jsonl",
                "question_count": 60,
                "task_type_counts": {"standard_rag_fact": 1},
                "source_scope_counts": {"sample_scope": 1},
                "expected_mode_counts": {"keyword": 1},
                "questions_with_graphrag_modes": 0,
                "minimums": {"task_types": 10, "source_scopes": 15, "graphrag_questions": 10},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "DATASET", dataset)
    monkeypatch.setattr(module, "EVAL_COVERAGE_PROFILE", profile)

    check = module.check_evaluation_coverage_profile()

    assert not check.passed
    assert "question_count" in check.detail


def test_application_validation_gate_rejects_missing_case_terms(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    validation_doc = tmp_path / "11_应用场景与专家验证.md"
    validation_doc.write_text("# 应用场景\n\n只有泛泛描述。\n", encoding="utf-8")
    validation_report = tmp_path / "application_validation_report.md"
    validation_report.write_text("# 应用验证报告\n\n缺少固定案例证据。\n", encoding="utf-8")
    monkeypatch.setattr(module, "APPLICATION_VALIDATION_DOC", validation_doc)
    monkeypatch.setattr(module, "APPLICATION_VALIDATION_REPORT", validation_report)

    check = module.check_application_validation_evidence()

    assert not check.passed
    assert "GT-07" in check.detail


def test_scenario_demo_gate_rejects_missing_required_records(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    browser_json = tmp_path / "browser_demo_smoke_report.json"
    browser_json.write_text(
        json.dumps(
            {
                "status": "pass",
                "browser": {
                    "query": "燃气轮机异常振动诊断流程",
                    "search_meta": "集合 gas_turbine_ocr_demo_snapshot · 延迟 42.10 ms · 结果 5 · 后端 public-demo",
                    "results_preview": "record demo-maint-thresholds-076\nrecord demo-gt07-fault-021",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    application_report = tmp_path / "application_validation_report.md"
    application_report.write_text("人工确认\n边界结论\n", encoding="utf-8")
    monkeypatch.setattr(module, "BROWSER_SMOKE_JSON", browser_json)
    monkeypatch.setattr(module, "APPLICATION_VALIDATION_REPORT", application_report)

    check = module.check_scenario_demo_evidence()

    assert not check.passed
    assert "demo-gt07-repair-022" in check.detail


def test_browser_visual_evidence_gate_rejects_hidden_search_results(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    screenshot = tmp_path / "desktop_search_results.png"
    screenshot.write_bytes(b"png")
    browser_json = tmp_path / "browser_demo_smoke_report.json"
    browser_json.write_text(
        json.dumps(
            {
                "browser": {
                    "screenshots": {
                        "desktop_overview": str(screenshot),
                        "desktop_search_results": str(screenshot),
                        "desktop_kg_artifacts": str(screenshot),
                        "mobile_overview": str(screenshot),
                    },
                    "kg_artifacts": [{"ok": True}, {"ok": True}, {"ok": True}, {"ok": True}],
                    "search_results_visible": False,
                    "visible_record_ids": ["demo-maint-thresholds-076"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "BROWSER_SMOKE_JSON", browser_json)

    check = module.check_browser_evidence_files()

    assert not check.passed
    assert "search_results_visible" in check.detail


def test_scenario_walkthrough_script_gate_rejects_missing_records(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    demo_script = tmp_path / "demo.md"
    demo_script.write_text("# 系统演示脚本\n\n固定场景演示：燃气轮机异常振动诊断流程。\n", encoding="utf-8")
    monkeypatch.setattr(module, "DEMO_SCRIPT", demo_script)

    check = module.check_scenario_walkthrough_script()

    assert not check.passed
    assert "demo-gt07-repair-022" in check.detail


def test_expert_feedback_protocol_gate_rejects_missing_integrity_terms(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    protocol = tmp_path / "12_专家反馈采集与整改闭环.md"
    protocol.write_text("# 专家反馈\n\n只有泛泛描述。\n", encoding="utf-8")
    form = tmp_path / "expert_feedback_form.md"
    form.write_text("# 表单\n\n评审人姓名\n", encoding="utf-8")
    monkeypatch.setattr(module, "EXPERT_FEEDBACK_PROTOCOL", protocol)
    monkeypatch.setattr(module, "EXPERT_FEEDBACK_FORM", form)

    check = module.check_expert_feedback_protocol()

    assert not check.passed
    assert "不伪造外部意见" in check.detail


def test_acceptance_checklist_gate_rejects_missing_submission_terms(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    checklist = tmp_path / "06_结项验收清单.md"
    checklist.write_text("# 结项验收清单\n\n只有泛泛勾选。\n", encoding="utf-8")
    monkeypatch.setattr(module, "ACCEPTANCE_CHECKLIST", checklist)

    check = module.check_acceptance_checklist()

    assert not check.passed
    assert "未完成项与边界" in check.detail


def test_numeric_consistency_gate_rejects_question_count_mismatch(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "question_count": 59,
                "evidence_files": [
                    "evaluation/system_eval_questions.jsonl",
                    "docs/challenge_cup/reproducibility/readiness_gate_report.md",
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    coverage = tmp_path / "evaluation_coverage_profile.json"
    coverage.write_text(json.dumps({"question_count": 60}, ensure_ascii=False), encoding="utf-8")
    dataset = tmp_path / "system_eval_questions.jsonl"
    dataset.write_text("{}\n" * 60, encoding="utf-8")
    browser_json = tmp_path / "browser_demo_smoke_report.json"
    browser_json.write_text(
        json.dumps(
            {
                "browser": {
                    "search_meta": "集合 gas_turbine_ocr_demo_snapshot · 延迟 41.80 ms · 结果 5 · 后端 public-demo",
                    "search_result_card_count": 5,
                    "visible_record_ids": [
                        "demo-maint-thresholds-076",
                        "demo-structure-fault-130",
                        "demo-gt07-fault-021",
                        "demo-gt07-repair-022",
                        "demo-gt07-manual-023",
                    ],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVAL_COVERAGE_PROFILE", coverage)
    monkeypatch.setattr(module, "DATASET", dataset)
    monkeypatch.setattr(module, "BROWSER_SMOKE_JSON", browser_json)

    check = module.check_numeric_consistency()

    assert not check.passed
    assert "question_count mismatch" in check.detail


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
