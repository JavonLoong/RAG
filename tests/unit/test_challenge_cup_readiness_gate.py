from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "readiness_gate_report.md"
READINESS_SCRIPT = REPO_ROOT / "scripts" / "check_challenge_cup_readiness.py"
DEFENSE_REHEARSAL_SCORECARD_BOUNDARY = (
    "This scorecard proves rehearsal readiness and evidence anchors; it does not prove a live defense "
    "has already happened or guarantee an award."
)
DEFENSE_REHEARSAL_RESULT_PACKET_BOUNDARY = (
    "This packet prepares actual timed rehearsal recording; it does not claim a timed rehearsal has "
    "already been completed."
)
EXPERT_FEEDBACK_REQUEST_PACKET_BOUNDARY = (
    "This packet proves review outreach readiness; it does not claim expert approval, signed feedback, "
    "or production validation."
)
GRAPH_ANSWER_BENCHMARK_BOUNDARY = (
    "This is a deterministic offline answer benchmark over the fixed GraphRAG subset; it does not claim "
    "online LLM answer win-rate or that GraphRAG beats every baseline question."
)
GRAPH_GAP_REMEDIATION_BOUNDARY = (
    "This report closes local partial/missing GraphRAG evidence gaps with auditable supplement records; "
    "it does not claim online LLM answer win-rate, external validation, or that GraphRAG beats every "
    "baseline question."
)


