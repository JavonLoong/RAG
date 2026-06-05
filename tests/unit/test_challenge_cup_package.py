from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
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
    "08_特等奖评审自评表.md",
    "09_专家快速审阅索引.md",
    "10_答辩攻防与彩排卡.md",
    "11_应用场景与专家验证.md",
    "12_专家反馈采集与整改闭环.md",
    "defense_deck/challenge_cup_defense_speaker_notes.md",
    "reproducibility/runbook.md",
    "reproducibility/dataset_manifest.md",
    "reproducibility/goal_completion_report.md",
    "reproducibility/evaluation_coverage_profile.json",
    "reproducibility/evidence_hashes.json",
    "reproducibility/application_validation_report.md",
    "reproducibility/expert_feedback_form.md",
    "reproducibility/graphrag_manual_evidence_supplement.csv",
    "reproducibility/defense_rehearsal_scorecard.md",
    "reproducibility/defense_rehearsal_scorecard.json",
    "reproducibility/defense_rehearsal_result_packet.md",
    "reproducibility/defense_rehearsal_result_packet.json",
    "reproducibility/expert_feedback_request_packet.md",
    "reproducibility/expert_feedback_request_packet.json",
    "reproducibility/expert_feedback_outreach_ledger.md",
    "reproducibility/expert_feedback_outreach_ledger.json",
    "reproducibility/expert_feedback_outreach/README.md",
    "reproducibility/official_rubric_alignment.md",
    "reproducibility/official_rubric_alignment.json",
    "reproducibility/hard_evidence_ledger.md",
    "reproducibility/hard_evidence_ledger.json",
    "reproducibility/hard_evidence/README.md",
    "reproducibility/hard_evidence/expert_feedback/README.md",
    "reproducibility/hard_evidence/timed_rehearsal/README.md",
    "reproducibility/challenge_cup_submission_archive_manifest.json",
    "reproducibility/command_log.md",
]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pptx_slide_text(path: Path) -> tuple[int, str]:
    with zipfile.ZipFile(path) as archive:
        slide_names = sorted(
            name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        texts: list[str] = []
        for name in slide_names:
            root = ET.fromstring(archive.read(name))
            texts.extend(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
    return len(slide_names), "\n".join(texts)


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
    assert "08_特等奖评审自评表.md" in readme
    assert "09_专家快速审阅索引.md" in readme
    assert "10_答辩攻防与彩排卡.md" in readme
    assert "11_应用场景与专家验证.md" in readme
    assert "12_专家反馈采集与整改闭环.md" in readme
    assert "defense_deck/challenge_cup_defense_deck.pptx" in readme
    assert "defense_deck/challenge_cup_defense_speaker_notes.md" in readme
    assert "reproducibility/official_rubric_alignment.md" in readme
    assert "reproducibility/hard_evidence_ledger.md" in readme
    assert "reproducibility/application_validation_report.md" in readme
    assert "reproducibility/expert_feedback_form.md" in readme
    assert "reproducibility/expert_feedback_outreach_ledger.md" in readme
    assert "reproducibility/readiness_gate_report.md" in readme
    assert "reproducibility/goal_completion_report.md" in readme
    acceptance_checklist = (PACKAGE_DIR / "06_结项验收清单.md").read_text(encoding="utf-8")
    for phrase in ["结项验收口径", "可提交材料", "验收步骤", "现场演示与离线备份", "未完成项与边界", "验收结论"]:
        assert phrase in acceptance_checklist
    for evidence in [
        "package_manifest.json",
        "readiness_gate_report.md",
        "challenge_cup_defense_deck.pptx",
        "challenge_cup_defense_speaker_notes.md",
        "browser_demo_smoke_report.md",
        "application_validation_report.md",
        "expert_feedback_form.md",
    ]:
        assert evidence in acceptance_checklist
    claim_matrix = (PACKAGE_DIR / "07_评审主张证据矩阵.md").read_text(encoding="utf-8")
    for phrase in ["创新性", "工程闭环", "科学评测", "可复现", "应用验证", "应用边界"]:
        assert phrase in claim_matrix
    for evidence in [
        "evaluation/system_eval_questions.jsonl",
        "11_应用场景与专家验证.md",
        "12_专家反馈采集与整改闭环.md",
        "application_validation_report.md",
        "expert_feedback_form.md",
        "browser_demo_smoke_report.md",
        "readiness_gate_report.md",
    ]:
        assert evidence in claim_matrix
    application_validation = (PACKAGE_DIR / "11_应用场景与专家验证.md").read_text(encoding="utf-8")
    for phrase in ["固定应用场景", "人工原流程", "系统辅助后流程", "验证角色", "量化收益", "边界声明"]:
        assert phrase in application_validation
    for evidence in ["application_validation_report.md", "browser_demo_smoke_report.json", "desktop_search_results.png"]:
        assert evidence in application_validation
    application_report = (PACKAGE_DIR / "reproducibility" / "application_validation_report.md").read_text(encoding="utf-8")
    for phrase in ["GT-07", "压气机出口温度偏高", "进气滤网", "压气机叶片", "温度传感器", "人工确认"]:
        assert phrase in application_report
    for evidence in ["demo-gt07-fault-021", "demo-gt07-repair-022", "demo-gt07-manual-023"]:
        assert evidence in application_report
    expert_feedback_loop = (PACKAGE_DIR / "12_专家反馈采集与整改闭环.md").read_text(encoding="utf-8")
    for phrase in ["反馈采集状态", "待真实反馈归档", "不伪造外部意见", "整改闭环", "专家反馈采集表"]:
        assert phrase in expert_feedback_loop
    for evidence in ["expert_feedback_form.md", "application_validation_report.md", "readiness_gate_report.md"]:
        assert evidence in expert_feedback_loop
    expert_feedback_form = (PACKAGE_DIR / "reproducibility" / "expert_feedback_form.md").read_text(encoding="utf-8")
    for phrase in ["评审人姓名", "单位或角色", "联系方式", "评审日期", "签字或邮件证据", "燃气轮机异常振动诊断流程", "demo-gt07-repair-022", "整改建议"]:
        assert phrase in expert_feedback_form
    expert_feedback_request_packet = (
        PACKAGE_DIR / "reproducibility" / "expert_feedback_request_packet.md"
    ).read_text(encoding="utf-8")
    for phrase in ["专家反馈外发包", "待真实反馈归档", "不宣称已获得专家认可", "建议邮件主题"]:
        assert phrase in expert_feedback_request_packet
    award_self_eval = (PACKAGE_DIR / "08_特等奖评审自评表.md").read_text(encoding="utf-8")
    for phrase in ["学术价值或实用性", "创新性", "作品完成情况", "现场答辩表现", "特等奖不超过6件"]:
        assert phrase in award_self_eval
    for evidence in ["07_评审主张证据矩阵.md", "readiness_gate_report.md", "browser_demo_smoke_report.md"]:
        assert evidence in award_self_eval
    assert "defense_rehearsal_scorecard.md" in award_self_eval
    expert_index = (PACKAGE_DIR / "09_专家快速审阅索引.md").read_text(encoding="utf-8")
    for phrase in ["三分钟审阅路径", "特等奖主张", "一键复核命令", "风险边界"]:
        assert phrase in expert_index
    for evidence in [
        "07_评审主张证据矩阵.md",
        "08_特等奖评审自评表.md",
        "readiness_gate_report.md",
        "browser_demo_smoke_report.md",
        "evaluation/system_eval_questions.jsonl",
    ]:
        assert evidence in expert_index
    defense_card = (PACKAGE_DIR / "10_答辩攻防与彩排卡.md").read_text(encoding="utf-8")
    for phrase in ["90秒开场", "三分钟演示节奏", "杀手问题", "不可夸大边界", "彩排通过标准"]:
        assert phrase in defense_card
    for evidence in [
        "04_系统演示脚本.md",
        "05_答辩问答手册.md",
        "07_评审主张证据矩阵.md",
        "08_特等奖评审自评表.md",
        "readiness_gate_report.md",
        "browser_demo_smoke_report.md",
    ]:
        assert evidence in defense_card
    scorecard = (PACKAGE_DIR / "reproducibility" / "defense_rehearsal_scorecard.md").read_text(encoding="utf-8")
    for phrase in ["答辩彩排计分卡", "20 秒内切换", "30 秒内回答", "不把 readiness gate 说成获奖保证"]:
        assert phrase in scorecard
    result_packet = (
        PACKAGE_DIR / "reproducibility" / "defense_rehearsal_result_packet.md"
    ).read_text(encoding="utf-8")
    for phrase in [
        "答辩计时彩排结果归档包",
        "尚未记录真实计时彩排",
        "不伪造现场彩排记录",
        "opening_actual_seconds",
        "killer_question_results",
    ]:
        assert phrase in result_packet
    demo_script = (PACKAGE_DIR / "04_系统演示脚本.md").read_text(encoding="utf-8")
    for phrase in [
        "固定场景演示",
        "燃气轮机异常振动诊断流程",
        "demo-maint-thresholds-076",
        "demo-structure-fault-130",
        "demo-gt07-fault-021",
        "demo-gt07-repair-022",
        "demo-gt07-manual-023",
        "结果 5",
        "人工确认",
        "application_validation_report.md",
        "desktop_search_results.png",
    ]:
        assert phrase in demo_script
    eval_report = (PACKAGE_DIR / "03_实验评测报告.md").read_text(encoding="utf-8")
    assert "GraphRAG 同题子集" in eval_report
    assert "challenge_cup_graphrag_same_question_report.md" in eval_report
    assert "challenge_cup_graphrag_context_demo.md" in eval_report
    assert "challenge_cup_graphrag_answer_benchmark.md" in eval_report
    assert "challenge_cup_graphrag_gap_remediation_plan.md" in eval_report
    assert "答案级覆盖对照" in eval_report
    assert "补证整改计划" in eval_report
    assert "manual evidence supplement" in eval_report
    assert "context-only" in eval_report
    runbook = (PACKAGE_DIR / "reproducibility" / "runbook.md").read_text(encoding="utf-8")
    assert "build_challenge_cup_defense_deck.py" in runbook
    assert "build_challenge_cup_official_rubric_alignment.py" in runbook
    assert "record_challenge_cup_hard_evidence.py expert_feedback" in runbook
    assert "record_challenge_cup_expert_outreach.py" in runbook
    assert "record_challenge_cup_hard_evidence.py timed_rehearsal" in runbook
    assert "run_challenge_cup_timed_rehearsal.py" in runbook
    assert "build_challenge_cup_expert_outreach_ledger.py" in runbook
    assert "build_challenge_cup_hard_evidence_ledger.py" in runbook
    assert "run_challenge_cup_live_demo_smoke.py" in runbook
    assert "run_challenge_cup_browser_demo_smoke.mjs" in runbook
    assert "check_challenge_cup_readiness.py" in runbook
    assert "check_challenge_cup_goal_completion.py" in runbook
    manifest = (PACKAGE_DIR / "reproducibility" / "dataset_manifest.md").read_text(encoding="utf-8")
    assert "live_demo_smoke_report.md" in manifest
    assert "browser_demo_smoke_report.md" in manifest
    assert "application_validation_report.md" in manifest
    assert "11_应用场景与专家验证.md" in manifest
    assert "expert_feedback_form.md" in manifest
    assert "12_专家反馈采集与整改闭环.md" in manifest
    assert "readiness_gate_report.md" in manifest
    assert "goal_completion_report.md" in manifest
    assert "evidence_hashes.json" in manifest
    assert "evaluation_coverage_profile.json" in manifest
    assert "challenge_cup_graphrag_context_demo.md" in manifest
    assert "challenge_cup_graphrag_context_demo.json" in manifest
    assert "challenge_cup_graphrag_answer_benchmark.md" in manifest
    assert "challenge_cup_graphrag_answer_benchmark.json" in manifest
    assert "challenge_cup_graphrag_gap_remediation_plan.md" in manifest
    assert "challenge_cup_graphrag_gap_remediation_plan.json" in manifest
    assert "graphrag_manual_evidence_supplement.csv" in manifest
    assert "defense_rehearsal_scorecard.md" in manifest
    assert "defense_rehearsal_scorecard.json" in manifest
    assert "defense_rehearsal_result_packet.md" in manifest
    assert "defense_rehearsal_result_packet.json" in manifest
    assert "expert_feedback_request_packet.md" in manifest
    assert "expert_feedback_request_packet.json" in manifest
    assert "expert_feedback_outreach_ledger.md" in manifest
    assert "expert_feedback_outreach_ledger.json" in manifest
    assert "expert_feedback_outreach/README.md" in manifest
    assert "official_rubric_alignment.md" in manifest
    assert "official_rubric_alignment.json" in manifest
    assert "challenge_cup_defense_deck.pptx" in manifest
    assert "challenge_cup_defense_speaker_notes.md" in manifest
    assert "hard_evidence_ledger.md" in manifest
    assert "hard_evidence_ledger.json" in manifest
    assert "hard_evidence/expert_feedback/README.md" in manifest
    assert "hard_evidence/timed_rehearsal/README.md" in manifest
    assert "challenge_cup_submission_package.zip" in manifest
    assert "challenge_cup_submission_archive_manifest.json" in manifest
    assert "browser_demo_smoke_report.json" in manifest
    assert "desktop_overview.png" in manifest
    assert "desktop_search_results.png" in manifest
    assert "desktop_kg_artifacts.png" in manifest
    assert "mobile_overview.png" in manifest
    coverage = json.loads((PACKAGE_DIR / "reproducibility" / "evaluation_coverage_profile.json").read_text(encoding="utf-8"))
    assert coverage["generated_from"] == "evaluation/system_eval_questions.jsonl"
    assert coverage["question_count"] == 60
    assert len(coverage["task_type_counts"]) >= 10
    assert len(coverage["source_scope_counts"]) >= 15
    assert coverage["expected_mode_counts"]["keyword"] >= 50
    assert coverage["expected_mode_counts"]["hybrid_rrf"] >= 50
    assert coverage["expected_mode_counts"]["graphrag_context"] >= 8
    assert coverage["expected_mode_counts"]["graphrag_global"] >= 4
    assert coverage["questions_with_graphrag_modes"] >= 10
    assert coverage["minimums"]["task_types"] == 10
    assert coverage["minimums"]["source_scopes"] == 15
    assert coverage["minimums"]["graphrag_questions"] == 10
    command_log = (PACKAGE_DIR / "reproducibility" / "command_log.md").read_text(encoding="utf-8")
    assert "run_challenge_cup_browser_demo_smoke.mjs" in command_log
    assert "browser_demo_smoke_report.json" in command_log
    assert "Status: pass (32/32 gates)" in command_log
    assert "Status: pass (30/30 gates)" not in command_log
    browser_smoke = json.loads((PACKAGE_DIR / "reproducibility" / "browser_demo_smoke_report.json").read_text(encoding="utf-8"))
    browser = browser_smoke["browser"]
    assert browser["query"] == "燃气轮机异常振动诊断流程"
    assert "结果 5" in browser["search_meta"]
    assert "延迟" in browser["search_meta"]
    assert browser["search_results_visible"] is True
    assert browser["visible_record_ids"] == [
        "demo-maint-thresholds-076",
        "demo-structure-fault-130",
        "demo-gt07-fault-021",
        "demo-gt07-repair-022",
        "demo-gt07-manual-023",
    ]
    assert browser["search_result_card_count"] >= 5
    for evidence in [
        "demo-maint-thresholds-076",
        "demo-structure-fault-130",
        "demo-gt07-fault-021",
        "demo-gt07-repair-022",
        "demo-gt07-manual-023",
        "压气机出口温度偏高",
        "进气滤网",
        "温度传感器",
    ]:
        assert evidence in browser["results_preview"]
    package_manifest = json.loads((PACKAGE_DIR / "package_manifest.json").read_text(encoding="utf-8"))
    evidence_files = package_manifest["evidence_files"]
    assert package_manifest["integrity_manifest"] == "docs/challenge_cup/reproducibility/evidence_hashes.json"
    assert package_manifest["evaluation_coverage_profile"] == (
        "docs/challenge_cup/reproducibility/evaluation_coverage_profile.json"
    )
    archive_relative = "docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip"
    archive_manifest_relative = "docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json"
    assert package_manifest["submission_archive"] == archive_relative
    assert package_manifest["submission_archive_manifest"] == archive_manifest_relative
    assert "docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx" in evidence_files
    assert "docs/challenge_cup/defense_deck/challenge_cup_defense_speaker_notes.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/hard_evidence_ledger.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/hard_evidence_ledger.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/hard_evidence/README.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/README.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/README.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/browser_demo_smoke_report.json" in evidence_files
    assert "docs/challenge_cup/06_结项验收清单.md" in evidence_files
    assert "docs/challenge_cup/07_评审主张证据矩阵.md" in evidence_files
    assert "docs/challenge_cup/08_特等奖评审自评表.md" in evidence_files
    assert "docs/challenge_cup/09_专家快速审阅索引.md" in evidence_files
    assert "docs/challenge_cup/10_答辩攻防与彩排卡.md" in evidence_files
    assert "evaluation/reports/challenge_cup_graphrag_context_demo.md" in evidence_files
    assert "evaluation/reports/challenge_cup_graphrag_context_demo.json" in evidence_files
    assert "evaluation/reports/challenge_cup_graphrag_answer_benchmark.md" in evidence_files
    assert "evaluation/reports/challenge_cup_graphrag_answer_benchmark.json" in evidence_files
    assert "evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.md" in evidence_files
    assert "evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/graphrag_manual_evidence_supplement.csv" in evidence_files
    assert "docs/challenge_cup/11_应用场景与专家验证.md" in evidence_files
    assert "docs/challenge_cup/12_专家反馈采集与整改闭环.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/application_validation_report.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/expert_feedback_form.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/expert_feedback_request_packet.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/expert_feedback_request_packet.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/expert_feedback_outreach_ledger.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/expert_feedback_outreach_ledger.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/expert_feedback_outreach/README.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/official_rubric_alignment.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/official_rubric_alignment.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/readiness_gate_report.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/goal_completion_report.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/browser_screenshots/desktop_overview.png" in evidence_files
    assert "docs/challenge_cup/reproducibility/browser_screenshots/desktop_kg_artifacts.png" in evidence_files
    hashes = json.loads((PACKAGE_DIR / "reproducibility" / "evidence_hashes.json").read_text(encoding="utf-8"))
    assert hashes["algorithm"] == "sha256"
    excluded = {"docs/challenge_cup/reproducibility/readiness_gate_report.md"}
    expected_hashed = sorted(path for path in evidence_files if path not in excluded)
    assert hashes["excluded_self_reports"] == sorted(excluded)
    assert [entry["path"] for entry in hashes["files"]] == expected_hashed
    for entry in hashes["files"]:
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
        assert entry["bytes"] == (REPO_ROOT / entry["path"]).stat().st_size
    deck_path = PACKAGE_DIR / "defense_deck" / "challenge_cup_defense_deck.pptx"
    notes_path = PACKAGE_DIR / "defense_deck" / "challenge_cup_defense_speaker_notes.md"
    assert deck_path.exists()
    assert deck_path.stat().st_size > 100_000
    slide_count, deck_text = pptx_slide_text(deck_path)
    assert slide_count == 10
    for term in ["GraphRAG", "GT-07", "60", "readiness", "专家反馈"]:
        assert term in deck_text
    notes = notes_path.read_text(encoding="utf-8")
    for term in ["90秒开场", "三分钟演示", "GT-07", "GraphRAG", "readiness gate", "不宣称已获得专家认可"]:
        assert term in notes
    hard_ledger = json.loads((PACKAGE_DIR / "reproducibility" / "hard_evidence_ledger.json").read_text(encoding="utf-8"))
    assert hard_ledger["report_type"] == "challenge_cup_hard_evidence_ledger"
    assert hard_ledger["status"] == "awaiting_real_external_feedback_and_timed_rehearsal"
    assert hard_ledger["completion_claim_allowed"] is False
    assert hard_ledger["categories"]["expert_feedback"]["collected_count"] == 0
    assert hard_ledger["categories"]["timed_rehearsal"]["collected_count"] == 0
    assert hard_ledger["required_before_goal_completion"] == ["expert_feedback", "timed_rehearsal"]
    hard_ledger_md = (PACKAGE_DIR / "reproducibility" / "hard_evidence_ledger.md").read_text(encoding="utf-8")
    for term in [
        "\u771f\u5b9e\u4e13\u5bb6\u53cd\u9988",
        "\u771f\u5b9e\u8ba1\u65f6\u5f69\u6392",
        "\u4e0d\u4f2a\u9020",
        "\u4e0d\u80fd\u6807\u8bb0\u76ee\u6807\u5b8c\u6210",
    ]:
        assert term in hard_ledger_md
    hard_evidence_readme = (PACKAGE_DIR / "reproducibility" / "hard_evidence" / "README.md").read_text(
        encoding="utf-8"
    )
    assert "record_challenge_cup_hard_evidence.py expert_feedback" in hard_evidence_readme
    assert "record_challenge_cup_hard_evidence.py timed_rehearsal" in hard_evidence_readme
    assert "run_challenge_cup_timed_rehearsal.py" in hard_evidence_readme
    outreach_ledger = json.loads(
        (PACKAGE_DIR / "reproducibility" / "expert_feedback_outreach_ledger.json").read_text(encoding="utf-8")
    )
    assert outreach_ledger["report_type"] == "challenge_cup_expert_feedback_outreach_ledger"
    assert outreach_ledger["status"] == "ready_to_send_no_outreach_recorded"
    assert outreach_ledger["no_external_feedback_claimed"] is True
    assert outreach_ledger["does_not_satisfy_goal_completion"] is True
    assert outreach_ledger["outreach_record_count"] == 0
    outreach_ledger_md = (
        PACKAGE_DIR / "reproducibility" / "expert_feedback_outreach_ledger.md"
    ).read_text(encoding="utf-8")
    assert "Expert Feedback Outreach Ledger" in outreach_ledger_md
    assert "do not prove expert approval" in outreach_ledger_md
    goal_completion = (PACKAGE_DIR / "reproducibility" / "goal_completion_report.md").read_text(encoding="utf-8")
    assert "Challenge Cup Goal Completion Gate" in goal_completion
    assert "Status: `fail`" in goal_completion
    assert "completion_claim_allowed=False" in goal_completion
    assert "不能标记目标完成" in goal_completion
    official_rubric = json.loads((PACKAGE_DIR / "reproducibility" / "official_rubric_alignment.json").read_text(encoding="utf-8"))
    assert official_rubric["report_type"] == "challenge_cup_official_rubric_alignment"
    assert official_rubric["official_source_count"] >= 4
    assert official_rubric["dimensions"]["academic_or_practical_value"]["evidence_files"]
    assert official_rubric["dimensions"]["innovation"]["evidence_files"]
    assert official_rubric["dimensions"]["completion"]["evidence_files"]
    assert official_rubric["dimensions"]["defense_performance"]["evidence_files"]
    assert official_rubric["special_prize_policy"]["max_special_prize_count"] == 6
    assert official_rubric["special_prize_policy"]["may_be_vacant"] is True
    assert official_rubric["integrity_rules"]["no_award_guarantee"] is True
    official_rubric_md = (PACKAGE_DIR / "reproducibility" / "official_rubric_alignment.md").read_text(encoding="utf-8")
    for term in ["学术/实用价值", "创新性", "作品完成度", "现场答辩", "特等奖不超过6件", "不承诺获奖"]:
        assert term in official_rubric_md
    archive_path = REPO_ROOT / archive_relative
    archive_manifest = json.loads((REPO_ROOT / archive_manifest_relative).read_text(encoding="utf-8"))
    assert archive_path.exists()
    assert archive_path.stat().st_size > 0
    assert archive_manifest["archive_path"] == archive_relative
    assert archive_manifest["bytes"] == archive_path.stat().st_size
    assert archive_manifest["sha256"] == sha256_file(archive_path)
    assert re.fullmatch(r"[0-9a-f]{64}", archive_manifest["sha256"])
    with zipfile.ZipFile(archive_path) as archive:
        archive_entries = sorted(info.filename for info in archive.infolist())
    assert archive_entries == archive_manifest["included_files"]
    assert archive_manifest["file_count"] == len(archive_entries)
    assert archive_relative not in archive_entries
    assert archive_manifest_relative not in archive_entries
    self_report = "docs/challenge_cup/reproducibility/readiness_gate_report.md"
    assert self_report not in archive_entries
    assert self_report in archive_manifest["excluded_files"]
    assert all(not Path(entry).is_absolute() and ".." not in Path(entry).parts for entry in archive_entries)
    required_archive_entries = set(evidence_files) | {
        "docs/challenge_cup/package_manifest.json",
        "docs/challenge_cup/reproducibility/dataset_manifest.md",
        "docs/challenge_cup/reproducibility/runbook.md",
        "docs/challenge_cup/reproducibility/command_log.md",
        "docs/challenge_cup/reproducibility/evidence_hashes.json",
        "docs/challenge_cup/reproducibility/goal_completion_report.md",
        "docs/challenge_cup/reproducibility/official_rubric_alignment.md",
        "docs/challenge_cup/reproducibility/official_rubric_alignment.json",
        "docs/challenge_cup/reproducibility/hard_evidence_ledger.md",
        "docs/challenge_cup/reproducibility/hard_evidence_ledger.json",
        "docs/challenge_cup/reproducibility/hard_evidence/README.md",
        "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/README.md",
        "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/README.md",
        "docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx",
        "docs/challenge_cup/defense_deck/challenge_cup_defense_speaker_notes.md",
    }
    required_archive_entries.discard(self_report)
    assert required_archive_entries <= set(archive_entries)


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
        PACKAGE_DIR / "reproducibility" / "goal_completion_report.md",
        PACKAGE_DIR / "11_应用场景与专家验证.md",
        PACKAGE_DIR / "reproducibility" / "application_validation_report.md",
        PACKAGE_DIR / "reproducibility" / "defense_rehearsal_scorecard.md",
        PACKAGE_DIR / "reproducibility" / "defense_rehearsal_scorecard.json",
        PACKAGE_DIR / "reproducibility" / "defense_rehearsal_result_packet.md",
        PACKAGE_DIR / "reproducibility" / "defense_rehearsal_result_packet.json",
        PACKAGE_DIR / "reproducibility" / "expert_feedback_request_packet.md",
        PACKAGE_DIR / "reproducibility" / "expert_feedback_request_packet.json",
        PACKAGE_DIR / "reproducibility" / "expert_feedback_outreach_ledger.md",
        PACKAGE_DIR / "reproducibility" / "expert_feedback_outreach_ledger.json",
        PACKAGE_DIR / "reproducibility" / "expert_feedback_outreach" / "README.md",
        PACKAGE_DIR / "reproducibility" / "official_rubric_alignment.md",
        PACKAGE_DIR / "reproducibility" / "official_rubric_alignment.json",
        PACKAGE_DIR / "reproducibility" / "hard_evidence_ledger.md",
        PACKAGE_DIR / "reproducibility" / "hard_evidence_ledger.json",
        PACKAGE_DIR / "reproducibility" / "hard_evidence" / "README.md",
        PACKAGE_DIR / "reproducibility" / "hard_evidence" / "expert_feedback" / "README.md",
        PACKAGE_DIR / "reproducibility" / "hard_evidence" / "timed_rehearsal" / "README.md",
        PACKAGE_DIR / "reproducibility" / "evaluation_coverage_profile.json",
        PACKAGE_DIR / "defense_deck" / "challenge_cup_defense_deck.pptx",
        PACKAGE_DIR / "defense_deck" / "challenge_cup_defense_speaker_notes.md",
        PACKAGE_DIR / "reproducibility" / "challenge_cup_submission_package.zip",
        PACKAGE_DIR / "reproducibility" / "challenge_cup_submission_archive_manifest.json",
        PACKAGE_DIR / "package_manifest.json",
    ]
    before = {path: path.read_bytes() for path in tracked}
    subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    after = {path: path.read_bytes() for path in tracked}
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
        "docs/challenge_cup/reproducibility/evidence_hashes.json",
        "docs/challenge_cup/reproducibility/evaluation_coverage_profile.json",
        "docs/challenge_cup/reproducibility/browser_demo_smoke_report.json",
        "docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.json",
        "docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.json",
        "docs/challenge_cup/reproducibility/expert_feedback_request_packet.json",
        "docs/challenge_cup/reproducibility/expert_feedback_outreach_ledger.json",
        "docs/challenge_cup/reproducibility/official_rubric_alignment.json",
        "docs/challenge_cup/reproducibility/hard_evidence_ledger.json",
        "docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json",
        "docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip",
        "evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.json",
    ]
    for target in tracked_json_entries:
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", "--", target],
            cwd=REPO_ROOT,
        )
        assert result.returncode != 0, target
