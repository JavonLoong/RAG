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
    "13_评委现场速览卡.md",
    "14_现场答辩操作Runbook.md",
    "15_结项交付移交清单.md",
    "16_现场问辩记录与整改台账.md",
    "17_评审风险控制与应急预案.md",
    "18_特等奖打分模拟与整改清单.md",
    "19_作品展墙报问辩与展台脚本.md",
    "20_成果转化与持续迭代路线图.md",
    "21_知识产权与开源合规说明.md",
    "22_同类方案对比与创新性证据卡.md",
    "23_终审提交总目录与签收页.md",
    "poster/challenge_cup_a0_poster.html",
    "defense_console/index.html",
    "defense_deck/challenge_cup_defense_speaker_notes.md",
    "reproducibility/runbook.md",
    "reproducibility/dataset_manifest.md",
    "reproducibility/goal_completion_report.md",
    "reproducibility/final_acceptance_audit.md",
    "reproducibility/final_acceptance_audit.json",
    "reproducibility/evaluation_coverage_profile.json",
    "reproducibility/evidence_hashes.json",
    "reproducibility/application_validation_report.md",
    "reproducibility/application_value_quantification.md",
    "reproducibility/application_value_quantification.json",
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
    "reproducibility/timed_rehearsal_schedule_ledger.md",
    "reproducibility/timed_rehearsal_schedule_ledger.json",
    "reproducibility/timed_rehearsal_schedule/README.md",
    "reproducibility/official_rubric_alignment.md",
    "reproducibility/official_rubric_alignment.json",
    "reproducibility/judge_objection_response_matrix.md",
    "reproducibility/judge_objection_response_matrix.json",
    "reproducibility/special_prize_readiness_dashboard.md",
    "reproducibility/special_prize_readiness_dashboard.json",
    "reproducibility/hard_evidence_closure_board.md",
    "reproducibility/hard_evidence_closure_board.json",
    "reproducibility/hard_evidence_action_pack.md",
    "reproducibility/hard_evidence_action_pack.json",
    "reproducibility/external_evidence_execution_kit.md",
    "reproducibility/external_evidence_execution_kit.json",
    "reproducibility/external_evidence_execution_kit/expert_review_handoff.md",
    "reproducibility/external_evidence_execution_kit/timed_rehearsal_observer_sheet.md",
    "reproducibility/hard_evidence_ledger.md",
    "reproducibility/hard_evidence_ledger.json",
    "reproducibility/hard_evidence/README.md",
    "reproducibility/hard_evidence/expert_feedback/README.md",
    "reproducibility/hard_evidence/timed_rehearsal/README.md",
    "reproducibility/verify_submission_package.py",
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
    assert "13_评委现场速览卡.md" in readme
    assert "14_现场答辩操作Runbook.md" in readme
    assert "15_结项交付移交清单.md" in readme
    assert "16_现场问辩记录与整改台账.md" in readme
    assert "17_评审风险控制与应急预案.md" in readme
    assert "18_特等奖打分模拟与整改清单.md" in readme
    assert "19_作品展墙报问辩与展台脚本.md" in readme
    assert "20_成果转化与持续迭代路线图.md" in readme
    assert "21_知识产权与开源合规说明.md" in readme
    assert "22_同类方案对比与创新性证据卡.md" in readme
    assert "23_终审提交总目录与签收页.md" in readme
    assert "defense_deck/challenge_cup_defense_deck.pptx" in readme
    assert "defense_deck/challenge_cup_defense_speaker_notes.md" in readme
    assert "defense_console/index.html" in readme
    assert "reproducibility/official_rubric_alignment.md" in readme
    assert "reproducibility/judge_objection_response_matrix.md" in readme
    assert "challenge_cup_failure_remediation_before_after.md" in readme
    assert "reproducibility/hard_evidence_ledger.md" in readme
    assert "reproducibility/application_validation_report.md" in readme
    assert "reproducibility/application_value_quantification.md" in readme
    assert "reproducibility/expert_feedback_form.md" in readme
    assert "reproducibility/expert_feedback_outreach_ledger.md" in readme
    assert "reproducibility/timed_rehearsal_schedule_ledger.md" in readme
    assert "reproducibility/hard_evidence_closure_board.md" in readme
    assert "reproducibility/hard_evidence_action_pack.md" in readme
    assert "reproducibility/external_evidence_execution_kit.md" in readme
    assert "reproducibility/special_prize_readiness_dashboard.md" in readme
    assert "reproducibility/judge_objection_response_matrix.md" in readme
    assert "poster/challenge_cup_a0_poster.html" in readme
    assert "defense_console/index.html" in readme
    assert "reproducibility/readiness_gate_report.md" in readme
    assert "reproducibility/goal_completion_report.md" in readme
    assert "reproducibility/final_acceptance_audit.md" in readme
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
    for evidence in [
        "application_validation_report.md",
        "application_value_quantification.md",
        "browser_demo_smoke_report.json",
        "desktop_search_results.png",
    ]:
        assert evidence in application_validation
    application_report = (PACKAGE_DIR / "reproducibility" / "application_validation_report.md").read_text(encoding="utf-8")
    for phrase in ["GT-07", "压气机出口温度偏高", "进气滤网", "压气机叶片", "温度传感器", "人工确认"]:
        assert phrase in application_report
    for evidence in ["demo-gt07-fault-021", "demo-gt07-repair-022", "demo-gt07-manual-023"]:
        assert evidence in application_report
    application_value = json.loads(
        (PACKAGE_DIR / "reproducibility" / "application_value_quantification.json").read_text(encoding="utf-8")
    )
    assert application_value["status"] == "application_value_quantified_no_external_validation_claim"
    assert application_value["completion_claim_allowed"] is False
    assert application_value["does_not_satisfy_goal_completion"] is True
    assert application_value["collection"] == "gas_turbine_ocr_demo_snapshot"
    assert application_value["retrieval_latency_ms"] == 41.8
    assert application_value["workflow_contrast"]["evidence_consolidation_ratio"] == 5.0
    assert [stage["record_id"] for stage in application_value["evidence_chain"]] == [
        "demo-maint-thresholds-076",
        "demo-structure-fault-130",
        "demo-gt07-fault-021",
        "demo-gt07-repair-022",
        "demo-gt07-manual-023",
    ]
    application_value_md = (
        PACKAGE_DIR / "reproducibility" / "application_value_quantification.md"
    ).read_text(encoding="utf-8")
    for phrase in ["Application Value Quantification", "GT-07", "41.8 ms", "5.0x evidence consolidation"]:
        assert phrase in application_value_md
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
    for phrase in ["学术价值或实用性", "创新性", "作品完成情况", "现场答辩表现", "第44届", "特等奖7项"]:
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
    judge_card = (PACKAGE_DIR / "13_评委现场速览卡.md").read_text(encoding="utf-8")
    for phrase in [
        "评委现场速览卡",
        "特等奖答辩路径",
        "三分钟审阅路径",
        "一页结论",
        "证据锚点",
        "不承诺获奖",
        "真实专家反馈",
        "真实计时彩排",
    ]:
        assert phrase in judge_card
    for evidence in [
        "00_项目一页纸.md",
        "07_评审主张证据矩阵.md",
        "08_特等奖评审自评表.md",
        "09_专家快速审阅索引.md",
        "special_prize_readiness_dashboard.md",
        "final_acceptance_audit.md",
        "goal_completion_report.md",
    ]:
        assert evidence in judge_card
    onsite_runbook = (PACKAGE_DIR / "14_现场答辩操作Runbook.md").read_text(encoding="utf-8")
    for phrase in [
        "现场答辩操作Runbook",
        "Preflight",
        "标签页顺序",
        "离线切换触发条件",
        "Q&A 证据映射",
        "留存材料",
        "禁止现场调试",
        "真实专家反馈",
        "真实计时彩排",
    ]:
        assert phrase in onsite_runbook
    for evidence in [
        "13_评委现场速览卡.md",
        "09_专家快速审阅索引.md",
        "04_系统演示脚本.md",
        "10_答辩攻防与彩排卡.md",
        "browser_demo_smoke_report.md",
        "desktop_search_results.png",
        "final_acceptance_audit.md",
        "goal_completion_report.md",
    ]:
        assert evidence in onsite_runbook
    assert "55 项 readiness gate" in onsite_runbook
    assert "54 项 readiness gate" not in onsite_runbook
    assert "53 项 readiness gate" not in onsite_runbook
    assert "52 项 readiness gate" not in onsite_runbook
    assert "51 项 readiness gate" not in onsite_runbook
    assert "50 项 readiness gate" not in onsite_runbook
    assert "49 项 readiness gate" not in onsite_runbook
    assert "48 项 readiness gate" not in onsite_runbook
    assert "47 项 readiness gate" not in onsite_runbook
    assert "46 项 readiness gate" not in onsite_runbook
    assert "45 项 readiness gate" not in onsite_runbook
    assert "44 项 readiness gate" not in onsite_runbook
    assert "43 项 readiness gate" not in onsite_runbook
    assert "42 项 readiness gate" not in onsite_runbook
    assert "40 项 readiness gate" not in onsite_runbook
    handoff_checklist = (PACKAGE_DIR / "15_结项交付移交清单.md").read_text(encoding="utf-8")
    for phrase in [
        "结项交付移交清单",
        "移交范围",
        "签收确认",
        "复核命令",
        "材料归档",
        "外部硬证据补齐",
        "真实专家反馈",
        "真实计时彩排",
        "不能标记目标完成",
    ]:
        assert phrase in handoff_checklist
    for evidence in [
        "README_先看这里.md",
        "package_manifest.json",
        "challenge_cup_submission_package.zip",
        "verify_submission_package.py",
        "readiness_gate_report.md",
        "final_acceptance_audit.md",
        "goal_completion_report.md",
        "hard_evidence_ledger.md",
        "hard_evidence_action_pack.md",
        "14_现场答辩操作Runbook.md",
    ]:
        assert evidence in handoff_checklist
    qa_remediation = (PACKAGE_DIR / "16_现场问辩记录与整改台账.md").read_text(encoding="utf-8")
    for phrase in [
        "现场问辩记录与整改台账",
        "记录范围",
        "现场记录表",
        "证据补链",
        "整改闭环",
        "复核命令",
        "边界声明",
        "judge_question",
        "evidence_anchor",
        "remediation_action",
        "closure_status",
        "真实专家反馈",
        "真实计时彩排",
        "不能标记目标完成",
    ]:
        assert phrase in qa_remediation
    for evidence in [
        "10_答辩攻防与彩排卡.md",
        "14_现场答辩操作Runbook.md",
        "15_结项交付移交清单.md",
        "07_评审主张证据矩阵.md",
        "09_专家快速审阅索引.md",
        "readiness_gate_report.md",
        "goal_completion_report.md",
        "hard_evidence_ledger.md",
        "hard_evidence_action_pack.md",
        "scripts/check_challenge_cup_readiness.py",
    ]:
        assert evidence in qa_remediation
    risk_plan = (PACKAGE_DIR / "17_评审风险控制与应急预案.md").read_text(encoding="utf-8")
    for phrase in [
        "评审风险控制与应急预案",
        "风险分级",
        "触发条件",
        "应急动作",
        "证据锚点",
        "关闭标准",
        "award_overclaim",
        "demo_failure",
        "external_evidence_gap",
        "data_boundary",
        "safety_boundary",
        "真实专家反馈",
        "真实计时彩排",
        "不能标记目标完成",
    ]:
        assert phrase in risk_plan
    for evidence in [
        "08_特等奖评审自评表.md",
        "14_现场答辩操作Runbook.md",
        "16_现场问辩记录与整改台账.md",
        "browser_demo_smoke_report.md",
        "desktop_search_results.png",
        "goal_completion_report.md",
        "hard_evidence_ledger.md",
        "special_prize_readiness_dashboard.md",
        "scripts/check_challenge_cup_readiness.py",
    ]:
        assert evidence in risk_plan
    scoring_drill = (PACKAGE_DIR / "18_特等奖打分模拟与整改清单.md").read_text(encoding="utf-8")
    for phrase in [
        "特等奖打分模拟与整改清单",
        "官方口径快照",
        "第44届",
        "2026年4月25日",
        "特等奖7项",
        "学术价值或实用性",
        "创新性",
        "作品完成情况",
        "现场答辩表现",
        "模拟扣分项",
        "整改动作",
        "关闭证据",
        "真实专家反馈",
        "真实计时彩排",
        "不承诺获奖",
    ]:
        assert phrase in scoring_drill
    for evidence in [
        "07_评审主张证据矩阵.md",
        "08_特等奖评审自评表.md",
        "13_评委现场速览卡.md",
        "14_现场答辩操作Runbook.md",
        "17_评审风险控制与应急预案.md",
        "official_rubric_alignment.md",
        "special_prize_readiness_dashboard.md",
        "final_acceptance_audit.md",
        "goal_completion_report.md",
        "hard_evidence_ledger.md",
    ]:
        assert evidence in scoring_drill
    poster_booth = (PACKAGE_DIR / "19_作品展墙报问辩与展台脚本.md").read_text(encoding="utf-8")
    for phrase in [
        "作品展墙报问辩与展台脚本",
        "墙报问辩表现",
        "作品展",
        "二维码",
        "线上线下融合",
        "展台三分钟路径",
        "展板信息架构",
        "现场互动脚本",
        "评委追问",
        "材料递交",
        "离线备份",
        "真实专家反馈",
        "真实计时彩排",
        "不承诺获奖",
    ]:
        assert phrase in poster_booth
    for evidence in [
        "13_评委现场速览卡.md",
        "18_特等奖打分模拟与整改清单.md",
        "07_评审主张证据矩阵.md",
        "08_特等奖评审自评表.md",
        "application_validation_report.md",
        "browser_demo_smoke_report.md",
        "desktop_search_results.png",
        "official_rubric_alignment.md",
        "readiness_gate_report.md",
        "goal_completion_report.md",
        "hard_evidence_ledger.md",
    ]:
        assert evidence in poster_booth
    poster_html = (PACKAGE_DIR / "poster" / "challenge_cup_a0_poster.html").read_text(encoding="utf-8")
    for phrase in [
        "<!doctype html>",
        "A0",
        "@page",
        "size: A0 landscape",
        "知燃知维",
        "GraphRAG",
        "证据链",
        "GT-07",
        "60 题评测",
        "9080 chunks",
        "二维码",
        "README",
        "submission verifier",
        "readiness gate",
        "真实专家反馈",
        "真实计时彩排",
        "不承诺获奖",
    ]:
        assert phrase in poster_html
    for evidence in [
        "docs/challenge_cup/README_先看这里.md",
        "docs/challenge_cup/13_评委现场速览卡.md",
        "docs/challenge_cup/19_作品展墙报问辩与展台脚本.md",
        "docs/challenge_cup/20_成果转化与持续迭代路线图.md",
        "docs/challenge_cup/reproducibility/application_validation_report.md",
        "docs/challenge_cup/reproducibility/readiness_gate_report.md",
        "docs/challenge_cup/reproducibility/verify_submission_package.py",
        "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md",
        "docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png",
    ]:
        assert evidence in poster_html
    defense_console = (PACKAGE_DIR / "defense_console" / "index.html").read_text(encoding="utf-8")
    for phrase in [
        "<!doctype html>",
        "Defense Control Console",
        "3-minute timer",
        "90-second opening",
        "offline fallback",
        "readiness gate",
        "submission verifier",
        "GT-07",
        "GraphRAG",
        "no award guarantee",
        "real expert feedback",
        "real timed rehearsal",
    ]:
        assert phrase in defense_console
    for evidence in [
        "docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx",
        "docs/challenge_cup/13_评委现场速览卡.md",
        "docs/challenge_cup/14_现场答辩操作Runbook.md",
        "docs/challenge_cup/reproducibility/readiness_gate_report.md",
        "docs/challenge_cup/reproducibility/verify_submission_package.py",
        "docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png",
        "docs/challenge_cup/reproducibility/application_validation_report.md",
        "docs/challenge_cup/reproducibility/final_acceptance_audit.md",
        "docs/challenge_cup/reproducibility/goal_completion_report.md",
    ]:
        assert evidence in defense_console
    commercialization_plan = (PACKAGE_DIR / "20_成果转化与持续迭代路线图.md").read_text(encoding="utf-8")
    for phrase in [
        "成果转化与持续迭代路线图",
        "服务国家战略",
        "高质量发展",
        "成果转化",
        "新质生产力",
        "试点路径",
        "推广对象",
        "迭代里程碑",
        "验收指标",
        "风险边界",
        "数据治理",
        "人工确认",
        "真实专家反馈",
        "真实计时彩排",
        "不承诺商业落地",
    ]:
        assert phrase in commercialization_plan
    for evidence in [
        "01_挑战杯项目书.md",
        "07_评审主张证据矩阵.md",
        "11_应用场景与专家验证.md",
        "18_特等奖打分模拟与整改清单.md",
        "19_作品展墙报问辩与展台脚本.md",
        "application_validation_report.md",
        "official_rubric_alignment.md",
        "special_prize_readiness_dashboard.md",
        "hard_evidence_action_pack.md",
        "hard_evidence_ledger.md",
        "goal_completion_report.md",
    ]:
        assert evidence in commercialization_plan
    compliance_doc = (PACKAGE_DIR / "21_知识产权与开源合规说明.md").read_text(encoding="utf-8")
    for phrase in [
        "知识产权与开源合规说明",
        "原创性声明",
        "第三方依赖",
        "开源许可证",
        "数据来源与授权边界",
        "学术诚信",
        "引用与证据路径",
        "不宣称已申请专利",
        "不宣称已发表论文",
        "不接入未授权生产资料",
        "人工确认",
        "真实专家反馈",
        "真实计时彩排",
        "不承诺获奖",
    ]:
        assert phrase in compliance_doc
    for evidence in [
        "README_先看这里.md",
        "01_挑战杯项目书.md",
        "02_技术白皮书.md",
        "03_实验评测报告.md",
        "07_评审主张证据矩阵.md",
        "20_成果转化与持续迭代路线图.md",
        "package_manifest.json",
        "evidence_hashes.json",
        "verify_submission_package.py",
        "official_rubric_alignment.md",
        "hard_evidence_ledger.md",
        "final_acceptance_audit.md",
    ]:
        assert evidence in compliance_doc
    baseline_card = (PACKAGE_DIR / "22_同类方案对比与创新性证据卡.md").read_text(encoding="utf-8")
    for phrase in [
        "同类方案对比与创新性证据卡",
        "不是普通 RAG 页面",
        "本地同题对照",
        "keyword / dense_hashing / hybrid_rrf / GraphRAG",
        "GraphRAG 用于关系证据组织",
        "supported=10, partial=0, missing=0",
        "GT-07",
        "不宣称 GraphRAG 全面优于 baseline",
        "不替代工程师做最终运维决策",
        "不依赖真实专家反馈或真实彩排",
        "Best baseline average coverage: 0.633333",
        "GraphRAG evidence average coverage: 0.866667",
        "Graph supported / partial / missing: 10 / 0 / 0",
    ]:
        assert phrase in baseline_card
    for evidence in [
        "evaluation/reports/day3_retrieval_baseline_comparison_20260605_210540.md",
        "evaluation/reports/day4_failure_analysis_20260605_210642.md",
        "evaluation/reports/challenge_cup_graphrag_same_question_report.md",
        "evaluation/reports/challenge_cup_graphrag_answer_benchmark.md",
        "evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.md",
        "docs/challenge_cup/reproducibility/application_validation_report.md",
        "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md",
        "docs/challenge_cup/03_实验评测报告.md",
        "docs/challenge_cup/07_评审主张证据矩阵.md",
        "docs/challenge_cup/08_特等奖评审自评表.md",
    ]:
        assert evidence in baseline_card
    final_submission_handoff = (PACKAGE_DIR / "23_终审提交总目录与签收页.md").read_text(encoding="utf-8")
    for phrase in [
        "终审提交总目录与签收页",
        "提交状态",
        "评委三分钟入口",
        "正式提交文件",
        "复核命令",
        "签收确认",
        "真实专家反馈",
        "真实计时彩排",
        "不能标记目标完成",
        "不承诺获奖",
        "package_ready_awaiting_external_hard_evidence",
    ]:
        assert phrase in final_submission_handoff
    for evidence in [
        "README_先看这里.md",
        "00_项目一页纸.md",
        "01_挑战杯项目书.md",
        "13_评委现场速览卡.md",
        "19_作品展墙报问辩与展台脚本.md",
        "challenge_cup_defense_deck.pptx",
        "challenge_cup_a0_poster.html",
        "package_manifest.json",
        "challenge_cup_submission_package.zip",
        "verify_submission_package.py",
        "readiness_gate_report.md",
        "final_acceptance_audit.md",
        "goal_completion_report.md",
        "external_evidence_execution_kit.md",
        "hard_evidence_ledger.md",
    ]:
        assert evidence in final_submission_handoff
    forbidden_control_chars = [
        ch for ch in final_submission_handoff if ord(ch) < 32 and ch not in {"\n", "\t"}
    ]
    assert forbidden_control_chars == []
    assert (
        ".\\.venv\\Scripts\\python.exe docs/challenge_cup/reproducibility/verify_submission_package.py --root ."
        in final_submission_handoff
    )
    assert (
        ".\\.venv\\Scripts\\python.exe scripts/build_challenge_cup_final_acceptance_audit.py"
        in final_submission_handoff
    )
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
    objection_matrix = (
        PACKAGE_DIR / "reproducibility" / "judge_objection_response_matrix.md"
    ).read_text(encoding="utf-8")
    for phrase in [
        "Judge Objection Response Matrix",
        "OJ-01-normal-rag",
        "OJ-08-special-prize-claim",
        "30 seconds",
        "no award guarantee",
        "real expert feedback",
        "real timed rehearsal",
        "readiness gate is not an award guarantee",
    ]:
        assert phrase in objection_matrix
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
    assert "challenge_cup_failure_remediation_before_after.md" in eval_report
    assert "Day4 失败整改 before/after" in eval_report
    assert "答案级覆盖对照" in eval_report
    assert "补证整改计划" in eval_report
    assert "manual evidence supplement" in eval_report
    assert "context-only" in eval_report
    runbook = (PACKAGE_DIR / "reproducibility" / "runbook.md").read_text(encoding="utf-8")
    assert "build_challenge_cup_defense_deck.py" in runbook
    assert "build_challenge_cup_official_rubric_alignment.py" in runbook
    assert "record_challenge_cup_hard_evidence.py expert_feedback" in runbook
    assert "preflight_challenge_cup_hard_evidence.py expert_feedback" in runbook
    assert "record_challenge_cup_expert_outreach.py" in runbook
    assert "record_challenge_cup_timed_rehearsal_schedule.py" in runbook
    assert "record_challenge_cup_hard_evidence.py timed_rehearsal" in runbook
    assert "preflight_challenge_cup_hard_evidence.py timed_rehearsal" in runbook
    assert "run_challenge_cup_timed_rehearsal.py" in runbook
    assert "build_challenge_cup_expert_outreach_ledger.py" in runbook
    assert "build_challenge_cup_timed_rehearsal_schedule_ledger.py" in runbook
    assert "build_challenge_cup_hard_evidence_closure_board.py" in runbook
    assert "build_challenge_cup_hard_evidence_action_pack.py" in runbook
    assert "build_challenge_cup_hard_evidence_ledger.py" in runbook
    assert "build_challenge_cup_special_prize_readiness_dashboard.py" in runbook
    assert "build_challenge_cup_failure_remediation_before_after.py" in runbook
    assert "build_challenge_cup_application_value_quantification.py" in runbook
    assert "run_challenge_cup_live_demo_smoke.py" in runbook
    assert "run_challenge_cup_browser_demo_smoke.mjs" in runbook
    assert "check_challenge_cup_readiness.py" in runbook
    assert "check_challenge_cup_goal_completion.py" in runbook
    assert "build_challenge_cup_final_acceptance_audit.py" in runbook
    assert "verify_submission_package.py" in runbook
    manifest = (PACKAGE_DIR / "reproducibility" / "dataset_manifest.md").read_text(encoding="utf-8")
    assert "live_demo_smoke_report.md" in manifest
    assert "browser_demo_smoke_report.md" in manifest
    assert "application_validation_report.md" in manifest
    assert "application_value_quantification.md" in manifest
    assert "application_value_quantification.json" in manifest
    assert "11_应用场景与专家验证.md" in manifest
    assert "expert_feedback_form.md" in manifest
    assert "12_专家反馈采集与整改闭环.md" in manifest
    assert "readiness_gate_report.md" in manifest
    assert "poster/challenge_cup_a0_poster.html" in manifest
    assert "defense_console/index.html" in manifest
    assert "judge_objection_response_matrix.md" in manifest
    assert "21_知识产权与开源合规说明.md" in manifest
    assert "22_同类方案对比与创新性证据卡.md" in manifest
    assert "23_终审提交总目录与签收页.md" in manifest
    assert "goal_completion_report.md" in manifest
    assert "final_acceptance_audit.md" in manifest
    assert "final_acceptance_audit.json" in manifest
    assert "evidence_hashes.json" in manifest
    assert "evaluation_coverage_profile.json" in manifest
    assert "challenge_cup_graphrag_context_demo.md" in manifest
    assert "challenge_cup_graphrag_context_demo.json" in manifest
    assert "challenge_cup_graphrag_answer_benchmark.md" in manifest
    assert "challenge_cup_graphrag_answer_benchmark.json" in manifest
    assert "challenge_cup_graphrag_gap_remediation_plan.md" in manifest
    assert "challenge_cup_graphrag_gap_remediation_plan.json" in manifest
    assert "challenge_cup_failure_remediation_before_after.md" in manifest
    assert "challenge_cup_failure_remediation_before_after.json" in manifest
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
    assert "timed_rehearsal_schedule_ledger.md" in manifest
    assert "timed_rehearsal_schedule_ledger.json" in manifest
    assert "timed_rehearsal_schedule/README.md" in manifest
    assert "official_rubric_alignment.md" in manifest
    assert "official_rubric_alignment.json" in manifest
    assert "special_prize_readiness_dashboard.md" in manifest
    assert "special_prize_readiness_dashboard.json" in manifest
    assert "13_评委现场速览卡.md" in manifest
    assert "14_现场答辩操作Runbook.md" in manifest
    assert "15_结项交付移交清单.md" in manifest
    assert "16_现场问辩记录与整改台账.md" in manifest
    assert "17_评审风险控制与应急预案.md" in manifest
    assert "18_特等奖打分模拟与整改清单.md" in manifest
    assert "19_作品展墙报问辩与展台脚本.md" in manifest
    assert "20_成果转化与持续迭代路线图.md" in manifest
    assert "hard_evidence_closure_board.md" in manifest
    assert "hard_evidence_closure_board.json" in manifest
    assert "hard_evidence_action_pack.md" in manifest
    assert "hard_evidence_action_pack.json" in manifest
    assert "external_evidence_execution_kit.md" in manifest
    assert "external_evidence_execution_kit.json" in manifest
    assert "external_evidence_execution_kit/expert_review_handoff.md" in manifest
    assert "external_evidence_execution_kit/timed_rehearsal_observer_sheet.md" in manifest
    assert "challenge_cup_defense_deck.pptx" in manifest
    assert "challenge_cup_defense_speaker_notes.md" in manifest
    assert "hard_evidence_ledger.md" in manifest
    assert "hard_evidence_ledger.json" in manifest
    assert "hard_evidence/expert_feedback/README.md" in manifest
    assert "hard_evidence/timed_rehearsal/README.md" in manifest
    assert "challenge_cup_submission_package.zip" in manifest
    assert "challenge_cup_submission_archive_manifest.json" in manifest
    assert "verify_submission_package.py" in manifest
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
    assert "build_challenge_cup_final_acceptance_audit.py" in command_log
    assert "build_challenge_cup_hard_evidence_action_pack.py" in command_log
    assert "build_challenge_cup_external_evidence_execution_kit.py" in command_log
    assert "build_challenge_cup_special_prize_readiness_dashboard.py" in command_log
    assert "build_challenge_cup_judge_objection_matrix.py" in command_log
    assert "build_challenge_cup_failure_remediation_before_after.py" in command_log
    assert "build_challenge_cup_application_value_quantification.py" in command_log
    assert "Status: remediation_card_ablation_ready_no_live_retriever_claim" in command_log
    assert "Status: application_value_quantified_no_external_validation_claim" in command_log
    assert "Status: package_ready_awaiting_external_hard_evidence" in command_log
    assert "Status: special_prize_review_ready_with_external_evidence_gaps" in command_log
    assert "Status: pass (55/55 gates)" in command_log
    assert "Status: pass (54/54 gates)" not in command_log
    assert "Status: pass (53/53 gates)" not in command_log
    assert "Status: pass (52/52 gates)" not in command_log
    assert "Status: pass (51/51 gates)" not in command_log
    assert "Status: pass (50/50 gates)" not in command_log
    assert "Status: pass (49/49 gates)" not in command_log
    assert "Status: pass (48/48 gates)" not in command_log
    assert "Status: pass (47/47 gates)" not in command_log
    assert "Status: pass (46/46 gates)" not in command_log
    assert "Status: pass (45/45 gates)" not in command_log
    assert "Status: pass (44/44 gates)" not in command_log
    assert "Status: pass (43/43 gates)" not in command_log
    assert "Status: pass (42/42 gates)" not in command_log
    assert "Status: pass (41/41 gates)" not in command_log
    assert "Status: pass (40/40 gates)" not in command_log
    assert "Status: pass (37/37 gates)" not in command_log
    assert "Status: pass (36/36 gates)" not in command_log
    assert "Status: pass (35/35 gates)" not in command_log
    assert "Status: pass (33/33 gates)" not in command_log
    assert "Status: pass (32/32 gates)" not in command_log
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
    assert "docs/challenge_cup/13_评委现场速览卡.md" in evidence_files
    assert "docs/challenge_cup/14_现场答辩操作Runbook.md" in evidence_files
    assert "docs/challenge_cup/15_结项交付移交清单.md" in evidence_files
    assert "docs/challenge_cup/16_现场问辩记录与整改台账.md" in evidence_files
    assert "docs/challenge_cup/17_评审风险控制与应急预案.md" in evidence_files
    assert "docs/challenge_cup/18_特等奖打分模拟与整改清单.md" in evidence_files
    assert "docs/challenge_cup/19_作品展墙报问辩与展台脚本.md" in evidence_files
    assert "docs/challenge_cup/20_成果转化与持续迭代路线图.md" in evidence_files
    assert "docs/challenge_cup/21_知识产权与开源合规说明.md" in evidence_files
    assert "docs/challenge_cup/22_同类方案对比与创新性证据卡.md" in evidence_files
    assert "docs/challenge_cup/23_终审提交总目录与签收页.md" in evidence_files
    assert "docs/challenge_cup/poster/challenge_cup_a0_poster.html" in evidence_files
    assert "docs/challenge_cup/defense_console/index.html" in evidence_files
    assert "evaluation/reports/challenge_cup_graphrag_context_demo.md" in evidence_files
    assert "evaluation/reports/challenge_cup_graphrag_context_demo.json" in evidence_files
    assert "evaluation/reports/challenge_cup_graphrag_answer_benchmark.md" in evidence_files
    assert "evaluation/reports/challenge_cup_graphrag_answer_benchmark.json" in evidence_files
    assert "evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.md" in evidence_files
    assert "evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.json" in evidence_files
    assert "evaluation/reports/challenge_cup_failure_remediation_before_after.md" in evidence_files
    assert "evaluation/reports/challenge_cup_failure_remediation_before_after.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/graphrag_manual_evidence_supplement.csv" in evidence_files
    assert "docs/challenge_cup/11_应用场景与专家验证.md" in evidence_files
    assert "docs/challenge_cup/12_专家反馈采集与整改闭环.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/application_validation_report.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/application_value_quantification.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/application_value_quantification.json" in evidence_files
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
    assert "docs/challenge_cup/reproducibility/timed_rehearsal_schedule_ledger.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/timed_rehearsal_schedule_ledger.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/timed_rehearsal_schedule/README.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/official_rubric_alignment.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/official_rubric_alignment.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/judge_objection_response_matrix.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/judge_objection_response_matrix.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/hard_evidence_closure_board.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/hard_evidence_closure_board.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/hard_evidence_action_pack.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/hard_evidence_action_pack.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/external_evidence_execution_kit.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/external_evidence_execution_kit.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/external_evidence_execution_kit/expert_review_handoff.md" in evidence_files
    assert (
        "docs/challenge_cup/reproducibility/external_evidence_execution_kit/"
        "timed_rehearsal_observer_sheet.md"
    ) in evidence_files
    assert "docs/challenge_cup/reproducibility/readiness_gate_report.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/goal_completion_report.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/final_acceptance_audit.md" in evidence_files
    assert "docs/challenge_cup/reproducibility/final_acceptance_audit.json" in evidence_files
    assert "docs/challenge_cup/reproducibility/verify_submission_package.py" in evidence_files
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
    assert "preflight_challenge_cup_hard_evidence.py expert_feedback" in hard_evidence_readme
    assert "--confirm-real-feedback" in hard_evidence_readme
    assert "record_challenge_cup_hard_evidence.py timed_rehearsal" in hard_evidence_readme
    assert "preflight_challenge_cup_hard_evidence.py timed_rehearsal" in hard_evidence_readme
    assert "--confirm-real-rehearsal" in hard_evidence_readme
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
    schedule_ledger = json.loads(
        (PACKAGE_DIR / "reproducibility" / "timed_rehearsal_schedule_ledger.json").read_text(encoding="utf-8")
    )
    assert schedule_ledger["report_type"] == "challenge_cup_timed_rehearsal_schedule_ledger"
    assert schedule_ledger["status"] == "ready_to_schedule_no_rehearsal_recorded"
    assert schedule_ledger["no_timed_rehearsal_claimed"] is True
    assert schedule_ledger["does_not_satisfy_goal_completion"] is True
    assert schedule_ledger["schedule_record_count"] == 0
    schedule_ledger_md = (
        PACKAGE_DIR / "reproducibility" / "timed_rehearsal_schedule_ledger.md"
    ).read_text(encoding="utf-8")
    assert "Timed Rehearsal Schedule Ledger" in schedule_ledger_md
    assert "do not prove a timed rehearsal was completed" in schedule_ledger_md
    closure_board = json.loads(
        (PACKAGE_DIR / "reproducibility" / "hard_evidence_closure_board.json").read_text(encoding="utf-8")
    )
    assert closure_board["report_type"] == "challenge_cup_hard_evidence_closure_board"
    assert closure_board["status"] == "awaiting_real_external_evidence_closure"
    assert closure_board["no_completion_claimed"] is True
    assert closure_board["does_not_satisfy_goal_completion"] is True
    assert closure_board["blocker_count"] == 2
    closure_board_md = (
        PACKAGE_DIR / "reproducibility" / "hard_evidence_closure_board.md"
    ).read_text(encoding="utf-8")
    assert "Hard Evidence Closure Board" in closure_board_md
    assert "does not satisfy goal completion" in closure_board_md
    action_pack = json.loads(
        (PACKAGE_DIR / "reproducibility" / "hard_evidence_action_pack.json").read_text(encoding="utf-8")
    )
    assert action_pack["report_type"] == "challenge_cup_hard_evidence_action_pack"
    assert action_pack["status"] == "ready_for_real_external_evidence_collection"
    assert action_pack["completion_claim_allowed"] is False
    assert action_pack["does_not_satisfy_goal_completion"] is True
    assert {item["category"] for item in action_pack["action_streams"]} == {
        "expert_feedback",
        "timed_rehearsal",
    }
    assert "--confirm-real-feedback" in json.dumps(action_pack, ensure_ascii=False)
    assert "--confirm-real-rehearsal" in json.dumps(action_pack, ensure_ascii=False)
    assert "preflight_challenge_cup_hard_evidence.py" in json.dumps(action_pack, ensure_ascii=False)
    execution_kit = json.loads(
        (PACKAGE_DIR / "reproducibility" / "external_evidence_execution_kit.json").read_text(encoding="utf-8")
    )
    assert execution_kit["report_type"] == "challenge_cup_external_evidence_execution_kit"
    assert execution_kit["status"] == "ready_for_external_execution_handoff"
    assert execution_kit["completion_claim_allowed"] is False
    assert execution_kit["does_not_satisfy_goal_completion"] is True
    assert {item["hard_evidence_category"] for item in execution_kit["execution_packets"]} == {
        "expert_feedback",
        "timed_rehearsal",
    }
    assert "--confirm-real-feedback" in json.dumps(execution_kit, ensure_ascii=False)
    assert "--confirm-real-rehearsal" in json.dumps(execution_kit, ensure_ascii=False)
    assert "preflight_challenge_cup_hard_evidence.py" in json.dumps(execution_kit, ensure_ascii=False)
    goal_completion = (PACKAGE_DIR / "reproducibility" / "goal_completion_report.md").read_text(encoding="utf-8")
    assert "Challenge Cup Goal Completion Gate" in goal_completion
    assert "Status: `fail`" in goal_completion
    assert "completion_claim_allowed=False" in goal_completion
    assert "不能标记目标完成" in goal_completion
    final_acceptance = json.loads(
        (PACKAGE_DIR / "reproducibility" / "final_acceptance_audit.json").read_text(encoding="utf-8")
    )
    assert final_acceptance["report_type"] == "challenge_cup_final_acceptance_audit"
    assert final_acceptance["status"] == "package_ready_awaiting_external_hard_evidence"
    assert final_acceptance["package_readiness"]["status"] == "pass"
    assert final_acceptance["package_readiness"]["passed"] == 55
    assert final_acceptance["package_readiness"]["total"] == 55
    assert final_acceptance["submission_package_verifier"]["available"] is True
    assert final_acceptance["submission_package_verifier"]["archived"] is True
    assert final_acceptance["goal_completion"]["status"] == "fail"
    assert final_acceptance["goal_completion"]["completion_claim_allowed"] is False
    assert final_acceptance["can_submit_for_package_review"] is True
    assert final_acceptance["can_mark_goal_complete"] is False
    assert {item["category"] for item in final_acceptance["blocking_items"]} == {
        "expert_feedback",
        "timed_rehearsal",
    }
    official_rubric = json.loads((PACKAGE_DIR / "reproducibility" / "official_rubric_alignment.json").read_text(encoding="utf-8"))
    assert official_rubric["report_type"] == "challenge_cup_official_rubric_alignment"
    assert official_rubric["official_source_count"] >= 5
    source_ids = {source["source_id"] for source in official_rubric["official_sources"]}
    assert "tsinghua_44th_2026" in source_ids
    assert official_rubric["dimensions"]["academic_or_practical_value"]["evidence_files"]
    assert official_rubric["dimensions"]["innovation"]["evidence_files"]
    assert official_rubric["dimensions"]["completion"]["evidence_files"]
    assert official_rubric["dimensions"]["defense_performance"]["evidence_files"]
    assert official_rubric["special_prize_policy"]["max_special_prize_count"] == 7
    assert official_rubric["special_prize_policy"]["latest_public_result_source_id"] == "tsinghua_44th_2026"
    assert official_rubric["special_prize_policy"]["may_be_vacant"] is True
    assert official_rubric["integrity_rules"]["no_award_guarantee"] is True
    source_lock = official_rubric["official_source_lock"]
    assert source_lock["current_as_of"] == "2026-06-06"
    latest_public_result = source_lock["latest_public_result"]
    assert latest_public_result["source_id"] == "tsinghua_44th_2026"
    assert latest_public_result["source_url"] == "https://www.tsinghua.edu.cn/info/1177/125861.htm"
    assert latest_public_result["published_date"] == "2026-04-29"
    assert latest_public_result["final_defense_date"] == "2026-04-25"
    assert latest_public_result["registration_count"] == 337
    assert latest_public_result["school_finalist_counts"] == {"undergraduate": 173, "graduate": 9}
    assert latest_public_result["main_track_award_counts"]["special_prize"] == 7
    assert latest_public_result["main_track_award_counts"]["total"] == 114
    assert source_lock["recency_policy"]["must_recheck_before_final_submission"] is True
    assert source_lock["recency_policy"]["no_award_guarantee"] is True
    special_prize_dashboard = json.loads(
        (PACKAGE_DIR / "reproducibility" / "special_prize_readiness_dashboard.json").read_text(encoding="utf-8")
    )
    assert special_prize_dashboard["report_type"] == "challenge_cup_special_prize_readiness_dashboard"
    assert special_prize_dashboard["status"] == "special_prize_review_ready_with_external_evidence_gaps"
    assert special_prize_dashboard["no_award_guarantee"] is True
    assert special_prize_dashboard["completion_claim_allowed"] is False
    assert special_prize_dashboard["can_mark_goal_complete"] is False
    assert {risk["risk_id"] for risk in special_prize_dashboard["top_risks"]} == {
        "expert_feedback",
        "timed_rehearsal",
        "award_overclaim",
    }
    official_rubric_md = (PACKAGE_DIR / "reproducibility" / "official_rubric_alignment.md").read_text(encoding="utf-8")
    for term in ["学术/实用价值", "创新性", "作品完成度", "现场答辩", "第44届", "特等奖7项", "不承诺获奖"]:
        assert term in official_rubric_md
    for term in ["Official Source Lock", "2026-04-25", "2026-04-29", "337", "173", "114"]:
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
    assert "docs/challenge_cup/reproducibility/verify_submission_package.py" in archive_entries
    assert "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md" in archive_entries
    assert "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.json" in archive_entries
    assert "docs/challenge_cup/reproducibility/hard_evidence_action_pack.md" in archive_entries
    assert "docs/challenge_cup/reproducibility/hard_evidence_action_pack.json" in archive_entries
    assert "docs/challenge_cup/reproducibility/external_evidence_execution_kit.md" in archive_entries
    assert "docs/challenge_cup/reproducibility/external_evidence_execution_kit.json" in archive_entries
    assert "docs/challenge_cup/reproducibility/external_evidence_execution_kit/expert_review_handoff.md" in archive_entries
    assert (
        "docs/challenge_cup/reproducibility/external_evidence_execution_kit/"
        "timed_rehearsal_observer_sheet.md"
    ) in archive_entries
    assert "docs/challenge_cup/reproducibility/final_acceptance_audit.md" in archive_entries
    assert "docs/challenge_cup/reproducibility/final_acceptance_audit.json" in archive_entries
    assert "docs/challenge_cup/reproducibility/application_value_quantification.md" in archive_entries
    assert "docs/challenge_cup/reproducibility/application_value_quantification.json" in archive_entries
    assert "evaluation/reports/challenge_cup_failure_remediation_before_after.md" in archive_entries
    assert "evaluation/reports/challenge_cup_failure_remediation_before_after.json" in archive_entries
    assert "docs/challenge_cup/13_评委现场速览卡.md" in archive_entries
    assert "docs/challenge_cup/14_现场答辩操作Runbook.md" in archive_entries
    assert "docs/challenge_cup/15_结项交付移交清单.md" in archive_entries
    assert "docs/challenge_cup/16_现场问辩记录与整改台账.md" in archive_entries
    assert "docs/challenge_cup/17_评审风险控制与应急预案.md" in archive_entries
    assert "docs/challenge_cup/18_特等奖打分模拟与整改清单.md" in archive_entries
    assert "docs/challenge_cup/19_作品展墙报问辩与展台脚本.md" in archive_entries
    assert "docs/challenge_cup/20_成果转化与持续迭代路线图.md" in archive_entries
    assert "docs/challenge_cup/21_知识产权与开源合规说明.md" in archive_entries
    assert "docs/challenge_cup/22_同类方案对比与创新性证据卡.md" in archive_entries
    assert "docs/challenge_cup/23_终审提交总目录与签收页.md" in archive_entries
    assert "docs/challenge_cup/poster/challenge_cup_a0_poster.html" in archive_entries
    assert "docs/challenge_cup/defense_console/index.html" in archive_entries
    assert "docs/challenge_cup/reproducibility/judge_objection_response_matrix.md" in archive_entries
    assert "docs/challenge_cup/reproducibility/judge_objection_response_matrix.json" in archive_entries
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
        "docs/challenge_cup/reproducibility/final_acceptance_audit.md",
        "docs/challenge_cup/reproducibility/final_acceptance_audit.json",
        "docs/challenge_cup/reproducibility/official_rubric_alignment.md",
        "docs/challenge_cup/reproducibility/official_rubric_alignment.json",
        "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md",
        "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.json",
        "docs/challenge_cup/reproducibility/hard_evidence_closure_board.md",
        "docs/challenge_cup/reproducibility/hard_evidence_closure_board.json",
        "docs/challenge_cup/reproducibility/hard_evidence_action_pack.md",
        "docs/challenge_cup/reproducibility/hard_evidence_action_pack.json",
        "docs/challenge_cup/reproducibility/external_evidence_execution_kit.md",
        "docs/challenge_cup/reproducibility/external_evidence_execution_kit.json",
        "docs/challenge_cup/reproducibility/external_evidence_execution_kit/expert_review_handoff.md",
        (
            "docs/challenge_cup/reproducibility/external_evidence_execution_kit/"
            "timed_rehearsal_observer_sheet.md"
        ),
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