def load_readiness_module():
    spec = importlib.util.spec_from_file_location("check_challenge_cup_readiness", READINESS_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_minimal_pptx(path: Path, slide_texts: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for index, text in enumerate(slide_texts, start=1):
            archive.writestr(
                f"ppt/slides/slide{index}.xml",
                (
                    '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                    f"<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p>"
                    "</p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
                ),
            )


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
    assert "chinese readability" in report
    assert "package evidence files" in report
    assert "submission archive" in report
    assert "submission package verifier" in report
    assert "final acceptance audit" in report
    assert "claim-evidence matrix" in report
    assert "award claims" in report
    assert "acceptance checklist" in report
    assert "numeric consistency" in report
    assert "special-prize rubric self-assessment" in report
    assert "official rubric alignment" in report
    assert "judge objection response matrix" in report
    assert "special prize readiness dashboard" in report
    assert "judge briefing card" in report
    assert "onsite defense runbook" in report
    assert "project handoff checklist" in report
    assert "defense q&a remediation ledger" in report
    assert "review risk response plan" in report
    assert "special prize scoring drill" in report
    assert "poster booth q&a pack" in report
    assert "commercialization roadmap" in report
    assert "poster board asset" in report
    assert "defense control console" in report
    assert "ip and open-source compliance" in report
    assert "local baseline differentiation evidence" in report
    assert "final submission handoff sheet" in report
    assert "expert review index" in report
    assert "defense rehearsal pack" in report
    assert "defense deck" in report
    assert "defense rehearsal scorecard" in report
    assert "defense rehearsal result packet" in report
    assert "expert feedback request packet" in report
    assert "expert feedback outreach ledger" in report
    assert "timed rehearsal schedule ledger" in report
    assert "hard evidence closure board" in report
    assert "hard evidence action pack" in report
    assert "external evidence execution kit" in report
    assert "hard evidence ledger" in report
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
    assert "graphrag evidence audit" in report
    assert "graphrag context demo" in report
    assert "graphrag answer benchmark" in report
    assert "graphrag gap remediation plan" in report
    assert "supported=10, partial=0, missing=0" in report


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


def test_defense_control_console_gate_rejects_missing_console(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    console_path = tmp_path / "docs" / "challenge_cup" / "defense_console" / "index.html"
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": []}), encoding="utf-8")
    hashes.write_text(json.dumps({"files": []}), encoding="utf-8")
    archive_manifest.write_text(json.dumps({"included_files": []}), encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "DEFENSE_CONTROL_CONSOLE", console_path)
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)

    check = module.check_defense_control_console()

    assert not check.passed
    assert "defense_console/index.html missing" in check.detail


def test_judge_objection_matrix_gate_rejects_missing_matrix(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    matrix_md = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "judge_objection_response_matrix.md"
    matrix_json = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "judge_objection_response_matrix.json"
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": []}), encoding="utf-8")
    hashes.write_text(json.dumps({"files": []}), encoding="utf-8")
    archive_manifest.write_text(json.dumps({"included_files": []}), encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "JUDGE_OBJECTION_MATRIX_MD", matrix_md)
    monkeypatch.setattr(module, "JUDGE_OBJECTION_MATRIX_JSON", matrix_json)
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)

    check = module.check_judge_objection_response_matrix()

    assert not check.passed
    assert "judge_objection_response_matrix.md missing" in check.detail
    assert "judge_objection_response_matrix.json missing" in check.detail


def test_challenge_cup_chinese_readability_gate_rejects_mojibake(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    package_dir = tmp_path / "docs" / "challenge_cup"
    package_dir.mkdir(parents=True)
    (package_dir / "README_先看这里.md").write_text(
        "挑战杯 结项 专家反馈 GraphRAG 不伪造 真实计时彩排\n",
        encoding="utf-8",
    )
    mojibake = "清华挑战杯".encode("utf-8").decode("gbk", errors="replace")
    (package_dir / "01_挑战杯项目书.md").write_text(
        f"# 项目书\n\n{mojibake}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "PACKAGE_DIR", package_dir)

    check = module.check_challenge_cup_chinese_readability()

    assert not check.passed
    assert "mojibake" in check.detail
    assert "01_挑战杯项目书.md" in check.detail


def test_challenge_cup_chinese_readability_ignores_readiness_self_report(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    package_dir = tmp_path / "docs" / "challenge_cup"
    repro_dir = package_dir / "reproducibility"
    repro_dir.mkdir(parents=True)
    report = repro_dir / "readiness_gate_report.md"
    report.write_text(f"# self report\n{module.MOJIBAKE_MARKERS[0]}\n", encoding="utf-8")
    (package_dir / "README_先看这里.md").write_text(
        " ".join(module.CHINESE_READABILITY_REQUIRED_TERMS),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "PACKAGE_DIR", package_dir)
    monkeypatch.setattr(module, "REPORT_MD", report)

    check = module.check_challenge_cup_chinese_readability()

    assert check.passed
    assert "1 challenge-cup text artifacts" in check.detail


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


def test_official_rubric_alignment_gate_rejects_missing_sources_and_evidence(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    rubric_json = tmp_path / "official_rubric_alignment.json"
    rubric_md = tmp_path / "official_rubric_alignment.md"
    rubric_json.write_text(
        json.dumps(
            {
                "report_type": "challenge_cup_official_rubric_alignment",
                "official_sources": [
                    {
                        "source_id": "tsinghua_43rd_2025",
                        "url": "",
                        "claims": ["special_prize_count"],
                    }
                ],
                "dimensions": {
                    "academic_or_practical_value": {"official_source_ids": [], "evidence_files": []},
                    "innovation": {"official_source_ids": ["tsinghua_43rd_2025"], "evidence_files": []},
                    "completion": {"official_source_ids": ["tsinghua_43rd_2025"], "evidence_files": []},
                    "defense_performance": {"official_source_ids": ["tsinghua_43rd_2025"], "evidence_files": []},
                },
                "special_prize_policy": {"max_special_prize_count": 7, "may_be_vacant": False},
                "integrity_rules": {"no_award_guarantee": False},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rubric_md.write_text("学术/实用价值\n创新性\n作品完成度\n现场答辩\n", encoding="utf-8")
    manifest = tmp_path / "package_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/official_rubric_alignment.md",
                    "docs/challenge_cup/reproducibility/official_rubric_alignment.json",
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "OFFICIAL_RUBRIC_ALIGNMENT_JSON", rubric_json)
    monkeypatch.setattr(module, "OFFICIAL_RUBRIC_ALIGNMENT_MD", rubric_md)
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: set(module.OFFICIAL_RUBRIC_REQUIRED_PATHS))
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_official_rubric_alignment()

    assert not check.passed
    assert "official_sources" in check.detail
    assert "tsinghua_44th_2026" in check.detail
    assert "academic_or_practical_value" in check.detail
    assert "no_award_guarantee" in check.detail
    assert "official_source_lock" in check.detail


def test_official_rubric_alignment_gate_rejects_stale_or_incomplete_source_lock(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    rubric_json = tmp_path / "official_rubric_alignment.json"
    rubric_md = tmp_path / "official_rubric_alignment.md"
    source_paths = [
        "docs/challenge_cup/00_项目一页纸.md",
        "docs/challenge_cup/02_技术白皮书.md",
        "docs/challenge_cup/package_manifest.json",
        "docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx",
    ]
    for relative in source_paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("evidence", encoding="utf-8")
    payload = {
        "report_type": "challenge_cup_official_rubric_alignment",
        "official_source_count": 5,
        "official_sources": [
            {
                "source_id": source_id,
                "title": source_id,
                "url": f"https://www.tsinghua.edu.cn/{source_id}",
                "checked_at": "2026-06-06",
                "claims": ["claim"],
            }
            for source_id in [
                "tsinghua_44th_2026",
                "tsinghua_43rd_2025",
                "tsinghua_39th_2021",
                "tsinghua_37th_2019",
                "tsinghua_rules_pdf_2017",
            ]
        ],
        "dimensions": {
            "academic_or_practical_value": {
                "official_source_ids": ["tsinghua_37th_2019"],
                "evidence_files": [source_paths[0]],
            },
            "innovation": {
                "official_source_ids": ["tsinghua_39th_2021"],
                "evidence_files": [source_paths[1]],
            },
            "completion": {
                "official_source_ids": ["tsinghua_39th_2021"],
                "evidence_files": [source_paths[2]],
            },
            "defense_performance": {
                "official_source_ids": ["tsinghua_37th_2019"],
                "evidence_files": [source_paths[3]],
            },
        },
        "special_prize_policy": {
            "max_special_prize_count": 7,
            "may_be_vacant": True,
            "latest_public_result_source_id": "tsinghua_44th_2026",
        },
        "integrity_rules": {"no_award_guarantee": True},
        "official_source_lock": {
            "current_as_of": "2026-06-06",
            "latest_public_result": {
                "source_id": "tsinghua_44th_2026",
                "source_url": "https://www.tsinghua.edu.cn/info/1177/125861.htm",
                "published_date": "2026-04-29",
                "final_defense_date": "2026-04-24",
                "award_ceremony_date": "2026-04-26",
                "registration_count": 336,
                "school_finalist_counts": {"undergraduate": 173, "graduate": 9},
                "main_track_award_counts": {
                    "total": 114,
                    "special_prize": 6,
                    "first_prize": 11,
                    "second_prize": 32,
                    "third_prize": 64,
                },
                "exhibition_work_count_min": 199,
            },
            "rubric_dimension_lock": {
                "source_ids": ["tsinghua_37th_2019"],
                "required_dimensions": ["academic_or_practical_value"],
            },
            "recency_policy": {
                "must_recheck_before_final_submission": False,
                "no_award_guarantee": False,
            },
        },
    }
    rubric_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    rubric_md.write_text(
        "官方评审口径对齐表\n"
        "学术/实用价值\n创新性\n作品完成度\n现场答辩\n第44届\n特等奖7项\n不承诺获奖\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "package_manifest.json"
    manifest.write_text(
        json.dumps({"evidence_files": module.OFFICIAL_RUBRIC_REQUIRED_PATHS}, ensure_ascii=False),
        encoding="utf-8",
    )
    hashes = tmp_path / "evidence_hashes.json"
    hashes.write_text(
        json.dumps({"files": [{"path": path} for path in module.OFFICIAL_RUBRIC_REQUIRED_PATHS]}),
        encoding="utf-8",
    )
    archive_manifest = tmp_path / "archive_manifest.json"
    archive_manifest.write_text(
        json.dumps({"included_files": module.OFFICIAL_RUBRIC_REQUIRED_PATHS}),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        module,
        "REPORT_MD",
        tmp_path / "docs" / "challenge_cup" / "reproducibility" / "readiness_gate_report.md",
    )
    monkeypatch.setattr(module, "OFFICIAL_RUBRIC_ALIGNMENT_JSON", rubric_json)
    monkeypatch.setattr(module, "OFFICIAL_RUBRIC_ALIGNMENT_MD", rubric_md)
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: set(module.OFFICIAL_RUBRIC_REQUIRED_PATHS))
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_official_rubric_alignment()

    assert not check.passed
    assert "final_defense_date" in check.detail
    assert "registration_count" in check.detail
    assert "special_prize" in check.detail
    assert "exhibition_work_count_min" in check.detail
    assert "rubric_dimension_lock" in check.detail
    assert "must_recheck_before_final_submission" in check.detail


def test_special_prize_dashboard_gate_rejects_missing_non_self_report_evidence(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    dashboard_json = tmp_path / "special_prize_readiness_dashboard.json"
    dashboard_md = tmp_path / "special_prize_readiness_dashboard.md"
    existing_evidence = "docs/challenge_cup/reproducibility/hard_evidence_action_pack.md"
    self_report_path = module.REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "temporary_self_report.md"
    self_report = self_report_path.relative_to(module.REPO_ROOT).as_posix()
    missing_evidence = "docs/challenge_cup/reproducibility/missing_dashboard_evidence_for_test.md"
    rubric_readiness = [
        {
            "dimension_key": key,
            "readiness_level": "strong_evidence_linked",
            "judge_message": "message",
            "defense_action": "action",
            "evidence_files": [existing_evidence],
        }
        for key in sorted(module.OFFICIAL_RUBRIC_REQUIRED_DIMENSIONS)
    ]
    rubric_readiness[0]["evidence_files"] = [self_report, missing_evidence]
    dashboard_json.write_text(
        json.dumps(
            {
                "report_type": "challenge_cup_special_prize_readiness_dashboard",
                "status": "special_prize_review_ready_with_external_evidence_gaps",
                "no_award_guarantee": True,
                "completion_claim_allowed": False,
                "can_mark_goal_complete": False,
                "official_basis": {
                    "latest_public_result_source_id": module.OFFICIAL_RUBRIC_LATEST_SOURCE_ID,
                    "max_special_prize_count": 7,
                    "may_be_vacant": True,
                },
                "rubric_readiness": rubric_readiness,
                "top_risks": [
                    {"risk_id": "expert_feedback"},
                    {"risk_id": "timed_rehearsal"},
                    {"risk_id": "award_overclaim"},
                ],
                "next_action_files": [existing_evidence],
                "verification_commands": ["python scripts/check_challenge_cup_goal_completion.py"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    dashboard_md.write_text(
        "\n".join(
            [
                "Special Prize Readiness Dashboard",
                "special_prize_review_ready_with_external_evidence_gaps",
                "no_award_guarantee=True",
                "expert_feedback",
                "timed_rehearsal",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "SPECIAL_PRIZE_READINESS_DASHBOARD_JSON", dashboard_json)
    monkeypatch.setattr(module, "SPECIAL_PRIZE_READINESS_DASHBOARD_MD", dashboard_md)
    monkeypatch.setattr(module, "SPECIAL_PRIZE_DASHBOARD_REQUIRED_PATHS", [])
    monkeypatch.setattr(module, "REPORT_MD", self_report_path)

    check = module.check_special_prize_readiness_dashboard()

    assert not check.passed
    assert missing_evidence in check.detail
    assert self_report not in check.detail


def test_judge_briefing_card_gate_rejects_missing_manifest_hash_archive_links(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": []}), encoding="utf-8")
    hashes.write_text(json.dumps({"files": []}), encoding="utf-8")
    archive_manifest.write_text(json.dumps({"included_files": []}), encoding="utf-8")
    card_relative = module.JUDGE_BRIEFING_CARD.relative_to(module.REPO_ROOT).as_posix()
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {card_relative})
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_judge_briefing_card()

    assert not check.passed
    assert "missing manifest entries" in check.detail
    assert "missing hash entries" in check.detail
    assert "missing archive entries" in check.detail
    assert card_relative in check.detail


def test_onsite_defense_runbook_gate_rejects_missing_manifest_hash_archive_links(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": []}), encoding="utf-8")
    hashes.write_text(json.dumps({"files": []}), encoding="utf-8")
    archive_manifest.write_text(json.dumps({"included_files": []}), encoding="utf-8")
    runbook_relative = module.ONSITE_DEFENSE_RUNBOOK.relative_to(module.REPO_ROOT).as_posix()
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {runbook_relative})
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_onsite_defense_runbook()

    assert not check.passed
    assert "missing manifest entries" in check.detail
    assert "missing hash entries" in check.detail
    assert "missing archive entries" in check.detail
    assert runbook_relative in check.detail


def test_project_handoff_checklist_gate_rejects_missing_manifest_hash_archive_links(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": []}), encoding="utf-8")
    hashes.write_text(json.dumps({"files": []}), encoding="utf-8")
    archive_manifest.write_text(json.dumps({"included_files": []}), encoding="utf-8")
    checklist_relative = module.PROJECT_HANDOFF_CHECKLIST.relative_to(module.REPO_ROOT).as_posix()
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {checklist_relative})
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_project_handoff_checklist()

    assert not check.passed
    assert "missing manifest entries" in check.detail
    assert "missing hash entries" in check.detail
    assert "missing archive entries" in check.detail
    assert checklist_relative in check.detail


def test_defense_qa_remediation_ledger_gate_rejects_missing_manifest_hash_archive_links(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": []}), encoding="utf-8")
    hashes.write_text(json.dumps({"files": []}), encoding="utf-8")
    archive_manifest.write_text(json.dumps({"included_files": []}), encoding="utf-8")
    ledger_relative = module.DEFENSE_QA_REMEDIATION_LEDGER.relative_to(module.REPO_ROOT).as_posix()
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {ledger_relative})
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_defense_qa_remediation_ledger()

    assert not check.passed
    assert "missing manifest entries" in check.detail
    assert "missing hash entries" in check.detail
    assert "missing archive entries" in check.detail
    assert ledger_relative in check.detail


def test_review_risk_response_plan_gate_rejects_missing_manifest_hash_archive_links(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": []}), encoding="utf-8")
    hashes.write_text(json.dumps({"files": []}), encoding="utf-8")
    archive_manifest.write_text(json.dumps({"included_files": []}), encoding="utf-8")
    plan_relative = module.REVIEW_RISK_RESPONSE_PLAN.relative_to(module.REPO_ROOT).as_posix()
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {plan_relative})
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_review_risk_response_plan()

    assert not check.passed
    assert "missing manifest entries" in check.detail
    assert "missing hash entries" in check.detail
    assert "missing archive entries" in check.detail
    assert plan_relative in check.detail


def test_special_prize_scoring_drill_gate_rejects_missing_manifest_hash_archive_links(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": []}), encoding="utf-8")
    hashes.write_text(json.dumps({"files": []}), encoding="utf-8")
    archive_manifest.write_text(json.dumps({"included_files": []}), encoding="utf-8")
    drill_relative = module.SPECIAL_PRIZE_SCORING_DRILL.relative_to(module.REPO_ROOT).as_posix()
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {drill_relative})
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_special_prize_scoring_drill()

    assert not check.passed
    assert "missing manifest entries" in check.detail
    assert "missing hash entries" in check.detail
    assert "missing archive entries" in check.detail
    assert drill_relative in check.detail


def test_poster_booth_qa_pack_gate_rejects_missing_manifest_hash_archive_links(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": []}), encoding="utf-8")
    hashes.write_text(json.dumps({"files": []}), encoding="utf-8")
    archive_manifest.write_text(json.dumps({"included_files": []}), encoding="utf-8")
    pack_relative = module.POSTER_BOOTH_QA_PACK.relative_to(module.REPO_ROOT).as_posix()
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {pack_relative})
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_poster_booth_qa_pack()

    assert not check.passed
    assert "missing manifest entries" in check.detail
    assert "missing hash entries" in check.detail
    assert "missing archive entries" in check.detail
    assert pack_relative in check.detail


def test_commercialization_roadmap_gate_rejects_missing_manifest_hash_archive_links(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": []}), encoding="utf-8")
    hashes.write_text(json.dumps({"files": []}), encoding="utf-8")
    archive_manifest.write_text(json.dumps({"included_files": []}), encoding="utf-8")
    roadmap_relative = module.COMMERCIALIZATION_ROADMAP.relative_to(module.REPO_ROOT).as_posix()
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {roadmap_relative})
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_commercialization_roadmap()

    assert not check.passed
    assert "missing manifest entries" in check.detail
    assert "missing hash entries" in check.detail
    assert "missing archive entries" in check.detail
    assert roadmap_relative in check.detail


def test_poster_board_asset_gate_rejects_missing_manifest_hash_archive_links(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": []}), encoding="utf-8")
    hashes.write_text(json.dumps({"files": []}), encoding="utf-8")
    archive_manifest.write_text(json.dumps({"included_files": []}), encoding="utf-8")
    poster_relative = module.POSTER_BOARD_HTML.relative_to(module.REPO_ROOT).as_posix()
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {poster_relative})
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_poster_board_asset()

    assert not check.passed
    assert "missing manifest entries" in check.detail
    assert "missing hash entries" in check.detail
    assert "missing archive entries" in check.detail
    assert poster_relative in check.detail


def test_ip_open_source_compliance_gate_rejects_missing_manifest_hash_archive_links(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": []}), encoding="utf-8")
    hashes.write_text(json.dumps({"files": []}), encoding="utf-8")
    archive_manifest.write_text(json.dumps({"included_files": []}), encoding="utf-8")
    compliance_relative = module.IP_OPEN_SOURCE_COMPLIANCE.relative_to(module.REPO_ROOT).as_posix()
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {compliance_relative})
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_ip_open_source_compliance()

    assert not check.passed
    assert "missing manifest entries" in check.detail
    assert "missing hash entries" in check.detail
    assert "missing archive entries" in check.detail
    assert compliance_relative in check.detail


def test_local_baseline_differentiation_gate_rejects_missing_manifest_hash_archive_links(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": []}), encoding="utf-8")
    hashes.write_text(json.dumps({"files": []}), encoding="utf-8")
    archive_manifest.write_text(json.dumps({"included_files": []}), encoding="utf-8")
    baseline_relative = module.LOCAL_BASELINE_DIFFERENTIATION.relative_to(module.REPO_ROOT).as_posix()
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {baseline_relative})
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_local_baseline_differentiation_evidence()

    assert not check.passed
    assert "missing manifest entries" in check.detail
    assert "missing hash entries" in check.detail
    assert "missing archive entries" in check.detail
    assert baseline_relative in check.detail


def test_external_evidence_execution_kit_gate_rejects_missing_manifest_hash_archive_links(
    monkeypatch,
    tmp_path,
) -> None:
    module = load_readiness_module()
    required_paths = [
        "docs/challenge_cup/reproducibility/external_evidence_execution_kit.md",
        "docs/challenge_cup/reproducibility/external_evidence_execution_kit.json",
        "docs/challenge_cup/reproducibility/external_evidence_execution_kit/expert_review_handoff.md",
        "docs/challenge_cup/reproducibility/external_evidence_execution_kit/timed_rehearsal_observer_sheet.md",
    ]
    for relative in required_paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "External Evidence Execution Kit\n"
            "does_not_satisfy_goal_completion=True\n"
            "\u4e0d\u4f2a\u9020\n"
            "\u771f\u5b9e\u4e13\u5bb6\u53cd\u9988\n"
            "\u771f\u5b9e\u8ba1\u65f6\u5f69\u6392\n",
            encoding="utf-8",
        )
    payload = {
        "report_type": "challenge_cup_external_evidence_execution_kit",
        "status": "ready_for_external_execution_handoff",
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "required_before_goal_completion": ["expert_feedback", "timed_rehearsal"],
        "execution_packets": [
            {
                "packet_id": "expert_feedback_review",
                "hard_evidence_category": "expert_feedback",
                "owner": "project lead",
                "handoff_file": required_paths[2],
                "attachment_files": [required_paths[2]],
                "execution_steps": ["send real packet"],
                "done_when": ["real expert feedback archived"],
                "recording_commands": [
                    "python scripts/record_challenge_cup_hard_evidence.py expert_feedback ... --confirm-real-feedback"
                ],
                "acceptance_gate": "hard_evidence_ledger.categories.expert_feedback.collected_count >= 1",
                "does_not_satisfy_goal_completion": True,
            },
            {
                "packet_id": "timed_rehearsal_observer",
                "hard_evidence_category": "timed_rehearsal",
                "owner": "observer",
                "handoff_file": required_paths[3],
                "attachment_files": [required_paths[3]],
                "execution_steps": ["run real timed rehearsal"],
                "done_when": ["real timed rehearsal archived"],
                "recording_commands": ["python scripts/run_challenge_cup_timed_rehearsal.py ... --confirm-real-rehearsal"],
                "acceptance_gate": "hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1",
                "does_not_satisfy_goal_completion": True,
            },
        ],
    }
    (tmp_path / required_paths[1]).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": []}), encoding="utf-8")
    hashes.write_text(json.dumps({"files": []}), encoding="utf-8")
    archive_manifest.write_text(json.dumps({"included_files": []}), encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "EXTERNAL_EVIDENCE_EXECUTION_KIT_REQUIRED_PATHS", required_paths)
    monkeypatch.setattr(module, "EXTERNAL_EVIDENCE_EXECUTION_KIT_MD", tmp_path / required_paths[0])
    monkeypatch.setattr(module, "EXTERNAL_EVIDENCE_EXECUTION_KIT_JSON", tmp_path / required_paths[1])
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: set(required_paths))
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_external_evidence_execution_kit()

    assert not check.passed
    assert "missing manifest entries" in check.detail
    assert "missing hash entries" in check.detail
    assert "missing archive entries" in check.detail
    assert required_paths[0] in check.detail


def install_control_artifact_links(module, monkeypatch, tmp_path: Path, required_paths: list[str]) -> None:
    manifest = tmp_path / "package_manifest.json"
    hashes = tmp_path / "evidence_hashes.json"
    archive_manifest = tmp_path / "archive_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": required_paths}, ensure_ascii=False), encoding="utf-8")
    hashes.write_text(
        json.dumps({"files": [{"path": relative} for relative in required_paths]}, ensure_ascii=False),
        encoding="utf-8",
    )
    archive_manifest.write_text(json.dumps({"included_files": required_paths}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: set(required_paths))
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())


def test_hard_evidence_action_pack_gate_rejects_missing_preflight_commands(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    required_paths = [
        "docs/challenge_cup/reproducibility/hard_evidence_action_pack.md",
        "docs/challenge_cup/reproducibility/hard_evidence_action_pack.json",
    ]
    action_md = tmp_path / required_paths[0]
    action_json = tmp_path / required_paths[1]
    action_md.parent.mkdir(parents=True, exist_ok=True)
    action_md.write_text(
        "External Hard Evidence Action Pack\n"
        "does_not_satisfy_goal_completion=True\n"
        "expert_feedback\n"
        "timed_rehearsal\n"
        "不伪造\n",
        encoding="utf-8",
    )
    payload = {
        "report_type": "challenge_cup_hard_evidence_action_pack",
        "status": "ready_for_real_external_evidence_collection",
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "required_before_goal_completion": ["expert_feedback", "timed_rehearsal"],
        "operator_outcome": "package can be reviewed; goal cannot be closed",
        "action_streams": [
            {
                "category": "expert_feedback",
                "human_owner": "lead",
                "human_action": "collect real feedback",
                "proof_to_collect": ["source"],
                "ready_packet_files": [required_paths[0]],
                "recording_commands": [
                    "python scripts/record_challenge_cup_expert_outreach.py ...",
                    "python scripts/record_challenge_cup_hard_evidence.py expert_feedback ... --confirm-real-feedback",
                ],
                "acceptance_gate": "hard_evidence_ledger.categories.expert_feedback.collected_count >= 1",
                "does_not_satisfy_goal_completion": True,
            },
            {
                "category": "timed_rehearsal",
                "human_owner": "observer",
                "human_action": "run real timed rehearsal",
                "proof_to_collect": ["timer"],
                "ready_packet_files": [required_paths[0]],
                "recording_commands": [
                    "python scripts/record_challenge_cup_timed_rehearsal_schedule.py ...",
                    "python scripts/run_challenge_cup_timed_rehearsal.py ... --confirm-real-rehearsal",
                    "python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal ... --confirm-real-rehearsal",
                ],
                "acceptance_gate": "hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1",
                "does_not_satisfy_goal_completion": True,
            },
        ],
        "verification_commands": ["python scripts/check_challenge_cup_goal_completion.py"],
    }
    action_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(module, "HARD_EVIDENCE_ACTION_PACK_MD", action_md)
    monkeypatch.setattr(module, "HARD_EVIDENCE_ACTION_PACK_JSON", action_json)
    monkeypatch.setattr(module, "HARD_EVIDENCE_ACTION_PACK_REQUIRED_PATHS", required_paths)
    install_control_artifact_links(module, monkeypatch, tmp_path, required_paths)

    check = module.check_hard_evidence_action_pack()

    assert not check.passed
    assert "preflight_challenge_cup_hard_evidence.py" in check.detail


def test_hard_evidence_closure_board_gate_rejects_missing_preflight_commands(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    required_paths = [
        "docs/challenge_cup/reproducibility/hard_evidence_closure_board.md",
        "docs/challenge_cup/reproducibility/hard_evidence_closure_board.json",
    ]
    board_md = tmp_path / required_paths[0]
    board_json = tmp_path / required_paths[1]
    board_md.parent.mkdir(parents=True, exist_ok=True)
    board_md.write_text(
        "Hard Evidence Closure Board\n"
        "does not satisfy goal completion\n"
        "expert_feedback\n"
        "timed_rehearsal\n"
        f"{module.HARD_EVIDENCE_CLOSURE_BOARD_BOUNDARY}\n",
        encoding="utf-8",
    )
    base_stream = {
        "target_min_count": 1,
        "current_collected_count": 0,
        "required_source_examples": ["signed_feedback_form", "email_reply", "meeting_minutes", "chat_screenshot"],
        "post_collection_commands": [
            "python scripts/build_challenge_cup_hard_evidence_ledger.py",
            "python scripts/build_challenge_cup_package.py",
            "python scripts/check_challenge_cup_readiness.py",
            "python scripts/check_challenge_cup_goal_completion.py",
        ],
    }
    payload = {
        "report_type": "challenge_cup_hard_evidence_closure_board",
        "status": "awaiting_real_external_evidence_closure",
        "no_completion_claimed": True,
        "does_not_satisfy_goal_completion": True,
        "required_before_goal_completion": ["expert_feedback", "timed_rehearsal"],
        "blocker_count": 2,
        "boundary": module.HARD_EVIDENCE_CLOSURE_BOARD_BOUNDARY,
        "closure_streams": [
            {
                **base_stream,
                "category": "expert_feedback",
                "closure_phase": "collect_real_external_feedback",
                "ready_to_execute_commands": [
                    "python scripts/record_challenge_cup_hard_evidence.py expert_feedback ... --confirm-real-feedback"
                ],
                "acceptance_gate": "hard_evidence_ledger.categories.expert_feedback.collected_count >= 1",
            },
            {
                **base_stream,
                "category": "timed_rehearsal",
                "closure_phase": "run_real_timed_rehearsal",
                "required_source_examples": [
                    "timer_screenshot",
                    "screen_recording",
                    "observer_note",
                    "missed_question_list",
                ],
                "ready_to_execute_commands": [
                    "python scripts/run_challenge_cup_timed_rehearsal.py ... --confirm-real-rehearsal",
                    "python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal ... --confirm-real-rehearsal",
                ],
                "acceptance_gate": "hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1",
            },
        ],
        "post_closure_verification_commands": ["python scripts/check_challenge_cup_goal_completion.py"],
    }
    board_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(module, "HARD_EVIDENCE_CLOSURE_BOARD_MD", board_md)
    monkeypatch.setattr(module, "HARD_EVIDENCE_CLOSURE_BOARD_JSON", board_json)
    monkeypatch.setattr(module, "HARD_EVIDENCE_CLOSURE_BOARD_REQUIRED_PATHS", required_paths)
    install_control_artifact_links(module, monkeypatch, tmp_path, required_paths)

    check = module.check_hard_evidence_closure_board()

    assert not check.passed
    assert "preflight_challenge_cup_hard_evidence.py" in check.detail


def test_external_evidence_execution_kit_gate_rejects_missing_preflight_commands(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    required_paths = [
        "docs/challenge_cup/reproducibility/external_evidence_execution_kit.md",
        "docs/challenge_cup/reproducibility/external_evidence_execution_kit.json",
        "docs/challenge_cup/reproducibility/external_evidence_execution_kit/expert_review_handoff.md",
        "docs/challenge_cup/reproducibility/external_evidence_execution_kit/timed_rehearsal_observer_sheet.md",
    ]
    for relative in required_paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "External Evidence Execution Kit\n"
            "does_not_satisfy_goal_completion=True\n"
            "不伪造\n"
            "真实专家反馈\n"
            "真实计时彩排\n",
            encoding="utf-8",
        )
    payload = {
        "report_type": "challenge_cup_external_evidence_execution_kit",
        "status": "ready_for_external_execution_handoff",
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "required_before_goal_completion": ["expert_feedback", "timed_rehearsal"],
        "execution_packets": [
            {
                "packet_id": "expert_feedback_review",
                "hard_evidence_category": "expert_feedback",
                "owner": "lead",
                "handoff_file": required_paths[2],
                "attachment_files": [required_paths[2]],
                "execution_steps": ["send real packet"],
                "done_when": ["real feedback archived"],
                "recording_commands": [
                    "python scripts/record_challenge_cup_hard_evidence.py expert_feedback ... --confirm-real-feedback"
                ],
                "acceptance_gate": "hard_evidence_ledger.categories.expert_feedback.collected_count >= 1",
                "does_not_satisfy_goal_completion": True,
            },
            {
                "packet_id": "timed_rehearsal_observer",
                "hard_evidence_category": "timed_rehearsal",
                "owner": "observer",
                "handoff_file": required_paths[3],
                "attachment_files": [required_paths[3]],
                "execution_steps": ["run real timed rehearsal"],
                "done_when": ["real timed rehearsal archived"],
                "recording_commands": [
                    "python scripts/run_challenge_cup_timed_rehearsal.py ... --confirm-real-rehearsal",
                    "python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal ... --confirm-real-rehearsal",
                ],
                "acceptance_gate": "hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1",
                "does_not_satisfy_goal_completion": True,
            },
        ],
        "verification_commands": [
            "python scripts/build_challenge_cup_external_evidence_execution_kit.py",
            "python scripts/check_challenge_cup_goal_completion.py",
        ],
    }
    (tmp_path / required_paths[1]).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(module, "EXTERNAL_EVIDENCE_EXECUTION_KIT_REQUIRED_PATHS", required_paths)
    monkeypatch.setattr(module, "EXTERNAL_EVIDENCE_EXECUTION_KIT_MD", tmp_path / required_paths[0])
    monkeypatch.setattr(module, "EXTERNAL_EVIDENCE_EXECUTION_KIT_JSON", tmp_path / required_paths[1])
    install_control_artifact_links(module, monkeypatch, tmp_path, required_paths)

    check = module.check_external_evidence_execution_kit()

    assert not check.passed
    assert "preflight_challenge_cup_hard_evidence.py" in check.detail


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


def test_graphrag_evidence_audit_gate_rejects_missing_required_fields(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    graph_json = tmp_path / "challenge_cup_graphrag_same_question_report.json"
    graph_json.write_text(
        json.dumps(
            {
                "total_questions": 60,
                "graphrag_question_count": 10,
                "mode_counts": {"graphrag_context": 8, "graphrag_global": 4},
                "cases": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    graph_md = tmp_path / "challenge_cup_graphrag_same_question_report.md"
    graph_md.write_text(
        "Graph evidence coverage audit\ntriples.csv\n不代表完整 GraphRAG 在线问答已优于 baseline\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "GRAPH_REPORT_JSON", graph_json)
    monkeypatch.setattr(module, "GRAPH_REPORT_MD", graph_md)

    check = module.check_graphrag_same_question_evidence()

    assert not check.passed
    assert "graph_evidence_source" in check.detail


def test_graphrag_context_demo_gate_rejects_generated_answers(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    demo_json = tmp_path / "challenge_cup_graphrag_context_demo.json"
    demo_json.write_text(
        json.dumps(
            {
                "report_type": "challenge_cup_graphrag_context_demo",
                "context_only": False,
                "answer_generated": True,
                "boundary": "wrong",
                "source_graph": "docs/project_deliverables/06_四本书KG工具跑通演示/triples.csv",
                "text_baseline_method": "keyword",
                "demo_case_count": 1,
                "case_ids": ["cc041"],
                "cases": [
                    {
                        "id": "cc041",
                        "text_evidence": [{"id": "T1", "source_type": "text"}],
                        "graph_evidence": [{"id": "G1", "source_type": "graph"}],
                        "citations": [{"id": "T1", "source_type": "text"}, {"id": "G1", "source_type": "graph"}],
                        "prompt_context": "## Text retrieval evidence\n## Graph retrieval evidence",
                        "answer": "generated answer",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    demo_md = tmp_path / "challenge_cup_graphrag_context_demo.md"
    demo_md.write_text(
        "GraphRAG context-only QA demo\n不生成 LLM 答案\ntriples.csv\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "GRAPH_CONTEXT_DEMO_JSON", demo_json)
    monkeypatch.setattr(module, "GRAPH_CONTEXT_DEMO_MD", demo_md)

    check = module.check_graphrag_context_demo()

    assert not check.passed
    assert "context_only" in check.detail


def test_graphrag_answer_benchmark_gate_rejects_online_win_rate_claim(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    benchmark_json = tmp_path / "challenge_cup_graphrag_answer_benchmark.json"
    benchmark_json.write_text(
        json.dumps(
            {
                "report_type": "challenge_cup_graphrag_answer_benchmark",
                "benchmark_mode": "deterministic_offline_reference_keyword_coverage",
                "llm_answer_generated": True,
                "boundary": GRAPH_ANSWER_BENCHMARK_BOUNDARY,
                "dataset": "evaluation/system_eval_questions.jsonl",
                "source_graph_report": "evaluation/reports/challenge_cup_graphrag_same_question_report.json",
                "answer_benchmark_case_count": 10,
                "partial_or_missing_cases_retained": False,
                "best_baseline_method_count": 3,
                "graphrag_supported_answer_case_count": 10,
                "graphrag_missing_answer_case_count": 0,
                "average_best_baseline_reference_keyword_coverage": 0.2,
                "average_graphrag_reference_keyword_coverage": 1.0,
                "summary_verdict": "GraphRAG beats every baseline question.",
                "cases": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    benchmark_md = tmp_path / "challenge_cup_graphrag_answer_benchmark.md"
    benchmark_md.write_text("GraphRAG answer benchmark\n10 道 GraphRAG 同题\n", encoding="utf-8")
    monkeypatch.setattr(module, "GRAPH_ANSWER_BENCHMARK_JSON", benchmark_json)
    monkeypatch.setattr(module, "GRAPH_ANSWER_BENCHMARK_MD", benchmark_md)

    check = module.check_graphrag_answer_benchmark()

    assert not check.passed
    assert "llm_answer_generated" in check.detail


def test_graphrag_gap_remediation_gate_rejects_claimed_fixed_gaps(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    plan_json = tmp_path / "challenge_cup_graphrag_gap_remediation_plan.json"
    plan_json.write_text(
        json.dumps(
            {
                "report_type": "challenge_cup_graphrag_gap_remediation_plan",
                "status": "ready_for_graph_iteration",
                "gaps_marked_fixed": True,
                "boundary": GRAPH_GAP_REMEDIATION_BOUNDARY,
                "source_dataset": "evaluation/system_eval_questions.jsonl",
                "source_graph_report": "evaluation/reports/challenge_cup_graphrag_same_question_report.json",
                "source_answer_benchmark": "evaluation/reports/challenge_cup_graphrag_answer_benchmark.json",
                "total_graph_cases": 10,
                "supported_count": 3,
                "partial_count": 3,
                "missing_count": 4,
                "partial_or_missing_count": 7,
                "priority_counts": {"P0": 4, "P1": 3},
                "no_overclaim_rules": ["不把 partial/missing 改写成成功案例"],
                "required_evidence_to_archive": [
                    "new_triples_or_summary_diff",
                    "source_page_or_doc_anchor",
                    "manual_review_note",
                    "rerun_report_json",
                ],
                "rerun_commands": [
                    "python scripts/build_graphrag_challenge_report.py",
                    "python scripts/build_graphrag_answer_benchmark.py",
                    "python scripts/build_graphrag_gap_remediation_plan.py",
                    "python scripts/check_challenge_cup_readiness.py",
                ],
                "remediation_items": [
                    {
                        "id": "cc032",
                        "current_status": "missing",
                        "priority": "P0",
                        "claim_fixed": True,
                        "missing_expected_keywords": ["OCR"],
                        "action_items": ["sample", "sample", "sample"],
                        "acceptance_evidence": ["rerun_report_json"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    plan_md = tmp_path / "challenge_cup_graphrag_gap_remediation_plan.md"
    plan_md.write_text(
        "GraphRAG 补证整改计划\n"
        "ready_for_graph_iteration\n"
        "不把 partial/missing 改写成成功案例\n"
        "cc032\n"
        "cc043\n"
        f"{GRAPH_GAP_REMEDIATION_BOUNDARY}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "GRAPH_GAP_REMEDIATION_JSON", plan_json)
    monkeypatch.setattr(module, "GRAPH_GAP_REMEDIATION_MD", plan_md)

    check = module.check_graphrag_gap_remediation_plan()

    assert not check.passed
    assert "local_graph_evidence_gaps_closed" in check.detail


def test_defense_rehearsal_scorecard_gate_rejects_missing_timing(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    score_json = tmp_path / "defense_rehearsal_scorecard.json"
    score_json.write_text(
        json.dumps(
            {
                "report_type": "challenge_cup_defense_rehearsal_scorecard",
                "status": "ready_for_timed_rehearsal",
                "boundary": DEFENSE_REHEARSAL_SCORECARD_BOUNDARY,
                "timing_targets": {"opening_seconds": 120},
                "opening_required_points": ["问题", "方法", "完成度", "边界"],
                "demo_timeline": [],
                "killer_questions": [],
                "no_overclaim_boundaries": [],
                "minimum_evidence_anchor_count": 0,
                "evidence_files": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    score_md = tmp_path / "defense_rehearsal_scorecard.md"
    score_md.write_text("答辩彩排计分卡\n90秒开场\n", encoding="utf-8")
    monkeypatch.setattr(module, "DEFENSE_REHEARSAL_SCORECARD_JSON", score_json)
    monkeypatch.setattr(module, "DEFENSE_REHEARSAL_SCORECARD_MD", score_md)

    check = module.check_defense_rehearsal_scorecard()

    assert not check.passed
    assert "opening_seconds" in check.detail


def test_defense_deck_gate_rejects_missing_fixed_scenario(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    deck = tmp_path / "challenge_cup_defense_deck.pptx"
    write_minimal_pptx(
        deck,
        [
            "GraphRAG 60 questions readiness expert feedback boundary"
            for _ in range(10)
        ],
    )
    notes = tmp_path / "challenge_cup_defense_speaker_notes.md"
    notes.write_text(
        "90秒开场\n三分钟演示\nGraphRAG\nreadiness gate\n不宣称已获得专家认可\n",
        encoding="utf-8",
    )
    deck_relative = "docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx"
    notes_relative = "docs/challenge_cup/defense_deck/challenge_cup_defense_speaker_notes.md"
    manifest = tmp_path / "package_manifest.json"
    manifest.write_text(
        json.dumps({"evidence_files": [deck_relative, notes_relative]}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "DEFENSE_DECK_PPTX", deck)
    monkeypatch.setattr(module, "DEFENSE_DECK_NOTES", notes)
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: {deck_relative, notes_relative})
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_defense_deck()

    assert not check.passed
    assert "GT-07" in check.detail


def test_defense_rehearsal_result_packet_gate_rejects_fake_completed_result(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    packet_json = tmp_path / "defense_rehearsal_result_packet.json"
    packet_json.write_text(
        json.dumps(
            {
                "report_type": "challenge_cup_defense_rehearsal_result_packet",
                "status": "ready_to_record_actual_rehearsal",
                "actual_rehearsal_completed": True,
                "boundary": DEFENSE_REHEARSAL_RESULT_PACKET_BOUNDARY,
                "timing_targets": {
                    "opening_seconds": 90,
                    "demo_seconds": 180,
                    "offline_fallback_seconds": 20,
                    "killer_question_seconds": 30,
                },
                "pass_fail_rules": {
                    "opening_actual_seconds_max": 90,
                    "demo_actual_seconds_max": 180,
                    "offline_fallback_actual_seconds_max": 20,
                    "each_killer_question_actual_seconds_max": 30,
                    "required_killer_question_count": 5,
                },
                "required_archive_evidence_types": ["计时截图", "彩排录屏", "观察员签字或备注", "问题遗漏清单"],
                "result_template": {
                    "overall_result": "pass",
                    "opening_actual_seconds": 88,
                    "demo_actual_seconds": 175,
                    "offline_fallback_actual_seconds": 18,
                    "killer_question_results": [],
                },
                "evidence_files": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    packet_md = tmp_path / "defense_rehearsal_result_packet.md"
    packet_md.write_text(
        "答辩计时彩排结果归档包\n"
        "尚未记录真实计时彩排\n"
        "不伪造现场彩排记录\n"
        "opening_actual_seconds\n"
        "offline_fallback_actual_seconds\n"
        "killer_question_results\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "DEFENSE_REHEARSAL_RESULT_PACKET_JSON", packet_json)
    monkeypatch.setattr(module, "DEFENSE_REHEARSAL_RESULT_PACKET_MD", packet_md)

    check = module.check_defense_rehearsal_result_packet()

    assert not check.passed
    assert "actual_rehearsal_completed" in check.detail


def test_expert_feedback_request_packet_gate_rejects_claimed_approval(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    packet_json = tmp_path / "expert_feedback_request_packet.json"
    packet_json.write_text(
        json.dumps(
            {
                "report_type": "challenge_cup_expert_feedback_request_packet",
                "status": "ready_to_send",
                "no_external_feedback_claimed": False,
                "boundary": EXPERT_FEEDBACK_REQUEST_PACKET_BOUNDARY,
                "recipient_roles": ["指导教师", "行业专家", "实验室同学"],
                "review_dimensions": ["实用性", "创新性", "工程完成度", "评测可信度", "答辩清晰度", "边界严谨性"],
                "required_archive_evidence_types": ["签字页", "邮件回复", "会议纪要", "聊天记录截图"],
                "review_questions": ["q1"] * 8,
                "sendable_message": {"subject": "sample", "body": "sample", "attachments": []},
                "minimum_evidence_file_count": 10,
                "evidence_files": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    packet_md = tmp_path / "expert_feedback_request_packet.md"
    packet_md.write_text("专家反馈外发包\n待真实反馈归档\n不宣称已获得专家认可\n建议邮件主题\n签字页\n邮件回复\n会议纪要\n聊天记录截图\n", encoding="utf-8")
    monkeypatch.setattr(module, "EXPERT_FEEDBACK_REQUEST_PACKET_JSON", packet_json)
    monkeypatch.setattr(module, "EXPERT_FEEDBACK_REQUEST_PACKET_MD", packet_md)

    check = module.check_expert_feedback_request_packet()

    assert not check.passed
    assert "no_external_feedback_claimed" in check.detail


def test_expert_feedback_outreach_ledger_gate_rejects_overclaim_and_invalid_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_readiness_module()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    ledger_json = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "expert_feedback_outreach_ledger.json"
    ledger_md = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "expert_feedback_outreach_ledger.md"
    outreach_readme = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "expert_feedback_outreach" / "README.md"
    metadata_relative = "docs/challenge_cup/reproducibility/expert_feedback_outreach/advisor-a-20260606.json"
    metadata_path = tmp_path / metadata_relative
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(
        json.dumps(
            {
                "outreach_type": "expert_feedback_request",
                "recipient_alias": "advisor-a",
                "recipient_role": "advisor",
                "channel": "email",
                "sent_date": "June 6 2026",
                "status": "sent",
                "request_source_path": metadata_relative,
                "requested_review_dimensions": ["practicality"],
                "requested_attachment_paths": ["docs/challenge_cup/00_项目一页纸.md"],
                "followup_due_date": "2026/06/09",
                "no_external_feedback_claimed": False,
                "does_not_satisfy_hard_evidence": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ledger_json.parent.mkdir(parents=True, exist_ok=True)
    ledger_json.write_text(
        json.dumps(
            {
                "report_type": "challenge_cup_expert_feedback_outreach_ledger",
                "status": "outreach_recorded_awaiting_response",
                "no_external_feedback_claimed": False,
                "does_not_satisfy_goal_completion": False,
                "boundary": module.EXPERT_FEEDBACK_OUTREACH_LEDGER_BOUNDARY,
                "outreach_record_count": 1,
                "metadata_record_count": 1,
                "outreach_files": [metadata_relative],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ledger_md.write_text(
        "Expert Feedback Outreach Ledger\n"
        "Outreach records prove that a real request was sent or followed up.\n"
        "They do not prove expert approval.\n",
        encoding="utf-8",
    )
    outreach_readme.write_text("Expert Feedback Outreach Intake\n", encoding="utf-8")
    package_manifest = tmp_path / "package_manifest.json"
    evidence_files = [
        "docs/challenge_cup/reproducibility/expert_feedback_outreach_ledger.md",
        "docs/challenge_cup/reproducibility/expert_feedback_outreach_ledger.json",
        "docs/challenge_cup/reproducibility/expert_feedback_outreach/README.md",
        metadata_relative,
    ]
    package_manifest.write_text(json.dumps({"evidence_files": evidence_files}, ensure_ascii=False), encoding="utf-8")
    evidence_hashes = tmp_path / "evidence_hashes.json"
    evidence_hashes.write_text(
        json.dumps({"files": [{"path": relative} for relative in evidence_files]}, ensure_ascii=False),
        encoding="utf-8",
    )
    archive_manifest = tmp_path / "archive_manifest.json"
    archive_manifest.write_text(json.dumps({"included_files": evidence_files}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(module, "EXPERT_FEEDBACK_OUTREACH_LEDGER_JSON", ledger_json)
    monkeypatch.setattr(module, "EXPERT_FEEDBACK_OUTREACH_LEDGER_MD", ledger_md)
    monkeypatch.setattr(module, "EXPERT_FEEDBACK_OUTREACH_README", outreach_readme)
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", package_manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", evidence_hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: set(evidence_files))
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_expert_feedback_outreach_ledger()

    assert not check.passed
    assert "no_external_feedback_claimed" in check.detail
    assert "does_not_satisfy_goal_completion" in check.detail
    assert "does_not_satisfy_hard_evidence" in check.detail
    assert "sent_date" in check.detail
    assert "followup_due_date" in check.detail
    assert "request_source_path" in check.detail
    assert "requested_review_dimensions" in check.detail


def test_timed_rehearsal_schedule_ledger_gate_rejects_overclaim_and_invalid_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_readiness_module()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    ledger_json = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "timed_rehearsal_schedule_ledger.json"
    ledger_md = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "timed_rehearsal_schedule_ledger.md"
    schedule_readme = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "timed_rehearsal_schedule" / "README.md"
    metadata_relative = "docs/challenge_cup/reproducibility/timed_rehearsal_schedule/rehearsal-schedule.json"
    metadata_path = tmp_path / metadata_relative
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(
        json.dumps(
            {
                "schedule_type": "timed_rehearsal_schedule",
                "scheduled_date": "June 6 2026",
                "observer": "observer-a",
                "venue_or_channel": "meeting-room-a",
                "status": "scheduled",
                "schedule_source_path": metadata_relative,
                "planned_timing_targets": {
                    "opening_planned_seconds": 90,
                    "demo_planned_seconds": 180,
                    "offline_fallback_planned_seconds": 20,
                    "killer_question_planned_seconds": 30,
                    "killer_question_count": 4,
                },
                "checklist_items": ["timer visible"],
                "required_hard_evidence_after_run": ["observer_note"],
                "no_timed_rehearsal_claimed": False,
                "does_not_satisfy_hard_evidence": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ledger_json.parent.mkdir(parents=True, exist_ok=True)
    ledger_json.write_text(
        json.dumps(
            {
                "report_type": "challenge_cup_timed_rehearsal_schedule_ledger",
                "status": "rehearsal_scheduled_awaiting_run",
                "no_timed_rehearsal_claimed": False,
                "does_not_satisfy_goal_completion": False,
                "boundary": module.TIMED_REHEARSAL_SCHEDULE_LEDGER_BOUNDARY,
                "schedule_record_count": 1,
                "metadata_record_count": 1,
                "schedule_files": [metadata_relative],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ledger_md.write_text(
        "Timed Rehearsal Schedule Ledger\n"
        "Schedule records prove that a real timed rehearsal was scheduled or observer preparation was recorded.\n"
        "They do not prove a timed rehearsal was completed.\n",
        encoding="utf-8",
    )
    schedule_readme.write_text("Timed Rehearsal Schedule Intake\n", encoding="utf-8")
    package_manifest = tmp_path / "package_manifest.json"
    evidence_files = [
        "docs/challenge_cup/reproducibility/timed_rehearsal_schedule_ledger.md",
        "docs/challenge_cup/reproducibility/timed_rehearsal_schedule_ledger.json",
        "docs/challenge_cup/reproducibility/timed_rehearsal_schedule/README.md",
        metadata_relative,
    ]
    package_manifest.write_text(json.dumps({"evidence_files": evidence_files}, ensure_ascii=False), encoding="utf-8")
    evidence_hashes = tmp_path / "evidence_hashes.json"
    evidence_hashes.write_text(
        json.dumps({"files": [{"path": relative} for relative in evidence_files]}, ensure_ascii=False),
        encoding="utf-8",
    )
    archive_manifest = tmp_path / "archive_manifest.json"
    archive_manifest.write_text(json.dumps({"included_files": evidence_files}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(module, "TIMED_REHEARSAL_SCHEDULE_LEDGER_JSON", ledger_json)
    monkeypatch.setattr(module, "TIMED_REHEARSAL_SCHEDULE_LEDGER_MD", ledger_md)
    monkeypatch.setattr(module, "TIMED_REHEARSAL_SCHEDULE_README", schedule_readme)
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", package_manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", evidence_hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: set(evidence_files))
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_timed_rehearsal_schedule_ledger()

    assert not check.passed
    assert "no_timed_rehearsal_claimed" in check.detail
    assert "does_not_satisfy_goal_completion" in check.detail
    assert "does_not_satisfy_hard_evidence" in check.detail
    assert "scheduled_date" in check.detail
    assert "schedule_source_path" in check.detail
    assert "killer_question_count" in check.detail
    assert "checklist_items" in check.detail


def test_hard_evidence_closure_board_gate_rejects_overclaim_and_missing_streams(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_readiness_module()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    board_json = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_closure_board.json"
    board_md = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_closure_board.md"
    board_json.parent.mkdir(parents=True)
    board_json.write_text(
        json.dumps(
            {
                "report_type": "challenge_cup_hard_evidence_closure_board",
                "status": "complete",
                "no_completion_claimed": False,
                "does_not_satisfy_goal_completion": False,
                "required_before_goal_completion": ["expert_feedback", "timed_rehearsal"],
                "blocker_count": 1,
                "closure_streams": [
                    {
                        "category": "expert_feedback",
                        "required_source_examples": [],
                        "ready_to_execute_commands": [],
                        "post_collection_commands": [],
                        "acceptance_gate": "",
                    }
                ],
                "post_closure_verification_commands": [],
                "boundary": module.HARD_EVIDENCE_CLOSURE_BOARD_BOUNDARY,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    board_md.write_text("Hard Evidence Closure Board\n", encoding="utf-8")
    package_manifest = tmp_path / "package_manifest.json"
    evidence_files = [
        "docs/challenge_cup/reproducibility/hard_evidence_closure_board.md",
        "docs/challenge_cup/reproducibility/hard_evidence_closure_board.json",
    ]
    package_manifest.write_text(json.dumps({"evidence_files": evidence_files}, ensure_ascii=False), encoding="utf-8")
    evidence_hashes = tmp_path / "evidence_hashes.json"
    evidence_hashes.write_text(
        json.dumps({"files": [{"path": relative} for relative in evidence_files]}, ensure_ascii=False),
        encoding="utf-8",
    )
    archive_manifest = tmp_path / "archive_manifest.json"
    archive_manifest.write_text(json.dumps({"included_files": evidence_files}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(module, "HARD_EVIDENCE_CLOSURE_BOARD_JSON", board_json)
    monkeypatch.setattr(module, "HARD_EVIDENCE_CLOSURE_BOARD_MD", board_md)
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", package_manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", evidence_hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: set(evidence_files))
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_hard_evidence_closure_board()

    assert not check.passed
    assert "no_completion_claimed" in check.detail
    assert "does_not_satisfy_goal_completion" in check.detail
    assert "timed_rehearsal" in check.detail
    assert "ready_to_execute_commands" in check.detail


def test_hard_evidence_ledger_gate_rejects_fake_completion(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    ledger_json = tmp_path / "hard_evidence_ledger.json"
    ledger_md = tmp_path / "hard_evidence_ledger.md"
    root_readme = tmp_path / "hard_evidence_README.md"
    expert_readme = tmp_path / "expert_feedback_README.md"
    rehearsal_readme = tmp_path / "timed_rehearsal_README.md"
    ledger_json.write_text(
        json.dumps(
            {
                "report_type": "challenge_cup_hard_evidence_ledger",
                "status": "hard_evidence_complete",
                "completion_claim_allowed": True,
                "required_before_goal_completion": ["expert_feedback", "timed_rehearsal"],
                "categories": {
                    "expert_feedback": {"collected_count": 0, "evidence_files": []},
                    "timed_rehearsal": {"collected_count": 0, "evidence_files": []},
                },
                "no_fake_evidence_rules": ["\u4e0d\u4f2a\u9020\u5916\u90e8\u610f\u89c1"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ledger_md.write_text(
        "\u771f\u5b9e\u4e13\u5bb6\u53cd\u9988\n"
        "\u771f\u5b9e\u8ba1\u65f6\u5f69\u6392\n"
        "\u4e0d\u4f2a\u9020\n"
        "\u4e0d\u80fd\u6807\u8bb0\u76ee\u6807\u5b8c\u6210\n",
        encoding="utf-8",
    )
    for path in (root_readme, expert_readme, rehearsal_readme):
        path.write_text("hard evidence intake\n", encoding="utf-8")
    manifest = tmp_path / "package_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence_ledger.md",
                    "docs/challenge_cup/reproducibility/hard_evidence_ledger.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/README.md",
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/README.md",
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/README.md",
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "HARD_EVIDENCE_LEDGER_JSON", ledger_json)
    monkeypatch.setattr(module, "HARD_EVIDENCE_LEDGER_MD", ledger_md)
    monkeypatch.setattr(module, "HARD_EVIDENCE_README", root_readme)
    monkeypatch.setattr(module, "HARD_EVIDENCE_EXPERT_README", expert_readme)
    monkeypatch.setattr(module, "HARD_EVIDENCE_REHEARSAL_README", rehearsal_readme)
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: set(module.HARD_EVIDENCE_REQUIRED_PATHS))
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())

    check = module.check_hard_evidence_ledger()

    assert not check.passed
    assert "completion_claim_allowed" in check.detail


def install_hard_evidence_fixture(
    module,
    monkeypatch,
    tmp_path: Path,
    payload: dict,
    raw_files: dict[str, dict],
) -> None:
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    path_attrs = {
        "HARD_EVIDENCE_LEDGER_JSON": "HARD_EVIDENCE_LEDGER_JSON_RELATIVE",
        "HARD_EVIDENCE_LEDGER_MD": "HARD_EVIDENCE_LEDGER_MD_RELATIVE",
        "HARD_EVIDENCE_README": "HARD_EVIDENCE_README_RELATIVE",
        "HARD_EVIDENCE_EXPERT_README": "HARD_EVIDENCE_EXPERT_README_RELATIVE",
        "HARD_EVIDENCE_REHEARSAL_README": "HARD_EVIDENCE_REHEARSAL_README_RELATIVE",
    }
    for attr, relative_attr in path_attrs.items():
        monkeypatch.setattr(module, attr, tmp_path / getattr(module, relative_attr))

    module.HARD_EVIDENCE_LEDGER_JSON.parent.mkdir(parents=True, exist_ok=True)
    module.HARD_EVIDENCE_LEDGER_JSON.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    module.HARD_EVIDENCE_LEDGER_MD.write_text(
        "\u771f\u5b9e\u4e13\u5bb6\u53cd\u9988\n"
        "\u771f\u5b9e\u8ba1\u65f6\u5f69\u6392\n"
        "\u4e0d\u4f2a\u9020\n"
        "\u4e0d\u80fd\u6807\u8bb0\u76ee\u6807\u5b8c\u6210\n",
        encoding="utf-8",
    )
    for path in (module.HARD_EVIDENCE_README, module.HARD_EVIDENCE_EXPERT_README, module.HARD_EVIDENCE_REHEARSAL_README):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("hard evidence intake\n", encoding="utf-8")
    for relative, content in raw_files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")

    evidence_files = module.HARD_EVIDENCE_REQUIRED_PATHS + sorted(raw_files)
    manifest = tmp_path / "package_manifest.json"
    manifest.write_text(json.dumps({"evidence_files": evidence_files}, ensure_ascii=False), encoding="utf-8")
    hashes = tmp_path / "evidence_hashes.json"
    hashes.write_text(
        json.dumps({"files": [{"path": path} for path in evidence_files]}, ensure_ascii=False),
        encoding="utf-8",
    )
    archive_manifest = tmp_path / "challenge_cup_submission_archive_manifest.json"
    archive_manifest.write_text(json.dumps({"included_files": evidence_files}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(module, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(module, "EVIDENCE_HASHES", hashes)
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", archive_manifest)
    monkeypatch.setattr(module, "git_tracked_paths", lambda: set(evidence_files))
    monkeypatch.setattr(module, "git_dirty_paths", lambda paths: set())


def hard_evidence_complete_payload(expert_file: str, rehearsal_file: str) -> dict:
    return {
        "report_type": "challenge_cup_hard_evidence_ledger",
        "status": "hard_evidence_collected_pending_review",
        "completion_claim_allowed": True,
        "required_before_goal_completion": ["expert_feedback", "timed_rehearsal"],
        "categories": {
            "expert_feedback": {
                "required_min_count": 1,
                "collected_count": 1,
                "accepted_evidence_types": ["signed_feedback_form", "email_reply", "meeting_minutes", "chat_screenshot"],
                "required_metadata_fields": [
                    "reviewer_identity",
                    "role_or_org",
                    "review_date",
                    "feedback_source_path",
                    "review_dimensions",
                    "remediation_record",
                    "real_feedback_confirmed",
                ],
                "evidence_files": [expert_file],
            },
            "timed_rehearsal": {
                "required_min_count": 1,
                "collected_count": 1,
                "accepted_evidence_types": ["timer_screenshot", "screen_recording", "observer_note", "missed_question_list"],
                "required_metadata_fields": [
                    "rehearsal_date",
                    "observer",
                    "opening_actual_seconds",
                    "demo_actual_seconds",
                    "offline_fallback_actual_seconds",
                    "killer_question_results",
                    "recording_or_timer_source_path",
                    "real_rehearsal_confirmed",
                ],
                "evidence_files": [rehearsal_file],
            },
        },
        "no_fake_evidence_rules": ["\u4e0d\u4f2a\u9020\u5916\u90e8\u610f\u89c1"],
    }


def test_hard_evidence_ledger_gate_rejects_expert_feedback_without_required_metadata(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    expert_file = "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/expert_feedback_summary.json"
    rehearsal_file = "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/timed_rehearsal_summary.json"
    install_hard_evidence_fixture(
        module,
        monkeypatch,
        tmp_path,
        hard_evidence_complete_payload(expert_file, rehearsal_file),
        {
            expert_file: {
                "evidence_type": "email_reply",
                "role_or_org": "advisor",
                "review_date": "2026-06-06",
                "feedback_source_path": expert_file,
                "review_dimensions": ["usefulness", "innovation", "boundary"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": True,
            },
            rehearsal_file: {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-a",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [{"question_index": index, "actual_seconds": 25} for index in range(1, 6)],
                "recording_or_timer_source_path": rehearsal_file,
                "real_rehearsal_confirmed": True,
            },
        },
    )

    check = module.check_hard_evidence_ledger()

    assert not check.passed
    assert "reviewer_identity" in check.detail


def test_hard_evidence_ledger_gate_rejects_timed_rehearsal_over_time_or_under_question_count(
    monkeypatch,
    tmp_path,
) -> None:
    module = load_readiness_module()
    expert_file = "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/expert_feedback_summary.json"
    rehearsal_file = "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/timed_rehearsal_summary.json"
    install_hard_evidence_fixture(
        module,
        monkeypatch,
        tmp_path,
        hard_evidence_complete_payload(expert_file, rehearsal_file),
        {
            expert_file: {
                "evidence_type": "email_reply",
                "reviewer_identity": "reviewer-a",
                "role_or_org": "advisor",
                "review_date": "2026-06-06",
                "feedback_source_path": expert_file,
                "review_dimensions": ["usefulness", "innovation", "boundary"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": True,
            },
            rehearsal_file: {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-a",
                "opening_actual_seconds": 96,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [{"question_index": 1, "actual_seconds": 25}],
                "recording_or_timer_source_path": rehearsal_file,
                "real_rehearsal_confirmed": True,
            },
        },
    )

    check = module.check_hard_evidence_ledger()

    assert not check.passed
    assert "opening_actual_seconds" in check.detail
    assert "killer_question_results" in check.detail


def test_hard_evidence_ledger_gate_rejects_metadata_without_real_source_attachment(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    expert_file = "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/expert_feedback_summary.json"
    rehearsal_file = "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/timed_rehearsal_summary.json"
    install_hard_evidence_fixture(
        module,
        monkeypatch,
        tmp_path,
        hard_evidence_complete_payload(expert_file, rehearsal_file),
        {
            expert_file: {
                "evidence_type": "email_reply",
                "reviewer_identity": "reviewer-a",
                "role_or_org": "advisor",
                "review_date": "2026-06-06",
                "feedback_source_path": expert_file,
                "review_dimensions": ["usefulness", "innovation", "boundary"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": True,
            },
            rehearsal_file: {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-a",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [{"question_index": index, "actual_seconds": 25} for index in range(1, 6)],
                "recording_or_timer_source_path": rehearsal_file,
                "real_rehearsal_confirmed": True,
            },
        },
    )

    check = module.check_hard_evidence_ledger()

    assert not check.passed
    assert "feedback_source_path" in check.detail
    assert "recording_or_timer_source_path" in check.detail


def test_hard_evidence_ledger_gate_rejects_metadata_without_real_confirmation(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    expert_file = "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/expert_feedback_summary.json"
    rehearsal_file = "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/timed_rehearsal_summary.json"
    expert_attachment = "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/email_reply.txt"
    rehearsal_attachment = "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/timer_note.txt"
    install_hard_evidence_fixture(
        module,
        monkeypatch,
        tmp_path,
        hard_evidence_complete_payload(expert_file, rehearsal_file),
        {
            expert_file: {
                "evidence_type": "email_reply",
                "reviewer_identity": "reviewer-a",
                "role_or_org": "advisor",
                "review_date": "2026-06-06",
                "feedback_source_path": expert_attachment,
                "review_dimensions": ["usefulness", "innovation", "boundary"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": False,
            },
            rehearsal_file: {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-a",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [{"question_index": index, "actual_seconds": 25} for index in range(1, 6)],
                "recording_or_timer_source_path": rehearsal_attachment,
            },
            expert_attachment: {"note": "source attachment placeholder for test"},
            rehearsal_attachment: {"note": "timer source attachment placeholder for test"},
        },
    )

    check = module.check_hard_evidence_ledger()

    assert not check.passed
    assert "real_feedback_confirmed" in check.detail
    assert "real_rehearsal_confirmed" in check.detail


def test_hard_evidence_ledger_gate_rejects_non_iso_evidence_dates(monkeypatch, tmp_path) -> None:
    module = load_readiness_module()
    expert_file = "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/expert_feedback_summary.json"
    rehearsal_file = "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/timed_rehearsal_summary.json"
    expert_attachment = "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/email_reply.txt"
    rehearsal_attachment = "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/timer_note.txt"
    install_hard_evidence_fixture(
        module,
        monkeypatch,
        tmp_path,
        hard_evidence_complete_payload(expert_file, rehearsal_file),
        {
            expert_file: {
                "evidence_type": "email_reply",
                "reviewer_identity": "reviewer-a",
                "role_or_org": "advisor",
                "review_date": "June 6 2026",
                "feedback_source_path": expert_attachment,
                "review_dimensions": ["usefulness", "innovation", "boundary"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": True,
            },
            rehearsal_file: {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026/06/06",
                "observer": "observer-a",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [{"question_index": index, "actual_seconds": 25} for index in range(1, 6)],
                "recording_or_timer_source_path": rehearsal_attachment,
                "real_rehearsal_confirmed": True,
            },
            expert_attachment: {"note": "source attachment placeholder for test"},
            rehearsal_attachment: {"note": "timer source attachment placeholder for test"},
        },
    )

    check = module.check_hard_evidence_ledger()

    assert not check.passed
    assert "review_date" in check.detail
    assert "rehearsal_date" in check.detail


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


def test_submission_archive_gate_rejects_mismatched_hash(monkeypatch, tmp_path) -> None:
    subprocess.run(
        [sys.executable, "scripts/build_challenge_cup_package.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    module = load_readiness_module()
    payload = json.loads(module.SUBMISSION_ARCHIVE_MANIFEST.read_text(encoding="utf-8"))
    payload["sha256"] = "0" * 64
    bad_manifest = tmp_path / "challenge_cup_submission_archive_manifest.json"
    bad_manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(module, "SUBMISSION_ARCHIVE_MANIFEST", bad_manifest)

    check = module.check_submission_archive()

    assert not check.passed
    assert "sha256 mismatch" in check.detail