def test_submission_package_verifier_runs_from_extracted_archive(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, "scripts/build_challenge_cup_package.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    archive_path = PACKAGE_DIR / "reproducibility" / "challenge_cup_submission_package.zip"
    extract_root = tmp_path / "submission"
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(extract_root)

    verifier = extract_root / "docs" / "challenge_cup" / "reproducibility" / "verify_submission_package.py"
    output_json = tmp_path / "verification.json"
    result = subprocess.run(
        [sys.executable, str(verifier), "--root", str(extract_root), "--json-output", str(output_json)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert "Status: pass" in result.stdout
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["report_type"] == "challenge_cup_submission_package_verification"
    assert payload["status"] == "pass"
    assert payload["hashed_files_verified"] >= 50
    assert payload["live_smoke_status"] == "pass"
    assert payload["browser_smoke_status"] == "pass"
    assert payload["completion_claim_allowed"] is False


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
        PACKAGE_DIR / "13_评委现场速览卡.md",
        PACKAGE_DIR / "14_现场答辩操作Runbook.md",
        PACKAGE_DIR / "15_结项交付移交清单.md",
        PACKAGE_DIR / "16_现场问辩记录与整改台账.md",
        PACKAGE_DIR / "17_评审风险控制与应急预案.md",
        PACKAGE_DIR / "18_特等奖打分模拟与整改清单.md",
        PACKAGE_DIR / "19_作品展墙报问辩与展台脚本.md",
        PACKAGE_DIR / "20_成果转化与持续迭代路线图.md",
        PACKAGE_DIR / "21_知识产权与开源合规说明.md",
        PACKAGE_DIR / "22_同类方案对比与创新性证据卡.md",
        PACKAGE_DIR / "23_终审提交总目录与签收页.md",
        PACKAGE_DIR / "poster" / "challenge_cup_a0_poster.html",
        PACKAGE_DIR / "03_实验评测报告.md",
        PACKAGE_DIR / "reproducibility" / "command_log.md",
        PACKAGE_DIR / "reproducibility" / "goal_completion_report.md",
        PACKAGE_DIR / "reproducibility" / "final_acceptance_audit.md",
        PACKAGE_DIR / "reproducibility" / "final_acceptance_audit.json",
        PACKAGE_DIR / "11_应用场景与专家验证.md",
        PACKAGE_DIR / "reproducibility" / "application_validation_report.md",
        PACKAGE_DIR / "reproducibility" / "application_value_quantification.md",
        PACKAGE_DIR / "reproducibility" / "application_value_quantification.json",
        PACKAGE_DIR / "reproducibility" / "defense_rehearsal_scorecard.md",
        PACKAGE_DIR / "reproducibility" / "defense_rehearsal_scorecard.json",
        PACKAGE_DIR / "reproducibility" / "defense_rehearsal_result_packet.md",
        PACKAGE_DIR / "reproducibility" / "defense_rehearsal_result_packet.json",
        PACKAGE_DIR / "reproducibility" / "expert_feedback_request_packet.md",
        PACKAGE_DIR / "reproducibility" / "expert_feedback_request_packet.json",
        PACKAGE_DIR / "reproducibility" / "expert_feedback_outreach_ledger.md",
        PACKAGE_DIR / "reproducibility" / "expert_feedback_outreach_ledger.json",
        PACKAGE_DIR / "reproducibility" / "expert_feedback_outreach" / "README.md",
        PACKAGE_DIR / "reproducibility" / "timed_rehearsal_schedule_ledger.md",
        PACKAGE_DIR / "reproducibility" / "timed_rehearsal_schedule_ledger.json",
        PACKAGE_DIR / "reproducibility" / "timed_rehearsal_schedule" / "README.md",
        PACKAGE_DIR / "reproducibility" / "official_rubric_alignment.md",
        PACKAGE_DIR / "reproducibility" / "official_rubric_alignment.json",
        PACKAGE_DIR / "reproducibility" / "special_prize_readiness_dashboard.md",
        PACKAGE_DIR / "reproducibility" / "special_prize_readiness_dashboard.json",
        PACKAGE_DIR / "reproducibility" / "hard_evidence_closure_board.md",
        PACKAGE_DIR / "reproducibility" / "hard_evidence_closure_board.json",
        PACKAGE_DIR / "reproducibility" / "hard_evidence_action_pack.md",
        PACKAGE_DIR / "reproducibility" / "hard_evidence_action_pack.json",
        PACKAGE_DIR / "reproducibility" / "external_evidence_execution_kit.md",
        PACKAGE_DIR / "reproducibility" / "external_evidence_execution_kit.json",
        PACKAGE_DIR / "reproducibility" / "external_evidence_execution_kit" / "expert_review_handoff.md",
        PACKAGE_DIR
        / "reproducibility"
        / "external_evidence_execution_kit"
        / "timed_rehearsal_observer_sheet.md",
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
        "docs/challenge_cup/reproducibility/application_value_quantification.json",
        "docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.json",
        "docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.json",
        "docs/challenge_cup/reproducibility/expert_feedback_request_packet.json",
        "docs/challenge_cup/reproducibility/expert_feedback_outreach_ledger.json",
        "docs/challenge_cup/reproducibility/timed_rehearsal_schedule_ledger.json",
        "docs/challenge_cup/reproducibility/official_rubric_alignment.json",
        "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.json",
        "docs/challenge_cup/reproducibility/hard_evidence_closure_board.json",
        "docs/challenge_cup/reproducibility/hard_evidence_action_pack.json",
        "docs/challenge_cup/reproducibility/external_evidence_execution_kit.json",
        "docs/challenge_cup/reproducibility/hard_evidence_ledger.json",
        "docs/challenge_cup/reproducibility/final_acceptance_audit.json",
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
