from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from challenge_cup_expert_review_dimensions import missing_required_review_dimension_groups
from challenge_cup_hard_evidence_dates import is_not_future_iso_date
from challenge_cup_hard_evidence_sources import source_path_looks_like_metadata, source_sha256_failure


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "docs" / "challenge_cup"
REPRO_DIR = PACKAGE_DIR / "reproducibility"
CURRENT_READINESS_GATE_COUNT = 62
PACKAGE_MANIFEST = PACKAGE_DIR / "package_manifest.json"
BROWSER_SMOKE_JSON = REPRO_DIR / "browser_demo_smoke_report.json"
LIVE_SMOKE_JSON = REPRO_DIR / "live_demo_smoke_report.json"
CLAIM_MATRIX = PACKAGE_DIR / "07_评审主张证据矩阵.md"
ACCEPTANCE_CHECKLIST = PACKAGE_DIR / "06_结项验收清单.md"
AWARD_SELF_EVAL = PACKAGE_DIR / "08_特等奖评审自评表.md"
EXPERT_REVIEW_INDEX = PACKAGE_DIR / "09_专家快速审阅索引.md"
DEFENSE_REHEARSAL_CARD = PACKAGE_DIR / "10_答辩攻防与彩排卡.md"
JUDGE_BRIEFING_CARD = PACKAGE_DIR / "13_评委现场速览卡.md"
ONSITE_DEFENSE_RUNBOOK = PACKAGE_DIR / "14_现场答辩操作Runbook.md"
PROJECT_HANDOFF_CHECKLIST = PACKAGE_DIR / "15_结项交付移交清单.md"
DEFENSE_QA_REMEDIATION_LEDGER = PACKAGE_DIR / "16_现场问辩记录与整改台账.md"
REVIEW_RISK_RESPONSE_PLAN = PACKAGE_DIR / "17_评审风险控制与应急预案.md"
SPECIAL_PRIZE_SCORING_DRILL = PACKAGE_DIR / "18_特等奖打分模拟与整改清单.md"
POSTER_BOOTH_QA_PACK = PACKAGE_DIR / "19_作品展墙报问辩与展台脚本.md"
COMMERCIALIZATION_ROADMAP = PACKAGE_DIR / "20_成果转化与持续迭代路线图.md"
IP_OPEN_SOURCE_COMPLIANCE = PACKAGE_DIR / "21_知识产权与开源合规说明.md"
LOCAL_BASELINE_DIFFERENTIATION = PACKAGE_DIR / "22_同类方案对比与创新性证据卡.md"
FINAL_SUBMISSION_HANDOFF = PACKAGE_DIR / "23_终审提交总目录与签收页.md"
POSTER_BOARD_HTML = PACKAGE_DIR / "poster" / "challenge_cup_a0_poster.html"
DEFENSE_CONTROL_CONSOLE = PACKAGE_DIR / "defense_console" / "index.html"
DEFENSE_REHEARSAL_SCORECARD_MD = REPRO_DIR / "defense_rehearsal_scorecard.md"
DEFENSE_REHEARSAL_SCORECARD_JSON = REPRO_DIR / "defense_rehearsal_scorecard.json"
DEFENSE_REHEARSAL_RESULT_PACKET_MD = REPRO_DIR / "defense_rehearsal_result_packet.md"
DEFENSE_REHEARSAL_RESULT_PACKET_JSON = REPRO_DIR / "defense_rehearsal_result_packet.json"
EXPERT_FEEDBACK_REQUEST_PACKET_MD = REPRO_DIR / "expert_feedback_request_packet.md"
EXPERT_FEEDBACK_REQUEST_PACKET_JSON = REPRO_DIR / "expert_feedback_request_packet.json"
EXPERT_FEEDBACK_OUTREACH_LEDGER_MD_RELATIVE = (
    "docs/challenge_cup/reproducibility/expert_feedback_outreach_ledger.md"
)
EXPERT_FEEDBACK_OUTREACH_LEDGER_JSON_RELATIVE = (
    "docs/challenge_cup/reproducibility/expert_feedback_outreach_ledger.json"
)
EXPERT_FEEDBACK_OUTREACH_README_RELATIVE = (
    "docs/challenge_cup/reproducibility/expert_feedback_outreach/README.md"
)
TIMED_REHEARSAL_SCHEDULE_LEDGER_MD_RELATIVE = (
    "docs/challenge_cup/reproducibility/timed_rehearsal_schedule_ledger.md"
)
TIMED_REHEARSAL_SCHEDULE_LEDGER_JSON_RELATIVE = (
    "docs/challenge_cup/reproducibility/timed_rehearsal_schedule_ledger.json"
)
TIMED_REHEARSAL_SCHEDULE_README_RELATIVE = (
    "docs/challenge_cup/reproducibility/timed_rehearsal_schedule/README.md"
)
HARD_EVIDENCE_LEDGER_MD_RELATIVE = "docs/challenge_cup/reproducibility/hard_evidence_ledger.md"
HARD_EVIDENCE_LEDGER_JSON_RELATIVE = "docs/challenge_cup/reproducibility/hard_evidence_ledger.json"
HARD_EVIDENCE_README_RELATIVE = "docs/challenge_cup/reproducibility/hard_evidence/README.md"
HARD_EVIDENCE_EXPERT_README_RELATIVE = "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/README.md"
HARD_EVIDENCE_REHEARSAL_README_RELATIVE = "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/README.md"
OFFICIAL_RUBRIC_ALIGNMENT_MD_RELATIVE = "docs/challenge_cup/reproducibility/official_rubric_alignment.md"
OFFICIAL_RUBRIC_ALIGNMENT_JSON_RELATIVE = "docs/challenge_cup/reproducibility/official_rubric_alignment.json"
JUDGE_OBJECTION_MATRIX_MD_RELATIVE = "docs/challenge_cup/reproducibility/judge_objection_response_matrix.md"
JUDGE_OBJECTION_MATRIX_JSON_RELATIVE = "docs/challenge_cup/reproducibility/judge_objection_response_matrix.json"
FAILURE_REMEDIATION_BEFORE_AFTER_MD_RELATIVE = (
    "evaluation/reports/challenge_cup_failure_remediation_before_after.md"
)
FAILURE_REMEDIATION_BEFORE_AFTER_JSON_RELATIVE = (
    "evaluation/reports/challenge_cup_failure_remediation_before_after.json"
)
SPECIAL_PRIZE_READINESS_DASHBOARD_MD_RELATIVE = (
    "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md"
)
SPECIAL_PRIZE_READINESS_DASHBOARD_JSON_RELATIVE = (
    "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.json"
)
HARD_EVIDENCE_CLOSURE_BOARD_MD_RELATIVE = "docs/challenge_cup/reproducibility/hard_evidence_closure_board.md"
HARD_EVIDENCE_CLOSURE_BOARD_JSON_RELATIVE = "docs/challenge_cup/reproducibility/hard_evidence_closure_board.json"
HARD_EVIDENCE_ACTION_PACK_MD_RELATIVE = "docs/challenge_cup/reproducibility/hard_evidence_action_pack.md"
HARD_EVIDENCE_ACTION_PACK_JSON_RELATIVE = "docs/challenge_cup/reproducibility/hard_evidence_action_pack.json"
EXTERNAL_EVIDENCE_EXECUTION_KIT_MD_RELATIVE = (
    "docs/challenge_cup/reproducibility/external_evidence_execution_kit.md"
)
EXTERNAL_EVIDENCE_EXECUTION_KIT_JSON_RELATIVE = (
    "docs/challenge_cup/reproducibility/external_evidence_execution_kit.json"
)
EXTERNAL_EVIDENCE_EXPERT_HANDOFF_RELATIVE = (
    "docs/challenge_cup/reproducibility/external_evidence_execution_kit/expert_review_handoff.md"
)
EXTERNAL_EVIDENCE_TIMED_REHEARSAL_OBSERVER_RELATIVE = (
    "docs/challenge_cup/reproducibility/external_evidence_execution_kit/timed_rehearsal_observer_sheet.md"
)
FINAL_ACCEPTANCE_AUDIT_MD_RELATIVE = "docs/challenge_cup/reproducibility/final_acceptance_audit.md"
FINAL_ACCEPTANCE_AUDIT_JSON_RELATIVE = "docs/challenge_cup/reproducibility/final_acceptance_audit.json"
APPLICATION_VALUE_QUANTIFICATION_MD_RELATIVE = (
    "docs/challenge_cup/reproducibility/application_value_quantification.md"
)
APPLICATION_VALUE_QUANTIFICATION_JSON_RELATIVE = (
    "docs/challenge_cup/reproducibility/application_value_quantification.json"
)
NUMERIC_TRACEABILITY_REPORT_MD_RELATIVE = "docs/challenge_cup/reproducibility/numeric_traceability_report.md"
NUMERIC_TRACEABILITY_REPORT_JSON_RELATIVE = "docs/challenge_cup/reproducibility/numeric_traceability_report.json"
NO_ANSWER_BOUNDARY_EVALUATION_MD_RELATIVE = (
    "docs/challenge_cup/reproducibility/no_answer_boundary_evaluation.md"
)
NO_ANSWER_BOUNDARY_EVALUATION_JSON_RELATIVE = (
    "docs/challenge_cup/reproducibility/no_answer_boundary_evaluation.json"
)
CLAIM_INTEGRITY_REPORT_MD_RELATIVE = "docs/challenge_cup/reproducibility/claim_integrity_report.md"
CLAIM_INTEGRITY_REPORT_JSON_RELATIVE = "docs/challenge_cup/reproducibility/claim_integrity_report.json"
RUBRIC_DEFENSE_COVERAGE_MD_RELATIVE = "docs/challenge_cup/reproducibility/rubric_defense_coverage.md"
RUBRIC_DEFENSE_COVERAGE_JSON_RELATIVE = "docs/challenge_cup/reproducibility/rubric_defense_coverage.json"
DEFENSE_SLIDE_TRACEABILITY_MD_RELATIVE = "docs/challenge_cup/reproducibility/defense_slide_traceability.md"
DEFENSE_SLIDE_TRACEABILITY_JSON_RELATIVE = "docs/challenge_cup/reproducibility/defense_slide_traceability.json"
RUNTIME_REPRODUCIBILITY_SNAPSHOT_MD_RELATIVE = (
    "docs/challenge_cup/reproducibility/runtime_reproducibility_snapshot.md"
)
RUNTIME_REPRODUCIBILITY_SNAPSHOT_JSON_RELATIVE = (
    "docs/challenge_cup/reproducibility/runtime_reproducibility_snapshot.json"
)
VERIFICATION_TRANSCRIPT_MD_RELATIVE = "docs/challenge_cup/reproducibility/verification_transcript.md"
VERIFICATION_TRANSCRIPT_JSON_RELATIVE = "docs/challenge_cup/reproducibility/verification_transcript.json"
EXPERT_FEEDBACK_OUTREACH_LEDGER_MD = REPO_ROOT / EXPERT_FEEDBACK_OUTREACH_LEDGER_MD_RELATIVE
EXPERT_FEEDBACK_OUTREACH_LEDGER_JSON = REPO_ROOT / EXPERT_FEEDBACK_OUTREACH_LEDGER_JSON_RELATIVE
EXPERT_FEEDBACK_OUTREACH_README = REPO_ROOT / EXPERT_FEEDBACK_OUTREACH_README_RELATIVE
TIMED_REHEARSAL_SCHEDULE_LEDGER_MD = REPO_ROOT / TIMED_REHEARSAL_SCHEDULE_LEDGER_MD_RELATIVE
TIMED_REHEARSAL_SCHEDULE_LEDGER_JSON = REPO_ROOT / TIMED_REHEARSAL_SCHEDULE_LEDGER_JSON_RELATIVE
TIMED_REHEARSAL_SCHEDULE_README = REPO_ROOT / TIMED_REHEARSAL_SCHEDULE_README_RELATIVE
HARD_EVIDENCE_LEDGER_MD = REPO_ROOT / HARD_EVIDENCE_LEDGER_MD_RELATIVE
HARD_EVIDENCE_LEDGER_JSON = REPO_ROOT / HARD_EVIDENCE_LEDGER_JSON_RELATIVE
HARD_EVIDENCE_README = REPO_ROOT / HARD_EVIDENCE_README_RELATIVE
HARD_EVIDENCE_EXPERT_README = REPO_ROOT / HARD_EVIDENCE_EXPERT_README_RELATIVE
HARD_EVIDENCE_REHEARSAL_README = REPO_ROOT / HARD_EVIDENCE_REHEARSAL_README_RELATIVE
OFFICIAL_RUBRIC_ALIGNMENT_MD = REPO_ROOT / OFFICIAL_RUBRIC_ALIGNMENT_MD_RELATIVE
OFFICIAL_RUBRIC_ALIGNMENT_JSON = REPO_ROOT / OFFICIAL_RUBRIC_ALIGNMENT_JSON_RELATIVE
JUDGE_OBJECTION_MATRIX_MD = REPO_ROOT / JUDGE_OBJECTION_MATRIX_MD_RELATIVE
JUDGE_OBJECTION_MATRIX_JSON = REPO_ROOT / JUDGE_OBJECTION_MATRIX_JSON_RELATIVE
FAILURE_REMEDIATION_BEFORE_AFTER_MD = REPO_ROOT / FAILURE_REMEDIATION_BEFORE_AFTER_MD_RELATIVE
FAILURE_REMEDIATION_BEFORE_AFTER_JSON = REPO_ROOT / FAILURE_REMEDIATION_BEFORE_AFTER_JSON_RELATIVE
SPECIAL_PRIZE_READINESS_DASHBOARD_MD = REPO_ROOT / SPECIAL_PRIZE_READINESS_DASHBOARD_MD_RELATIVE
SPECIAL_PRIZE_READINESS_DASHBOARD_JSON = REPO_ROOT / SPECIAL_PRIZE_READINESS_DASHBOARD_JSON_RELATIVE
HARD_EVIDENCE_CLOSURE_BOARD_MD = REPO_ROOT / HARD_EVIDENCE_CLOSURE_BOARD_MD_RELATIVE
HARD_EVIDENCE_CLOSURE_BOARD_JSON = REPO_ROOT / HARD_EVIDENCE_CLOSURE_BOARD_JSON_RELATIVE
HARD_EVIDENCE_ACTION_PACK_MD = REPO_ROOT / HARD_EVIDENCE_ACTION_PACK_MD_RELATIVE
HARD_EVIDENCE_ACTION_PACK_JSON = REPO_ROOT / HARD_EVIDENCE_ACTION_PACK_JSON_RELATIVE
EXTERNAL_EVIDENCE_EXECUTION_KIT_MD = REPO_ROOT / EXTERNAL_EVIDENCE_EXECUTION_KIT_MD_RELATIVE
EXTERNAL_EVIDENCE_EXECUTION_KIT_JSON = REPO_ROOT / EXTERNAL_EVIDENCE_EXECUTION_KIT_JSON_RELATIVE
EXTERNAL_EVIDENCE_EXPERT_HANDOFF = REPO_ROOT / EXTERNAL_EVIDENCE_EXPERT_HANDOFF_RELATIVE
EXTERNAL_EVIDENCE_TIMED_REHEARSAL_OBSERVER = REPO_ROOT / EXTERNAL_EVIDENCE_TIMED_REHEARSAL_OBSERVER_RELATIVE
FINAL_ACCEPTANCE_AUDIT_MD = REPO_ROOT / FINAL_ACCEPTANCE_AUDIT_MD_RELATIVE
FINAL_ACCEPTANCE_AUDIT_JSON = REPO_ROOT / FINAL_ACCEPTANCE_AUDIT_JSON_RELATIVE
APPLICATION_VALUE_QUANTIFICATION_MD = REPO_ROOT / APPLICATION_VALUE_QUANTIFICATION_MD_RELATIVE
APPLICATION_VALUE_QUANTIFICATION_JSON = REPO_ROOT / APPLICATION_VALUE_QUANTIFICATION_JSON_RELATIVE
NUMERIC_TRACEABILITY_REPORT_MD = REPO_ROOT / NUMERIC_TRACEABILITY_REPORT_MD_RELATIVE
NUMERIC_TRACEABILITY_REPORT_JSON = REPO_ROOT / NUMERIC_TRACEABILITY_REPORT_JSON_RELATIVE
NO_ANSWER_BOUNDARY_EVALUATION_MD = REPO_ROOT / NO_ANSWER_BOUNDARY_EVALUATION_MD_RELATIVE
NO_ANSWER_BOUNDARY_EVALUATION_JSON = REPO_ROOT / NO_ANSWER_BOUNDARY_EVALUATION_JSON_RELATIVE
CLAIM_INTEGRITY_REPORT_MD = REPO_ROOT / CLAIM_INTEGRITY_REPORT_MD_RELATIVE
CLAIM_INTEGRITY_REPORT_JSON = REPO_ROOT / CLAIM_INTEGRITY_REPORT_JSON_RELATIVE
RUBRIC_DEFENSE_COVERAGE_MD = REPO_ROOT / RUBRIC_DEFENSE_COVERAGE_MD_RELATIVE
RUBRIC_DEFENSE_COVERAGE_JSON = REPO_ROOT / RUBRIC_DEFENSE_COVERAGE_JSON_RELATIVE
DEFENSE_SLIDE_TRACEABILITY_MD = REPO_ROOT / DEFENSE_SLIDE_TRACEABILITY_MD_RELATIVE
DEFENSE_SLIDE_TRACEABILITY_JSON = REPO_ROOT / DEFENSE_SLIDE_TRACEABILITY_JSON_RELATIVE
RUNTIME_REPRODUCIBILITY_SNAPSHOT_MD = REPO_ROOT / RUNTIME_REPRODUCIBILITY_SNAPSHOT_MD_RELATIVE
RUNTIME_REPRODUCIBILITY_SNAPSHOT_JSON = REPO_ROOT / RUNTIME_REPRODUCIBILITY_SNAPSHOT_JSON_RELATIVE
VERIFICATION_TRANSCRIPT_MD = REPO_ROOT / VERIFICATION_TRANSCRIPT_MD_RELATIVE
VERIFICATION_TRANSCRIPT_JSON = REPO_ROOT / VERIFICATION_TRANSCRIPT_JSON_RELATIVE
HARD_EVIDENCE_REQUIRED_PATHS = [
    HARD_EVIDENCE_LEDGER_MD_RELATIVE,
    HARD_EVIDENCE_LEDGER_JSON_RELATIVE,
    HARD_EVIDENCE_README_RELATIVE,
    HARD_EVIDENCE_EXPERT_README_RELATIVE,
    HARD_EVIDENCE_REHEARSAL_README_RELATIVE,
]
EXPERT_FEEDBACK_OUTREACH_REQUIRED_PATHS = [
    EXPERT_FEEDBACK_OUTREACH_LEDGER_MD_RELATIVE,
    EXPERT_FEEDBACK_OUTREACH_LEDGER_JSON_RELATIVE,
    EXPERT_FEEDBACK_OUTREACH_README_RELATIVE,
]
TIMED_REHEARSAL_SCHEDULE_REQUIRED_PATHS = [
    TIMED_REHEARSAL_SCHEDULE_LEDGER_MD_RELATIVE,
    TIMED_REHEARSAL_SCHEDULE_LEDGER_JSON_RELATIVE,
    TIMED_REHEARSAL_SCHEDULE_README_RELATIVE,
]
OFFICIAL_RUBRIC_REQUIRED_PATHS = [
    OFFICIAL_RUBRIC_ALIGNMENT_MD_RELATIVE,
    OFFICIAL_RUBRIC_ALIGNMENT_JSON_RELATIVE,
]
JUDGE_OBJECTION_MATRIX_REQUIRED_PATHS = [
    JUDGE_OBJECTION_MATRIX_MD_RELATIVE,
    JUDGE_OBJECTION_MATRIX_JSON_RELATIVE,
]
FAILURE_REMEDIATION_BEFORE_AFTER_REQUIRED_PATHS = [
    FAILURE_REMEDIATION_BEFORE_AFTER_MD_RELATIVE,
    FAILURE_REMEDIATION_BEFORE_AFTER_JSON_RELATIVE,
]
SPECIAL_PRIZE_DASHBOARD_REQUIRED_PATHS = [
    SPECIAL_PRIZE_READINESS_DASHBOARD_MD_RELATIVE,
    SPECIAL_PRIZE_READINESS_DASHBOARD_JSON_RELATIVE,
]
HARD_EVIDENCE_CLOSURE_BOARD_REQUIRED_PATHS = [
    HARD_EVIDENCE_CLOSURE_BOARD_MD_RELATIVE,
    HARD_EVIDENCE_CLOSURE_BOARD_JSON_RELATIVE,
]
HARD_EVIDENCE_ACTION_PACK_REQUIRED_PATHS = [
    HARD_EVIDENCE_ACTION_PACK_MD_RELATIVE,
    HARD_EVIDENCE_ACTION_PACK_JSON_RELATIVE,
]
EXTERNAL_EVIDENCE_EXECUTION_KIT_REQUIRED_PATHS = [
    EXTERNAL_EVIDENCE_EXECUTION_KIT_MD_RELATIVE,
    EXTERNAL_EVIDENCE_EXECUTION_KIT_JSON_RELATIVE,
    EXTERNAL_EVIDENCE_EXPERT_HANDOFF_RELATIVE,
    EXTERNAL_EVIDENCE_TIMED_REHEARSAL_OBSERVER_RELATIVE,
]
FINAL_ACCEPTANCE_AUDIT_REQUIRED_PATHS = [
    FINAL_ACCEPTANCE_AUDIT_MD_RELATIVE,
    FINAL_ACCEPTANCE_AUDIT_JSON_RELATIVE,
]
APPLICATION_VALUE_QUANTIFICATION_REQUIRED_PATHS = [
    APPLICATION_VALUE_QUANTIFICATION_MD_RELATIVE,
    APPLICATION_VALUE_QUANTIFICATION_JSON_RELATIVE,
]
NUMERIC_TRACEABILITY_REPORT_REQUIRED_PATHS = [
    NUMERIC_TRACEABILITY_REPORT_MD_RELATIVE,
    NUMERIC_TRACEABILITY_REPORT_JSON_RELATIVE,
]
NO_ANSWER_BOUNDARY_EVALUATION_REQUIRED_PATHS = [
    NO_ANSWER_BOUNDARY_EVALUATION_MD_RELATIVE,
    NO_ANSWER_BOUNDARY_EVALUATION_JSON_RELATIVE,
]
CLAIM_INTEGRITY_REPORT_REQUIRED_PATHS = [
    CLAIM_INTEGRITY_REPORT_MD_RELATIVE,
    CLAIM_INTEGRITY_REPORT_JSON_RELATIVE,
]
RUBRIC_DEFENSE_COVERAGE_REQUIRED_PATHS = [
    RUBRIC_DEFENSE_COVERAGE_MD_RELATIVE,
    RUBRIC_DEFENSE_COVERAGE_JSON_RELATIVE,
]
DEFENSE_SLIDE_TRACEABILITY_REQUIRED_PATHS = [
    DEFENSE_SLIDE_TRACEABILITY_MD_RELATIVE,
    DEFENSE_SLIDE_TRACEABILITY_JSON_RELATIVE,
]
RUNTIME_REPRODUCIBILITY_SNAPSHOT_REQUIRED_PATHS = [
    RUNTIME_REPRODUCIBILITY_SNAPSHOT_MD_RELATIVE,
    RUNTIME_REPRODUCIBILITY_SNAPSHOT_JSON_RELATIVE,
]
VERIFICATION_TRANSCRIPT_REQUIRED_PATHS = [
    VERIFICATION_TRANSCRIPT_MD_RELATIVE,
    VERIFICATION_TRANSCRIPT_JSON_RELATIVE,
]
APPLICATION_VALIDATION_DOC = PACKAGE_DIR / "11_应用场景与专家验证.md"
EXPERT_FEEDBACK_PROTOCOL = PACKAGE_DIR / "12_专家反馈采集与整改闭环.md"
DEMO_SCRIPT = PACKAGE_DIR / "04_系统演示脚本.md"
DEFENSE_DECK_PPTX_RELATIVE = "docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx"
DEFENSE_DECK_NOTES_RELATIVE = "docs/challenge_cup/defense_deck/challenge_cup_defense_speaker_notes.md"
DEFENSE_DECK_PPTX = REPO_ROOT / DEFENSE_DECK_PPTX_RELATIVE
DEFENSE_DECK_NOTES = REPO_ROOT / DEFENSE_DECK_NOTES_RELATIVE
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
DATASET_RELATIVE = "evaluation/system_eval_questions.jsonl"
REPORT_MD = REPRO_DIR / "readiness_gate_report.md"
EVIDENCE_HASHES = REPRO_DIR / "evidence_hashes.json"
EVAL_COVERAGE_PROFILE = REPRO_DIR / "evaluation_coverage_profile.json"
SUBMISSION_ARCHIVE_RELATIVE = "docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip"
SUBMISSION_ARCHIVE_MANIFEST_RELATIVE = (
    "docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json"
)
SUBMISSION_ARCHIVE = REPO_ROOT / SUBMISSION_ARCHIVE_RELATIVE
SUBMISSION_ARCHIVE_MANIFEST = REPO_ROOT / SUBMISSION_ARCHIVE_MANIFEST_RELATIVE
SUBMISSION_PACKAGE_VERIFIER_RELATIVE = "docs/challenge_cup/reproducibility/verify_submission_package.py"
SUBMISSION_PACKAGE_VERIFIER = REPO_ROOT / SUBMISSION_PACKAGE_VERIFIER_RELATIVE
APPLICATION_VALIDATION_REPORT = REPRO_DIR / "application_validation_report.md"
APPLICATION_VALUE_QUANTIFICATION_BOUNDARY = (
    "This is a local application-value quantification over the fixed GT-07 browser-smoke scenario; "
    "it is not a production validation, does not replace engineers, provides no external validation "
    "claim, and does not replace real expert feedback or real timed rehearsal evidence."
)
NUMERIC_TRACEABILITY_BOUNDARY = (
    "This is a local numeric traceability report for the fixed GT-07 browser-smoke scenario; it does not "
    "claim production validation, does not claim external validation, does not replace engineers, and does "
    "not replace real expert feedback or real timed rehearsal evidence."
)
NO_ANSWER_BOUNDARY_EVALUATION_BOUNDARY = (
    "This is a deterministic empty-context and noisy/contradictory retrieved-context no-answer boundary "
    "evaluation for the local HallucinationGuard; it does not claim live retriever coverage, does not claim "
    "online LLM behavior, does not claim external validation, and does not satisfy goal completion without "
    "real expert feedback and real timed rehearsal evidence."
)
CLAIM_INTEGRITY_REPORT_BOUNDARY = (
    "This report audits package-level defense claims for evidence links and forbidden overclaims. It does "
    "not guarantee an award, does not claim expert approval, does not claim timed rehearsal completion, "
    "does not claim production deployment, and does not satisfy goal completion without real expert feedback "
    "and real timed rehearsal evidence."
)
RUBRIC_DEFENSE_COVERAGE_BOUNDARY = (
    "This report maps public rubric dimensions to local defense assets, judge-objection answers, "
    "and evidence-bound claims. It does not guarantee an award, does not claim expert approval, "
    "does not claim timed rehearsal completion, and does not satisfy goal completion without real "
    "expert feedback and real timed rehearsal evidence."
)
DEFENSE_SLIDE_TRACEABILITY_BOUNDARY = (
    "This report maps the defense deck slide-by-slide to local evidence, judge-objection answers, "
    "and evidence-bound claims. It does not guarantee an award, does not claim expert approval, "
    "does not claim timed rehearsal completion, and does not satisfy goal completion without real "
    "expert feedback and real timed rehearsal evidence."
)
RUNTIME_REPRODUCIBILITY_SNAPSHOT_BOUNDARY = (
    "This snapshot records the local runtime used to reproduce the challenge-cup package; it is not a "
    "production deployment certification, does not guarantee a special-prize result, and does not replace "
    "real expert feedback or real timed rehearsal evidence."
)
VERIFICATION_TRANSCRIPT_BOUNDARY = (
    "This transcript summarizes current machine-verification reports for reviewer navigation; it does not "
    "claim goal completion, does not claim expert approval or timed rehearsal completion, and does not "
    "replace real expert feedback or real timed rehearsal evidence."
)
EXPERT_FEEDBACK_FORM = REPRO_DIR / "expert_feedback_form.md"
GRAPH_REPORT_JSON = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_same_question_report.json"
GRAPH_REPORT_MD = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_same_question_report.md"
GRAPH_CONTEXT_DEMO_JSON = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_context_demo.json"
GRAPH_CONTEXT_DEMO_MD = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_context_demo.md"
GRAPH_ANSWER_BENCHMARK_JSON = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_answer_benchmark.json"
GRAPH_ANSWER_BENCHMARK_MD = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_answer_benchmark.md"
GRAPH_GAP_REMEDIATION_JSON = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_gap_remediation_plan.json"
GRAPH_GAP_REMEDIATION_MD = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_gap_remediation_plan.md"
GRAPH_MANUAL_EVIDENCE_SUPPLEMENT = REPRO_DIR / "graphrag_manual_evidence_supplement.csv"
GRAPH_EVIDENCE_BOUNDARY = (
    "Graph evidence coverage audits triples.csv keyword support; it is not a completed GraphRAG answer win-rate."
)
GRAPH_CONTEXT_DEMO_BOUNDARY = (
    "This report is a context-only GraphRAG retrieval demo; it does not generate LLM answers "
    "or prove online answer win-rate."
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
FAILURE_REMEDIATION_BEFORE_AFTER_BOUNDARY = (
    "This is a remediation-card ablation over the fixed Day4 failure set. It proves which failures can be "
    "closed or bounded by explicit glossary, fact-card, structured-fact, and keyword-guardrail evidence; it is "
    "not a live retriever upgrade, not an online LLM answer win-rate, provides no award guarantee, and does not "
    "replace real expert feedback or real timed rehearsal evidence."
)
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
EXPERT_FEEDBACK_OUTREACH_LEDGER_BOUNDARY = (
    "Outreach records prove that a real request was sent or followed up. They do not prove expert "
    "approval and do not satisfy the expert_feedback hard-evidence requirement."
)
TIMED_REHEARSAL_SCHEDULE_LEDGER_BOUNDARY = (
    "Schedule records prove that a real timed rehearsal was scheduled or observer preparation was "
    "recorded. They do not prove a timed rehearsal was completed and do not satisfy the "
    "timed_rehearsal hard-evidence requirement."
)
HARD_EVIDENCE_CLOSURE_BOARD_BOUNDARY = (
    "This closure board is an execution control artifact. It does not satisfy goal completion, "
    "does not prove expert feedback, and does not prove a timed rehearsal was completed."
)
EXPERT_FEEDBACK_OUTREACH_STATUSES = {
    "ready_to_send_no_outreach_recorded",
    "outreach_recorded_awaiting_response",
}
EXPERT_FEEDBACK_OUTREACH_METADATA_STATUSES = {"sent", "followed_up", "no_response_yet", "declined"}
EXPERT_FEEDBACK_OUTREACH_CHANNELS = {"email", "chat", "meeting", "phone", "in_person"}
TIMED_REHEARSAL_SCHEDULE_STATUSES = {
    "ready_to_schedule_no_rehearsal_recorded",
    "rehearsal_scheduled_awaiting_run",
}
TIMED_REHEARSAL_SCHEDULE_METADATA_STATUSES = {"scheduled", "rescheduled", "cancelled", "observer_ready"}
TIMED_REHEARSAL_SCHEDULE_TIMING_LIMITS = {
    "opening_planned_seconds": 90,
    "demo_planned_seconds": 180,
    "offline_fallback_planned_seconds": 20,
    "killer_question_planned_seconds": 30,
    "killer_question_count": 5,
}
DEFENSE_DECK_REQUIRED_TERMS = {"GraphRAG", "GT-07", "60", "readiness", "专家反馈"}
DEFENSE_DECK_NOTES_REQUIRED_TERMS = {
    "90秒开场",
    "三分钟演示",
    "GT-07",
    "GraphRAG",
    "readiness gate",
    "不宣称已获得专家认可",
}
REQUIRED_GRAPH_CASE_FIELDS = {
    "id",
    "graph_evidence_coverage",
    "graph_evidence_status",
    "graph_matchable_keyword_count",
    "matched_graph_evidence",
}

REQUIRED_PACKAGE_DOCS = [
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
    "defense_deck/challenge_cup_defense_deck.pptx",
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
    "reproducibility/numeric_traceability_report.md",
    "reproducibility/numeric_traceability_report.json",
    "reproducibility/no_answer_boundary_evaluation.md",
    "reproducibility/no_answer_boundary_evaluation.json",
    "reproducibility/runtime_reproducibility_snapshot.md",
    "reproducibility/runtime_reproducibility_snapshot.json",
    "reproducibility/verification_transcript.md",
    "reproducibility/verification_transcript.json",
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
DEFENSE_REHEARSAL_TIMING_TARGETS = {
    "opening_seconds": 90,
    "demo_seconds": 180,
    "offline_fallback_seconds": 20,
    "killer_question_seconds": 30,
}
DEFENSE_REHEARSAL_REQUIRED_EVIDENCE_FILES = {
    "docs/challenge_cup/00_项目一页纸.md",
    "docs/challenge_cup/03_实验评测报告.md",
    "docs/challenge_cup/04_系统演示脚本.md",
    "docs/challenge_cup/05_答辩问答手册.md",
    "docs/challenge_cup/07_评审主张证据矩阵.md",
    "docs/challenge_cup/08_特等奖评审自评表.md",
    "docs/challenge_cup/10_答辩攻防与彩排卡.md",
    "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md",
    "docs/challenge_cup/reproducibility/application_validation_report.md",
    "docs/challenge_cup/reproducibility/readiness_gate_report.md",
    "evaluation/reports/challenge_cup_graphrag_context_demo.md",
    "evaluation/reports/challenge_cup_graphrag_same_question_report.md",
}
DEFENSE_REHEARSAL_MARKDOWN_TERMS = {
    "答辩彩排计分卡",
    "90秒开场",
    "三分钟演示节奏",
    "20 秒内切换",
    "30 秒内回答",
    "不把 readiness gate 说成获奖保证",
}
DEFENSE_REHEARSAL_RESULT_PASS_FAIL_RULES = {
    "opening_actual_seconds_max": 90,
    "demo_actual_seconds_max": 180,
    "offline_fallback_actual_seconds_max": 20,
    "each_killer_question_actual_seconds_max": 30,
    "required_killer_question_count": 5,
}
DEFENSE_REHEARSAL_RESULT_REQUIRED_ARCHIVE_TYPES = ["计时截图", "彩排录屏", "观察员签字或备注", "问题遗漏清单"]
DEFENSE_REHEARSAL_RESULT_REQUIRED_EVIDENCE_FILES = {
    "docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md",
    "docs/challenge_cup/10_答辩攻防与彩排卡.md",
}
DEFENSE_REHEARSAL_RESULT_MARKDOWN_TERMS = {
    "答辩计时彩排结果归档包",
    "尚未记录真实计时彩排",
    "不伪造现场彩排记录",
    "opening_actual_seconds",
    "offline_fallback_actual_seconds",
    "killer_question_results",
}
EXPERT_FEEDBACK_REQUEST_DIMENSIONS = [
    "实用性",
    "创新性",
    "工程完成度",
    "评测可信度",
    "答辩清晰度",
    "边界严谨性",
]
EXPERT_FEEDBACK_REQUIRED_ARCHIVE_TYPES = ["签字页", "邮件回复", "会议纪要", "聊天记录截图"]
EXPERT_FEEDBACK_REQUEST_REQUIRED_EVIDENCE_FILES = {
    "docs/challenge_cup/00_项目一页纸.md",
    "docs/challenge_cup/03_实验评测报告.md",
    "docs/challenge_cup/04_系统演示脚本.md",
    "docs/challenge_cup/07_评审主张证据矩阵.md",
    "docs/challenge_cup/08_特等奖评审自评表.md",
    "docs/challenge_cup/10_答辩攻防与彩排卡.md",
    "docs/challenge_cup/11_应用场景与专家验证.md",
    "docs/challenge_cup/12_专家反馈采集与整改闭环.md",
    "docs/challenge_cup/reproducibility/application_validation_report.md",
    "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md",
    "docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md",
    "docs/challenge_cup/reproducibility/expert_feedback_form.md",
    "docs/challenge_cup/reproducibility/readiness_gate_report.md",
}
EXPERT_FEEDBACK_REQUEST_MARKDOWN_TERMS = {
    "专家反馈外发包",
    "待真实反馈归档",
    "不宣称已获得专家认可",
    "建议邮件主题",
    "签字页",
    "邮件回复",
    "会议纪要",
    "聊天记录截图",
}
HARD_EVIDENCE_MARKDOWN_TERMS = {
    "真实专家反馈",
    "真实计时彩排",
    "不伪造",
    "不能标记目标完成",
}
HARD_EVIDENCE_REQUIRED_CATEGORIES = {"expert_feedback", "timed_rehearsal"}
HARD_EVIDENCE_MIN_REVIEW_DIMENSIONS = 3
HARD_EVIDENCE_TIMING_LIMITS = {
    "opening_actual_seconds": 90,
    "demo_actual_seconds": 180,
    "offline_fallback_actual_seconds": 20,
    "killer_question_actual_seconds": 30,
    "killer_question_count": 5,
}
GRAPH_ANSWER_BENCHMARK_MARKDOWN_TERMS = {
    "GraphRAG answer benchmark",
    "10 道 GraphRAG 同题",
    "All fixed GraphRAG evidence gaps closed",
    "不宣称 GraphRAG 全面优于 baseline",
}
GRAPH_GAP_REMEDIATION_MARKDOWN_TERMS = {
    "GraphRAG 补证整改计划",
    "graph_evidence_gaps_closed_pending_external_validation",
    "All fixed GraphRAG evidence gaps closed",
    "P0 missing 已补证",
    "不宣称在线 LLM answer win-rate",
    "cc056",
}
GRAPH_GAP_REQUIRED_ARCHIVE_EVIDENCE = [
    "new_triples_or_summary_diff",
    "source_page_or_doc_anchor",
    "manual_review_note",
    "rerun_report_json",
]
GRAPH_GAP_REQUIRED_RERUN_COMMANDS = [
    "python scripts/build_graphrag_challenge_report.py",
    "python scripts/build_graphrag_answer_benchmark.py",
    "python scripts/build_graphrag_gap_remediation_plan.py",
    "python scripts/check_challenge_cup_readiness.py",
]
FAILURE_REMEDIATION_REQUIRED_CATEGORIES = {
    "corpus_gap_or_query_gap",
    "evaluation_concept_gap",
    "exact_number_fact",
    "hybrid_dilution",
    "partial_ranking_gap",
    "structured_fact_routing",
    "terminology_alias_gap",
}
FAILURE_REMEDIATION_ALLOWED_CATEGORY_STATUSES = {
    "closed_by_remediation_card",
    "bounded_by_keyword_guardrail",
}
FAILURE_REMEDIATION_CRITICAL_CASE_IDS = {"se013", "se024", "se027", "se028"}
FAILURE_REMEDIATION_REQUIRED_CARD_IDS = {
    "evaluation_metric_glossary",
    "kg_poc_fact_card",
    "goldwind_structured_fact_card",
    "reranker_alias_card",
    "keyword_guardrail_policy",
}
FAILURE_REMEDIATION_REQUIRED_COMMANDS = {
    "python scripts/build_challenge_cup_failure_remediation_before_after.py",
    "python scripts/build_challenge_cup_package.py",
    "python scripts/check_challenge_cup_readiness.py",
}
FAILURE_REMEDIATION_MARKDOWN_TERMS = {
    "Failure Remediation Before/After",
    "remediation-card ablation",
    "se013",
    "se024",
    "se027",
    "se028",
    "not a live retriever upgrade",
    "real expert feedback",
    "real timed rehearsal",
}
EVAL_COVERAGE_MINIMUMS = {
    "task_types": 10,
    "source_scopes": 15,
    "graphrag_questions": 10,
}
REQUIRED_EXPECTED_MODES = {
    "keyword": 50,
    "hybrid_rrf": 50,
    "graphrag_context": 8,
    "graphrag_global": 4,
}

REQUIRED_BROWSER_CHECKS = {
    "health endpoint",
    "libs route",
    "assets route",
    "deliverables route",
    "page identity",
    "desktop not blank",
    "desktop console health",
    "search interaction",
    "search results visible",
    "KG SVG render",
    "KG artifact links",
    "mobile not blank",
    "mobile console health",
}

REQUIRED_LIVE_CHECKS = {
    "health endpoint",
    "frontend root page",
    "trusted cors origin",
    "search top_k guard",
    "graphrag path guard",
}

REQUIRED_CLAIM_MATRIX_TERMS = {
    "创新性",
    "工程闭环",
    "科学评测",
    "可复现",
    "应用验证",
    "应用边界",
    "evaluation/system_eval_questions.jsonl",
    "11_应用场景与专家验证.md",
    "12_专家反馈采集与整改闭环.md",
    "application_validation_report.md",
    "expert_feedback_form.md",
    "browser_demo_smoke_report.md",
    "readiness_gate_report.md",
}
REQUIRED_ACCEPTANCE_CHECKLIST_TERMS = {
    "结项验收口径",
    "可提交材料",
    "验收步骤",
    "现场演示与离线备份",
    "未完成项与边界",
    "验收结论",
    "package_manifest.json",
    "readiness_gate_report.md",
    "browser_demo_smoke_report.md",
    "application_validation_report.md",
    "expert_feedback_form.md",
}
REQUIRED_AWARD_SELF_EVAL_TERMS = {
    "学术价值或实用性",
    "创新性",
    "作品完成情况",
    "现场答辩表现",
    "第44届",
    "特等奖7项",
    "07_评审主张证据矩阵.md",
    "readiness_gate_report.md",
    "browser_demo_smoke_report.md",
    "defense_rehearsal_scorecard.md",
    "defense_rehearsal_result_packet.md",
}
OFFICIAL_RUBRIC_REQUIRED_DIMENSIONS = {
    "academic_or_practical_value",
    "innovation",
    "completion",
    "defense_performance",
}
RUBRIC_DEFENSE_COVERAGE_REQUIRED_DIMENSIONS = {
    "academic_or_practical_value",
    "innovation",
    "completion",
    "defense_performance",
    "academic_norms_and_rigor",
}
RUBRIC_DEFENSE_COVERAGE_MARKDOWN_TERMS = {
    "Rubric Defense Coverage",
    "academic_or_practical_value",
    "innovation",
    "completion",
    "defense_performance",
    "academic_norms_and_rigor",
    "no award guarantee",
}
DEFENSE_SLIDE_TRACEABILITY_REQUIRED_SLIDE_INDEXES = set(range(1, 11))
DEFENSE_SLIDE_TRACEABILITY_MARKDOWN_TERMS = {
    "Defense Slide Traceability",
    "slide 1",
    "slide 10",
    "no award guarantee",
    "timed rehearsal",
}
OFFICIAL_RUBRIC_REQUIRED_TERMS = {
    "学术/实用价值",
    "创新性",
    "作品完成度",
    "现场答辩",
    "第44届",
    "特等奖7项",
    "不承诺获奖",
}
OFFICIAL_RUBRIC_MIN_SOURCE_COUNT = 7
OFFICIAL_RUBRIC_CURRENT_AS_OF = "2026-06-07"
OFFICIAL_RUBRIC_LATEST_SOURCE_ID = "tsinghua_44th_2026"
OFFICIAL_RUBRIC_BENCHMARK_SOURCE_IDS = [
    "tsinghua_44th_2026",
    "tsinghua_ee_44th_2026",
    "tsinghua_auto_44th_2026",
]
OFFICIAL_RUBRIC_DEPARTMENT_BENCHMARK_SPECS = {
    "tsinghua_ee_44th_2026": {
        "rank_signal": "department_total_score_first",
        "reported_awards": {
            "special_prize": 1,
            "first_prize": 1,
            "second_prize": 2,
        },
    },
    "tsinghua_auto_44th_2026": {
        "rank_signal": "department_total_score_fifth",
        "reported_awards": {
            "second_prize": 4,
            "third_prize": 2,
        },
    },
}
JUDGE_OBJECTION_MATRIX_REQUIRED_IDS = {
    "OJ-01-normal-rag",
    "OJ-02-graphrag-baseline",
    "OJ-03-engineer-replacement",
    "OJ-04-production-data",
    "OJ-05-live-demo-failure",
    "OJ-06-cherry-picked-evaluation",
    "OJ-07-expert-validation",
    "OJ-08-special-prize-claim",
    "OJ-09-ip-and-compliance",
    "OJ-10-project-closure",
}
JUDGE_OBJECTION_MATRIX_REQUIRED_TERMS = {
    "Judge Objection Response Matrix",
    "OJ-01-normal-rag",
    "OJ-08-special-prize-claim",
    "30 seconds",
    "no award guarantee",
    "real expert feedback",
    "real timed rehearsal",
    "readiness gate is not an award guarantee",
}
REQUIRED_EXPERT_REVIEW_INDEX_TERMS = {
    "三分钟审阅路径",
    "特等奖主张",
    "一键复核命令",
    "风险边界",
    "07_评审主张证据矩阵.md",
    "08_特等奖评审自评表.md",
    "readiness_gate_report.md",
    "browser_demo_smoke_report.md",
    "evaluation/system_eval_questions.jsonl",
}
REQUIRED_JUDGE_BRIEFING_CARD_TERMS = {
    "评委现场速览卡",
    "特等奖答辩路径",
    "三分钟审阅路径",
    "一页结论",
    "证据锚点",
    "不承诺获奖",
    "真实专家反馈",
    "真实计时彩排",
    "demo-maint-thresholds-076",
    "demo-structure-fault-130",
    "demo-gt07-fault-021",
    "demo-gt07-repair-022",
    "demo-gt07-manual-023",
    "special_prize_readiness_dashboard.md",
    "final_acceptance_audit.md",
    "goal_completion_report.md",
}
REQUIRED_ONSITE_DEFENSE_RUNBOOK_TERMS = {
    "现场答辩操作Runbook",
    "Preflight",
    "标签页顺序",
    "离线切换触发条件",
    "Q&A 证据映射",
    "留存材料",
    "禁止现场调试",
    "真实专家反馈",
    "真实计时彩排",
    "13_评委现场速览卡.md",
    "09_专家快速审阅索引.md",
    "04_系统演示脚本.md",
    "10_答辩攻防与彩排卡.md",
    "browser_demo_smoke_report.md",
    "desktop_search_results.png",
    "final_acceptance_audit.md",
    "goal_completion_report.md",
}
REQUIRED_PROJECT_HANDOFF_CHECKLIST_TERMS = {
    "结项交付移交清单",
    "移交范围",
    "签收确认",
    "复核命令",
    "材料归档",
    "外部硬证据补齐",
    "真实专家反馈",
    "真实计时彩排",
    "不能标记目标完成",
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
}
REQUIRED_DEFENSE_QA_REMEDIATION_LEDGER_TERMS = {
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
}
REQUIRED_REVIEW_RISK_RESPONSE_PLAN_TERMS = {
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
    "08_特等奖评审自评表.md",
    "14_现场答辩操作Runbook.md",
    "16_现场问辩记录与整改台账.md",
    "browser_demo_smoke_report.md",
    "desktop_search_results.png",
    "goal_completion_report.md",
    "hard_evidence_ledger.md",
    "special_prize_readiness_dashboard.md",
    "scripts/check_challenge_cup_readiness.py",
}
REQUIRED_SPECIAL_PRIZE_SCORING_DRILL_TERMS = {
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
}
REQUIRED_POSTER_BOOTH_QA_PACK_TERMS = {
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
}
REQUIRED_COMMERCIALIZATION_ROADMAP_TERMS = {
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
}
REQUIRED_POSTER_BOARD_HTML_TERMS = {
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
    "docs/challenge_cup/README_先看这里.md",
    "docs/challenge_cup/13_评委现场速览卡.md",
    "docs/challenge_cup/19_作品展墙报问辩与展台脚本.md",
    "docs/challenge_cup/20_成果转化与持续迭代路线图.md",
    "docs/challenge_cup/reproducibility/application_validation_report.md",
    "docs/challenge_cup/reproducibility/readiness_gate_report.md",
    "docs/challenge_cup/reproducibility/verify_submission_package.py",
    "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md",
    "docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png",
}
REQUIRED_DEFENSE_CONTROL_CONSOLE_TERMS = {
    "<!doctype html>",
    "Defense Control Console",
    "知燃知维 GraphRAG 挑战杯现场总控台",
    "现场演示流程",
    "证据启动台",
    "兜底与边界",
    "演示失败",
    "不过度承诺",
    "硬证据边界",
    "主动声明边界",
    "3-minute timer",
    "三分钟演示",
    "90-second opening",
    "offline fallback",
    "readiness gate",
    "submission verifier",
    "GT-07",
    "GraphRAG",
    "no award guarantee",
    "real expert feedback",
    "real timed rehearsal",
    "docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx",
    "docs/challenge_cup/13_评委现场速览卡.md",
    "docs/challenge_cup/14_现场答辩操作Runbook.md",
    "docs/challenge_cup/reproducibility/readiness_gate_report.md",
    "docs/challenge_cup/reproducibility/verify_submission_package.py",
    "docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png",
    "docs/challenge_cup/reproducibility/application_validation_report.md",
    "docs/challenge_cup/reproducibility/final_acceptance_audit.md",
    "docs/challenge_cup/reproducibility/goal_completion_report.md",
}
DEFENSE_CONTROL_CONSOLE_MOJIBAKE_MARKERS = (
    "\ufffd",
    "鐭",
    "绛",
    "鍦",
    "杈",
    "褰",
)
REQUIRED_IP_OPEN_SOURCE_COMPLIANCE_TERMS = {
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
}
REQUIRED_LOCAL_BASELINE_DIFFERENTIATION_TERMS = {
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
}
REQUIRED_FINAL_SUBMISSION_HANDOFF_TERMS = {
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
}
REQUIRED_DEFENSE_REHEARSAL_TERMS = {
    "90秒开场",
    "三分钟演示节奏",
    "杀手问题",
    "不可夸大边界",
    "彩排通过标准",
    "04_系统演示脚本.md",
    "05_答辩问答手册.md",
    "07_评审主张证据矩阵.md",
    "08_特等奖评审自评表.md",
    "readiness_gate_report.md",
    "browser_demo_smoke_report.md",
    "defense_rehearsal_result_packet.md",
}
REQUIRED_APPLICATION_VALIDATION_TERMS = {
    "固定应用场景",
    "人工原流程",
    "系统辅助后流程",
    "验证角色",
    "量化收益",
    "边界声明",
    "多场景覆盖矩阵",
    "scenario-gt07-abnormal-vibration",
    "scenario-maintenance-thresholds",
    "scenario-compressor-temperature",
    "application_validation_report.md",
    "browser_demo_smoke_report.json",
    "desktop_search_results.png",
}
REQUIRED_APPLICATION_REPORT_TERMS = {
    "GT-07",
    "压气机出口温度偏高",
    "进气滤网",
    "压气机叶片",
    "温度传感器",
    "人工确认",
    "demo-maint-thresholds-076",
    "demo-structure-fault-130",
    "demo-gt07-fault-021",
    "demo-gt07-repair-022",
    "demo-gt07-manual-023",
    "Scenario Coverage Matrix",
    "scenario-gt07-abnormal-vibration",
    "scenario-maintenance-thresholds",
    "scenario-compressor-temperature",
    "not production full-scenario validation",
}
REQUIRED_SCENARIO_QUERY = "燃气轮机异常振动诊断流程"
APPLICATION_VALUE_EXPECTED_STAGE_IDS = [
    "threshold_screening",
    "mechanism_explanation",
    "case_symptom",
    "repair_result",
    "disposition_recommendation",
]
APPLICATION_VALUE_EXPECTED_RECORD_IDS = [
    "demo-maint-thresholds-076",
    "demo-structure-fault-130",
    "demo-gt07-fault-021",
    "demo-gt07-repair-022",
    "demo-gt07-manual-023",
]
NUMERIC_TRACEABILITY_EXPECTED_RECORD_IDS = APPLICATION_VALUE_EXPECTED_RECORD_IDS
APPLICATION_VALUE_REQUIRED_CLAIM_IDS = {
    "practical_value",
    "review_efficiency",
    "risk_boundary",
}
APPLICATION_VALUE_MARKDOWN_TERMS = {
    "Application Value Quantification",
    "GT-07",
    "41.8 ms",
    "5.0x evidence consolidation",
    "not a production validation",
    *APPLICATION_VALUE_EXPECTED_RECORD_IDS,
}
NUMERIC_TRACEABILITY_MARKDOWN_TERMS = {
    "Numeric Traceability Report",
    "numeric_traceability_consistent_no_external_claim",
    "41.80 ms",
    "2,655 chunks",
    "1,185,989 tokens",
    "does not claim production validation",
    *NUMERIC_TRACEABILITY_EXPECTED_RECORD_IDS,
}
NO_ANSWER_BOUNDARY_MARKDOWN_TERMS = {
    "No-Answer Boundary Evaluation",
    "no_answer_boundary_guard_verified_no_live_llm_claim",
    "No retrieved evidence",
    "证据不足",
    "does not claim live retriever coverage",
    "does not claim online LLM behavior",
}
CLAIM_INTEGRITY_MARKDOWN_TERMS = {
    "Claim Integrity Report",
    "claim_integrity_verified_no_award_or_external_claim",
    "package_review_ready",
    "special_prize_competition_argument",
    "does not guarantee an award",
    "does not claim expert approval",
}
REQUIRED_SCENARIO_TERMS = {
    "demo-maint-thresholds-076",
    "demo-structure-fault-130",
    "demo-gt07-fault-021",
    "demo-gt07-repair-022",
    "demo-gt07-manual-023",
    "压气机出口温度偏高",
    "进气滤网",
    "压气机叶片",
    "温度传感器",
}
REQUIRED_SCENARIO_RECORD_IDS = {
    "demo-maint-thresholds-076",
    "demo-structure-fault-130",
    "demo-gt07-fault-021",
    "demo-gt07-repair-022",
    "demo-gt07-manual-023",
}
REQUIRED_SCENARIO_BOUNDARY_TERMS = {
    "人工确认",
    "不证明",
    "替代工程师",
}
REQUIRED_SCENARIO_WALKTHROUGH_TERMS = {
    "固定场景演示",
    "燃气轮机异常振动诊断流程",
    "结果 5",
    "demo-maint-thresholds-076",
    "demo-structure-fault-130",
    "demo-gt07-fault-021",
    "demo-gt07-repair-022",
    "demo-gt07-manual-023",
    "人工确认",
    "application_validation_report.md",
    "desktop_search_results.png",
}
REQUIRED_EXPERT_FEEDBACK_PROTOCOL_TERMS = {
    "反馈采集状态",
    "待真实反馈归档",
    "不伪造外部意见",
    "整改闭环",
    "专家反馈采集表",
    "expert_feedback_form.md",
    "application_validation_report.md",
    "readiness_gate_report.md",
}
REQUIRED_EXPERT_FEEDBACK_FORM_TERMS = {
    "评审人姓名",
    "单位或角色",
    "联系方式",
    "评审日期",
    "签字或邮件证据",
    "燃气轮机异常振动诊断流程",
    "demo-gt07-repair-022",
    "整改建议",
    "归档路径",
}
COMMAND_PREFIXES = ("python ", "node ", ".\\", "npm ", "uv ")
COMMAND_FRAGMENTS = (";", "http://", "https://")
CHALLENGE_CUP_TEXT_SUFFIXES = {".md", ".json", ".txt"}
CHINESE_READABILITY_REQUIRED_TERMS = {
    "挑战杯",
    "结项",
    "专家反馈",
    "GraphRAG",
    "不伪造",
    "真实计时彩排",
}
MOJIBAKE_MARKERS = (
    "\ufffd",
    "锛",
    "銆",
    "鈥",
    "娓呭崕",
    "鎸戞垬",
    "鐗圭瓑",
    "缁撻",
    "涓撳",
    "璇勫",
)


@dataclass(slots=True)
class GateCheck:
    name: str
    passed: bool
    detail: str


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def is_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def validate_source_path(relative: str, payload: dict[str, Any], field: str) -> list[str]:
    failures: list[str] = []
    source = str(payload.get(field, "")).strip()
    if not source:
        failures.append(f"{relative}: {field} missing")
        return failures
    posix = PurePosixPath(source)
    if posix.is_absolute() or ".." in posix.parts or "\\" in source:
        failures.append(f"{relative}: {field} unsafe")
        return failures
    if source == relative:
        failures.append(f"{relative}: {field} points to metadata file")
        return failures
    if source_path_looks_like_metadata(source):
        failures.append(f"{relative}: {field} must not be a json metadata file")
        return failures
    source_path = REPO_ROOT / source
    if not nonempty(source_path):
        failures.append(f"{relative}: {field} missing or empty")
        return failures
    sha_failure = source_sha256_failure(source_path, payload.get("source_sha256"))
    if sha_failure:
        failures.append(f"{relative}: {sha_failure}")
    return failures


def count_jsonl(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def expected_coverage_profile() -> dict[str, Any]:
    rows = read_jsonl(DATASET)
    task_type_counts = Counter(str(row["task_type"]) for row in rows)
    source_scope_counts = Counter(str(row["source_scope"]) for row in rows)
    expected_mode_counts: Counter[str] = Counter()
    questions_with_graphrag_modes = 0
    for row in rows:
        modes = [str(mode) for mode in row.get("expected_modes", [])]
        expected_mode_counts.update(modes)
        if any(mode.startswith("graphrag_") for mode in modes):
            questions_with_graphrag_modes += 1
    return {
        "generated_from": DATASET_RELATIVE,
        "question_count": len(rows),
        "task_type_counts": dict(sorted(task_type_counts.items())),
        "source_scope_counts": dict(sorted(source_scope_counts.items())),
        "expected_mode_counts": dict(sorted(expected_mode_counts.items())),
        "questions_with_graphrag_modes": questions_with_graphrag_modes,
        "minimums": dict(EVAL_COVERAGE_MINIMUMS),
    }


def nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        try:
            return path.relative_to(PACKAGE_DIR).as_posix()
        except ValueError:
            return path.as_posix()


def challenge_cup_text_paths() -> list[Path]:
    if not PACKAGE_DIR.exists():
        return []
    readiness_self_report = REPORT_MD.resolve()
    return sorted(
        path
        for path in PACKAGE_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in CHALLENGE_CUP_TEXT_SUFFIXES
        and path.resolve() != readiness_self_report
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pptx_text_and_slide_count(path: Path) -> tuple[int, str]:
    with zipfile.ZipFile(path) as archive:
        slide_names = sorted(
            name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        text_nodes: list[str] = []
        for name in slide_names:
            root = ET.fromstring(archive.read(name))
            text_nodes.extend(node.text or "" for node in root.iter() if node.tag.endswith("}t") or node.tag == "t")
    return len(slide_names), "\n".join(text_nodes)


def git_tracked_paths() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return {item for item in result.stdout.decode("utf-8", errors="replace").split("\0") if item}


def git_dirty_paths(paths: list[str]) -> set[str]:
    if not paths:
        return set()
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--", *paths],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    entries = [item for item in result.stdout.decode("utf-8", errors="replace").split("\0") if item]
    return {entry[3:].replace("\\", "/") for entry in entries if len(entry) > 3}


def check_package_docs() -> GateCheck:
    missing = [relative for relative in REQUIRED_PACKAGE_DOCS if not nonempty(PACKAGE_DIR / relative)]
    return GateCheck(
        "package documents",
        not missing,
        "all required challenge cup docs exist" if not missing else f"missing: {', '.join(missing)}",
    )


def check_challenge_cup_chinese_readability() -> GateCheck:
    if not PACKAGE_DIR.exists():
        return GateCheck("chinese readability", False, "docs/challenge_cup missing")
    paths = challenge_cup_text_paths()
    if not paths:
        return GateCheck("chinese readability", False, "no challenge cup text artifacts found")

    failures: list[str] = []
    combined: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            failures.append(f"{display_path(path)}: invalid utf-8 ({exc})")
            continue
        combined.append(text)
        hits = [marker for marker in MOJIBAKE_MARKERS if marker in text]
        if hits:
            failures.append(f"{display_path(path)}: mojibake markers {', '.join(hits[:4])}")
        control_chars = sorted(
            {f"U+{ord(ch):04X}" for ch in text if ord(ch) < 32 and ch not in {"\n", "\t"}}
        )
        if control_chars:
            failures.append(f"{display_path(path)}: control characters {', '.join(control_chars)}")

    aggregate_text = "\n".join(combined)
    missing_terms = sorted(term for term in CHINESE_READABILITY_REQUIRED_TERMS if term not in aggregate_text)
    if missing_terms:
        failures.append(f"missing required Chinese review terms: {', '.join(missing_terms)}")

    return GateCheck(
        "chinese readability",
        not failures,
        f"{len(paths)} challenge-cup text artifacts are UTF-8 readable with required Chinese review terms"
        if not failures
        else "; ".join(failures[:12]),
    )


def check_package_control_files() -> GateCheck:
    controls = [
        PACKAGE_MANIFEST.relative_to(REPO_ROOT).as_posix(),
        EVIDENCE_HASHES.relative_to(REPO_ROOT).as_posix(),
    ]
    tracked = git_tracked_paths()
    missing = [path for path in controls if not nonempty(REPO_ROOT / path)]
    untracked = [path for path in controls if path not in tracked]
    dirty = sorted(git_dirty_paths(controls))
    passed = not missing and not untracked and not dirty
    return GateCheck(
        "package control files",
        passed,
        f"{len(controls)} control files exist, are git-tracked, and are clean"
        if passed
        else f"missing={missing}, untracked={untracked}, dirty={dirty}",
    )


def check_eval_dataset() -> GateCheck:
    count = count_jsonl(DATASET) if DATASET.exists() else 0
    return GateCheck(
        "60 evaluation questions",
        count >= 60,
        f"{count} evaluation questions",
    )


def check_evaluation_coverage_profile() -> GateCheck:
    if not EVAL_COVERAGE_PROFILE.exists():
        return GateCheck("evaluation coverage profile", False, "evaluation_coverage_profile.json missing")
    profile = load_json(EVAL_COVERAGE_PROFILE)
    expected = expected_coverage_profile()
    failures: list[str] = []
    for key in (
        "generated_from",
        "question_count",
        "task_type_counts",
        "source_scope_counts",
        "expected_mode_counts",
        "questions_with_graphrag_modes",
        "minimums",
    ):
        if profile.get(key) != expected[key]:
            failures.append(f"{key} mismatch")
    if expected["question_count"] < 60:
        failures.append(f"question_count below 60: {expected['question_count']}")
    if len(expected["task_type_counts"]) < EVAL_COVERAGE_MINIMUMS["task_types"]:
        failures.append(f"task_types below {EVAL_COVERAGE_MINIMUMS['task_types']}")
    if len(expected["source_scope_counts"]) < EVAL_COVERAGE_MINIMUMS["source_scopes"]:
        failures.append(f"source_scopes below {EVAL_COVERAGE_MINIMUMS['source_scopes']}")
    if expected["questions_with_graphrag_modes"] < EVAL_COVERAGE_MINIMUMS["graphrag_questions"]:
        failures.append(f"graphrag_questions below {EVAL_COVERAGE_MINIMUMS['graphrag_questions']}")
    mode_counts = expected["expected_mode_counts"]
    for mode, minimum in REQUIRED_EXPECTED_MODES.items():
        actual = int(mode_counts.get(mode, 0))
        if actual < minimum:
            failures.append(f"{mode} below {minimum}: {actual}")
    return GateCheck(
        "evaluation coverage profile",
        not failures,
        (
            f"{expected['question_count']} questions across {len(expected['task_type_counts'])} task types, "
            f"{len(expected['source_scope_counts'])} source scopes, "
            f"{expected['questions_with_graphrag_modes']} GraphRAG-tagged questions"
        )
        if not failures
        else "; ".join(failures),
    )


def check_package_manifest() -> GateCheck:
    if not PACKAGE_MANIFEST.exists():
        return GateCheck("package evidence files", False, "package_manifest.json missing")
    manifest = load_json(PACKAGE_MANIFEST)
    evidence = manifest.get("evidence_files", [])
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing = [path for path in evidence if path != self_report and not nonempty(REPO_ROOT / path)]
    tracked = git_tracked_paths()
    untracked = [path for path in evidence if path not in tracked]
    dirty = sorted(path for path in git_dirty_paths(evidence) if path != self_report)
    question_count = int(manifest.get("question_count") or 0)
    passed = bool(evidence) and question_count >= 60 and not missing and not untracked and not dirty
    if passed:
        detail = f"{len(evidence)} evidence files exist, are git-tracked, and are clean; {question_count} questions"
    else:
        detail = f"evidence={len(evidence)}, questions={question_count}, missing={missing}, untracked={untracked}, dirty={dirty}"
    return GateCheck("package evidence files", passed, detail)


def check_evidence_hashes() -> GateCheck:
    if not EVIDENCE_HASHES.exists():
        return GateCheck("evidence integrity hashes", False, "evidence_hashes.json missing")
    manifest = load_json(PACKAGE_MANIFEST)
    hashes = load_json(EVIDENCE_HASHES)
    evidence = list(manifest.get("evidence_files", []))
    excluded = set(hashes.get("excluded_self_reports", []))
    expected_paths = sorted(path for path in evidence if path not in excluded)
    entries = hashes.get("files", [])
    entry_by_path = {str(item.get("path", "")): item for item in entries}
    missing_entries = sorted(path for path in expected_paths if path not in entry_by_path)
    extra_entries = sorted(path for path in entry_by_path if path not in expected_paths)
    failures: list[str] = []
    if hashes.get("algorithm") != "sha256":
        failures.append(f"algorithm={hashes.get('algorithm')}")
    if missing_entries:
        failures.append(f"missing hash entries: {missing_entries}")
    if extra_entries:
        failures.append(f"extra hash entries: {extra_entries}")
    for relative in expected_paths:
        path = REPO_ROOT / relative
        entry = entry_by_path.get(relative)
        if entry is None:
            continue
        if not path.exists():
            failures.append(f"missing file: {relative}")
            continue
        if int(entry.get("bytes") or -1) != path.stat().st_size:
            failures.append(f"bytes mismatch: {relative}")
        if str(entry.get("sha256", "")) != sha256_file(path):
            failures.append(f"sha256 mismatch: {relative}")
    return GateCheck(
        "evidence integrity hashes",
        not failures,
        f"{len(expected_paths)} evidence hashes verified; excluded={sorted(excluded)}"
        if not failures
        else "; ".join(failures),
    )


def check_submission_archive() -> GateCheck:
    failures: list[str] = []
    if not PACKAGE_MANIFEST.exists():
        return GateCheck("submission archive", False, "package_manifest.json missing")
    manifest = load_json(PACKAGE_MANIFEST)
    if manifest.get("submission_archive") != SUBMISSION_ARCHIVE_RELATIVE:
        failures.append(f"submission_archive mismatch: {manifest.get('submission_archive')}")
    if manifest.get("submission_archive_manifest") != SUBMISSION_ARCHIVE_MANIFEST_RELATIVE:
        failures.append(f"submission_archive_manifest mismatch: {manifest.get('submission_archive_manifest')}")
    if not nonempty(SUBMISSION_ARCHIVE):
        failures.append(f"{SUBMISSION_ARCHIVE_RELATIVE} missing or empty")
    if not nonempty(SUBMISSION_ARCHIVE_MANIFEST):
        failures.append(f"{SUBMISSION_ARCHIVE_MANIFEST_RELATIVE} missing or empty")
    if failures:
        return GateCheck("submission archive", False, "; ".join(failures))

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST)
    included_files = [str(item) for item in archive_manifest.get("included_files", [])]
    if archive_manifest.get("archive_path") != SUBMISSION_ARCHIVE_RELATIVE:
        failures.append(f"archive_path mismatch: {archive_manifest.get('archive_path')}")
    if archive_manifest.get("algorithm") != "sha256":
        failures.append(f"algorithm={archive_manifest.get('algorithm')}")
    if int(archive_manifest.get("bytes") or -1) != SUBMISSION_ARCHIVE.stat().st_size:
        failures.append("bytes mismatch")
    if str(archive_manifest.get("sha256", "")) != sha256_file(SUBMISSION_ARCHIVE):
        failures.append("sha256 mismatch")
    if int(archive_manifest.get("file_count") or -1) != len(included_files):
        failures.append("file_count mismatch")
    if included_files != sorted(included_files):
        failures.append("included_files not sorted")
    duplicated = sorted(path for path in set(included_files) if included_files.count(path) > 1)
    if duplicated:
        failures.append(f"duplicate entries: {duplicated}")

    unsafe = []
    for relative in included_files:
        posix = PurePosixPath(relative)
        if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
            unsafe.append(relative)
    if unsafe:
        failures.append(f"unsafe archive paths: {unsafe}")
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    self_included = sorted(
        path
        for path in (self_report, SUBMISSION_ARCHIVE_RELATIVE, SUBMISSION_ARCHIVE_MANIFEST_RELATIVE)
        if path in included_files
    )
    if self_included:
        failures.append(f"archive self-inclusion: {self_included}")

    required_package_docs = {
        f"docs/challenge_cup/{relative}"
        for relative in REQUIRED_PACKAGE_DOCS
        if relative != "reproducibility/challenge_cup_submission_archive_manifest.json"
    }
    required_archive_entries = set(manifest.get("evidence_files", [])) | required_package_docs | {
        PACKAGE_MANIFEST.relative_to(REPO_ROOT).as_posix(),
        EVIDENCE_HASHES.relative_to(REPO_ROOT).as_posix(),
        EVAL_COVERAGE_PROFILE.relative_to(REPO_ROOT).as_posix(),
        "docs/challenge_cup/reproducibility/dataset_manifest.md",
        "docs/challenge_cup/reproducibility/runbook.md",
        "docs/challenge_cup/reproducibility/command_log.md",
    }
    required_archive_entries.discard(self_report)
    missing_required = sorted(required_archive_entries - set(included_files))
    if missing_required:
        failures.append(f"missing archive entries: {missing_required}")

    try:
        with zipfile.ZipFile(SUBMISSION_ARCHIVE) as archive:
            zip_entries = sorted(info.filename for info in archive.infolist())
            if zip_entries != included_files:
                failures.append("zip entries do not match archive manifest")
            for relative in included_files:
                current_path = REPO_ROOT / relative
                if not current_path.exists():
                    failures.append(f"current file missing: {relative}")
                    continue
                if archive.read(relative) != current_path.read_bytes():
                    failures.append(f"stale archive entry: {relative}")
    except (KeyError, zipfile.BadZipFile) as exc:
        failures.append(f"invalid zip archive: {exc}")

    archive_controls = [SUBMISSION_ARCHIVE_RELATIVE, SUBMISSION_ARCHIVE_MANIFEST_RELATIVE]
    tracked = git_tracked_paths()
    untracked = [path for path in archive_controls if path not in tracked]
    dirty = sorted(git_dirty_paths(archive_controls))
    if untracked:
        failures.append(f"untracked archive controls: {untracked}")
    if dirty:
        failures.append(f"dirty archive controls: {dirty}")

    return GateCheck(
        "submission archive",
        not failures,
        f"{len(included_files)} files archived; {SUBMISSION_ARCHIVE.stat().st_size} bytes; sha256 verified"
        if not failures
        else "; ".join(failures),
    )


def check_submission_package_verifier() -> GateCheck:
    failures: list[str] = []
    if not nonempty(SUBMISSION_ARCHIVE):
        failures.append(f"{SUBMISSION_ARCHIVE_RELATIVE} missing or empty")
    if not nonempty(SUBMISSION_PACKAGE_VERIFIER):
        failures.append(f"{SUBMISSION_PACKAGE_VERIFIER_RELATIVE} missing or empty")
    if failures:
        return GateCheck("submission package verifier", False, "; ".join(failures))

    with tempfile.TemporaryDirectory(prefix="challenge-cup-submission-verify-") as temp_name:
        extract_root = Path(temp_name)
        try:
            with zipfile.ZipFile(SUBMISSION_ARCHIVE) as archive:
                archive.extractall(extract_root)
        except zipfile.BadZipFile as exc:
            return GateCheck("submission package verifier", False, f"invalid zip archive: {exc}")

        verifier = extract_root / SUBMISSION_PACKAGE_VERIFIER_RELATIVE
        output_json = extract_root / "submission_package_verification.json"
        if not nonempty(verifier):
            failures.append(f"verifier missing from archive: {SUBMISSION_PACKAGE_VERIFIER_RELATIVE}")
        else:
            result = subprocess.run(
                [sys.executable, str(verifier), "--root", str(extract_root), "--json-output", str(output_json)],
                cwd=extract_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                failures.append(f"verifier exit={result.returncode}: {result.stdout.strip()} {result.stderr.strip()}")
            if not output_json.exists():
                failures.append("verifier json output missing")
            else:
                try:
                    payload = json.loads(output_json.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    failures.append(f"verifier json invalid: {exc}")
                    payload = {}
                if payload.get("report_type") != "challenge_cup_submission_package_verification":
                    failures.append(f"verifier report_type={payload.get('report_type')}")
                if payload.get("status") != "pass":
                    failures.append(f"verifier status={payload.get('status')}")
                if int(payload.get("hashed_files_verified") or 0) < 50:
                    failures.append(f"hashed_files_verified={payload.get('hashed_files_verified')}")
                if payload.get("live_smoke_status") != "pass":
                    failures.append(f"live_smoke_status={payload.get('live_smoke_status')}")
                if payload.get("browser_smoke_status") != "pass":
                    failures.append(f"browser_smoke_status={payload.get('browser_smoke_status')}")

    return GateCheck(
        "submission package verifier",
        not failures,
        "extracted submission package verifier passed from archived script"
        if not failures
        else "; ".join(failures),
    )


def check_final_acceptance_audit() -> GateCheck:
    failures: list[str] = []
    bootstrapping_readiness_report = not REPORT_MD.exists()
    if not nonempty(FINAL_ACCEPTANCE_AUDIT_MD):
        failures.append(f"{FINAL_ACCEPTANCE_AUDIT_MD_RELATIVE} missing or empty")
    if not nonempty(FINAL_ACCEPTANCE_AUDIT_JSON):
        failures.append(f"{FINAL_ACCEPTANCE_AUDIT_JSON_RELATIVE} missing or empty")
    if failures:
        return GateCheck("final acceptance audit", False, "; ".join(failures))

    try:
        payload = json.loads(FINAL_ACCEPTANCE_AUDIT_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return GateCheck("final acceptance audit", False, f"invalid json: {exc}")

    if payload.get("report_type") != "challenge_cup_final_acceptance_audit":
        failures.append(f"report_type={payload.get('report_type')}")

    status = payload.get("status")
    allowed_statuses = {"package_ready_awaiting_external_hard_evidence", "goal_complete"}
    if bootstrapping_readiness_report:
        allowed_statuses.add("not_ready")
    if status not in allowed_statuses:
        failures.append(f"status={status}")

    package_readiness = payload.get("package_readiness")
    if not isinstance(package_readiness, dict):
        failures.append("package_readiness missing")
    else:
        if package_readiness.get("status") != "pass" and not bootstrapping_readiness_report:
            failures.append(f"package_readiness.status={package_readiness.get('status')}")
        if package_readiness.get("passed") != package_readiness.get("total") and not bootstrapping_readiness_report:
            failures.append(
                f"package_readiness count={package_readiness.get('passed')}/{package_readiness.get('total')}"
            )

    verifier = payload.get("submission_package_verifier")
    if not isinstance(verifier, dict):
        failures.append("submission_package_verifier missing")
    else:
        if verifier.get("available") is not True:
            failures.append(f"submission_package_verifier.available={verifier.get('available')}")
        if verifier.get("archived") is not True:
            failures.append(f"submission_package_verifier.archived={verifier.get('archived')}")
        if verifier.get("path") != SUBMISSION_PACKAGE_VERIFIER_RELATIVE:
            failures.append(f"submission_package_verifier.path={verifier.get('path')}")

    goal_completion = payload.get("goal_completion")
    if not isinstance(goal_completion, dict):
        failures.append("goal_completion missing")
    else:
        if status == "package_ready_awaiting_external_hard_evidence":
            if goal_completion.get("status") != "fail":
                failures.append(f"goal_completion.status={goal_completion.get('status')}")
            if goal_completion.get("completion_claim_allowed") is not False:
                failures.append(
                    f"goal_completion.completion_claim_allowed={goal_completion.get('completion_claim_allowed')}"
                )
        elif status == "goal_complete":
            if goal_completion.get("status") != "pass":
                failures.append(f"goal_completion.status={goal_completion.get('status')}")
            if goal_completion.get("completion_claim_allowed") is not True:
                failures.append(
                    f"goal_completion.completion_claim_allowed={goal_completion.get('completion_claim_allowed')}"
                )

    if status == "package_ready_awaiting_external_hard_evidence":
        if payload.get("can_submit_for_package_review") is not True:
            failures.append(f"can_submit_for_package_review={payload.get('can_submit_for_package_review')}")
        if payload.get("can_mark_goal_complete") is not False:
            failures.append(f"can_mark_goal_complete={payload.get('can_mark_goal_complete')}")
        blocking_items = payload.get("blocking_items")
        if not isinstance(blocking_items, list):
            failures.append("blocking_items missing")
        else:
            blocking_categories = {
                str(item.get("category")) for item in blocking_items if isinstance(item, dict)
            }
            if blocking_categories != {"expert_feedback", "timed_rehearsal"}:
                failures.append(f"blocking_items={sorted(blocking_categories)}")
    elif status == "goal_complete":
        if payload.get("can_submit_for_package_review") is not True:
            failures.append(f"can_submit_for_package_review={payload.get('can_submit_for_package_review')}")
        if payload.get("can_mark_goal_complete") is not True:
            failures.append(f"can_mark_goal_complete={payload.get('can_mark_goal_complete')}")
    elif status == "not_ready" and bootstrapping_readiness_report:
        if package_readiness.get("report") != REPORT_MD.relative_to(REPO_ROOT).as_posix():
            failures.append(f"package_readiness.report={package_readiness.get('report')}")

    markdown = FINAL_ACCEPTANCE_AUDIT_MD.read_text(encoding="utf-8")
    for term in [
        "Final Acceptance Audit",
        "verify_submission_package.py",
        "completion_claim_allowed=False"
        if status in {"package_ready_awaiting_external_hard_evidence", "not_ready"}
        else "goal_complete",
    ]:
        if term not in markdown:
            failures.append(f"markdown missing {term}")

    return GateCheck(
        "final acceptance audit",
        not failures,
        "package can be reviewed while goal completion remains blocked by expert feedback and timed rehearsal"
        if not failures and status == "package_ready_awaiting_external_hard_evidence"
        else "goal completion audit passed"
        if not failures
        else "; ".join(failures),
    )


def check_defense_deck() -> GateCheck:
    failures: list[str] = []
    if not nonempty(DEFENSE_DECK_PPTX):
        failures.append(f"{DEFENSE_DECK_PPTX_RELATIVE} missing or empty")
    if not nonempty(DEFENSE_DECK_NOTES):
        failures.append(f"{DEFENSE_DECK_NOTES_RELATIVE} missing or empty")
    if not PACKAGE_MANIFEST.exists():
        failures.append("package_manifest.json missing")
    if failures:
        return GateCheck("defense deck", False, "; ".join(failures))

    try:
        slide_count, deck_text = pptx_text_and_slide_count(DEFENSE_DECK_PPTX)
    except (ET.ParseError, KeyError, zipfile.BadZipFile) as exc:
        return GateCheck("defense deck", False, f"invalid pptx: {exc}")

    if slide_count != 10:
        failures.append(f"slide_count={slide_count}, expected=10")
    missing_deck_terms = sorted(term for term in DEFENSE_DECK_REQUIRED_TERMS if term not in deck_text)
    if missing_deck_terms:
        failures.append(f"missing deck terms: {missing_deck_terms}")

    notes = DEFENSE_DECK_NOTES.read_text(encoding="utf-8", errors="ignore")
    missing_notes_terms = sorted(term for term in DEFENSE_DECK_NOTES_REQUIRED_TERMS if term not in notes)
    if missing_notes_terms:
        failures.append(f"missing speaker notes terms: {missing_notes_terms}")

    manifest = load_json(PACKAGE_MANIFEST)
    evidence = set(manifest.get("evidence_files", []))
    missing_manifest_entries = sorted(
        relative
        for relative in (DEFENSE_DECK_PPTX_RELATIVE, DEFENSE_DECK_NOTES_RELATIVE)
        if relative not in evidence
    )
    if missing_manifest_entries:
        failures.append(f"missing manifest entries: {missing_manifest_entries}")

    controls = [DEFENSE_DECK_PPTX_RELATIVE, DEFENSE_DECK_NOTES_RELATIVE]
    tracked = git_tracked_paths()
    untracked = [path for path in controls if path not in tracked]
    dirty = sorted(git_dirty_paths(controls))
    if untracked:
        failures.append(f"untracked defense deck files: {untracked}")
    if dirty:
        failures.append(f"dirty defense deck files: {dirty}")

    return GateCheck(
        "defense deck",
        not failures,
        f"{slide_count} slides, speaker notes, fixed GT-07 scenario, GraphRAG, readiness, and feedback boundary verified"
        if not failures
        else "; ".join(failures),
    )


def check_numeric_consistency() -> GateCheck:
    failures: list[str] = []
    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    coverage = load_json(EVAL_COVERAGE_PROFILE) if EVAL_COVERAGE_PROFILE.exists() else {}
    browser_payload = load_json(BROWSER_SMOKE_JSON) if BROWSER_SMOKE_JSON.exists() else {}
    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {}

    dataset_count = sum(1 for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()) if DATASET.exists() else -1
    manifest_count = int(manifest.get("question_count") or -1)
    coverage_count = int(coverage.get("question_count") or -1)
    if not (dataset_count == manifest_count == coverage_count == 60):
        failures.append(
            f"question_count mismatch: dataset={dataset_count}, manifest={manifest_count}, coverage={coverage_count}, expected=60"
        )

    evidence_files = manifest.get("evidence_files", [])
    excluded = set(hashes.get("excluded_self_reports", []))
    hashed_count = len(hashes.get("files", [])) + len(excluded)
    if len(evidence_files) != hashed_count:
        failures.append(f"evidence file/hash count mismatch: evidence_files={len(evidence_files)}, hashed_plus_excluded={hashed_count}")

    browser = browser_payload.get("browser", {})
    search_meta = str(browser.get("search_meta", ""))
    match = re.search(r"结果\s*(\d+)", search_meta)
    meta_result_count = int(match.group(1)) if match else -1
    card_count = int(browser.get("search_result_card_count") or -1)
    visible_record_ids = {str(item) for item in browser.get("visible_record_ids", [])}
    visible_count = len(visible_record_ids)
    expected_visible = len(REQUIRED_SCENARIO_RECORD_IDS)
    if not (meta_result_count == card_count == visible_count == expected_visible == 5):
        failures.append(
            f"search result count mismatch: meta={meta_result_count}, cards={card_count}, visible={visible_count}, expected={expected_visible}"
        )
    missing_visible_records = sorted(REQUIRED_SCENARIO_RECORD_IDS - visible_record_ids)
    if missing_visible_records:
        failures.append(f"missing visible record ids: {missing_visible_records}")

    return GateCheck(
        "numeric consistency",
        not failures,
        f"60 questions, {len(evidence_files)} evidence files, and 5 visible search records are consistent"
        if not failures
        else "; ".join(failures),
    )


def check_graphrag_same_question_evidence() -> GateCheck:
    failures: list[str] = []
    if not GRAPH_REPORT_JSON.exists():
        return GateCheck("graphrag evidence audit", False, f"{GRAPH_REPORT_JSON.relative_to(REPO_ROOT)} missing")
    if not GRAPH_REPORT_MD.exists():
        return GateCheck("graphrag evidence audit", False, f"{GRAPH_REPORT_MD.relative_to(REPO_ROOT)} missing")

    payload = load_json(GRAPH_REPORT_JSON)
    markdown = GRAPH_REPORT_MD.read_text(encoding="utf-8")
    if int(payload.get("total_questions") or 0) != 60:
        failures.append("total_questions must be 60")
    if int(payload.get("graphrag_question_count") or 0) != 10:
        failures.append("graphrag_question_count must be 10")
    mode_counts = payload.get("mode_counts", {})
    if int(mode_counts.get("graphrag_context") or 0) < 8:
        failures.append("graphrag_context count below 8")
    if int(mode_counts.get("graphrag_global") or 0) < 4:
        failures.append("graphrag_global count below 4")

    source = str(payload.get("graph_evidence_source", ""))
    if not source.endswith("triples.csv"):
        failures.append("graph_evidence_source must point to triples.csv")
    elif not nonempty(REPO_ROOT / source):
        failures.append(f"graph_evidence_source missing or empty: {source}")

    supplement = str(payload.get("graph_evidence_supplement", ""))
    expected_supplement = GRAPH_MANUAL_EVIDENCE_SUPPLEMENT.relative_to(REPO_ROOT).as_posix()
    if supplement != expected_supplement:
        failures.append(f"graph_evidence_supplement={supplement}")
    elif not nonempty(REPO_ROOT / supplement):
        failures.append(f"graph_evidence_supplement missing or empty: {supplement}")
    base_count = int(payload.get("base_graph_triple_count") or 0)
    supplement_count = int(payload.get("manual_evidence_supplement_count") or 0)
    if base_count < 240:
        failures.append(f"base_graph_triple_count below 240: {base_count}")
    if supplement_count < 5:
        failures.append(f"manual_evidence_supplement_count below 5: {supplement_count}")
    triple_count = int(payload.get("graph_triple_count") or 0)
    if triple_count != base_count + supplement_count:
        failures.append(f"graph_triple_count mismatch: {triple_count} != {base_count}+{supplement_count}")
    supported = int(payload.get("graph_evidence_supported_case_count") or 0)
    partial = int(payload.get("graph_evidence_partial_case_count") or 0)
    missing = int(payload.get("graph_evidence_missing_case_count") or 0)
    if supported != 10:
        failures.append(f"graph_evidence_supported_case_count must be 10 after cc056 supplement: {supported}")
    if partial != 0:
        failures.append(f"graph_evidence_partial_case_count must be 0 after cc056 supplement: {partial}")
    if missing != 0:
        failures.append(f"graph_evidence_missing_case_count must be 0 after P0 supplement: {missing}")
    if payload.get("graph_evidence_boundary") != GRAPH_EVIDENCE_BOUNDARY:
        failures.append("graph_evidence_boundary mismatch")

    cases = payload.get("cases", [])
    if not isinstance(cases, list) or len(cases) != int(payload.get("graphrag_question_count") or -1):
        failures.append("cases must match graphrag_question_count")
        cases = []
    supported_with_hits = 0
    required_supported_cases = {"cc032", "cc035", "cc043", "cc048", "cc056"}
    for case in cases:
        missing_fields = sorted(REQUIRED_GRAPH_CASE_FIELDS - set(case))
        if missing_fields:
            failures.append(f"case {case.get('id', '<unknown>')} missing fields: {missing_fields}")
            continue
        coverage = float(case.get("graph_evidence_coverage") or 0)
        if coverage < 0 or coverage > 1:
            failures.append(f"case {case.get('id')} graph_evidence_coverage out of range")
        status = str(case.get("graph_evidence_status", ""))
        hits = case.get("matched_graph_evidence", [])
        if status == "supported" and hits:
            supported_with_hits += 1
        if str(case.get("id")) in required_supported_cases and status != "supported":
            failures.append(f"manual supplement case {case.get('id')} not supported")
        if str(case.get("id")) == "cc035":
            if int(case.get("graph_matchable_keyword_count") or 0) != 2:
                failures.append("cc035 graph_matchable_keyword_count must ignore pure numeric keywords")
            if case.get("ignored_graph_keywords") != ["27", "26", "1", "0"]:
                failures.append("cc035 ignored_graph_keywords mismatch")
        if str(case.get("id")) == "cc056":
            if float(case.get("graph_evidence_coverage") or 0) != 1.0:
                failures.append("cc056 graph_evidence_coverage must be 1.0 after relation schema supplement")
            expected_keywords = {"related_to", "关系类型", "原因", "症状", "处理措施", "过滤"}
            if set(case.get("matched_graph_keywords", [])) != expected_keywords:
                failures.append("cc056 matched_graph_keywords mismatch")
    if supported_with_hits < 1:
        failures.append("no supported GraphRAG evidence case with matched_graph_evidence")

    required_markdown_terms = {
        "Graph evidence coverage audit",
        "triples.csv",
        "manual evidence supplement",
        "不代表完整 GraphRAG 在线问答已优于 baseline",
    }
    missing_markdown_terms = sorted(term for term in required_markdown_terms if term not in markdown)
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    return GateCheck(
        "graphrag evidence audit",
        not failures,
        f"{supported} supported, {partial} partial, {missing} missing cases over {triple_count} triples"
        if not failures
        else "; ".join(failures),
    )


def check_graphrag_context_demo() -> GateCheck:
    failures: list[str] = []
    if not GRAPH_CONTEXT_DEMO_JSON.exists():
        return GateCheck("graphrag context demo", False, f"{GRAPH_CONTEXT_DEMO_JSON.relative_to(REPO_ROOT)} missing")
    if not GRAPH_CONTEXT_DEMO_MD.exists():
        return GateCheck("graphrag context demo", False, f"{GRAPH_CONTEXT_DEMO_MD.relative_to(REPO_ROOT)} missing")

    payload = load_json(GRAPH_CONTEXT_DEMO_JSON)
    markdown = GRAPH_CONTEXT_DEMO_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_graphrag_context_demo":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("context_only") is not True:
        failures.append("context_only must be true")
    if payload.get("answer_generated") is not False:
        failures.append("answer_generated must be false")
    if payload.get("boundary") != GRAPH_CONTEXT_DEMO_BOUNDARY:
        failures.append("boundary mismatch")
    if str(payload.get("text_baseline_method", "")) != "keyword":
        failures.append("text_baseline_method must be keyword")
    source_graph = str(payload.get("source_graph", ""))
    if not source_graph.endswith("triples.csv"):
        failures.append("source_graph must point to triples.csv")
    elif not nonempty(REPO_ROOT / source_graph):
        failures.append(f"source_graph missing or empty: {source_graph}")
    case_ids = [str(item) for item in payload.get("case_ids", [])]
    required_case_ids = ["cc039", "cc040", "cc041"]
    if case_ids != required_case_ids:
        failures.append(f"case_ids must be {required_case_ids}: {case_ids}")
    cases = payload.get("cases", [])
    if not isinstance(cases, list) or len(cases) != int(payload.get("demo_case_count") or -1):
        failures.append("cases must match demo_case_count")
        cases = []
    if int(payload.get("demo_case_count") or 0) < 3:
        failures.append("demo_case_count below 3")
    for case in cases:
        case_id = str(case.get("id", "<unknown>"))
        if case.get("answer") is not None:
            failures.append(f"case {case_id} answer must be null")
        if not case.get("text_evidence"):
            failures.append(f"case {case_id} missing text_evidence")
        if not case.get("graph_evidence"):
            failures.append(f"case {case_id} missing graph_evidence")
        citation_types = {str(citation.get("source_type", "")) for citation in case.get("citations", [])}
        if not {"text", "graph"} <= citation_types:
            failures.append(f"case {case_id} citations must include text and graph")
        prompt_context = str(case.get("prompt_context", ""))
        for term in ("Context-only debug mode", "## Text retrieval evidence", "## Graph retrieval evidence"):
            if term not in prompt_context:
                failures.append(f"case {case_id} prompt_context missing {term}")

    required_markdown_terms = {
        "GraphRAG context-only QA demo",
        "不生成 LLM 答案",
        "triples.csv",
        GRAPH_CONTEXT_DEMO_BOUNDARY,
    }
    missing_markdown_terms = sorted(term for term in required_markdown_terms if term not in markdown)
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    return GateCheck(
        "graphrag context demo",
        not failures,
        f"{payload.get('demo_case_count')} context-only cases with text and graph citations"
        if not failures
        else "; ".join(failures),
    )


def check_graphrag_answer_benchmark() -> GateCheck:
    failures: list[str] = []
    if not GRAPH_ANSWER_BENCHMARK_JSON.exists():
        return GateCheck("graphrag answer benchmark", False, f"{GRAPH_ANSWER_BENCHMARK_JSON.relative_to(REPO_ROOT)} missing")
    if not GRAPH_ANSWER_BENCHMARK_MD.exists():
        return GateCheck("graphrag answer benchmark", False, f"{GRAPH_ANSWER_BENCHMARK_MD.relative_to(REPO_ROOT)} missing")

    payload = load_json(GRAPH_ANSWER_BENCHMARK_JSON)
    markdown = GRAPH_ANSWER_BENCHMARK_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_graphrag_answer_benchmark":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("benchmark_mode") != "deterministic_offline_reference_keyword_coverage":
        failures.append(f"benchmark_mode={payload.get('benchmark_mode')}")
    if payload.get("llm_answer_generated") is not False:
        failures.append(f"llm_answer_generated={payload.get('llm_answer_generated')}")
    if payload.get("boundary") != GRAPH_ANSWER_BENCHMARK_BOUNDARY:
        failures.append("boundary mismatch")
    if payload.get("dataset") != DATASET_RELATIVE:
        failures.append(f"dataset={payload.get('dataset')}")
    if payload.get("source_graph_report") != GRAPH_REPORT_JSON.relative_to(REPO_ROOT).as_posix():
        failures.append(f"source_graph_report={payload.get('source_graph_report')}")
    if int(payload.get("answer_benchmark_case_count") or 0) != 10:
        failures.append("answer_benchmark_case_count must be 10")
    if payload.get("partial_or_missing_cases_retained") is not False:
        failures.append("partial_or_missing_cases_retained must be false after cc056 supplement")
    if int(payload.get("best_baseline_method_count") or 0) != 3:
        failures.append("best_baseline_method_count must be 3")
    supported = int(payload.get("graphrag_supported_answer_case_count") or 0)
    partial = int(payload.get("graphrag_partial_answer_case_count") or 0)
    missing = int(payload.get("graphrag_missing_answer_case_count") or 0)
    if supported != 10:
        failures.append(f"graphrag_supported_answer_case_count must be 10 after cc056 supplement: {supported}")
    if partial != 0:
        failures.append(f"graphrag_partial_answer_case_count must be 0 after cc056 supplement: {partial}")
    if missing != 0:
        failures.append(f"graphrag_missing_answer_case_count must be 0 after P0 supplement: {missing}")
    baseline_avg = float(payload.get("average_best_baseline_reference_keyword_coverage") or -1)
    graph_avg = float(payload.get("average_graphrag_reference_keyword_coverage") or -1)
    if not (0 <= baseline_avg <= 1 and 0 <= graph_avg <= 1):
        failures.append(f"average coverage out of range: baseline={baseline_avg}, graph={graph_avg}")
    summary = str(payload.get("summary_verdict", ""))
    if "manual graph evidence now closes all fixed GraphRAG evidence gaps" not in summary:
        failures.append("summary_verdict missing full manual supplement closure")
    if "does not claim online LLM answer win-rate" not in summary:
        failures.append("summary_verdict missing no-online-win-rate boundary")

    cases = payload.get("cases", [])
    if not isinstance(cases, list) or len(cases) != 10:
        failures.append("cases must contain 10 GraphRAG questions")
        cases = []
    case_ids = {str(case.get("id", "")) for case in cases}
    required_case_ids = {"cc032", "cc033", "cc034", "cc035", "cc039", "cc040", "cc041", "cc043", "cc048", "cc056"}
    if case_ids != required_case_ids:
        failures.append(f"case ids mismatch: {sorted(case_ids)}")
    verdicts = {str(case.get("answer_level_verdict", "")) for case in cases}
    if verdicts != {"graph_supported"}:
        failures.append(f"verdicts must all be graph_supported after cc056 supplement: {sorted(verdicts)}")
    required_supported_cases = {"cc032", "cc035", "cc043", "cc048", "cc056"}
    for case in cases:
        case_id = str(case.get("id", "<unknown>"))
        if case_id in required_supported_cases and case.get("graphrag_answer_status") != "supported":
            failures.append(f"manual supplement answer case {case_id} not supported")
        for key in ("question", "reference_answer", "expected_evidence_keywords", "graphrag_answer_draft"):
            if not case.get(key):
                failures.append(f"case {case_id} missing {key}")
        if str(case.get("boundary", "")) != "保留该题原始 GraphRAG 证据状态，不把 partial/missing 改写成成功案例。":
            failures.append(f"case {case_id} boundary mismatch")

    missing_markdown_terms = sorted(
        term for term in (GRAPH_ANSWER_BENCHMARK_MARKDOWN_TERMS | {GRAPH_ANSWER_BENCHMARK_BOUNDARY}) if term not in markdown
    )
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    return GateCheck(
        "graphrag answer benchmark",
        not failures,
        f"{len(cases)} fixed GraphRAG answer cases; supported={supported}, partial={partial}, missing={missing}, graph_avg={graph_avg}"
        if not failures
        else "; ".join(failures),
    )


def check_graphrag_gap_remediation_plan() -> GateCheck:
    failures: list[str] = []
    if not GRAPH_GAP_REMEDIATION_JSON.exists():
        return GateCheck(
            "graphrag gap remediation plan",
            False,
            f"{GRAPH_GAP_REMEDIATION_JSON.relative_to(REPO_ROOT)} missing",
        )
    if not GRAPH_GAP_REMEDIATION_MD.exists():
        return GateCheck(
            "graphrag gap remediation plan",
            False,
            f"{GRAPH_GAP_REMEDIATION_MD.relative_to(REPO_ROOT)} missing",
        )

    payload = load_json(GRAPH_GAP_REMEDIATION_JSON)
    benchmark = load_json(GRAPH_ANSWER_BENCHMARK_JSON)
    markdown = GRAPH_GAP_REMEDIATION_MD.read_text(encoding="utf-8")
    benchmark_cases = benchmark.get("cases", [])
    expected_gap_cases = {
        str(case["id"]): str(case["graphrag_answer_status"])
        for case in benchmark_cases
        if case.get("graphrag_answer_status") in {"partial", "missing"}
    }
    expected_supported = sum(1 for case in benchmark_cases if case.get("graphrag_answer_status") == "supported")
    expected_partial = sum(1 for status in expected_gap_cases.values() if status == "partial")
    expected_missing = sum(1 for status in expected_gap_cases.values() if status == "missing")

    if payload.get("report_type") != "challenge_cup_graphrag_gap_remediation_plan":
        failures.append(f"report_type={payload.get('report_type')}")
    local_gaps_closed = not expected_gap_cases and expected_supported == len(benchmark_cases)
    expected_status = (
        "graph_evidence_gaps_closed_pending_external_validation"
        if local_gaps_closed
        else "ready_for_graph_iteration"
    )
    if payload.get("status") != expected_status:
        failures.append(f"status={payload.get('status')}")
    if payload.get("gaps_marked_fixed") is not local_gaps_closed:
        failures.append(f"gaps_marked_fixed={payload.get('gaps_marked_fixed')}")
    if payload.get("local_graph_evidence_gaps_closed") is not local_gaps_closed:
        failures.append(f"local_graph_evidence_gaps_closed={payload.get('local_graph_evidence_gaps_closed')}")
    if payload.get("boundary") != GRAPH_GAP_REMEDIATION_BOUNDARY:
        failures.append("boundary mismatch")
    if payload.get("source_dataset") != DATASET_RELATIVE:
        failures.append(f"source_dataset={payload.get('source_dataset')}")
    if payload.get("source_graph_report") != GRAPH_REPORT_JSON.relative_to(REPO_ROOT).as_posix():
        failures.append(f"source_graph_report={payload.get('source_graph_report')}")
    if payload.get("source_answer_benchmark") != GRAPH_ANSWER_BENCHMARK_JSON.relative_to(REPO_ROOT).as_posix():
        failures.append(f"source_answer_benchmark={payload.get('source_answer_benchmark')}")
    if int(payload.get("total_graph_cases", -1)) != len(benchmark_cases):
        failures.append("total_graph_cases mismatch")
    if int(payload.get("supported_count", -1)) != expected_supported:
        failures.append("supported_count mismatch")
    if int(payload.get("partial_count", -1)) != expected_partial:
        failures.append("partial_count mismatch")
    if int(payload.get("missing_count", -1)) != expected_missing:
        failures.append("missing_count mismatch")
    if int(payload.get("partial_or_missing_count", -1)) != len(expected_gap_cases):
        failures.append("partial_or_missing_count mismatch")
    if payload.get("required_evidence_to_archive") != GRAPH_GAP_REQUIRED_ARCHIVE_EVIDENCE:
        failures.append("required_evidence_to_archive mismatch")
    if payload.get("rerun_commands") != GRAPH_GAP_REQUIRED_RERUN_COMMANDS:
        failures.append("rerun_commands mismatch")
    if "不宣称在线 LLM answer win-rate" not in payload.get("no_overclaim_rules", []):
        failures.append("missing no-overclaim rule")
    if "不宣称 GraphRAG 全面优于 baseline" not in payload.get("no_overclaim_rules", []):
        failures.append("missing no-baseline-overclaim rule")

    closure = payload.get("closure_evidence", {})
    if not isinstance(closure, dict):
        failures.append("closure_evidence missing")
        closure = {}
    if local_gaps_closed:
        if closure.get("closed_case_ids") != ["cc056"]:
            failures.append(f"closure_evidence.closed_case_ids={closure.get('closed_case_ids')}")
        expected_supplement = GRAPH_MANUAL_EVIDENCE_SUPPLEMENT.relative_to(REPO_ROOT).as_posix()
        if closure.get("manual_supplement") != expected_supplement:
            failures.append(f"closure_evidence.manual_supplement={closure.get('manual_supplement')}")
        if closure.get("source_graph_report") != GRAPH_REPORT_JSON.relative_to(REPO_ROOT).as_posix():
            failures.append(f"closure_evidence.source_graph_report={closure.get('source_graph_report')}")
        if closure.get("source_answer_benchmark") != GRAPH_ANSWER_BENCHMARK_JSON.relative_to(REPO_ROOT).as_posix():
            failures.append(f"closure_evidence.source_answer_benchmark={closure.get('source_answer_benchmark')}")

    items = payload.get("remediation_items", [])
    if not isinstance(items, list):
        failures.append("remediation_items missing")
        items = []
    item_by_id = {str(item.get("id")): item for item in items if isinstance(item, dict)}
    if set(item_by_id) != set(expected_gap_cases):
        failures.append(f"remediation ids mismatch: expected={sorted(expected_gap_cases)}, actual={sorted(item_by_id)}")
    for case_id, expected_status in expected_gap_cases.items():
        item = item_by_id.get(case_id, {})
        if item.get("current_status") != expected_status:
            failures.append(f"{case_id}.current_status={item.get('current_status')}")
        expected_priority = "P0" if expected_status == "missing" else "P1"
        if item.get("priority") != expected_priority:
            failures.append(f"{case_id}.priority={item.get('priority')}")
        if item.get("claim_fixed") is not False:
            failures.append(f"{case_id}.claim_fixed={item.get('claim_fixed')}")
        if not item.get("missing_expected_keywords"):
            failures.append(f"{case_id}.missing_expected_keywords missing")
        if len(item.get("action_items", [])) < 3:
            failures.append(f"{case_id}.action_items below 3")
        acceptance = set(str(value) for value in item.get("acceptance_evidence", []))
        missing_acceptance = sorted(set(GRAPH_GAP_REQUIRED_ARCHIVE_EVIDENCE) - acceptance)
        if missing_acceptance:
            failures.append(f"{case_id}.acceptance_evidence missing {missing_acceptance}")

    missing_markdown_terms = sorted(
        term for term in (GRAPH_GAP_REMEDIATION_MARKDOWN_TERMS | {GRAPH_GAP_REMEDIATION_BOUNDARY}) if term not in markdown
    )
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    return GateCheck(
        "graphrag gap remediation plan",
        not failures,
        (
            "local GraphRAG evidence gaps closed; 0 remediation tasks remain"
            if local_gaps_closed
            else f"{len(expected_gap_cases)} partial/missing cases converted into remediation tasks"
        )
        if not failures
        else "; ".join(failures),
    )


def check_failure_remediation_before_after() -> GateCheck:
    failures: list[str] = []
    required_files = [FAILURE_REMEDIATION_BEFORE_AFTER_MD, FAILURE_REMEDIATION_BEFORE_AFTER_JSON]
    missing_files = [path.name + " missing" for path in required_files if not nonempty(path)]
    if missing_files:
        return GateCheck("failure remediation before/after", False, ", ".join(missing_files))

    try:
        payload = load_json(FAILURE_REMEDIATION_BEFORE_AFTER_JSON)
    except (OSError, json.JSONDecodeError) as exc:
        return GateCheck("failure remediation before/after", False, f"invalid before/after json: {exc}")
    markdown = FAILURE_REMEDIATION_BEFORE_AFTER_MD.read_text(encoding="utf-8")

    if payload.get("report_type") != "challenge_cup_failure_remediation_before_after":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "remediation_card_ablation_ready_no_live_retriever_claim":
        failures.append(f"status={payload.get('status')}")
    if payload.get("completion_claim_allowed") is not False:
        failures.append(f"completion_claim_allowed={payload.get('completion_claim_allowed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")
    if payload.get("live_retriever_upgrade_claimed") is not False:
        failures.append(f"live_retriever_upgrade_claimed={payload.get('live_retriever_upgrade_claimed')}")
    if payload.get("boundary") != FAILURE_REMEDIATION_BEFORE_AFTER_BOUNDARY:
        failures.append("boundary mismatch")
    if payload.get("source_day4_failure_analysis") != "evaluation/reports/day4_failure_analysis_20260605_210642.json":
        failures.append(f"source_day4_failure_analysis={payload.get('source_day4_failure_analysis')}")
    if payload.get("source_graphrag_same_question_report") != GRAPH_REPORT_JSON.relative_to(REPO_ROOT).as_posix():
        failures.append(f"source_graphrag_same_question_report={payload.get('source_graphrag_same_question_report')}")

    analyzed = int(payload.get("analyzed_question_count") or -1)
    if analyzed != 40:
        failures.append(f"analyzed_question_count={payload.get('analyzed_question_count')}")

    category_closure = payload.get("category_closure", {})
    if not isinstance(category_closure, dict):
        failures.append("category_closure missing")
        category_closure = {}
    category_keys = {str(key) for key in category_closure}
    if category_keys != FAILURE_REMEDIATION_REQUIRED_CATEGORIES:
        failures.append(f"category_closure keys={sorted(category_keys)}")
    category_closed_count = 0
    for category, item in category_closure.items():
        if not isinstance(item, dict):
            failures.append(f"{category}: category closure item invalid")
            continue
        status = str(item.get("status", ""))
        if status not in FAILURE_REMEDIATION_ALLOWED_CATEGORY_STATUSES:
            failures.append(f"{category}: status={status}")
        category_closed_count += int(item.get("closed_or_bounded_count") or 0)

    before = payload.get("before", {})
    after = payload.get("after", {})
    if not isinstance(before, dict):
        failures.append("before missing")
        before = {}
    if not isinstance(after, dict):
        failures.append("after missing")
        after = {}
    before_avg = float(before.get("avg_hybrid_coverage") or -1)
    after_avg = float(after.get("avg_effective_coverage") or -1)
    before_zero = int(before.get("zero_coverage_question_count") or -1)
    after_zero = int(after.get("zero_coverage_question_count") or -1)
    if after_avg <= before_avg:
        failures.append(f"after avg coverage not improved: before={before_avg}, after={after_avg}")
    if after_zero >= before_zero:
        failures.append(f"zero coverage not reduced: before={before_zero}, after={after_zero}")
    if int(after.get("closed_or_bounded_case_count") or -1) != analyzed:
        failures.append(f"closed_or_bounded_case_count={after.get('closed_or_bounded_case_count')}")
    if category_closed_count != analyzed:
        failures.append(f"category closed_or_bounded total={category_closed_count}")

    critical_status = after.get("critical_case_status", {})
    expected_critical_status = {case_id: "closed_or_bounded" for case_id in sorted(FAILURE_REMEDIATION_CRITICAL_CASE_IDS)}
    if critical_status != expected_critical_status:
        failures.append(f"critical_case_status={critical_status}")

    case_results = payload.get("case_results", [])
    if not isinstance(case_results, list) or len(case_results) != analyzed:
        failures.append(f"case_results count={len(case_results) if isinstance(case_results, list) else 'invalid'}")
        case_results = []
    result_ids = {str(item.get("id", "")) for item in case_results if isinstance(item, dict)}
    missing_critical = sorted(FAILURE_REMEDIATION_CRITICAL_CASE_IDS - result_ids)
    if missing_critical:
        failures.append(f"critical cases missing from case_results: {missing_critical}")
    for item in case_results:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("id", ""))
        if item.get("closure_status") != "closed_or_bounded":
            failures.append(f"{case_id}: closure_status={item.get('closure_status')}")
        after_effective = float(item.get("after_effective_coverage") or 0)
        if after_effective < 0 or after_effective > 1:
            failures.append(f"{case_id}: after_effective_coverage={after_effective}")

    card_ids = {
        str(item.get("card_id", ""))
        for item in payload.get("remediation_cards", [])
        if isinstance(item, dict)
    }
    missing_cards = sorted(FAILURE_REMEDIATION_REQUIRED_CARD_IDS - card_ids)
    if missing_cards:
        failures.append(f"missing remediation cards: {missing_cards}")

    graph_subset = payload.get("graph_fixed_subset", {})
    if not isinstance(graph_subset, dict):
        failures.append("graph_fixed_subset missing")
        graph_subset = {}
    if int(graph_subset.get("supported_count", -1)) != 10:
        failures.append(f"graph supported_count={graph_subset.get('supported_count')}")
    if int(graph_subset.get("partial_count", -1)) != 0:
        failures.append(f"graph partial_count={graph_subset.get('partial_count')}")
    if int(graph_subset.get("missing_count", -1)) != 0:
        failures.append(f"graph missing_count={graph_subset.get('missing_count')}")
    minimum_avg = float(graph_subset.get("minimum_required_average_coverage") or 0)
    observed_avg = float(graph_subset.get("observed_average_coverage") or 0)
    observed_min = float(graph_subset.get("observed_min_coverage") or 0)
    if minimum_avg != 0.866667:
        failures.append(f"minimum_required_average_coverage={minimum_avg}")
    if observed_avg < minimum_avg:
        failures.append(f"observed_average_coverage={observed_avg}")
    if observed_min < 0.5:
        failures.append(f"observed_min_coverage={observed_min}")

    verification_commands = {str(item) for item in payload.get("verification_commands", [])}
    missing_commands = sorted(FAILURE_REMEDIATION_REQUIRED_COMMANDS - verification_commands)
    if missing_commands:
        failures.append(f"missing verification_commands: {missing_commands}")
    output_files = {str(item) for item in payload.get("output_files", [])}
    missing_output_files = sorted(path for path in FAILURE_REMEDIATION_BEFORE_AFTER_REQUIRED_PATHS if path not in output_files)
    if missing_output_files:
        failures.append(f"output_files missing: {missing_output_files}")

    missing_markdown_terms = sorted(
        term
        for term in (FAILURE_REMEDIATION_MARKDOWN_TERMS | {FAILURE_REMEDIATION_BEFORE_AFTER_BOUNDARY})
        if term not in markdown
    )
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    missing_manifest = sorted(
        path for path in FAILURE_REMEDIATION_BEFORE_AFTER_REQUIRED_PATHS if path not in manifest_evidence
    )
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(
        path for path in FAILURE_REMEDIATION_BEFORE_AFTER_REQUIRED_PATHS if path not in hashed_paths
    )
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(
        path for path in FAILURE_REMEDIATION_BEFORE_AFTER_REQUIRED_PATHS if path not in archived_paths
    )
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in FAILURE_REMEDIATION_BEFORE_AFTER_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(FAILURE_REMEDIATION_BEFORE_AFTER_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked failure remediation files: {untracked}")
    if dirty:
        failures.append(f"dirty failure remediation files: {dirty}")

    return GateCheck(
        "failure remediation before/after",
        not failures,
        (
            f"{analyzed} Day4 cases, {len(category_keys)} categories, "
            f"{len(FAILURE_REMEDIATION_CRITICAL_CASE_IDS)} critical cases, graph_avg={observed_avg}"
        )
        if not failures
        else "; ".join(failures),
    )


def check_report_payload(path: Path, required_checks: set[str], name: str) -> GateCheck:
    if not path.exists():
        return GateCheck(name, False, f"{path.relative_to(REPO_ROOT)} missing")
    payload = load_json(path)
    checks = payload.get("checks", [])
    check_names = {str(item.get("name", "")) for item in checks}
    missing = sorted(required_checks - check_names)
    failed = [str(item.get("name", "")) for item in checks if not item.get("passed")]
    passed = payload.get("status") == "pass" and int(payload.get("passed") or 0) == int(payload.get("total") or -1) and not missing and not failed
    if passed:
        detail = f"{payload.get('passed')}/{payload.get('total')} checks pass"
    else:
        detail = f"status={payload.get('status')}, missing={missing}, failed={failed}"
    return GateCheck(name, passed, detail)


def check_browser_evidence_files() -> GateCheck:
    payload = load_json(BROWSER_SMOKE_JSON) if BROWSER_SMOKE_JSON.exists() else {}
    browser = payload.get("browser", {})
    screenshots = browser.get("screenshots", {})
    missing = [path for path in screenshots.values() if not nonempty(REPO_ROOT / str(path))]
    kg_artifacts = browser.get("kg_artifacts", [])
    bad_artifacts = [str(item.get("href", "")) for item in kg_artifacts if not item.get("ok")]
    visible_record_ids = {str(item) for item in browser.get("visible_record_ids", [])}
    missing_visible_records = sorted(REQUIRED_SCENARIO_RECORD_IDS - visible_record_ids)
    search_results_visible = browser.get("search_results_visible") is True
    passed = (
        len(screenshots) >= 4
        and not missing
        and len(kg_artifacts) >= 4
        and not bad_artifacts
        and search_results_visible
        and not missing_visible_records
    )
    detail = (
        f"{len(screenshots)} screenshots, {len(kg_artifacts)} KG artifacts, and {len(visible_record_ids)} visible search records verified"
        if passed
        else f"missing_screenshots={missing}, bad_artifacts={bad_artifacts}, search_results_visible={search_results_visible}, missing_visible_records={missing_visible_records}"
    )
    return GateCheck("browser visual evidence", passed, detail)


def extract_markdown_code_span_paths(text: str) -> list[str]:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    paths: list[str] = []
    for value in re.findall(r"`([^`\n]+)`", text):
        item = value.strip()
        if not item or item.startswith(COMMAND_PREFIXES):
            continue
        if any(fragment in item for fragment in COMMAND_FRAGMENTS):
            continue
        if "/" in item or "\\" in item or item.endswith((".md", ".json", ".jsonl", ".html", ".svg", ".csv", ".png")):
            paths.append(item.replace("\\", "/"))
    return paths


def check_claim_evidence_matrix() -> GateCheck:
    if not CLAIM_MATRIX.exists():
        return GateCheck("claim-evidence matrix", False, "07_评审主张证据矩阵.md missing")
    text = CLAIM_MATRIX.read_text(encoding="utf-8")
    missing_terms = sorted(term for term in REQUIRED_CLAIM_MATRIX_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    missing = missing_terms + missing_paths
    return GateCheck(
        "claim-evidence matrix",
        not missing,
        f"award claims mapped to evidence, commands, and boundaries; {len(evidence_paths)} evidence links verified"
        if not missing
        else f"missing terms or evidence paths: {', '.join(missing)}",
    )


def check_acceptance_checklist() -> GateCheck:
    if not ACCEPTANCE_CHECKLIST.exists():
        return GateCheck("acceptance checklist", False, "06_结项验收清单.md missing")
    text = ACCEPTANCE_CHECKLIST.read_text(encoding="utf-8")
    missing_terms = sorted(term for term in REQUIRED_ACCEPTANCE_CHECKLIST_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    missing = missing_terms + missing_paths
    return GateCheck(
        "acceptance checklist",
        not missing,
        f"submission materials, acceptance steps, offline fallback, boundaries, and conclusion verified; {len(evidence_paths)} evidence links verified"
        if not missing
        else f"missing acceptance checklist terms or evidence paths: {', '.join(missing)}",
    )


def check_award_self_eval() -> GateCheck:
    if not AWARD_SELF_EVAL.exists():
        return GateCheck("special-prize rubric self-assessment", False, "08_特等奖评审自评表.md missing")
    text = AWARD_SELF_EVAL.read_text(encoding="utf-8")
    missing_terms = sorted(term for term in REQUIRED_AWARD_SELF_EVAL_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    missing = missing_terms + missing_paths
    return GateCheck(
        "special-prize rubric self-assessment",
        not missing,
        f"public Tsinghua rubric dimensions mapped to evidence; {len(evidence_paths)} evidence links verified"
        if not missing
        else f"missing terms or evidence paths: {', '.join(missing)}",
    )


def check_official_rubric_alignment() -> GateCheck:
    failures: list[str] = []
    required_files = [OFFICIAL_RUBRIC_ALIGNMENT_MD, OFFICIAL_RUBRIC_ALIGNMENT_JSON]
    missing_files = [path.relative_to(REPO_ROOT).as_posix() for path in required_files if not nonempty(path)]
    if missing_files:
        return GateCheck("official rubric alignment", False, f"missing or empty: {missing_files}")

    try:
        payload = load_json(OFFICIAL_RUBRIC_ALIGNMENT_JSON)
    except (OSError, json.JSONDecodeError) as exc:
        return GateCheck("official rubric alignment", False, f"invalid official rubric json: {exc}")
    markdown = OFFICIAL_RUBRIC_ALIGNMENT_MD.read_text(encoding="utf-8")

    if payload.get("report_type") != "challenge_cup_official_rubric_alignment":
        failures.append(f"report_type={payload.get('report_type')}")

    official_sources = payload.get("official_sources", [])
    if not isinstance(official_sources, list):
        failures.append("official_sources missing")
        official_sources = []
    official_source_count = payload.get("official_source_count")
    if official_source_count != len(official_sources):
        failures.append(
            f"official_source_count mismatch: {official_source_count} != {len(official_sources)}"
        )
    if len(official_sources) < OFFICIAL_RUBRIC_MIN_SOURCE_COUNT:
        failures.append(f"official_sources below {OFFICIAL_RUBRIC_MIN_SOURCE_COUNT}: {len(official_sources)}")

    source_ids: set[str] = set()
    duplicate_source_ids: set[str] = set()
    for index, item in enumerate(official_sources, start=1):
        if not isinstance(item, dict):
            failures.append(f"official_sources[{index}] invalid")
            continue
        source_id = str(item.get("source_id", "")).strip()
        if not source_id:
            failures.append(f"official_sources[{index}].source_id missing")
        elif source_id in source_ids:
            duplicate_source_ids.add(source_id)
        else:
            source_ids.add(source_id)
        if not str(item.get("title", "")).strip():
            failures.append(f"official_sources[{index}].title missing")
        url = str(item.get("url", "")).strip()
        if not url.startswith("https://"):
            failures.append(f"official_sources[{index}].url must start with https://")
        claims = item.get("claims")
        if not isinstance(claims, list) or not claims:
            failures.append(f"official_sources[{index}].claims missing")
        if not is_iso_date(item.get("checked_at")):
            failures.append(f"official_sources[{index}].checked_at must be YYYY-MM-DD")
    if duplicate_source_ids:
        failures.append(f"duplicate official source ids: {sorted(duplicate_source_ids)}")
    if OFFICIAL_RUBRIC_LATEST_SOURCE_ID not in source_ids:
        failures.append(f"missing latest official source: {OFFICIAL_RUBRIC_LATEST_SOURCE_ID}")
    missing_benchmark_source_ids = sorted(set(OFFICIAL_RUBRIC_BENCHMARK_SOURCE_IDS) - source_ids)
    if missing_benchmark_source_ids:
        failures.append(f"missing department benchmark official sources: {missing_benchmark_source_ids}")

    dimensions = payload.get("dimensions", {})
    if not isinstance(dimensions, dict):
        failures.append("dimensions missing")
        dimensions = {}
    missing_dimensions = sorted(OFFICIAL_RUBRIC_REQUIRED_DIMENSIONS - set(dimensions))
    if missing_dimensions:
        failures.append(f"missing required dimensions: {missing_dimensions}")

    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    evidence_paths: set[str] = set()
    for dimension_key, dimension in dimensions.items():
        if not isinstance(dimension, dict):
            failures.append(f"{dimension_key}: dimension invalid")
            continue
        dimension_source_ids = [str(item) for item in dimension.get("official_source_ids", [])]
        if not dimension_source_ids:
            failures.append(f"{dimension_key}: official_source_ids missing")
        missing_source_refs = sorted(source_id for source_id in dimension_source_ids if source_id not in source_ids)
        if missing_source_refs:
            failures.append(f"{dimension_key}: unknown official_source_ids {missing_source_refs}")

        dimension_evidence = dimension.get("evidence_files", [])
        if not isinstance(dimension_evidence, list) or not dimension_evidence:
            failures.append(f"{dimension_key}: evidence_files missing")
            continue
        for value in dimension_evidence:
            relative = str(value).strip()
            if not relative:
                failures.append(f"{dimension_key}: empty evidence file")
                continue
            posix = PurePosixPath(relative)
            if relative.startswith(("http://", "https://")):
                failures.append(f"{dimension_key}: evidence_files must be repo paths, not URLs: {relative}")
                continue
            if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
                failures.append(f"{dimension_key}: unsafe evidence path: {relative}")
                continue
            if relative in OFFICIAL_RUBRIC_REQUIRED_PATHS:
                failures.append(f"{dimension_key}: evidence_files self-reference official rubric: {relative}")
                continue
            evidence_paths.add(relative)
            if relative != self_report and not nonempty(REPO_ROOT / relative):
                failures.append(f"{dimension_key}: evidence path missing or empty: {relative}")

    special_prize_policy = payload.get("special_prize_policy", {})
    if not isinstance(special_prize_policy, dict):
        failures.append("special_prize_policy missing")
        special_prize_policy = {}
    if special_prize_policy.get("max_special_prize_count") != 7:
        failures.append(f"max_special_prize_count={special_prize_policy.get('max_special_prize_count')}")
    if special_prize_policy.get("latest_public_result_source_id") != OFFICIAL_RUBRIC_LATEST_SOURCE_ID:
        failures.append(
            f"latest_public_result_source_id={special_prize_policy.get('latest_public_result_source_id')}"
        )
    if special_prize_policy.get("may_be_vacant") is not True:
        failures.append(f"may_be_vacant={special_prize_policy.get('may_be_vacant')}")
    policy_source_ids = {str(item) for item in special_prize_policy.get("source_ids", [])}
    if not set(OFFICIAL_RUBRIC_BENCHMARK_SOURCE_IDS).issubset(policy_source_ids):
        failures.append(f"special_prize_policy.source_ids missing benchmark sources: {sorted(policy_source_ids)}")

    benchmarks = payload.get("special_prize_competition_benchmarks")
    if not isinstance(benchmarks, dict):
        failures.append("special_prize_competition_benchmarks missing")
        benchmarks = {}
    else:
        if benchmarks.get("current_as_of") != OFFICIAL_RUBRIC_CURRENT_AS_OF:
            failures.append(f"special_prize_competition_benchmarks.current_as_of={benchmarks.get('current_as_of')}")
        if benchmarks.get("benchmark_source_ids") != OFFICIAL_RUBRIC_BENCHMARK_SOURCE_IDS:
            failures.append(
                f"special_prize_competition_benchmarks.benchmark_source_ids={benchmarks.get('benchmark_source_ids')}"
            )
        if benchmarks.get("no_award_guarantee") is not True:
            failures.append(f"special_prize_competition_benchmarks.no_award_guarantee={benchmarks.get('no_award_guarantee')}")
        department_benchmarks = benchmarks.get("department_benchmarks")
        if not isinstance(department_benchmarks, list):
            failures.append("special_prize_competition_benchmarks.department_benchmarks missing")
            department_benchmarks = []
        benchmark_by_source: dict[str, dict[str, Any]] = {}
        for item in department_benchmarks:
            if not isinstance(item, dict):
                failures.append("special_prize_competition_benchmarks.department_benchmarks item invalid")
                continue
            source_id = str(item.get("source_id", "")).strip()
            if not source_id:
                failures.append("special_prize_competition_benchmarks.department_benchmarks.source_id missing")
                continue
            benchmark_by_source[source_id] = item
            if source_id not in source_ids:
                failures.append(f"special_prize_competition_benchmarks unknown source_id: {source_id}")
            for field in ("department", "rank_signal", "benchmark_signal", "project_implication"):
                if not has_value(item.get(field)):
                    failures.append(f"special_prize_competition_benchmarks.{source_id}.{field} missing")
        expected_department_ids = set(OFFICIAL_RUBRIC_DEPARTMENT_BENCHMARK_SPECS)
        if set(benchmark_by_source) != expected_department_ids:
            failures.append(
                "special_prize_competition_benchmarks.department_benchmark_ids="
                f"{sorted(benchmark_by_source)}"
            )
        for source_id, expected in OFFICIAL_RUBRIC_DEPARTMENT_BENCHMARK_SPECS.items():
            item = benchmark_by_source.get(source_id, {})
            if item.get("rank_signal") != expected["rank_signal"]:
                failures.append(
                    f"special_prize_competition_benchmarks.{source_id}.rank_signal={item.get('rank_signal')}"
                )
            if item.get("reported_awards") != expected["reported_awards"]:
                failures.append(
                    f"special_prize_competition_benchmarks.{source_id}.reported_awards={item.get('reported_awards')}"
                )
        interpretation = benchmarks.get("interpretation")
        if not isinstance(interpretation, list) or len(interpretation) < 2:
            failures.append("special_prize_competition_benchmarks.interpretation below 2")

    source_lock = payload.get("official_source_lock")
    if not isinstance(source_lock, dict):
        failures.append("official_source_lock missing")
        source_lock = {}
    else:
        if not is_iso_date(source_lock.get("current_as_of")):
            failures.append(f"official_source_lock.current_as_of={source_lock.get('current_as_of')}")
        if source_lock.get("current_as_of") != OFFICIAL_RUBRIC_CURRENT_AS_OF:
            failures.append(f"official_source_lock.current_as_of={source_lock.get('current_as_of')}")

        latest = source_lock.get("latest_public_result")
        if not isinstance(latest, dict):
            failures.append("official_source_lock.latest_public_result missing")
            latest = {}
        expected_latest = {
            "source_id": OFFICIAL_RUBRIC_LATEST_SOURCE_ID,
            "source_url": "https://www.tsinghua.edu.cn/info/1177/125861.htm",
            "published_date": "2026-04-29",
            "final_defense_date": "2026-04-25",
            "award_ceremony_date": "2026-04-26",
            "registration_count": 337,
            "exhibition_work_count_min": 200,
        }
        for key, expected in expected_latest.items():
            if latest.get(key) != expected:
                failures.append(f"official_source_lock.latest_public_result.{key}={latest.get(key)}")
        finalists = latest.get("school_finalist_counts")
        if finalists != {"undergraduate": 173, "graduate": 9}:
            failures.append(f"official_source_lock.latest_public_result.school_finalist_counts={finalists}")
        awards = latest.get("main_track_award_counts")
        expected_awards = {
            "total": 114,
            "special_prize": 7,
            "first_prize": 11,
            "second_prize": 32,
            "third_prize": 64,
        }
        if awards != expected_awards:
            failures.append(f"official_source_lock.latest_public_result.main_track_award_counts={awards}")
        anchor_terms = latest.get("anchor_terms")
        if not isinstance(anchor_terms, list) or len(anchor_terms) < 5:
            failures.append("official_source_lock.latest_public_result.anchor_terms below 5")

        dimension_lock = source_lock.get("rubric_dimension_lock")
        if not isinstance(dimension_lock, dict):
            failures.append("official_source_lock.rubric_dimension_lock missing")
            dimension_lock = {}
        dimension_source_ids = {str(item) for item in dimension_lock.get("source_ids", [])}
        if not {"tsinghua_37th_2019", "tsinghua_39th_2021"}.issubset(dimension_source_ids):
            failures.append(f"official_source_lock.rubric_dimension_lock.source_ids={sorted(dimension_source_ids)}")
        locked_dimensions = [str(item) for item in dimension_lock.get("required_dimensions", [])]
        expected_locked_dimensions = [
            "academic_or_practical_value",
            "innovation",
            "completion",
            "defense_performance",
        ]
        if locked_dimensions != expected_locked_dimensions:
            failures.append(f"official_source_lock.rubric_dimension_lock.required_dimensions={locked_dimensions}")

        recency_policy = source_lock.get("recency_policy")
        if not isinstance(recency_policy, dict):
            failures.append("official_source_lock.recency_policy missing")
            recency_policy = {}
        if recency_policy.get("must_recheck_before_final_submission") is not True:
            failures.append(
                "official_source_lock.recency_policy.must_recheck_before_final_submission="
                f"{recency_policy.get('must_recheck_before_final_submission')}"
            )
        if recency_policy.get("no_award_guarantee") is not True:
            failures.append(
                f"official_source_lock.recency_policy.no_award_guarantee={recency_policy.get('no_award_guarantee')}"
            )

    integrity_rules = payload.get("integrity_rules", {})
    if not isinstance(integrity_rules, dict):
        failures.append("integrity_rules missing")
        integrity_rules = {}
    if integrity_rules.get("no_award_guarantee") is not True:
        failures.append(f"no_award_guarantee={integrity_rules.get('no_award_guarantee')}")

    missing_terms = sorted(term for term in OFFICIAL_RUBRIC_REQUIRED_TERMS if term not in markdown)
    if missing_terms:
        failures.append(f"markdown missing terms: {missing_terms}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    required_manifest_missing = sorted(path for path in OFFICIAL_RUBRIC_REQUIRED_PATHS if path not in manifest_evidence)
    if required_manifest_missing:
        failures.append(f"missing manifest entries: {required_manifest_missing}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    excluded_hashes = {str(item) for item in hashes.get("excluded_self_reports", [])}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(
        path for path in OFFICIAL_RUBRIC_REQUIRED_PATHS if path not in excluded_hashes and path not in hashed_paths
    )
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {"included_files": []}
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(path for path in OFFICIAL_RUBRIC_REQUIRED_PATHS if path not in archived_paths)
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in OFFICIAL_RUBRIC_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(OFFICIAL_RUBRIC_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked official rubric files: {untracked}")
    if dirty:
        failures.append(f"dirty official rubric files: {dirty}")

    return GateCheck(
        "official rubric alignment",
        not failures,
        (
            f"{len(official_sources)} official sources, {len(dimensions)} rubric dimensions, "
            f"and {len(evidence_paths)} project evidence paths verified"
        )
        if not failures
        else "; ".join(failures),
    )


def check_judge_objection_response_matrix() -> GateCheck:
    failures: list[str] = []
    required_files = [JUDGE_OBJECTION_MATRIX_MD, JUDGE_OBJECTION_MATRIX_JSON]
    missing_files = [path.name + " missing" for path in required_files if not nonempty(path)]
    if missing_files:
        return GateCheck("judge objection response matrix", False, ", ".join(missing_files))

    try:
        payload = load_json(JUDGE_OBJECTION_MATRIX_JSON)
    except (OSError, json.JSONDecodeError) as exc:
        return GateCheck("judge objection response matrix", False, f"invalid objection matrix json: {exc}")
    markdown = JUDGE_OBJECTION_MATRIX_MD.read_text(encoding="utf-8")

    if payload.get("report_type") != "challenge_cup_judge_objection_response_matrix":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "ready_for_judge_objection_drill_no_external_claims":
        failures.append(f"status={payload.get('status')}")
    if payload.get("completion_claim_allowed") is not False:
        failures.append(f"completion_claim_allowed={payload.get('completion_claim_allowed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")

    response_rules = payload.get("response_rules", {})
    if not isinstance(response_rules, dict):
        failures.append("response_rules missing")
        response_rules = {}
    if response_rules.get("max_answer_seconds") != 30:
        failures.append(f"max_answer_seconds={response_rules.get('max_answer_seconds')}")
    if response_rules.get("must_cite_evidence") is not True:
        failures.append(f"must_cite_evidence={response_rules.get('must_cite_evidence')}")
    if response_rules.get("must_state_boundary_when_external_validation_is_missing") is not True:
        failures.append(
            "must_state_boundary_when_external_validation_is_missing="
            f"{response_rules.get('must_state_boundary_when_external_validation_is_missing')}"
        )
    if response_rules.get("no_award_guarantee") is not True:
        failures.append(f"no_award_guarantee={response_rules.get('no_award_guarantee')}")
    if response_rules.get("no_fake_external_validation") is not True:
        failures.append(f"no_fake_external_validation={response_rules.get('no_fake_external_validation')}")

    objections = payload.get("objections")
    if not isinstance(objections, list):
        failures.append("objections missing")
        objections = []
    if len(objections) < len(JUDGE_OBJECTION_MATRIX_REQUIRED_IDS):
        failures.append(
            f"objection count below {len(JUDGE_OBJECTION_MATRIX_REQUIRED_IDS)}: {len(objections)}"
        )
    objection_ids = {str(item.get("objection_id", "")) for item in objections if isinstance(item, dict)}
    missing_ids = sorted(JUDGE_OBJECTION_MATRIX_REQUIRED_IDS - objection_ids)
    if missing_ids:
        failures.append(f"missing objection ids: {missing_ids}")

    evidence_paths: set[str] = set()
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    for index, item in enumerate(objections, start=1):
        if not isinstance(item, dict):
            failures.append(f"objections[{index}] invalid")
            continue
        objection_id = str(item.get("objection_id", f"objections[{index}]"))
        if item.get("severity") not in {"P0", "P1"}:
            failures.append(f"{objection_id}: severity={item.get('severity')}")
        if item.get("answer_time_limit_seconds", 999) > 30:
            failures.append(f"{objection_id}: answer_time_limit_seconds={item.get('answer_time_limit_seconds')}")
        for field in (
            "judge_objection",
            "one_sentence_answer",
            "fallback_if_challenged",
            "forbidden_overclaim",
            "rubric_dimensions",
        ):
            if not has_value(item.get(field)):
                failures.append(f"{objection_id}: {field} missing")

        item_evidence = item.get("evidence_files", [])
        if not isinstance(item_evidence, list) or not item_evidence:
            failures.append(f"{objection_id}: evidence_files missing")
            continue
        for value in item_evidence:
            relative = str(value).strip()
            if not relative:
                failures.append(f"{objection_id}: empty evidence file")
                continue
            posix = PurePosixPath(relative)
            if relative.startswith(("http://", "https://")):
                failures.append(f"{objection_id}: evidence_files must be repo paths, not URLs: {relative}")
                continue
            if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
                failures.append(f"{objection_id}: unsafe evidence path: {relative}")
                continue
            if not relative.startswith(("docs/", "evaluation/")):
                failures.append(f"{objection_id}: evidence path outside allowed scope: {relative}")
                continue
            evidence_paths.add(relative)
            if relative != self_report and not nonempty(REPO_ROOT / relative):
                failures.append(f"{objection_id}: evidence path missing or empty: {relative}")

    closure_answers = [
        str(item.get("one_sentence_answer", ""))
        for item in objections
        if isinstance(item, dict) and item.get("objection_id") == "OJ-10-project-closure"
    ]
    if closure_answers:
        expected_gate_phrase = f"{CURRENT_READINESS_GATE_COUNT} readiness gates"
        stale_gate_phrases = [
            phrase
            for phrase in re.findall(r"\b\d+\s+readiness gates\b", "\n".join(closure_answers + [markdown]))
            if phrase != expected_gate_phrase
        ]
        if expected_gate_phrase not in closure_answers[0]:
            failures.append(
                f"stale readiness gate count in OJ-10-project-closure: expected {expected_gate_phrase}"
            )
        if stale_gate_phrases:
            failures.append(f"stale readiness gate count phrases: {sorted(set(stale_gate_phrases))}")

    payload_evidence = {str(item) for item in payload.get("evidence_files", [])}
    missing_payload_evidence = sorted(
        path for path in JUDGE_OBJECTION_MATRIX_REQUIRED_PATHS if path not in payload_evidence
    )
    if missing_payload_evidence:
        failures.append(f"payload evidence_files missing: {missing_payload_evidence}")

    missing_terms = sorted(term for term in JUDGE_OBJECTION_MATRIX_REQUIRED_TERMS if term not in markdown)
    if missing_terms:
        failures.append(f"markdown missing terms: {missing_terms}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    missing_manifest = sorted(path for path in JUDGE_OBJECTION_MATRIX_REQUIRED_PATHS if path not in manifest_evidence)
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(path for path in JUDGE_OBJECTION_MATRIX_REQUIRED_PATHS if path not in hashed_paths)
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(path for path in JUDGE_OBJECTION_MATRIX_REQUIRED_PATHS if path not in archived_paths)
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in JUDGE_OBJECTION_MATRIX_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(JUDGE_OBJECTION_MATRIX_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked judge objection matrix files: {untracked}")
    if dirty:
        failures.append(f"dirty judge objection matrix files: {dirty}")

    return GateCheck(
        "judge objection response matrix",
        not failures,
        f"{len(objections)} objection responses, 30-second boundary, and {len(evidence_paths)} evidence links verified"
        if not failures
        else "; ".join(failures),
    )


def check_special_prize_readiness_dashboard() -> GateCheck:
    failures: list[str] = []
    required_files = [SPECIAL_PRIZE_READINESS_DASHBOARD_MD, SPECIAL_PRIZE_READINESS_DASHBOARD_JSON]
    missing_files = [path.relative_to(REPO_ROOT).as_posix() for path in required_files if not nonempty(path)]
    if missing_files:
        return GateCheck("special prize readiness dashboard", False, f"missing or empty: {missing_files}")

    try:
        payload = load_json(SPECIAL_PRIZE_READINESS_DASHBOARD_JSON)
    except (OSError, json.JSONDecodeError) as exc:
        return GateCheck("special prize readiness dashboard", False, f"invalid dashboard json: {exc}")
    markdown = SPECIAL_PRIZE_READINESS_DASHBOARD_MD.read_text(encoding="utf-8")

    if payload.get("report_type") != "challenge_cup_special_prize_readiness_dashboard":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "special_prize_review_ready_with_external_evidence_gaps":
        failures.append(f"status={payload.get('status')}")
    if payload.get("no_award_guarantee") is not True:
        failures.append(f"no_award_guarantee={payload.get('no_award_guarantee')}")
    if payload.get("completion_claim_allowed") is not False:
        failures.append(f"completion_claim_allowed={payload.get('completion_claim_allowed')}")
    if payload.get("can_mark_goal_complete") is not False:
        failures.append(f"can_mark_goal_complete={payload.get('can_mark_goal_complete')}")

    official_basis = payload.get("official_basis", {})
    if not isinstance(official_basis, dict):
        failures.append("official_basis missing")
        official_basis = {}
    if official_basis.get("latest_public_result_source_id") != OFFICIAL_RUBRIC_LATEST_SOURCE_ID:
        failures.append(f"latest_public_result_source_id={official_basis.get('latest_public_result_source_id')}")
    if official_basis.get("max_special_prize_count") != 7:
        failures.append(f"max_special_prize_count={official_basis.get('max_special_prize_count')}")
    if official_basis.get("may_be_vacant") is not True:
        failures.append(f"may_be_vacant={official_basis.get('may_be_vacant')}")

    readiness = payload.get("rubric_readiness")
    if not isinstance(readiness, list):
        failures.append("rubric_readiness missing")
        readiness = []
    dimension_keys = {str(item.get("dimension_key", "")) for item in readiness if isinstance(item, dict)}
    missing_dimensions = sorted(OFFICIAL_RUBRIC_REQUIRED_DIMENSIONS - dimension_keys)
    if missing_dimensions:
        failures.append(f"missing rubric dimensions: {missing_dimensions}")
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    for item in readiness:
        if not isinstance(item, dict):
            failures.append("rubric_readiness item invalid")
            continue
        key = str(item.get("dimension_key", ""))
        if item.get("readiness_level") not in {"strong_evidence_linked", "ready_with_external_gap"}:
            failures.append(f"{key}: readiness_level={item.get('readiness_level')}")
        for field in ("judge_message", "defense_action", "evidence_files"):
            if not has_value(item.get(field)):
                failures.append(f"{key}: {field} missing")
        for relative in [str(value) for value in item.get("evidence_files", [])]:
            if relative != self_report and not nonempty(REPO_ROOT / relative):
                failures.append(f"{key}: evidence file missing or empty: {relative}")

    top_risks = payload.get("top_risks")
    if not isinstance(top_risks, list):
        failures.append("top_risks missing")
        top_risks = []
    risk_ids = {str(item.get("risk_id", "")) for item in top_risks if isinstance(item, dict)}
    if risk_ids != {"expert_feedback", "timed_rehearsal", "award_overclaim"}:
        failures.append(f"top_risks={sorted(risk_ids)}")

    next_action_files = [str(item) for item in payload.get("next_action_files", [])]
    if "docs/challenge_cup/reproducibility/hard_evidence_action_pack.md" not in next_action_files:
        failures.append("next_action_files missing hard evidence action pack")
    missing_action_files = sorted(relative for relative in next_action_files if not nonempty(REPO_ROOT / relative))
    if missing_action_files:
        failures.append(f"next_action_files missing or empty: {missing_action_files}")

    verification_commands = {str(item) for item in payload.get("verification_commands", [])}
    if "python scripts/check_challenge_cup_goal_completion.py" not in verification_commands:
        failures.append("verification_commands missing goal completion check")

    for term in (
        "Special Prize Readiness Dashboard",
        "special_prize_review_ready_with_external_evidence_gaps",
        "no_award_guarantee=True",
        "expert_feedback",
        "timed_rehearsal",
    ):
        if term not in markdown:
            failures.append(f"markdown missing {term}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    missing_manifest = sorted(path for path in SPECIAL_PRIZE_DASHBOARD_REQUIRED_PATHS if path not in manifest_evidence)
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(path for path in SPECIAL_PRIZE_DASHBOARD_REQUIRED_PATHS if path not in hashed_paths)
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(path for path in SPECIAL_PRIZE_DASHBOARD_REQUIRED_PATHS if path not in archived_paths)
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in SPECIAL_PRIZE_DASHBOARD_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(SPECIAL_PRIZE_DASHBOARD_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked special prize dashboard files: {untracked}")
    if dirty:
        failures.append(f"dirty special prize dashboard files: {dirty}")

    return GateCheck(
        "special prize readiness dashboard",
        not failures,
        f"{len(readiness)} rubric dimensions, 3 top risks, and no-award boundary verified"
        if not failures
        else "; ".join(failures),
    )


def check_expert_review_index() -> GateCheck:
    if not EXPERT_REVIEW_INDEX.exists():
        return GateCheck("expert review index", False, "09_专家快速审阅索引.md missing")
    text = EXPERT_REVIEW_INDEX.read_text(encoding="utf-8")
    missing_terms = sorted(term for term in REQUIRED_EXPERT_REVIEW_INDEX_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    missing = missing_terms + missing_paths
    return GateCheck(
        "expert review index",
        not missing,
        f"judge-facing review path maps claims, commands, and boundaries; {len(evidence_paths)} evidence links verified"
        if not missing
        else f"missing terms or evidence paths: {', '.join(missing)}",
    )


def check_judge_briefing_card() -> GateCheck:
    if not JUDGE_BRIEFING_CARD.exists():
        return GateCheck("judge briefing card", False, "13_评委现场速览卡.md missing")
    text = JUDGE_BRIEFING_CARD.read_text(encoding="utf-8")
    card_relative = JUDGE_BRIEFING_CARD.relative_to(REPO_ROOT).as_posix()
    missing_terms = sorted(term for term in REQUIRED_JUDGE_BRIEFING_CARD_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    failures = missing_terms + missing_paths

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    if card_relative not in manifest_evidence:
        failures.append(f"missing manifest entries: ['{card_relative}']")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    if card_relative not in hashed_paths:
        failures.append(f"missing hash entries: ['{card_relative}']")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and card_relative not in archived_paths:
        failures.append(f"missing archive entries: ['{card_relative}']")

    tracked = git_tracked_paths()
    dirty = sorted(git_dirty_paths([card_relative]))
    if card_relative not in tracked:
        failures.append(f"untracked judge briefing card: {card_relative}")
    if dirty:
        failures.append(f"dirty judge briefing card: {dirty}")
    return GateCheck(
        "judge briefing card",
        not failures,
        f"one-page judge leave-behind, evidence anchors, and no-overclaim boundaries verified; {len(evidence_paths)} evidence links verified"
        if not failures
        else f"missing terms, evidence paths, or package links: {', '.join(failures)}",
    )


def check_onsite_defense_runbook() -> GateCheck:
    if not ONSITE_DEFENSE_RUNBOOK.exists():
        return GateCheck("onsite defense runbook", False, "14_现场答辩操作Runbook.md missing")
    text = ONSITE_DEFENSE_RUNBOOK.read_text(encoding="utf-8")
    runbook_relative = ONSITE_DEFENSE_RUNBOOK.relative_to(REPO_ROOT).as_posix()
    missing_terms = sorted(term for term in REQUIRED_ONSITE_DEFENSE_RUNBOOK_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    failures = missing_terms + missing_paths

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    if runbook_relative not in manifest_evidence:
        failures.append(f"missing manifest entries: ['{runbook_relative}']")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    if runbook_relative not in hashed_paths:
        failures.append(f"missing hash entries: ['{runbook_relative}']")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and runbook_relative not in archived_paths:
        failures.append(f"missing archive entries: ['{runbook_relative}']")

    tracked = git_tracked_paths()
    dirty = sorted(git_dirty_paths([runbook_relative]))
    if runbook_relative not in tracked:
        failures.append(f"untracked onsite defense runbook: {runbook_relative}")
    if dirty:
        failures.append(f"dirty onsite defense runbook: {dirty}")

    return GateCheck(
        "onsite defense runbook",
        not failures,
        f"preflight, tab order, offline fallback, Q&A evidence map, and no-live-debugging boundary verified; {len(evidence_paths)} evidence links verified"
        if not failures
        else f"missing terms, evidence paths, or package links: {', '.join(failures)}",
    )


def check_project_handoff_checklist() -> GateCheck:
    if not PROJECT_HANDOFF_CHECKLIST.exists():
        return GateCheck("project handoff checklist", False, "15_结项交付移交清单.md missing")
    text = PROJECT_HANDOFF_CHECKLIST.read_text(encoding="utf-8")
    checklist_relative = PROJECT_HANDOFF_CHECKLIST.relative_to(REPO_ROOT).as_posix()
    missing_terms = sorted(term for term in REQUIRED_PROJECT_HANDOFF_CHECKLIST_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    failures = missing_terms + missing_paths

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    if checklist_relative not in manifest_evidence:
        failures.append(f"missing manifest entries: ['{checklist_relative}']")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    if checklist_relative not in hashed_paths:
        failures.append(f"missing hash entries: ['{checklist_relative}']")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and checklist_relative not in archived_paths:
        failures.append(f"missing archive entries: ['{checklist_relative}']")

    tracked = git_tracked_paths()
    dirty = sorted(git_dirty_paths([checklist_relative]))
    if checklist_relative not in tracked:
        failures.append(f"untracked project handoff checklist: {checklist_relative}")
    if dirty:
        failures.append(f"dirty project handoff checklist: {dirty}")

    return GateCheck(
        "project handoff checklist",
        not failures,
        f"handoff scope, signoff, verification commands, archive boundary, and external hard-evidence follow-up verified; {len(evidence_paths)} evidence links verified"
        if not failures
        else f"missing terms, evidence paths, or package links: {', '.join(failures)}",
    )


def check_defense_qa_remediation_ledger() -> GateCheck:
    if not DEFENSE_QA_REMEDIATION_LEDGER.exists():
        return GateCheck("defense q&a remediation ledger", False, "16_现场问辩记录与整改台账.md missing")
    text = DEFENSE_QA_REMEDIATION_LEDGER.read_text(encoding="utf-8")
    ledger_relative = DEFENSE_QA_REMEDIATION_LEDGER.relative_to(REPO_ROOT).as_posix()
    missing_terms = sorted(term for term in REQUIRED_DEFENSE_QA_REMEDIATION_LEDGER_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    failures = missing_terms + missing_paths

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    if ledger_relative not in manifest_evidence:
        failures.append(f"missing manifest entries: ['{ledger_relative}']")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    if ledger_relative not in hashed_paths:
        failures.append(f"missing hash entries: ['{ledger_relative}']")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and ledger_relative not in archived_paths:
        failures.append(f"missing archive entries: ['{ledger_relative}']")

    tracked = git_tracked_paths()
    dirty = sorted(git_dirty_paths([ledger_relative]))
    if ledger_relative not in tracked:
        failures.append(f"untracked defense q&a remediation ledger: {ledger_relative}")
    if dirty:
        failures.append(f"dirty defense q&a remediation ledger: {dirty}")

    return GateCheck(
        "defense q&a remediation ledger",
        not failures,
        f"judge-question capture, evidence-gap mapping, remediation closure, and no-fake boundary verified; {len(evidence_paths)} evidence links verified"
        if not failures
        else f"missing terms, evidence paths, or package links: {', '.join(failures)}",
    )


def check_review_risk_response_plan() -> GateCheck:
    if not REVIEW_RISK_RESPONSE_PLAN.exists():
        return GateCheck("review risk response plan", False, "17_评审风险控制与应急预案.md missing")
    text = REVIEW_RISK_RESPONSE_PLAN.read_text(encoding="utf-8")
    plan_relative = REVIEW_RISK_RESPONSE_PLAN.relative_to(REPO_ROOT).as_posix()
    missing_terms = sorted(term for term in REQUIRED_REVIEW_RISK_RESPONSE_PLAN_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    failures = missing_terms + missing_paths

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    if plan_relative not in manifest_evidence:
        failures.append(f"missing manifest entries: ['{plan_relative}']")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    if plan_relative not in hashed_paths:
        failures.append(f"missing hash entries: ['{plan_relative}']")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and plan_relative not in archived_paths:
        failures.append(f"missing archive entries: ['{plan_relative}']")

    tracked = git_tracked_paths()
    dirty = sorted(git_dirty_paths([plan_relative]))
    if plan_relative not in tracked:
        failures.append(f"untracked review risk response plan: {plan_relative}")
    if dirty:
        failures.append(f"dirty review risk response plan: {dirty}")

    return GateCheck(
        "review risk response plan",
        not failures,
        f"risk levels, triggers, response actions, evidence anchors, closure standards, and no-overclaim boundaries verified; {len(evidence_paths)} evidence links verified"
        if not failures
        else f"missing terms, evidence paths, or package links: {', '.join(failures)}",
    )


def check_special_prize_scoring_drill() -> GateCheck:
    if not SPECIAL_PRIZE_SCORING_DRILL.exists():
        return GateCheck("special prize scoring drill", False, "18_特等奖打分模拟与整改清单.md missing")
    text = SPECIAL_PRIZE_SCORING_DRILL.read_text(encoding="utf-8")
    drill_relative = SPECIAL_PRIZE_SCORING_DRILL.relative_to(REPO_ROOT).as_posix()
    missing_terms = sorted(term for term in REQUIRED_SPECIAL_PRIZE_SCORING_DRILL_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    failures = missing_terms + missing_paths

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    if drill_relative not in manifest_evidence:
        failures.append(f"missing manifest entries: ['{drill_relative}']")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    if drill_relative not in hashed_paths:
        failures.append(f"missing hash entries: ['{drill_relative}']")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and drill_relative not in archived_paths:
        failures.append(f"missing archive entries: ['{drill_relative}']")

    tracked = git_tracked_paths()
    dirty = sorted(git_dirty_paths([drill_relative]))
    if drill_relative not in tracked:
        failures.append(f"untracked special prize scoring drill: {drill_relative}")
    if dirty:
        failures.append(f"dirty special prize scoring drill: {dirty}")

    return GateCheck(
        "special prize scoring drill",
        not failures,
        f"official rubric snapshot, scoring simulation, deduction risks, remediation actions, and closure evidence verified; {len(evidence_paths)} evidence links verified"
        if not failures
        else f"missing terms, evidence paths, or package links: {', '.join(failures)}",
    )


def check_poster_booth_qa_pack() -> GateCheck:
    if not POSTER_BOOTH_QA_PACK.exists():
        return GateCheck("poster booth q&a pack", False, "19_作品展墙报问辩与展台脚本.md missing")
    text = POSTER_BOOTH_QA_PACK.read_text(encoding="utf-8")
    pack_relative = POSTER_BOOTH_QA_PACK.relative_to(REPO_ROOT).as_posix()
    missing_terms = sorted(term for term in REQUIRED_POSTER_BOOTH_QA_PACK_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    failures = missing_terms + missing_paths

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    if pack_relative not in manifest_evidence:
        failures.append(f"missing manifest entries: ['{pack_relative}']")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    if pack_relative not in hashed_paths:
        failures.append(f"missing hash entries: ['{pack_relative}']")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and pack_relative not in archived_paths:
        failures.append(f"missing archive entries: ['{pack_relative}']")

    tracked = git_tracked_paths()
    dirty = sorted(git_dirty_paths([pack_relative]))
    if pack_relative not in tracked:
        failures.append(f"untracked poster booth q&a pack: {pack_relative}")
    if dirty:
        failures.append(f"dirty poster booth q&a pack: {dirty}")

    return GateCheck(
        "poster booth q&a pack",
        not failures,
        f"poster structure, QR path, booth script, interactive Q&A, offline fallback, and no-overclaim boundary verified; {len(evidence_paths)} evidence links verified"
        if not failures
        else f"missing terms, evidence paths, or package links: {', '.join(failures)}",
    )


def check_commercialization_roadmap() -> GateCheck:
    if not COMMERCIALIZATION_ROADMAP.exists():
        return GateCheck("commercialization roadmap", False, "20_成果转化与持续迭代路线图.md missing")
    text = COMMERCIALIZATION_ROADMAP.read_text(encoding="utf-8")
    roadmap_relative = COMMERCIALIZATION_ROADMAP.relative_to(REPO_ROOT).as_posix()
    missing_terms = sorted(term for term in REQUIRED_COMMERCIALIZATION_ROADMAP_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    failures = missing_terms + missing_paths

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    if roadmap_relative not in manifest_evidence:
        failures.append(f"missing manifest entries: ['{roadmap_relative}']")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    if roadmap_relative not in hashed_paths:
        failures.append(f"missing hash entries: ['{roadmap_relative}']")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and roadmap_relative not in archived_paths:
        failures.append(f"missing archive entries: ['{roadmap_relative}']")

    tracked = git_tracked_paths()
    dirty = sorted(git_dirty_paths([roadmap_relative]))
    if roadmap_relative not in tracked:
        failures.append(f"untracked commercialization roadmap: {roadmap_relative}")
    if dirty:
        failures.append(f"dirty commercialization roadmap: {dirty}")

    return GateCheck(
        "commercialization roadmap",
        not failures,
        f"strategic value, pilot path, milestones, acceptance metrics, governance, and no-commercial-overclaim boundary verified; {len(evidence_paths)} evidence links verified"
        if not failures
        else f"missing terms, evidence paths, or package links: {', '.join(failures)}",
    )


def check_poster_board_asset() -> GateCheck:
    if not POSTER_BOARD_HTML.exists():
        return GateCheck("poster board asset", False, "poster/challenge_cup_a0_poster.html missing")
    text = POSTER_BOARD_HTML.read_text(encoding="utf-8")
    poster_relative = POSTER_BOARD_HTML.relative_to(REPO_ROOT).as_posix()
    missing_terms = sorted(term for term in REQUIRED_POSTER_BOARD_HTML_TERMS if term not in text)
    failures = missing_terms

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    if poster_relative not in manifest_evidence:
        failures.append(f"missing manifest entries: ['{poster_relative}']")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    if poster_relative not in hashed_paths:
        failures.append(f"missing hash entries: ['{poster_relative}']")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and poster_relative not in archived_paths:
        failures.append(f"missing archive entries: ['{poster_relative}']")

    tracked = git_tracked_paths()
    dirty = sorted(git_dirty_paths([poster_relative]))
    if poster_relative not in tracked:
        failures.append(f"untracked poster board asset: {poster_relative}")
    if dirty:
        failures.append(f"dirty poster board asset: {dirty}")

    return GateCheck(
        "poster board asset",
        not failures,
        "printable A0 HTML poster, QR/material links, evidence anchors, and no-overclaim boundaries verified"
        if not failures
        else f"missing terms, evidence paths, or package links: {', '.join(failures)}",
    )


def check_defense_control_console() -> GateCheck:
    if not DEFENSE_CONTROL_CONSOLE.exists():
        return GateCheck("defense control console", False, "defense_console/index.html missing")
    text = DEFENSE_CONTROL_CONSOLE.read_text(encoding="utf-8")
    console_relative = DEFENSE_CONTROL_CONSOLE.relative_to(REPO_ROOT).as_posix()
    failures = sorted(term for term in REQUIRED_DEFENSE_CONTROL_CONSOLE_TERMS if term not in text)
    mojibake_hits = [marker for marker in DEFENSE_CONTROL_CONSOLE_MOJIBAKE_MARKERS if marker in text]
    if mojibake_hits:
        failures.append(f"mojibake markers in defense console: {', '.join(mojibake_hits)}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    if console_relative not in manifest_evidence:
        failures.append(f"missing manifest entries: ['{console_relative}']")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    if console_relative not in hashed_paths:
        failures.append(f"missing hash entries: ['{console_relative}']")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and console_relative not in archived_paths:
        failures.append(f"missing archive entries: ['{console_relative}']")

    tracked = git_tracked_paths()
    dirty = sorted(git_dirty_paths([console_relative]))
    if console_relative not in tracked:
        failures.append(f"untracked defense control console: {console_relative}")
    if dirty:
        failures.append(f"dirty defense control console: {dirty}")

    return GateCheck(
        "defense control console",
        not failures,
        "offline defense console, timer, launchpad, fallback, and no-overclaim boundaries verified"
        if not failures
        else f"missing terms, evidence paths, or package links: {', '.join(failures)}",
    )


def check_ip_open_source_compliance() -> GateCheck:
    if not IP_OPEN_SOURCE_COMPLIANCE.exists():
        return GateCheck("ip and open-source compliance", False, "21_知识产权与开源合规说明.md missing")
    text = IP_OPEN_SOURCE_COMPLIANCE.read_text(encoding="utf-8")
    compliance_relative = IP_OPEN_SOURCE_COMPLIANCE.relative_to(REPO_ROOT).as_posix()
    missing_terms = sorted(term for term in REQUIRED_IP_OPEN_SOURCE_COMPLIANCE_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    failures = missing_terms + missing_paths

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    if compliance_relative not in manifest_evidence:
        failures.append(f"missing manifest entries: ['{compliance_relative}']")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    if compliance_relative not in hashed_paths:
        failures.append(f"missing hash entries: ['{compliance_relative}']")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and compliance_relative not in archived_paths:
        failures.append(f"missing archive entries: ['{compliance_relative}']")

    tracked = git_tracked_paths()
    dirty = sorted(git_dirty_paths([compliance_relative]))
    if compliance_relative not in tracked:
        failures.append(f"untracked ip/open-source compliance doc: {compliance_relative}")
    if dirty:
        failures.append(f"dirty ip/open-source compliance doc: {dirty}")

    return GateCheck(
        "ip and open-source compliance",
        not failures,
        f"originality, third-party dependency, open-source license, data authorization, citation, and no-overclaim boundaries verified; {len(evidence_paths)} evidence links verified"
        if not failures
        else f"missing terms, evidence paths, or package links: {', '.join(failures)}",
    )


def check_local_baseline_differentiation_evidence() -> GateCheck:
    if not LOCAL_BASELINE_DIFFERENTIATION.exists():
        return GateCheck("local baseline differentiation evidence", False, "22_同类方案对比与创新性证据卡.md missing")
    text = LOCAL_BASELINE_DIFFERENTIATION.read_text(encoding="utf-8")
    baseline_relative = LOCAL_BASELINE_DIFFERENTIATION.relative_to(REPO_ROOT).as_posix()
    missing_terms = sorted(term for term in REQUIRED_LOCAL_BASELINE_DIFFERENTIATION_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    failures = missing_terms + missing_paths

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    if baseline_relative not in manifest_evidence:
        failures.append(f"missing manifest entries: ['{baseline_relative}']")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    if baseline_relative not in hashed_paths:
        failures.append(f"missing hash entries: ['{baseline_relative}']")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and baseline_relative not in archived_paths:
        failures.append(f"missing archive entries: ['{baseline_relative}']")

    tracked = git_tracked_paths()
    dirty = sorted(git_dirty_paths([baseline_relative]))
    if baseline_relative not in tracked:
        failures.append(f"untracked local baseline differentiation evidence: {baseline_relative}")
    if dirty:
        failures.append(f"dirty local baseline differentiation evidence: {dirty}")

    return GateCheck(
        "local baseline differentiation evidence",
        not failures,
        f"baseline comparison, GraphRAG subset, GT-07 application anchor, and no-overclaim boundaries verified; {len(evidence_paths)} evidence links verified"
        if not failures
        else f"missing terms, evidence paths, or package links: {', '.join(failures)}",
    )


def check_final_submission_handoff_sheet() -> GateCheck:
    if not FINAL_SUBMISSION_HANDOFF.exists():
        return GateCheck("final submission handoff sheet", False, "23_终审提交总目录与签收页.md missing")
    text = FINAL_SUBMISSION_HANDOFF.read_text(encoding="utf-8")
    handoff_relative = FINAL_SUBMISSION_HANDOFF.relative_to(REPO_ROOT).as_posix()
    missing_terms = sorted(term for term in REQUIRED_FINAL_SUBMISSION_HANDOFF_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    failures = missing_terms + missing_paths

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    if handoff_relative not in manifest_evidence:
        failures.append(f"missing manifest entries: ['{handoff_relative}']")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    if handoff_relative not in hashed_paths:
        failures.append(f"missing hash entries: ['{handoff_relative}']")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and handoff_relative not in archived_paths:
        failures.append(f"missing archive entries: ['{handoff_relative}']")

    tracked = git_tracked_paths()
    dirty = sorted(git_dirty_paths([handoff_relative]))
    if handoff_relative not in tracked:
        failures.append(f"untracked final submission handoff sheet: {handoff_relative}")
    if dirty:
        failures.append(f"dirty final submission handoff sheet: {dirty}")

    return GateCheck(
        "final submission handoff sheet",
        not failures,
        f"final review directory, signoff fields, verification commands, external hard-evidence boundary, and no-award-guarantee language verified; {len(evidence_paths)} evidence links verified"
        if not failures
        else f"missing terms, evidence paths, or package links: {', '.join(failures)}",
    )


def check_defense_rehearsal_card() -> GateCheck:
    if not DEFENSE_REHEARSAL_CARD.exists():
        return GateCheck("defense rehearsal pack", False, "10_答辩攻防与彩排卡.md missing")
    text = DEFENSE_REHEARSAL_CARD.read_text(encoding="utf-8")
    missing_terms = sorted(term for term in REQUIRED_DEFENSE_REHEARSAL_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    missing = missing_terms + missing_paths
    return GateCheck(
        "defense rehearsal pack",
        not missing,
        f"timed defense script, killer questions, and boundaries mapped to evidence; {len(evidence_paths)} evidence links verified"
        if not missing
        else f"missing terms or evidence paths: {', '.join(missing)}",
    )


def check_defense_rehearsal_scorecard() -> GateCheck:
    failures: list[str] = []
    if not DEFENSE_REHEARSAL_SCORECARD_JSON.exists():
        return GateCheck(
            "defense rehearsal scorecard",
            False,
            f"{DEFENSE_REHEARSAL_SCORECARD_JSON.relative_to(REPO_ROOT)} missing",
        )
    if not DEFENSE_REHEARSAL_SCORECARD_MD.exists():
        return GateCheck(
            "defense rehearsal scorecard",
            False,
            f"{DEFENSE_REHEARSAL_SCORECARD_MD.relative_to(REPO_ROOT)} missing",
        )

    payload = load_json(DEFENSE_REHEARSAL_SCORECARD_JSON)
    markdown = DEFENSE_REHEARSAL_SCORECARD_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_defense_rehearsal_scorecard":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "ready_for_timed_rehearsal":
        failures.append(f"status={payload.get('status')}")
    if payload.get("boundary") != DEFENSE_REHEARSAL_SCORECARD_BOUNDARY:
        failures.append("boundary mismatch")

    timing = payload.get("timing_targets", {})
    for key, expected in DEFENSE_REHEARSAL_TIMING_TARGETS.items():
        actual = timing.get(key) if isinstance(timing, dict) else None
        if int(actual or -1) != expected:
            failures.append(f"{key}={actual}, expected={expected}")
    if payload.get("opening_required_points") != ["问题", "方法", "完成度", "边界"]:
        failures.append("opening_required_points mismatch")

    demo_timeline = payload.get("demo_timeline", [])
    if not isinstance(demo_timeline, list) or len(demo_timeline) != 5:
        failures.append("demo_timeline must contain exactly 5 steps")
    else:
        missing_demo_anchors = [
            str(item.get("timebox", index))
            for index, item in enumerate(demo_timeline, start=1)
            if not item.get("evidence_anchor")
        ]
        if missing_demo_anchors:
            failures.append(f"demo_timeline missing evidence_anchor: {missing_demo_anchors}")

    killer_questions = payload.get("killer_questions", [])
    if not isinstance(killer_questions, list) or len(killer_questions) < 5:
        failures.append("killer_questions below 5")
        killer_questions = []
    for index, item in enumerate(killer_questions, start=1):
        seconds = int(item.get("answer_seconds") or 999)
        if seconds > DEFENSE_REHEARSAL_TIMING_TARGETS["killer_question_seconds"]:
            failures.append(f"killer_question {index} answer_seconds={seconds}")
        if not item.get("evidence_anchors"):
            failures.append(f"killer_question {index} missing evidence_anchors")

    boundaries = {str(item) for item in payload.get("no_overclaim_boundaries", [])}
    if len(boundaries) < 4:
        failures.append("no_overclaim_boundaries below 4")
    if "不把 readiness gate 说成获奖保证" not in boundaries:
        failures.append("missing readiness gate no-overclaim boundary")
    if int(payload.get("minimum_evidence_anchor_count") or 0) < 12:
        failures.append("minimum_evidence_anchor_count below 12")

    evidence_files = {str(item) for item in payload.get("evidence_files", [])}
    missing_required_evidence = sorted(DEFENSE_REHEARSAL_REQUIRED_EVIDENCE_FILES - evidence_files)
    if missing_required_evidence:
        failures.append(f"missing evidence_files: {missing_required_evidence}")
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_evidence_paths = sorted(
        path for path in evidence_files if path != self_report and not nonempty(REPO_ROOT / path)
    )
    if missing_evidence_paths:
        failures.append(f"evidence path missing or empty: {missing_evidence_paths}")

    missing_markdown_terms = sorted(
        term for term in (DEFENSE_REHEARSAL_MARKDOWN_TERMS | {DEFENSE_REHEARSAL_SCORECARD_BOUNDARY}) if term not in markdown
    )
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    return GateCheck(
        "defense rehearsal scorecard",
        not failures,
        (
            f"{len(demo_timeline)} timed demo steps, {len(killer_questions)} killer questions, "
            f"{len(evidence_files)} evidence files"
        )
        if not failures
        else "; ".join(failures),
    )


def check_defense_rehearsal_result_packet() -> GateCheck:
    failures: list[str] = []
    if not DEFENSE_REHEARSAL_RESULT_PACKET_JSON.exists():
        return GateCheck(
            "defense rehearsal result packet",
            False,
            f"{DEFENSE_REHEARSAL_RESULT_PACKET_JSON.relative_to(REPO_ROOT)} missing",
        )
    if not DEFENSE_REHEARSAL_RESULT_PACKET_MD.exists():
        return GateCheck(
            "defense rehearsal result packet",
            False,
            f"{DEFENSE_REHEARSAL_RESULT_PACKET_MD.relative_to(REPO_ROOT)} missing",
        )

    payload = load_json(DEFENSE_REHEARSAL_RESULT_PACKET_JSON)
    markdown = DEFENSE_REHEARSAL_RESULT_PACKET_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_defense_rehearsal_result_packet":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "ready_to_record_actual_rehearsal":
        failures.append(f"status={payload.get('status')}")
    if payload.get("actual_rehearsal_completed") is not False:
        failures.append(f"actual_rehearsal_completed={payload.get('actual_rehearsal_completed')}")
    if payload.get("boundary") != DEFENSE_REHEARSAL_RESULT_PACKET_BOUNDARY:
        failures.append("boundary mismatch")
    if payload.get("timing_targets") != DEFENSE_REHEARSAL_TIMING_TARGETS:
        failures.append("timing_targets mismatch")
    if payload.get("pass_fail_rules") != DEFENSE_REHEARSAL_RESULT_PASS_FAIL_RULES:
        failures.append("pass_fail_rules mismatch")
    if payload.get("required_archive_evidence_types") != DEFENSE_REHEARSAL_RESULT_REQUIRED_ARCHIVE_TYPES:
        failures.append("required_archive_evidence_types mismatch")

    template = payload.get("result_template", {})
    if not isinstance(template, dict):
        failures.append("result_template missing")
        template = {}
    for key in ("opening_actual_seconds", "demo_actual_seconds", "offline_fallback_actual_seconds"):
        if template.get(key) is not None:
            failures.append(f"{key} must remain unrecorded")
    if template.get("overall_result") != "not_recorded":
        failures.append(f"overall_result={template.get('overall_result')}")
    killer_results = template.get("killer_question_results", [])
    if not isinstance(killer_results, list) or len(killer_results) != 5:
        failures.append("killer_question_results must contain exactly 5 templates")
        killer_results = []
    for index, item in enumerate(killer_results, start=1):
        if not isinstance(item, dict):
            failures.append(f"killer_question_results[{index}] invalid")
            continue
        if item.get("actual_seconds") is not None:
            failures.append(f"killer_question_results[{index}].actual_seconds must remain unrecorded")

    evidence_files = {str(item) for item in payload.get("evidence_files", [])}
    missing_required_evidence = sorted(DEFENSE_REHEARSAL_RESULT_REQUIRED_EVIDENCE_FILES - evidence_files)
    if missing_required_evidence:
        failures.append(f"missing evidence_files: {missing_required_evidence}")
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_evidence_paths = sorted(
        path for path in evidence_files if path != self_report and not nonempty(REPO_ROOT / path)
    )
    if missing_evidence_paths:
        failures.append(f"evidence path missing or empty: {missing_evidence_paths}")

    missing_markdown_terms = sorted(
        term
        for term in (DEFENSE_REHEARSAL_RESULT_MARKDOWN_TERMS | {DEFENSE_REHEARSAL_RESULT_PACKET_BOUNDARY})
        if term not in markdown
    )
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    return GateCheck(
        "defense rehearsal result packet",
        not failures,
        f"{len(killer_results)} killer-question templates, {len(evidence_files)} evidence files, no actual result claimed"
        if not failures
        else "; ".join(failures),
    )


def check_expert_feedback_request_packet() -> GateCheck:
    failures: list[str] = []
    if not EXPERT_FEEDBACK_REQUEST_PACKET_JSON.exists():
        return GateCheck(
            "expert feedback request packet",
            False,
            f"{EXPERT_FEEDBACK_REQUEST_PACKET_JSON.relative_to(REPO_ROOT)} missing",
        )
    if not EXPERT_FEEDBACK_REQUEST_PACKET_MD.exists():
        return GateCheck(
            "expert feedback request packet",
            False,
            f"{EXPERT_FEEDBACK_REQUEST_PACKET_MD.relative_to(REPO_ROOT)} missing",
        )

    payload = load_json(EXPERT_FEEDBACK_REQUEST_PACKET_JSON)
    markdown = EXPERT_FEEDBACK_REQUEST_PACKET_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_expert_feedback_request_packet":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "ready_to_send":
        failures.append(f"status={payload.get('status')}")
    if payload.get("no_external_feedback_claimed") is not True:
        failures.append(f"no_external_feedback_claimed={payload.get('no_external_feedback_claimed')}")
    if payload.get("boundary") != EXPERT_FEEDBACK_REQUEST_PACKET_BOUNDARY:
        failures.append("boundary mismatch")
    if payload.get("review_dimensions") != EXPERT_FEEDBACK_REQUEST_DIMENSIONS:
        failures.append("review_dimensions mismatch")
    if payload.get("required_archive_evidence_types") != EXPERT_FEEDBACK_REQUIRED_ARCHIVE_TYPES:
        failures.append("required_archive_evidence_types mismatch")
    if len(payload.get("recipient_roles", [])) < 3:
        failures.append("recipient_roles below 3")
    if len(payload.get("review_questions", [])) < 8:
        failures.append("review_questions below 8")
    if int(payload.get("minimum_evidence_file_count") or 0) < 10:
        failures.append("minimum_evidence_file_count below 10")

    sendable = payload.get("sendable_message", {})
    body = str(sendable.get("body", ""))
    attachments = [str(item) for item in sendable.get("attachments", [])]
    if not sendable.get("subject"):
        failures.append("sendable_message.subject missing")
    if "待真实反馈归档" not in body:
        failures.append("sendable_message.body missing pending-feedback boundary")
    for forbidden in ("已经获得专家认可", "通过专家验证"):
        if forbidden in body:
            failures.append(f"sendable_message.body overclaims: {forbidden}")
    if len(attachments) < 5:
        failures.append("sendable_message.attachments below 5")

    evidence_files = {str(item) for item in payload.get("evidence_files", [])}
    missing_required_evidence = sorted(EXPERT_FEEDBACK_REQUEST_REQUIRED_EVIDENCE_FILES - evidence_files)
    if missing_required_evidence:
        failures.append(f"missing evidence_files: {missing_required_evidence}")
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_evidence_paths = sorted(
        path for path in evidence_files if path != self_report and not nonempty(REPO_ROOT / path)
    )
    if missing_evidence_paths:
        failures.append(f"evidence path missing or empty: {missing_evidence_paths}")

    missing_markdown_terms = sorted(
        term
        for term in (EXPERT_FEEDBACK_REQUEST_MARKDOWN_TERMS | {EXPERT_FEEDBACK_REQUEST_PACKET_BOUNDARY})
        if term not in markdown
    )
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    return GateCheck(
        "expert feedback request packet",
        not failures,
        f"{len(payload.get('recipient_roles', []))} recipient roles, {len(payload.get('review_questions', []))} review questions, {len(evidence_files)} evidence files"
        if not failures
        else "; ".join(failures),
    )


def validate_expert_feedback_outreach_metadata(relative: str, payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if payload.get("outreach_type") != "expert_feedback_request":
        failures.append(f"{relative}: outreach_type={payload.get('outreach_type')}")
    for field in (
        "recipient_alias",
        "recipient_role",
        "channel",
        "sent_date",
        "status",
        "request_source_path",
        "requested_review_dimensions",
        "requested_attachment_paths",
    ):
        if not has_value(payload.get(field)):
            failures.append(f"{relative}: {field} missing")
    channel = str(payload.get("channel", ""))
    if channel and channel not in EXPERT_FEEDBACK_OUTREACH_CHANNELS:
        failures.append(f"{relative}: channel={channel}")
    status = str(payload.get("status", ""))
    if status and status not in EXPERT_FEEDBACK_OUTREACH_METADATA_STATUSES:
        failures.append(f"{relative}: status={status}")
    if payload.get("no_external_feedback_claimed") is not True:
        failures.append(f"{relative}: no_external_feedback_claimed={payload.get('no_external_feedback_claimed')}")
    if payload.get("does_not_satisfy_hard_evidence") is not True:
        failures.append(
            f"{relative}: does_not_satisfy_hard_evidence={payload.get('does_not_satisfy_hard_evidence')}"
        )
    if not is_iso_date(payload.get("sent_date")):
        failures.append(f"{relative}: sent_date must be YYYY-MM-DD")
    followup_due = payload.get("followup_due_date")
    if has_value(followup_due) and not is_iso_date(followup_due):
        failures.append(f"{relative}: followup_due_date must be YYYY-MM-DD")
    failures.extend(validate_source_path(relative, payload, "request_source_path"))

    dimensions = payload.get("requested_review_dimensions")
    if not isinstance(dimensions, list) or len(dimensions) < HARD_EVIDENCE_MIN_REVIEW_DIMENSIONS:
        failures.append(f"{relative}: requested_review_dimensions below {HARD_EVIDENCE_MIN_REVIEW_DIMENSIONS}")

    attachments = payload.get("requested_attachment_paths")
    if not isinstance(attachments, list) or not attachments:
        failures.append(f"{relative}: requested_attachment_paths missing")
    else:
        for attachment in attachments:
            attachment_path = str(attachment)
            posix = PurePosixPath(attachment_path)
            if posix.is_absolute() or ".." in posix.parts or "\\" in attachment_path:
                failures.append(f"{relative}: requested_attachment_paths unsafe: {attachment_path}")
            elif not nonempty(REPO_ROOT / attachment_path):
                failures.append(f"{relative}: requested_attachment_paths missing or empty: {attachment_path}")
    return failures


def check_expert_feedback_outreach_ledger() -> GateCheck:
    failures: list[str] = []
    required_files = [
        EXPERT_FEEDBACK_OUTREACH_LEDGER_MD,
        EXPERT_FEEDBACK_OUTREACH_LEDGER_JSON,
        EXPERT_FEEDBACK_OUTREACH_README,
    ]
    missing_files = [path.relative_to(REPO_ROOT).as_posix() for path in required_files if not nonempty(path)]
    if missing_files:
        return GateCheck("expert feedback outreach ledger", False, f"missing or empty: {missing_files}")

    payload = load_json(EXPERT_FEEDBACK_OUTREACH_LEDGER_JSON)
    markdown = EXPERT_FEEDBACK_OUTREACH_LEDGER_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_expert_feedback_outreach_ledger":
        failures.append(f"report_type={payload.get('report_type')}")
    status = str(payload.get("status", ""))
    if status not in EXPERT_FEEDBACK_OUTREACH_STATUSES:
        failures.append(f"status={status}")
    if payload.get("no_external_feedback_claimed") is not True:
        failures.append(f"no_external_feedback_claimed={payload.get('no_external_feedback_claimed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")
    if payload.get("boundary") != EXPERT_FEEDBACK_OUTREACH_LEDGER_BOUNDARY:
        failures.append("boundary mismatch")

    outreach_files = [str(item) for item in payload.get("outreach_files", [])]
    metadata_files = [relative for relative in outreach_files if relative.lower().endswith(".json")]
    if int(payload.get("outreach_record_count") or 0) != len(outreach_files):
        failures.append("outreach_record_count mismatch")
    if int(payload.get("metadata_record_count") or 0) != len(metadata_files):
        failures.append("metadata_record_count mismatch")
    if outreach_files and status != "outreach_recorded_awaiting_response":
        failures.append(f"status={status} while outreach files exist")
    if not outreach_files and status != "ready_to_send_no_outreach_recorded":
        failures.append(f"status={status} while no outreach files exist")

    unsafe_paths: list[str] = []
    missing_paths: list[str] = []
    metadata_failures: list[str] = []
    for relative in outreach_files:
        posix = PurePosixPath(relative)
        if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
            unsafe_paths.append(relative)
            continue
        path = REPO_ROOT / relative
        if not nonempty(path):
            missing_paths.append(relative)
            continue
        if relative.lower().endswith(".json"):
            try:
                metadata = load_json(path)
            except (OSError, json.JSONDecodeError) as exc:
                metadata_failures.append(f"{relative}: invalid metadata json: {exc}")
                continue
            metadata_failures.extend(validate_expert_feedback_outreach_metadata(relative, metadata))
    if unsafe_paths:
        failures.append(f"unsafe outreach paths: {unsafe_paths}")
    if missing_paths:
        failures.append(f"outreach files missing or empty: {missing_paths}")
    failures.extend(metadata_failures)

    missing_markdown_terms = sorted(
        term
        for term in (
            "Expert Feedback Outreach Ledger",
            "do not prove expert approval",
            EXPERT_FEEDBACK_OUTREACH_LEDGER_BOUNDARY,
        )
        if term not in markdown
    )
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    required_and_outreach = EXPERT_FEEDBACK_OUTREACH_REQUIRED_PATHS + outreach_files
    missing_manifest = sorted(path for path in required_and_outreach if path not in manifest_evidence)
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(path for path in required_and_outreach if path not in hashed_paths)
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(path for path in required_and_outreach if path not in archived_paths)
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in required_and_outreach if path not in tracked]
    dirty = sorted(git_dirty_paths(required_and_outreach))
    if untracked:
        failures.append(f"untracked expert outreach files: {untracked}")
    if dirty:
        failures.append(f"dirty expert outreach files: {dirty}")

    return GateCheck(
        "expert feedback outreach ledger",
        not failures,
        f"outreach ledger schema, boundary, {len(outreach_files)} outreach files, and manifest/hash/archive links verified"
        if not failures
        else "; ".join(failures),
    )


def validate_timed_rehearsal_schedule_metadata(relative: str, payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if payload.get("schedule_type") != "timed_rehearsal_schedule":
        failures.append(f"{relative}: schedule_type={payload.get('schedule_type')}")
    for field in (
        "scheduled_date",
        "observer",
        "venue_or_channel",
        "status",
        "schedule_source_path",
        "planned_timing_targets",
        "checklist_items",
        "required_hard_evidence_after_run",
    ):
        if not has_value(payload.get(field)):
            failures.append(f"{relative}: {field} missing")
    status = str(payload.get("status", ""))
    if status and status not in TIMED_REHEARSAL_SCHEDULE_METADATA_STATUSES:
        failures.append(f"{relative}: status={status}")
    if payload.get("no_timed_rehearsal_claimed") is not True:
        failures.append(f"{relative}: no_timed_rehearsal_claimed={payload.get('no_timed_rehearsal_claimed')}")
    if payload.get("does_not_satisfy_hard_evidence") is not True:
        failures.append(
            f"{relative}: does_not_satisfy_hard_evidence={payload.get('does_not_satisfy_hard_evidence')}"
        )
    if payload.get("actual_rehearsal_completed") is True:
        failures.append(f"{relative}: actual_rehearsal_completed overclaims schedule evidence")
    if not is_iso_date(payload.get("scheduled_date")):
        failures.append(f"{relative}: scheduled_date must be YYYY-MM-DD")
    failures.extend(validate_source_path(relative, payload, "schedule_source_path"))

    planned = payload.get("planned_timing_targets")
    if not isinstance(planned, dict):
        failures.append(f"{relative}: planned_timing_targets invalid")
    else:
        for field, limit in TIMED_REHEARSAL_SCHEDULE_TIMING_LIMITS.items():
            actual = numeric_value(planned.get(field))
            if actual is None:
                failures.append(f"{relative}: planned_timing_targets.{field} must be numeric")
                continue
            if field == "killer_question_count":
                if int(actual) != limit:
                    failures.append(f"{relative}: planned_timing_targets.{field} must be {limit}")
            elif actual > limit:
                failures.append(f"{relative}: planned_timing_targets.{field}={actual:g} exceeds {limit}")
            elif actual <= 0:
                failures.append(f"{relative}: planned_timing_targets.{field} must be positive")

    checklist = payload.get("checklist_items")
    if not isinstance(checklist, list) or len(checklist) < 4:
        failures.append(f"{relative}: checklist_items below 4")

    required_hard_evidence = payload.get("required_hard_evidence_after_run")
    if not isinstance(required_hard_evidence, list) or len(required_hard_evidence) < 4:
        failures.append(f"{relative}: required_hard_evidence_after_run below 4")

    for hard_evidence_field in (
        "opening_actual_seconds",
        "demo_actual_seconds",
        "offline_fallback_actual_seconds",
        "killer_question_results",
        "recording_or_timer_source_path",
    ):
        if has_value(payload.get(hard_evidence_field)):
            failures.append(f"{relative}: {hard_evidence_field} belongs to timed_rehearsal hard evidence")
    return failures


def check_timed_rehearsal_schedule_ledger() -> GateCheck:
    failures: list[str] = []
    required_files = [
        TIMED_REHEARSAL_SCHEDULE_LEDGER_MD,
        TIMED_REHEARSAL_SCHEDULE_LEDGER_JSON,
        TIMED_REHEARSAL_SCHEDULE_README,
    ]
    missing_files = [path.relative_to(REPO_ROOT).as_posix() for path in required_files if not nonempty(path)]
    if missing_files:
        return GateCheck("timed rehearsal schedule ledger", False, f"missing or empty: {missing_files}")

    payload = load_json(TIMED_REHEARSAL_SCHEDULE_LEDGER_JSON)
    markdown = TIMED_REHEARSAL_SCHEDULE_LEDGER_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_timed_rehearsal_schedule_ledger":
        failures.append(f"report_type={payload.get('report_type')}")
    status = str(payload.get("status", ""))
    if status not in TIMED_REHEARSAL_SCHEDULE_STATUSES:
        failures.append(f"status={status}")
    if payload.get("no_timed_rehearsal_claimed") is not True:
        failures.append(f"no_timed_rehearsal_claimed={payload.get('no_timed_rehearsal_claimed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")
    if payload.get("boundary") != TIMED_REHEARSAL_SCHEDULE_LEDGER_BOUNDARY:
        failures.append("boundary mismatch")

    schedule_files = [str(item) for item in payload.get("schedule_files", [])]
    metadata_files = [relative for relative in schedule_files if relative.lower().endswith(".json")]
    if int(payload.get("schedule_record_count") or 0) != len(schedule_files):
        failures.append("schedule_record_count mismatch")
    if int(payload.get("metadata_record_count") or 0) != len(metadata_files):
        failures.append("metadata_record_count mismatch")
    if schedule_files and status != "rehearsal_scheduled_awaiting_run":
        failures.append(f"status={status} while schedule files exist")
    if not schedule_files and status != "ready_to_schedule_no_rehearsal_recorded":
        failures.append(f"status={status} while no schedule files exist")

    unsafe_paths: list[str] = []
    missing_paths: list[str] = []
    metadata_failures: list[str] = []
    for relative in schedule_files:
        posix = PurePosixPath(relative)
        if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
            unsafe_paths.append(relative)
            continue
        path = REPO_ROOT / relative
        if not nonempty(path):
            missing_paths.append(relative)
            continue
        if relative.lower().endswith(".json"):
            try:
                metadata = load_json(path)
            except (OSError, json.JSONDecodeError) as exc:
                metadata_failures.append(f"{relative}: invalid metadata json: {exc}")
                continue
            metadata_failures.extend(validate_timed_rehearsal_schedule_metadata(relative, metadata))
    if unsafe_paths:
        failures.append(f"unsafe schedule paths: {unsafe_paths}")
    if missing_paths:
        failures.append(f"schedule files missing or empty: {missing_paths}")
    failures.extend(metadata_failures)

    missing_markdown_terms = sorted(
        term
        for term in (
            "Timed Rehearsal Schedule Ledger",
            "do not prove a timed rehearsal was completed",
            TIMED_REHEARSAL_SCHEDULE_LEDGER_BOUNDARY,
        )
        if term not in markdown
    )
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    required_and_schedule = TIMED_REHEARSAL_SCHEDULE_REQUIRED_PATHS + schedule_files
    missing_manifest = sorted(path for path in required_and_schedule if path not in manifest_evidence)
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(path for path in required_and_schedule if path not in hashed_paths)
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(path for path in required_and_schedule if path not in archived_paths)
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in required_and_schedule if path not in tracked]
    dirty = sorted(git_dirty_paths(required_and_schedule))
    if untracked:
        failures.append(f"untracked timed rehearsal schedule files: {untracked}")
    if dirty:
        failures.append(f"dirty timed rehearsal schedule files: {dirty}")

    return GateCheck(
        "timed rehearsal schedule ledger",
        not failures,
        f"schedule ledger schema, boundary, {len(schedule_files)} schedule files, and manifest/hash/archive links verified"
        if not failures
        else "; ".join(failures),
    )


def validate_hard_evidence_closure_stream(stream: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    category = str(stream.get("category", ""))
    if category not in HARD_EVIDENCE_REQUIRED_CATEGORIES:
        failures.append(f"invalid category={category}")
    for field in (
        "closure_phase",
        "target_min_count",
        "current_collected_count",
        "required_source_examples",
        "ready_to_execute_commands",
        "post_collection_commands",
        "acceptance_gate",
    ):
        if not has_value(stream.get(field)):
            failures.append(f"{category or 'stream'}: {field} missing")
    if int(stream.get("target_min_count") or 0) < 1:
        failures.append(f"{category}: target_min_count below 1")
    if int(stream.get("current_collected_count") or 0) != 0:
        failures.append(f"{category}: current_collected_count should remain 0 until real hard evidence exists")
    examples = stream.get("required_source_examples")
    if not isinstance(examples, list) or len(examples) < 4:
        failures.append(f"{category}: required_source_examples below 4")
    ready_commands = stream.get("ready_to_execute_commands")
    if not isinstance(ready_commands, list) or not ready_commands:
        failures.append(f"{category}: ready_to_execute_commands missing")
    else:
        joined = "\n".join(str(item) for item in ready_commands)
        if category == "expert_feedback":
            if "preflight_challenge_cup_hard_evidence.py expert_feedback" not in joined:
                failures.append(
                    f"{category}: ready_to_execute_commands missing preflight_challenge_cup_hard_evidence.py expert_feedback"
                )
            if "record_challenge_cup_hard_evidence.py expert_feedback" not in joined:
                failures.append(f"{category}: ready_to_execute_commands missing expert hard-evidence recorder")
            if "--confirm-real-feedback" not in joined:
                failures.append(f"{category}: ready_to_execute_commands missing --confirm-real-feedback")
        if category == "timed_rehearsal":
            if "preflight_challenge_cup_hard_evidence.py timed_rehearsal" not in joined:
                failures.append(
                    f"{category}: ready_to_execute_commands missing preflight_challenge_cup_hard_evidence.py timed_rehearsal"
                )
            if "run_challenge_cup_timed_rehearsal.py" not in joined:
                failures.append(f"{category}: ready_to_execute_commands missing timed rehearsal runner")
            if "--confirm-real-rehearsal" not in joined:
                failures.append(f"{category}: ready_to_execute_commands missing --confirm-real-rehearsal")
    post_commands = stream.get("post_collection_commands")
    if not isinstance(post_commands, list) or "python scripts/check_challenge_cup_goal_completion.py" not in {
        str(item) for item in post_commands
    }:
        failures.append(f"{category}: post_collection_commands missing goal completion check")
    acceptance_gate = str(stream.get("acceptance_gate", ""))
    if category and category not in acceptance_gate:
        failures.append(f"{category}: acceptance_gate does not reference category")
    return failures


def check_hard_evidence_closure_board() -> GateCheck:
    failures: list[str] = []
    required_files = [
        HARD_EVIDENCE_CLOSURE_BOARD_MD,
        HARD_EVIDENCE_CLOSURE_BOARD_JSON,
    ]
    missing_files = [path.relative_to(REPO_ROOT).as_posix() for path in required_files if not nonempty(path)]
    if missing_files:
        return GateCheck("hard evidence closure board", False, f"missing or empty: {missing_files}")

    payload = load_json(HARD_EVIDENCE_CLOSURE_BOARD_JSON)
    markdown = HARD_EVIDENCE_CLOSURE_BOARD_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_hard_evidence_closure_board":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "awaiting_real_external_evidence_closure":
        failures.append(f"status={payload.get('status')}")
    if payload.get("no_completion_claimed") is not True:
        failures.append(f"no_completion_claimed={payload.get('no_completion_claimed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")
    if payload.get("boundary") != HARD_EVIDENCE_CLOSURE_BOARD_BOUNDARY:
        failures.append("boundary mismatch")
    required_before = [str(item) for item in payload.get("required_before_goal_completion", [])]
    if required_before != ["expert_feedback", "timed_rehearsal"]:
        failures.append(f"required_before_goal_completion={required_before}")
    if int(payload.get("blocker_count") or 0) != 2:
        failures.append(f"blocker_count={payload.get('blocker_count')}")

    streams = payload.get("closure_streams")
    if not isinstance(streams, list):
        failures.append("closure_streams missing")
        streams = []
    categories = {str(item.get("category", "")) for item in streams if isinstance(item, dict)}
    missing_categories = sorted(HARD_EVIDENCE_REQUIRED_CATEGORIES - categories)
    if missing_categories:
        failures.append(f"missing closure streams: {missing_categories}")
    for stream in streams:
        if not isinstance(stream, dict):
            failures.append("closure_streams item invalid")
            continue
        failures.extend(validate_hard_evidence_closure_stream(stream))

    verification_commands = payload.get("post_closure_verification_commands")
    if not isinstance(verification_commands, list) or "python scripts/check_challenge_cup_goal_completion.py" not in {
        str(item) for item in verification_commands
    }:
        failures.append("post_closure_verification_commands missing goal completion check")

    missing_markdown_terms = sorted(
        term
        for term in (
            "Hard Evidence Closure Board",
            "does not satisfy goal completion",
            "expert_feedback",
            "timed_rehearsal",
            HARD_EVIDENCE_CLOSURE_BOARD_BOUNDARY,
        )
        if term not in markdown
    )
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    missing_manifest = sorted(path for path in HARD_EVIDENCE_CLOSURE_BOARD_REQUIRED_PATHS if path not in manifest_evidence)
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(path for path in HARD_EVIDENCE_CLOSURE_BOARD_REQUIRED_PATHS if path not in hashed_paths)
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(path for path in HARD_EVIDENCE_CLOSURE_BOARD_REQUIRED_PATHS if path not in archived_paths)
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in HARD_EVIDENCE_CLOSURE_BOARD_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(HARD_EVIDENCE_CLOSURE_BOARD_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked hard evidence closure board files: {untracked}")
    if dirty:
        failures.append(f"dirty hard evidence closure board files: {dirty}")

    return GateCheck(
        "hard evidence closure board",
        not failures,
        "closure board schema, boundary, real-evidence streams, and manifest/hash/archive links verified"
        if not failures
        else "; ".join(failures),
    )


def check_hard_evidence_action_pack() -> GateCheck:
    failures: list[str] = []
    required_files = [
        HARD_EVIDENCE_ACTION_PACK_MD,
        HARD_EVIDENCE_ACTION_PACK_JSON,
    ]
    missing_files = [path.relative_to(REPO_ROOT).as_posix() for path in required_files if not nonempty(path)]
    if missing_files:
        return GateCheck("hard evidence action pack", False, f"missing or empty: {missing_files}")

    payload = load_json(HARD_EVIDENCE_ACTION_PACK_JSON)
    markdown = HARD_EVIDENCE_ACTION_PACK_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_hard_evidence_action_pack":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "ready_for_real_external_evidence_collection":
        failures.append(f"status={payload.get('status')}")
    if payload.get("completion_claim_allowed") is not False:
        failures.append(f"completion_claim_allowed={payload.get('completion_claim_allowed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")
    required_before = [str(item) for item in payload.get("required_before_goal_completion", [])]
    if required_before != ["expert_feedback", "timed_rehearsal"]:
        failures.append(f"required_before_goal_completion={required_before}")
    if payload.get("operator_outcome") != "package can be reviewed; goal cannot be closed":
        failures.append(f"operator_outcome={payload.get('operator_outcome')}")

    streams = payload.get("action_streams")
    if not isinstance(streams, list):
        failures.append("action_streams missing")
        streams = []
    categories = {str(item.get("category", "")) for item in streams if isinstance(item, dict)}
    missing_categories = sorted(HARD_EVIDENCE_REQUIRED_CATEGORIES - categories)
    if missing_categories:
        failures.append(f"missing action streams: {missing_categories}")
    for stream in streams:
        if not isinstance(stream, dict):
            failures.append("action_streams item invalid")
            continue
        category = str(stream.get("category", ""))
        for field in ("human_owner", "human_action", "proof_to_collect", "ready_packet_files", "recording_commands"):
            if not has_value(stream.get(field)):
                failures.append(f"{category}: {field} missing")
        if stream.get("does_not_satisfy_goal_completion") is not True:
            failures.append(f"{category}: does_not_satisfy_goal_completion={stream.get('does_not_satisfy_goal_completion')}")
        acceptance_gate = str(stream.get("acceptance_gate", ""))
        if category and category not in acceptance_gate:
            failures.append(f"{category}: acceptance_gate does not reference category")
        ready_files = [str(item) for item in stream.get("ready_packet_files", [])]
        missing_ready_files = sorted(relative for relative in ready_files if not nonempty(REPO_ROOT / relative))
        if missing_ready_files:
            failures.append(f"{category}: ready_packet_files missing or empty: {missing_ready_files}")
        commands = "\n".join(str(item) for item in stream.get("recording_commands", []))
        if category == "expert_feedback":
            if "preflight_challenge_cup_hard_evidence.py expert_feedback" not in commands:
                failures.append(
                    f"{category}: recording_commands missing preflight_challenge_cup_hard_evidence.py expert_feedback"
                )
            if "record_challenge_cup_expert_outreach.py" not in commands:
                failures.append(f"{category}: recording_commands missing outreach recorder")
            if "record_challenge_cup_hard_evidence.py expert_feedback" not in commands:
                failures.append(f"{category}: recording_commands missing expert hard-evidence recorder")
            if "--confirm-real-feedback" not in commands:
                failures.append(f"{category}: recording_commands missing --confirm-real-feedback")
        if category == "timed_rehearsal":
            if "preflight_challenge_cup_hard_evidence.py timed_rehearsal" not in commands:
                failures.append(
                    f"{category}: recording_commands missing preflight_challenge_cup_hard_evidence.py timed_rehearsal"
                )
            if "record_challenge_cup_timed_rehearsal_schedule.py" not in commands:
                failures.append(f"{category}: recording_commands missing schedule recorder")
            if "run_challenge_cup_timed_rehearsal.py" not in commands:
                failures.append(f"{category}: recording_commands missing timed rehearsal runner")
            if "--confirm-real-rehearsal" not in commands:
                failures.append(f"{category}: recording_commands missing --confirm-real-rehearsal")

    verification_commands = payload.get("verification_commands")
    if not isinstance(verification_commands, list) or "python scripts/check_challenge_cup_goal_completion.py" not in {
        str(item) for item in verification_commands
    }:
        failures.append("verification_commands missing goal completion check")

    missing_markdown_terms = sorted(
        term
        for term in (
            "External Hard Evidence Action Pack",
            "does_not_satisfy_goal_completion=True",
            "expert_feedback",
            "timed_rehearsal",
            "不伪造",
        )
        if term not in markdown
    )
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    missing_manifest = sorted(path for path in HARD_EVIDENCE_ACTION_PACK_REQUIRED_PATHS if path not in manifest_evidence)
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(path for path in HARD_EVIDENCE_ACTION_PACK_REQUIRED_PATHS if path not in hashed_paths)
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(path for path in HARD_EVIDENCE_ACTION_PACK_REQUIRED_PATHS if path not in archived_paths)
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in HARD_EVIDENCE_ACTION_PACK_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(HARD_EVIDENCE_ACTION_PACK_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked hard evidence action pack files: {untracked}")
    if dirty:
        failures.append(f"dirty hard evidence action pack files: {dirty}")

    return GateCheck(
        "hard evidence action pack",
        not failures,
        "human handoff, no-fake boundary, recording commands, and manifest/hash/archive links verified"
        if not failures
        else "; ".join(failures),
    )


def check_external_evidence_execution_kit() -> GateCheck:
    failures: list[str] = []
    bootstrapping_readiness_report = not REPORT_MD.exists()
    try:
        self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        self_report = "docs/challenge_cup/reproducibility/readiness_gate_report.md"
    missing_files = [
        relative
        for relative in EXTERNAL_EVIDENCE_EXECUTION_KIT_REQUIRED_PATHS
        if not nonempty(REPO_ROOT / relative)
    ]
    if missing_files:
        return GateCheck("external evidence execution kit", False, f"missing or empty: {missing_files}")

    payload = load_json(EXTERNAL_EVIDENCE_EXECUTION_KIT_JSON)
    markdown = EXTERNAL_EVIDENCE_EXECUTION_KIT_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_external_evidence_execution_kit":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "ready_for_external_execution_handoff":
        failures.append(f"status={payload.get('status')}")
    if payload.get("completion_claim_allowed") is not False:
        failures.append(f"completion_claim_allowed={payload.get('completion_claim_allowed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")
    required_before = [str(item) for item in payload.get("required_before_goal_completion", [])]
    if required_before != ["expert_feedback", "timed_rehearsal"]:
        failures.append(f"required_before_goal_completion={required_before}")

    operator_sequence = payload.get("operator_sequence")
    expected_sequence = [
        "verify_package_ready",
        "record_expert_outreach",
        "record_rehearsal_schedule",
        "preflight_expert_feedback",
        "record_expert_feedback",
        "run_timed_rehearsal",
        "rebuild_package_and_gates",
        "refresh_final_audit",
    ]
    if not isinstance(operator_sequence, list):
        failures.append("operator_sequence missing")
        operator_sequence = []
    actual_sequence = [str(item.get("step_id", "")) for item in operator_sequence if isinstance(item, dict)]
    if actual_sequence != expected_sequence:
        failures.append(f"operator_sequence={actual_sequence}")
    sequence_by_id = {str(item.get("step_id", "")): item for item in operator_sequence if isinstance(item, dict)}
    for step_id in expected_sequence:
        item = sequence_by_id.get(step_id)
        if not isinstance(item, dict):
            failures.append(f"{step_id}: operator step missing")
            continue
        for field in ("phase", "category", "command", "human_proof_required", "expected_after_step", "guardrail"):
            if not has_value(item.get(field)):
                failures.append(f"{step_id}: {field} missing")
        if item.get("does_not_claim_award_or_completion") is not True:
            failures.append(
                f"{step_id}: does_not_claim_award_or_completion={item.get('does_not_claim_award_or_completion')}"
            )
    for step_id in ("record_expert_outreach", "record_rehearsal_schedule", "preflight_expert_feedback"):
        item = sequence_by_id.get(step_id, {})
        if isinstance(item, dict) and item.get("counts_as_hard_evidence") is not False:
            failures.append(f"{step_id}: counts_as_hard_evidence={item.get('counts_as_hard_evidence')}")
    for step_id in ("record_expert_feedback", "run_timed_rehearsal"):
        item = sequence_by_id.get(step_id, {})
        if isinstance(item, dict) and item.get("counts_as_hard_evidence") is not True:
            failures.append(f"{step_id}: counts_as_hard_evidence={item.get('counts_as_hard_evidence')}")
    command_requirements = {
        "record_expert_outreach": "record_challenge_cup_expert_outreach.py",
        "record_rehearsal_schedule": "record_challenge_cup_timed_rehearsal_schedule.py",
        "preflight_expert_feedback": "preflight_challenge_cup_hard_evidence.py expert_feedback",
        "record_expert_feedback": "record_challenge_cup_hard_evidence.py expert_feedback",
        "run_timed_rehearsal": "run_challenge_cup_timed_rehearsal.py",
        "rebuild_package_and_gates": "check_challenge_cup_goal_completion.py",
        "refresh_final_audit": "build_challenge_cup_final_acceptance_audit.py",
    }
    for step_id, required_command in command_requirements.items():
        item = sequence_by_id.get(step_id, {})
        command = str(item.get("command", "")) if isinstance(item, dict) else ""
        if required_command not in command:
            failures.append(f"{step_id}: command missing {required_command}")

    packets = payload.get("execution_packets")
    if not isinstance(packets, list):
        failures.append("execution_packets missing")
        packets = []
    categories = {str(item.get("hard_evidence_category", "")) for item in packets if isinstance(item, dict)}
    missing_categories = sorted(HARD_EVIDENCE_REQUIRED_CATEGORIES - categories)
    if missing_categories:
        failures.append(f"missing execution packets: {missing_categories}")

    for packet in packets:
        if not isinstance(packet, dict):
            failures.append("execution_packets item invalid")
            continue
        category = str(packet.get("hard_evidence_category", ""))
        packet_id = str(packet.get("packet_id", category))
        for field in (
            "packet_id",
            "hard_evidence_category",
            "owner",
            "handoff_file",
            "attachment_files",
            "execution_steps",
            "done_when",
            "recording_commands",
            "acceptance_gate",
        ):
            if not has_value(packet.get(field)):
                failures.append(f"{packet_id}: {field} missing")
        if packet.get("does_not_satisfy_goal_completion") is not True:
            failures.append(f"{packet_id}: does_not_satisfy_goal_completion={packet.get('does_not_satisfy_goal_completion')}")
        acceptance_gate = str(packet.get("acceptance_gate", ""))
        if category and category not in acceptance_gate:
            failures.append(f"{packet_id}: acceptance_gate does not reference category")

        handoff_file = str(packet.get("handoff_file", ""))
        if handoff_file and handoff_file not in EXTERNAL_EVIDENCE_EXECUTION_KIT_REQUIRED_PATHS:
            failures.append(f"{packet_id}: handoff_file not in required paths")
        if handoff_file and not nonempty(REPO_ROOT / handoff_file):
            failures.append(f"{packet_id}: handoff_file missing or empty")

        attachment_files = [str(item) for item in packet.get("attachment_files", [])]
        missing_attachments = sorted(
            relative
            for relative in attachment_files
            if not (bootstrapping_readiness_report and relative == self_report)
            and not nonempty(REPO_ROOT / relative)
        )
        if missing_attachments:
            failures.append(f"{packet_id}: attachment_files missing or empty: {missing_attachments}")

        commands = "\n".join(str(item) for item in packet.get("recording_commands", []))
        if category == "expert_feedback":
            if "preflight_challenge_cup_hard_evidence.py expert_feedback" not in commands:
                failures.append(
                    f"{packet_id}: recording_commands missing preflight_challenge_cup_hard_evidence.py expert_feedback"
                )
            if "record_challenge_cup_hard_evidence.py expert_feedback" not in commands:
                failures.append(f"{packet_id}: recording_commands missing expert hard-evidence recorder")
            if "--confirm-real-feedback" not in commands:
                failures.append(f"{packet_id}: recording_commands missing --confirm-real-feedback")
        if category == "timed_rehearsal":
            if "preflight_challenge_cup_hard_evidence.py timed_rehearsal" not in commands:
                failures.append(
                    f"{packet_id}: recording_commands missing preflight_challenge_cup_hard_evidence.py timed_rehearsal"
                )
            if "run_challenge_cup_timed_rehearsal.py" not in commands:
                failures.append(f"{packet_id}: recording_commands missing timed rehearsal runner")
            if "--confirm-real-rehearsal" not in commands:
                failures.append(f"{packet_id}: recording_commands missing --confirm-real-rehearsal")

    verification_commands = {str(item) for item in payload.get("verification_commands", [])}
    for command in (
        "python scripts/build_challenge_cup_external_evidence_execution_kit.py",
        "python scripts/check_challenge_cup_goal_completion.py",
    ):
        if command not in verification_commands:
            failures.append(f"verification_commands missing {command}")

    missing_markdown_terms = sorted(
        term
        for term in (
            "External Evidence Execution Kit",
            "Operator Sequence",
            "verify_package_ready",
            "record_expert_feedback",
            "run_timed_rehearsal",
            "does_not_satisfy_goal_completion=True",
            "不伪造",
            "真实专家反馈",
            "真实计时彩排",
        )
        if term not in markdown
    )
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    missing_manifest = sorted(
        path for path in EXTERNAL_EVIDENCE_EXECUTION_KIT_REQUIRED_PATHS if path not in manifest_evidence
    )
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(
        path for path in EXTERNAL_EVIDENCE_EXECUTION_KIT_REQUIRED_PATHS if path not in hashed_paths
    )
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(
        path for path in EXTERNAL_EVIDENCE_EXECUTION_KIT_REQUIRED_PATHS if path not in archived_paths
    )
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in EXTERNAL_EVIDENCE_EXECUTION_KIT_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(EXTERNAL_EVIDENCE_EXECUTION_KIT_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked external evidence execution kit files: {untracked}")
    if dirty:
        failures.append(f"dirty external evidence execution kit files: {dirty}")

    return GateCheck(
        "external evidence execution kit",
        not failures,
        "expert-review and timed-rehearsal handoff packets, no-fake boundary, commands, and manifest/hash/archive links verified"
        if not failures
        else "; ".join(failures),
    )


def validate_expert_feedback_metadata(relative: str, payload: dict[str, Any], category: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    accepted_types = {str(item) for item in category.get("accepted_evidence_types", [])}
    evidence_type = str(payload.get("evidence_type", ""))
    if evidence_type not in accepted_types:
        failures.append(f"{relative}: evidence_type={evidence_type}")
    for field in category.get("required_metadata_fields", []):
        if not has_value(payload.get(str(field))):
            failures.append(f"{relative}: {field} missing")
    review_dimensions = payload.get("review_dimensions")
    if not isinstance(review_dimensions, list) or len(review_dimensions) < HARD_EVIDENCE_MIN_REVIEW_DIMENSIONS:
        failures.append(f"{relative}: review_dimensions below {HARD_EVIDENCE_MIN_REVIEW_DIMENSIONS}")
    else:
        missing_dimension_groups = missing_required_review_dimension_groups(review_dimensions)
        if missing_dimension_groups:
            failures.append(
                f"{relative}: missing required expert review dimension groups: "
                + ", ".join(missing_dimension_groups)
            )
    remediation_record = payload.get("remediation_record")
    if not isinstance(remediation_record, list) or not remediation_record:
        failures.append(f"{relative}: remediation_record missing")
    if not is_iso_date(payload.get("review_date")):
        failures.append(f"{relative}: review_date must be YYYY-MM-DD")
    elif not is_not_future_iso_date(payload.get("review_date")):
        failures.append(f"{relative}: review_date must be YYYY-MM-DD and not in the future")
    if payload.get("real_feedback_confirmed") is not True:
        failures.append(f"{relative}: real_feedback_confirmed must be true")
    failures.extend(validate_source_path(relative, payload, "feedback_source_path"))
    return failures


def validate_timed_rehearsal_metadata(relative: str, payload: dict[str, Any], category: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    accepted_types = {str(item) for item in category.get("accepted_evidence_types", [])}
    evidence_type = str(payload.get("evidence_type", ""))
    if evidence_type not in accepted_types:
        failures.append(f"{relative}: evidence_type={evidence_type}")
    for field in category.get("required_metadata_fields", []):
        if not has_value(payload.get(str(field))):
            failures.append(f"{relative}: {field} missing")

    for field in ("opening_actual_seconds", "demo_actual_seconds", "offline_fallback_actual_seconds"):
        actual = numeric_value(payload.get(field))
        limit = HARD_EVIDENCE_TIMING_LIMITS[field]
        if actual is None:
            failures.append(f"{relative}: {field} must be numeric")
        elif actual > limit:
            failures.append(f"{relative}: {field}={actual:g} exceeds {limit}")

    if not is_iso_date(payload.get("rehearsal_date")):
        failures.append(f"{relative}: rehearsal_date must be YYYY-MM-DD")
    elif not is_not_future_iso_date(payload.get("rehearsal_date")):
        failures.append(f"{relative}: rehearsal_date must be YYYY-MM-DD and not in the future")
    if payload.get("real_rehearsal_confirmed") is not True:
        failures.append(f"{relative}: real_rehearsal_confirmed must be true")
    failures.extend(validate_source_path(relative, payload, "recording_or_timer_source_path"))

    killer_results = payload.get("killer_question_results")
    if not isinstance(killer_results, list):
        failures.append(f"{relative}: killer_question_results missing")
        return failures
    required_count = HARD_EVIDENCE_TIMING_LIMITS["killer_question_count"]
    if len(killer_results) < required_count:
        failures.append(f"{relative}: killer_question_results below {required_count}")
    for index, item in enumerate(killer_results, start=1):
        if not isinstance(item, dict):
            failures.append(f"{relative}: killer_question_results[{index}] invalid")
            continue
        actual = numeric_value(item.get("actual_seconds"))
        limit = HARD_EVIDENCE_TIMING_LIMITS["killer_question_actual_seconds"]
        if actual is None:
            failures.append(f"{relative}: killer_question_results[{index}].actual_seconds must be numeric")
        elif actual > limit:
            failures.append(f"{relative}: killer_question_results[{index}].actual_seconds={actual:g} exceeds {limit}")
    return failures


def validate_hard_evidence_metadata(category_key: str, files: list[str], category: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if not files:
        return failures
    metadata_files = [relative for relative in files if relative.lower().endswith(".json")]
    if not metadata_files:
        failures.append(f"{category_key}: metadata json missing")
        return failures
    for relative in metadata_files:
        path = REPO_ROOT / relative
        try:
            payload = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"{relative}: invalid metadata json: {exc}")
            continue
        if category_key == "expert_feedback":
            failures.extend(validate_expert_feedback_metadata(relative, payload, category))
        elif category_key == "timed_rehearsal":
            failures.extend(validate_timed_rehearsal_metadata(relative, payload, category))
    return failures


def check_hard_evidence_ledger() -> GateCheck:
    failures: list[str] = []
    required_files = [
        HARD_EVIDENCE_LEDGER_MD,
        HARD_EVIDENCE_LEDGER_JSON,
        HARD_EVIDENCE_README,
        HARD_EVIDENCE_EXPERT_README,
        HARD_EVIDENCE_REHEARSAL_README,
    ]
    missing_files = [path.relative_to(REPO_ROOT).as_posix() for path in required_files if not nonempty(path)]
    if missing_files:
        return GateCheck("hard evidence ledger", False, f"missing or empty: {missing_files}")

    payload = load_json(HARD_EVIDENCE_LEDGER_JSON)
    markdown = HARD_EVIDENCE_LEDGER_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_hard_evidence_ledger":
        failures.append(f"report_type={payload.get('report_type')}")
    required_before = [str(item) for item in payload.get("required_before_goal_completion", [])]
    if required_before != ["expert_feedback", "timed_rehearsal"]:
        failures.append(f"required_before_goal_completion={required_before}")

    categories = payload.get("categories", {})
    if not isinstance(categories, dict):
        failures.append("categories missing")
        categories = {}
    missing_categories = sorted(HARD_EVIDENCE_REQUIRED_CATEGORIES - set(categories))
    if missing_categories:
        failures.append(f"missing categories: {missing_categories}")

    raw_evidence_files: list[str] = []
    category_satisfied = True
    for key in sorted(HARD_EVIDENCE_REQUIRED_CATEGORIES):
        category = categories.get(key, {})
        if not isinstance(category, dict):
            failures.append(f"{key} category invalid")
            category_satisfied = False
            continue
        files = [str(item) for item in category.get("evidence_files", [])]
        metadata_files = [str(item) for item in category.get("metadata_files", [])]
        source_files = [str(item) for item in category.get("source_files", [])]
        evidence_records = category.get("evidence_records", [])
        raw_evidence_files.extend(files)
        collected_count = int(category.get("collected_count") or 0)
        raw_file_count = int(category.get("raw_file_count") or 0)
        metadata_file_count = int(category.get("metadata_file_count") or 0)
        source_file_count = int(category.get("source_file_count") or 0)
        evidence_record_count = int(category.get("evidence_record_count") or 0)
        required_min = int(category.get("required_min_count") or 0)
        for schema_field in (
            "raw_file_count",
            "metadata_file_count",
            "source_file_count",
            "evidence_record_count",
            "metadata_files",
            "source_files",
            "evidence_records",
        ):
            if schema_field not in category:
                failures.append(f"{key}.{schema_field} missing")
        expected_metadata_files = sorted(relative for relative in files if relative.lower().endswith(".json"))
        expected_source_files = sorted(relative for relative in files if not relative.lower().endswith(".json"))
        if raw_file_count != len(files):
            failures.append(f"{key}.raw_file_count mismatch")
        if metadata_file_count != len(expected_metadata_files):
            failures.append(f"{key}.metadata_file_count mismatch")
        if source_file_count != len(expected_source_files):
            failures.append(f"{key}.source_file_count mismatch")
        if sorted(metadata_files) != expected_metadata_files:
            failures.append(f"{key}.metadata_files mismatch")
        if sorted(source_files) != expected_source_files:
            failures.append(f"{key}.source_files mismatch")
        if not isinstance(evidence_records, list):
            failures.append(f"{key}.evidence_records invalid")
            evidence_records = []
        if evidence_record_count != len(evidence_records):
            failures.append(f"{key}.evidence_record_count mismatch")
        if collected_count != evidence_record_count:
            failures.append(f"{key}.collected_count must equal evidence_record_count")
        metadata_file_set = set(metadata_files)
        source_file_set = set(source_files)
        for index, record in enumerate(evidence_records, start=1):
            if not isinstance(record, dict):
                failures.append(f"{key}.evidence_records[{index}] invalid")
                continue
            metadata_path = str(record.get("metadata_path", ""))
            source_path = str(record.get("source_path", ""))
            if metadata_path not in metadata_file_set:
                failures.append(f"{key}.evidence_records[{index}].metadata_path not in metadata_files")
            if source_path not in source_file_set:
                failures.append(f"{key}.evidence_records[{index}].source_path not in source_files")
        if required_min < 1:
            failures.append(f"{key}.required_min_count below 1")
            category_satisfied = False
        if collected_count < required_min:
            category_satisfied = False
        if not category.get("accepted_evidence_types"):
            failures.append(f"{key}.accepted_evidence_types missing")
        required_metadata_fields = [str(item) for item in category.get("required_metadata_fields", [])]
        if not required_metadata_fields:
            failures.append(f"{key}.required_metadata_fields missing")
        if key == "expert_feedback" and "real_feedback_confirmed" not in required_metadata_fields:
            failures.append(f"{key}.required_metadata_fields missing real_feedback_confirmed")
        if key == "timed_rehearsal" and "real_rehearsal_confirmed" not in required_metadata_fields:
            failures.append(f"{key}.required_metadata_fields missing real_rehearsal_confirmed")
        metadata_failures = validate_hard_evidence_metadata(key, files, category)
        if metadata_failures:
            category_satisfied = False
            failures.extend(metadata_failures)

    completion_claim_allowed = payload.get("completion_claim_allowed")
    if completion_claim_allowed is True and not category_satisfied:
        failures.append("completion_claim_allowed true before required hard evidence is collected")
    if not category_satisfied:
        if payload.get("status") != "awaiting_real_external_feedback_and_timed_rehearsal":
            failures.append(f"status={payload.get('status')} while hard evidence is incomplete")
        if completion_claim_allowed is not False:
            failures.append(f"completion_claim_allowed={completion_claim_allowed} while hard evidence is incomplete")

    missing_terms = sorted(term for term in HARD_EVIDENCE_MARKDOWN_TERMS if term not in markdown)
    if missing_terms:
        failures.append(f"markdown missing terms: {missing_terms}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    required_manifest_missing = sorted(path for path in HARD_EVIDENCE_REQUIRED_PATHS if path not in manifest_evidence)
    if required_manifest_missing:
        failures.append(f"missing manifest entries: {required_manifest_missing}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {"included_files": []}
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}

    raw_evidence_files = sorted(set(raw_evidence_files))
    unsafe_raw_paths = []
    missing_raw_files = []
    missing_raw_manifest = []
    missing_raw_hashes = []
    missing_raw_archive = []
    for relative in raw_evidence_files:
        posix = PurePosixPath(relative)
        if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
            unsafe_raw_paths.append(relative)
            continue
        current = REPO_ROOT / relative
        if not nonempty(current):
            missing_raw_files.append(relative)
        if relative not in manifest_evidence:
            missing_raw_manifest.append(relative)
        if relative not in hashed_paths:
            missing_raw_hashes.append(relative)
        if SUBMISSION_ARCHIVE_MANIFEST.exists() and relative not in archived_paths:
            missing_raw_archive.append(relative)
    if unsafe_raw_paths:
        failures.append(f"unsafe raw evidence paths: {unsafe_raw_paths}")
    if missing_raw_files:
        failures.append(f"raw evidence missing or empty: {missing_raw_files}")
    if missing_raw_manifest:
        failures.append(f"raw evidence missing from manifest: {missing_raw_manifest}")
    if missing_raw_hashes:
        failures.append(f"raw evidence missing from hashes: {missing_raw_hashes}")
    if missing_raw_archive:
        failures.append(f"raw evidence missing from archive: {missing_raw_archive}")

    tracked = git_tracked_paths()
    required_and_raw = HARD_EVIDENCE_REQUIRED_PATHS + raw_evidence_files
    untracked = [path for path in required_and_raw if path not in tracked]
    dirty = sorted(git_dirty_paths(required_and_raw))
    if untracked:
        failures.append(f"untracked hard evidence files: {untracked}")
    if dirty:
        failures.append(f"dirty hard evidence files: {dirty}")

    return GateCheck(
        "hard evidence ledger",
        not failures,
        f"ledger schema, no-fake boundary, {len(raw_evidence_files)} raw hard evidence files, and manifest/hash/archive links verified"
        if not failures
        else "; ".join(failures),
    )


def check_application_validation_evidence() -> GateCheck:
    if not APPLICATION_VALIDATION_DOC.exists():
        return GateCheck("application validation evidence", False, "11_应用场景与专家验证.md missing")
    if not APPLICATION_VALIDATION_REPORT.exists():
        return GateCheck("application validation evidence", False, "application_validation_report.md missing")
    doc_text = APPLICATION_VALIDATION_DOC.read_text(encoding="utf-8")
    report_text = APPLICATION_VALIDATION_REPORT.read_text(encoding="utf-8")
    missing_terms = sorted(term for term in REQUIRED_APPLICATION_VALIDATION_TERMS if term not in doc_text)
    missing_terms.extend(sorted(term for term in REQUIRED_APPLICATION_REPORT_TERMS if term not in report_text))
    evidence_paths = extract_markdown_code_span_paths(doc_text + "\n" + report_text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    missing = missing_terms + missing_paths
    return GateCheck(
        "application validation evidence",
        not missing,
        f"fixed GT-07 application case, multi-scenario matrix, evidence records, benefits, and boundaries verified; {len(evidence_paths)} evidence links verified"
        if not missing
        else f"missing application validation terms or evidence paths: {', '.join(missing)}",
    )


def check_application_value_quantification() -> GateCheck:
    failures: list[str] = []
    missing_files = [
        path
        for path in (APPLICATION_VALUE_QUANTIFICATION_MD, APPLICATION_VALUE_QUANTIFICATION_JSON)
        if not nonempty(path)
    ]
    if missing_files:
        missing = [display_path(path) for path in missing_files]
        return GateCheck("application value quantification", False, f"missing or empty: {missing}")

    payload = load_json(APPLICATION_VALUE_QUANTIFICATION_JSON)
    markdown = APPLICATION_VALUE_QUANTIFICATION_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_application_value_quantification":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "application_value_quantified_no_external_validation_claim":
        failures.append(f"status={payload.get('status')}")
    if payload.get("completion_claim_allowed") is not False:
        failures.append(f"completion_claim_allowed={payload.get('completion_claim_allowed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")
    if payload.get("external_validation_claimed") is not False:
        failures.append(f"external_validation_claimed={payload.get('external_validation_claimed')}")
    if payload.get("source_browser_smoke") != "docs/challenge_cup/reproducibility/browser_demo_smoke_report.json":
        failures.append(f"source_browser_smoke={payload.get('source_browser_smoke')}")
    if payload.get("source_application_validation_report") != (
        "docs/challenge_cup/reproducibility/application_validation_report.md"
    ):
        failures.append(f"source_application_validation_report={payload.get('source_application_validation_report')}")
    if payload.get("query") != REQUIRED_SCENARIO_QUERY:
        failures.append(f"query={payload.get('query')}")
    if payload.get("collection") != "gas_turbine_ocr_demo_snapshot":
        failures.append(f"collection={payload.get('collection')}")
    if float(payload.get("retrieval_latency_ms") or 0) != 41.8:
        failures.append(f"retrieval_latency_ms={payload.get('retrieval_latency_ms')}")
    for key, expected in {
        "returned_record_count": 5,
        "visible_record_count": 5,
        "indexed_chunks": 2655,
        "indexed_tokens": 1185989,
        "evidence_chain_stage_count": 5,
    }.items():
        if int(payload.get(key) or -1) != expected:
            failures.append(f"{key}={payload.get(key)}")
    if payload.get("evidence_chain_complete") is not True:
        failures.append(f"evidence_chain_complete={payload.get('evidence_chain_complete')}")

    chain = payload.get("evidence_chain", [])
    if not isinstance(chain, list):
        failures.append("evidence_chain missing")
        chain = []
    stage_ids = [str(stage.get("stage_id")) for stage in chain if isinstance(stage, dict)]
    record_ids = [str(stage.get("record_id")) for stage in chain if isinstance(stage, dict)]
    if stage_ids != APPLICATION_VALUE_EXPECTED_STAGE_IDS:
        failures.append(f"stage_ids={stage_ids}")
    if record_ids != APPLICATION_VALUE_EXPECTED_RECORD_IDS:
        failures.append(f"record_ids={record_ids}")
    invisible = [
        str(stage.get("record_id"))
        for stage in chain
        if isinstance(stage, dict) and stage.get("visible") is not True
    ]
    if invisible:
        failures.append(f"invisible records={invisible}")

    workflow = payload.get("workflow_contrast", {})
    if not isinstance(workflow, dict):
        failures.append("workflow_contrast missing")
        workflow = {}
    if int(workflow.get("manual_lookup_step_count") or -1) != 5:
        failures.append(f"manual_lookup_step_count={workflow.get('manual_lookup_step_count')}")
    if int(workflow.get("system_result_step_count") or -1) != 1:
        failures.append(f"system_result_step_count={workflow.get('system_result_step_count')}")
    if float(workflow.get("evidence_consolidation_ratio") or 0) != 5.0:
        failures.append(f"evidence_consolidation_ratio={workflow.get('evidence_consolidation_ratio')}")
    if workflow.get("record_id_traceability") is not True:
        failures.append(f"record_id_traceability={workflow.get('record_id_traceability')}")

    claim_ids = {
        str(claim.get("claim_id"))
        for claim in payload.get("judge_value_claims", [])
        if isinstance(claim, dict)
    }
    missing_claim_ids = sorted(APPLICATION_VALUE_REQUIRED_CLAIM_IDS - claim_ids)
    if missing_claim_ids:
        failures.append(f"missing claim_ids: {missing_claim_ids}")
    boundary = str(payload.get("boundary", ""))
    if boundary != APPLICATION_VALUE_QUANTIFICATION_BOUNDARY:
        failures.append("boundary mismatch")
    for term in (
        "not a production validation",
        "does not replace engineers",
        "real expert feedback",
        "real timed rehearsal",
    ):
        if term not in boundary:
            failures.append(f"boundary missing {term}")

    output_files = {str(item) for item in payload.get("output_files", [])}
    missing_output_files = sorted(path for path in APPLICATION_VALUE_QUANTIFICATION_REQUIRED_PATHS if path not in output_files)
    if missing_output_files:
        failures.append(f"output_files missing: {missing_output_files}")
    missing_markdown_terms = sorted(term for term in APPLICATION_VALUE_MARKDOWN_TERMS if term not in markdown)
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    missing_manifest = sorted(
        path for path in APPLICATION_VALUE_QUANTIFICATION_REQUIRED_PATHS if path not in manifest_evidence
    )
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(path for path in APPLICATION_VALUE_QUANTIFICATION_REQUIRED_PATHS if path not in hashed_paths)
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(
        path for path in APPLICATION_VALUE_QUANTIFICATION_REQUIRED_PATHS if path not in archived_paths
    )
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in APPLICATION_VALUE_QUANTIFICATION_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(APPLICATION_VALUE_QUANTIFICATION_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked application value quantification files: {untracked}")
    if dirty:
        failures.append(f"dirty application value quantification files: {dirty}")

    return GateCheck(
        "application value quantification",
        not failures,
        "GT-07 application value quantified with 5-stage traceability, 41.8 ms latency, and no-external-claim boundary"
        if not failures
        else "; ".join(failures),
    )


def check_numeric_traceability_report() -> GateCheck:
    failures: list[str] = []
    missing_files = [
        path
        for path in (NUMERIC_TRACEABILITY_REPORT_MD, NUMERIC_TRACEABILITY_REPORT_JSON)
        if not nonempty(path)
    ]
    if missing_files:
        missing = [display_path(path) for path in missing_files]
        return GateCheck("numeric traceability report", False, f"missing or empty: {missing}")

    payload = load_json(NUMERIC_TRACEABILITY_REPORT_JSON)
    markdown = NUMERIC_TRACEABILITY_REPORT_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_numeric_traceability_report":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "numeric_traceability_consistent_no_external_claim":
        failures.append(f"status={payload.get('status')}")
    if payload.get("completion_claim_allowed") is not False:
        failures.append(f"completion_claim_allowed={payload.get('completion_claim_allowed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")
    if payload.get("external_validation_claimed") is not False:
        failures.append(f"external_validation_claimed={payload.get('external_validation_claimed')}")

    latency = payload.get("latency_ms", {})
    if not isinstance(latency, dict):
        failures.append("latency_ms missing")
        latency = {}
    if float(latency.get("browser_smoke") or 0) != 41.8:
        failures.append(f"browser_smoke latency={latency.get('browser_smoke')}")
    if float(latency.get("application_value") or 0) != 41.8:
        failures.append(f"application_value latency={latency.get('application_value')}")
    validation_latencies = latency.get("application_validation_report")
    if validation_latencies != [41.8, 41.8]:
        failures.append(f"application_validation_report latency={validation_latencies}")

    result_counts = payload.get("result_counts", {})
    if not isinstance(result_counts, dict):
        failures.append("result_counts missing")
        result_counts = {}
    for key, expected in {
        "browser_smoke": 5,
        "application_value": 5,
        "browser_visible_record_ids": 5,
        "application_value_visible_record_count": 5,
    }.items():
        if int(result_counts.get(key) or -1) != expected:
            failures.append(f"{key}={result_counts.get(key)}")

    index_scale = payload.get("index_scale", {})
    if not isinstance(index_scale, dict):
        failures.append("index_scale missing")
        index_scale = {}
    if int(index_scale.get("chunks") or -1) != 2655:
        failures.append(f"chunks={index_scale.get('chunks')}")
    if int(index_scale.get("tokens") or -1) != 1185989:
        failures.append(f"tokens={index_scale.get('tokens')}")

    if payload.get("record_ids") != NUMERIC_TRACEABILITY_EXPECTED_RECORD_IDS:
        failures.append(f"record_ids={payload.get('record_ids')}")
    if payload.get("application_value_record_ids") != NUMERIC_TRACEABILITY_EXPECTED_RECORD_IDS:
        failures.append(f"application_value_record_ids={payload.get('application_value_record_ids')}")
    report_failures = payload.get("failures")
    if report_failures != []:
        failures.append(f"failures={report_failures}")

    boundary = str(payload.get("boundary", ""))
    if boundary != NUMERIC_TRACEABILITY_BOUNDARY:
        failures.append("boundary mismatch")
    for term in (
        "does not claim production validation",
        "does not claim external validation",
        "does not replace engineers",
        "real expert feedback",
        "real timed rehearsal",
    ):
        if term not in boundary:
            failures.append(f"boundary missing {term}")

    output_files = {str(item) for item in payload.get("output_files", [])}
    missing_output_files = sorted(path for path in NUMERIC_TRACEABILITY_REPORT_REQUIRED_PATHS if path not in output_files)
    if missing_output_files:
        failures.append(f"output_files missing: {missing_output_files}")
    missing_markdown_terms = sorted(term for term in NUMERIC_TRACEABILITY_MARKDOWN_TERMS if term not in markdown)
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")
    if "42.10 ms" in markdown:
        failures.append("markdown contains stale 42.10 ms drift")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    missing_manifest = sorted(
        path for path in NUMERIC_TRACEABILITY_REPORT_REQUIRED_PATHS if path not in manifest_evidence
    )
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(path for path in NUMERIC_TRACEABILITY_REPORT_REQUIRED_PATHS if path not in hashed_paths)
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(path for path in NUMERIC_TRACEABILITY_REPORT_REQUIRED_PATHS if path not in archived_paths)
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in NUMERIC_TRACEABILITY_REPORT_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(NUMERIC_TRACEABILITY_REPORT_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked numeric traceability report files: {untracked}")
    if dirty:
        failures.append(f"dirty numeric traceability report files: {dirty}")

    return GateCheck(
        "numeric traceability report",
        not failures,
        "GT-07 browser/application/application-validation numbers are traceable: 41.80 ms, 5 records, 2,655 chunks, 1,185,989 tokens"
        if not failures
        else "; ".join(failures),
    )


def check_no_answer_boundary_evaluation() -> GateCheck:
    failures: list[str] = []
    missing_files = [
        path
        for path in (NO_ANSWER_BOUNDARY_EVALUATION_MD, NO_ANSWER_BOUNDARY_EVALUATION_JSON)
        if not nonempty(path)
    ]
    if missing_files:
        missing = [display_path(path) for path in missing_files]
        return GateCheck("no-answer boundary evaluation", False, f"missing or empty: {missing}")

    payload = load_json(NO_ANSWER_BOUNDARY_EVALUATION_JSON)
    markdown = NO_ANSWER_BOUNDARY_EVALUATION_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_no_answer_boundary_evaluation":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "no_answer_boundary_guard_verified_no_live_llm_claim":
        failures.append(f"status={payload.get('status')}")
    if payload.get("completion_claim_allowed") is not False:
        failures.append(f"completion_claim_allowed={payload.get('completion_claim_allowed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")
    if payload.get("external_validation_claimed") is not False:
        failures.append(f"external_validation_claimed={payload.get('external_validation_claimed')}")
    if payload.get("live_retriever_claimed") is not False:
        failures.append(f"live_retriever_claimed={payload.get('live_retriever_claimed')}")
    if payload.get("online_llm_behavior_claimed") is not False:
        failures.append(f"online_llm_behavior_claimed={payload.get('online_llm_behavior_claimed')}")
    if payload.get("deterministic_guard_only") is not True:
        failures.append(f"deterministic_guard_only={payload.get('deterministic_guard_only')}")
    if payload.get("guard") != "rag_orchestrator.HallucinationGuard":
        failures.append(f"guard={payload.get('guard')}")
    if int(payload.get("case_count") or -1) != 14:
        failures.append(f"case_count={payload.get('case_count')}")
    if int(payload.get("empty_context_case_count") or -1) != 4:
        failures.append(f"empty_context_case_count={payload.get('empty_context_case_count')}")
    if int(payload.get("noisy_retrieved_context_case_count") or -1) != 10:
        failures.append(
            f"noisy_retrieved_context_case_count={payload.get('noisy_retrieved_context_case_count')}"
        )
    if int(payload.get("unsafe_specific_claim_count") or -1) != 6:
        failures.append(f"unsafe_specific_claim_count={payload.get('unsafe_specific_claim_count')}")
    if int(payload.get("unsafe_noisy_specific_claim_count") or -1) != 5:
        failures.append(f"unsafe_noisy_specific_claim_count={payload.get('unsafe_noisy_specific_claim_count')}")
    if int(payload.get("safe_no_answer_count") or -1) != 7:
        failures.append(f"safe_no_answer_count={payload.get('safe_no_answer_count')}")
    if int(payload.get("safe_noisy_boundary_count") or -1) != 5:
        failures.append(f"safe_noisy_boundary_count={payload.get('safe_noisy_boundary_count')}")
    if payload.get("all_cases_passed") is not True:
        failures.append(f"all_cases_passed={payload.get('all_cases_passed')}")
    if payload.get("failures") != []:
        failures.append(f"failures={payload.get('failures')}")

    cases = {
        str(case.get("case_id")): case
        for case in payload.get("cases", [])
        if isinstance(case, dict)
    }
    required_case_ids = {
        "empty_context_specific_maintenance_claim",
        "empty_context_chinese_no_answer",
        "empty_context_english_no_answer",
        "empty_context_empty_answer",
        "noisy_context_conflicting_temperature_restart",
        "noisy_context_multiple_root_causes_single_cause",
        "noisy_context_low_similarity_repair_instruction",
        "noisy_context_stale_maintenance_threshold",
        "noisy_context_conflicting_sensor_fault",
        "noisy_context_safe_temperature_boundary",
        "noisy_context_safe_root_cause_boundary",
        "noisy_context_safe_similarity_boundary",
        "noisy_context_safe_threshold_boundary",
        "noisy_context_safe_sensor_boundary",
    }
    missing_cases = sorted(required_case_ids - set(cases))
    if missing_cases:
        failures.append(f"missing cases: {missing_cases}")
    unsupported = cases.get("empty_context_specific_maintenance_claim", {})
    if unsupported.get("expected_safe") is not False or unsupported.get("actual_safe") is not False:
        failures.append("unsupported maintenance claim was not rejected")
    if float(unsupported.get("score") or 0) != 0.0:
        failures.append(f"unsupported score={unsupported.get('score')}")
    unsupported_claims = [str(item) for item in unsupported.get("hallucinated_claims", [])]
    if not any("No retrieved evidence" in claim for claim in unsupported_claims):
        failures.append("unsupported case missing No retrieved evidence claim")
    chinese = cases.get("empty_context_chinese_no_answer", {})
    if chinese.get("expected_safe") is not True or chinese.get("actual_safe") is not True:
        failures.append("Chinese no-answer boundary was not accepted")
    if "证据不足" not in str(chinese.get("answer", "")):
        failures.append("Chinese no-answer case missing 证据不足")
    english = cases.get("empty_context_english_no_answer", {})
    if english.get("expected_safe") is not True or english.get("actual_safe") is not True:
        failures.append("English no-answer boundary was not accepted")
    for case_id in sorted(case for case in required_case_ids if case.startswith("noisy_context_")):
        case = cases.get(case_id, {})
        if case.get("context_type") != "noisy_or_contradictory_retrieved_context":
            failures.append(f"{case_id}: context_type={case.get('context_type')}")
        if case.get("expected_safe") is not case.get("actual_safe"):
            failures.append(f"{case_id}: expected_safe={case.get('expected_safe')} actual_safe={case.get('actual_safe')}")
        if case.get("expected_safe") is False:
            claims = [str(item) for item in case.get("hallucinated_claims", [])]
            if not any("contradictory or insufficient retrieved evidence" in claim for claim in claims):
                failures.append(f"{case_id}: missing contradictory/insufficient evidence claim")

    boundary = str(payload.get("boundary", ""))
    if boundary != NO_ANSWER_BOUNDARY_EVALUATION_BOUNDARY:
        failures.append("boundary mismatch")
    for term in (
        "does not claim live retriever coverage",
        "does not claim online LLM behavior",
        "does not claim external validation",
        "real expert feedback",
        "real timed rehearsal",
    ):
        if term not in boundary:
            failures.append(f"boundary missing {term}")

    output_files = {str(item) for item in payload.get("output_files", [])}
    missing_output_files = sorted(path for path in NO_ANSWER_BOUNDARY_EVALUATION_REQUIRED_PATHS if path not in output_files)
    if missing_output_files:
        failures.append(f"output_files missing: {missing_output_files}")
    missing_markdown_terms = sorted(term for term in NO_ANSWER_BOUNDARY_MARKDOWN_TERMS if term not in markdown)
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    missing_manifest = sorted(
        path for path in NO_ANSWER_BOUNDARY_EVALUATION_REQUIRED_PATHS if path not in manifest_evidence
    )
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(path for path in NO_ANSWER_BOUNDARY_EVALUATION_REQUIRED_PATHS if path not in hashed_paths)
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(path for path in NO_ANSWER_BOUNDARY_EVALUATION_REQUIRED_PATHS if path not in archived_paths)
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in NO_ANSWER_BOUNDARY_EVALUATION_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(NO_ANSWER_BOUNDARY_EVALUATION_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked no-answer boundary evaluation files: {untracked}")
    if dirty:
        failures.append(f"dirty no-answer boundary evaluation files: {dirty}")

    return GateCheck(
        "no-answer boundary evaluation",
        not failures,
        "empty/noisy-context guard rejects unsupported maintenance claims and accepts explicit no-answer boundaries without live retriever or online LLM claims"
        if not failures
        else "; ".join(failures),
    )


def check_claim_integrity_report() -> GateCheck:
    failures: list[str] = []
    missing_files = [
        path for path in (CLAIM_INTEGRITY_REPORT_MD, CLAIM_INTEGRITY_REPORT_JSON) if not nonempty(path)
    ]
    if missing_files:
        missing = [display_path(path) for path in missing_files]
        return GateCheck("claim integrity report", False, f"missing or empty: {missing}")

    payload = load_json(CLAIM_INTEGRITY_REPORT_JSON)
    markdown = CLAIM_INTEGRITY_REPORT_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_claim_integrity_report":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "claim_integrity_verified_no_award_or_external_claim":
        failures.append(f"status={payload.get('status')}")
    if payload.get("completion_claim_allowed") is not False:
        failures.append(f"completion_claim_allowed={payload.get('completion_claim_allowed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")
    for field in (
        "award_guarantee_claimed",
        "expert_approval_claimed",
        "timed_rehearsal_completion_claimed",
        "production_deployment_claimed",
    ):
        if payload.get(field) is not False:
            failures.append(f"{field}={payload.get(field)}")
    if payload.get("all_claims_evidence_bound") is not True:
        failures.append(f"all_claims_evidence_bound={payload.get('all_claims_evidence_bound')}")
    if int(payload.get("forbidden_hit_count", -1)) != 0:
        failures.append(f"forbidden_hit_count={payload.get('forbidden_hit_count')}")
    if payload.get("forbidden_hits") not in ([], None):
        failures.append(f"forbidden_hits={payload.get('forbidden_hits')}")
    if int(payload.get("claim_count") or -1) < 8:
        failures.append(f"claim_count={payload.get('claim_count')}")
    if payload.get("failures") != []:
        failures.append(f"failures={payload.get('failures')}")

    claims = [claim for claim in payload.get("claims", []) if isinstance(claim, dict)]
    claim_ids = {str(claim.get("claim_id", "")) for claim in claims}
    bootstrapping_readiness_report = not REPORT_MD.exists()
    readiness_self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    required_claim_ids = {
        "package_review_ready",
        "graphrag_innovation_bounded",
        "evaluation_transparency",
        "application_value_bounded",
        "defense_demo_fallback_ready",
        "external_hard_evidence_not_closed",
        "special_prize_competition_argument",
        "human_decision_boundary",
    }
    missing_claim_ids = sorted(required_claim_ids - claim_ids)
    if missing_claim_ids:
        failures.append(f"missing claim ids: {missing_claim_ids}")
    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        evidence_files = [str(path) for path in claim.get("evidence_files", [])]
        if not evidence_files:
            failures.append(f"{claim_id}: evidence_files missing")
        for relative in evidence_files:
            if not relative.startswith("docs/") and not relative.startswith("evaluation/"):
                failures.append(f"{claim_id}: evidence_files must be repo paths: {relative}")
            if bootstrapping_readiness_report and relative == readiness_self_report:
                continue
            if not nonempty(REPO_ROOT / relative):
                failures.append(f"{claim_id}: evidence file missing or empty: {relative}")
        if not str(claim.get("boundary", "")).strip():
            failures.append(f"{claim_id}: boundary missing")
        if not str(claim.get("forbidden_overclaim", "")).strip():
            failures.append(f"{claim_id}: forbidden_overclaim missing")

    boundary = str(payload.get("boundary", ""))
    if boundary != CLAIM_INTEGRITY_REPORT_BOUNDARY:
        failures.append("boundary mismatch")
    for term in (
        "does not guarantee an award",
        "does not claim expert approval",
        "does not claim timed rehearsal completion",
        "does not claim production deployment",
        "real expert feedback",
        "real timed rehearsal",
    ):
        if term not in boundary:
            failures.append(f"boundary missing {term}")

    output_files = {str(item) for item in payload.get("output_files", [])}
    missing_output_files = sorted(path for path in CLAIM_INTEGRITY_REPORT_REQUIRED_PATHS if path not in output_files)
    if missing_output_files:
        failures.append(f"output_files missing: {missing_output_files}")
    missing_markdown_terms = sorted(term for term in CLAIM_INTEGRITY_MARKDOWN_TERMS if term not in markdown)
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    missing_manifest = sorted(path for path in CLAIM_INTEGRITY_REPORT_REQUIRED_PATHS if path not in manifest_evidence)
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(path for path in CLAIM_INTEGRITY_REPORT_REQUIRED_PATHS if path not in hashed_paths)
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(path for path in CLAIM_INTEGRITY_REPORT_REQUIRED_PATHS if path not in archived_paths)
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in CLAIM_INTEGRITY_REPORT_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(CLAIM_INTEGRITY_REPORT_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked claim integrity report files: {untracked}")
    if dirty:
        failures.append(f"dirty claim integrity report files: {dirty}")

    return GateCheck(
        "claim integrity report",
        not failures,
        "8 defense claim families are evidence-bound with no award, expert-approval, timed-rehearsal, or production-deployment overclaim"
        if not failures
        else "; ".join(failures),
    )


def check_rubric_defense_coverage() -> GateCheck:
    failures: list[str] = []
    missing_files = [
        path for path in (RUBRIC_DEFENSE_COVERAGE_MD, RUBRIC_DEFENSE_COVERAGE_JSON) if not nonempty(path)
    ]
    if missing_files:
        missing = [display_path(path) for path in missing_files]
        return GateCheck("rubric defense coverage", False, f"missing or empty: {missing}")

    try:
        payload = load_json(RUBRIC_DEFENSE_COVERAGE_JSON)
    except (OSError, json.JSONDecodeError) as exc:
        return GateCheck("rubric defense coverage", False, f"invalid rubric defense coverage json: {exc}")
    markdown = RUBRIC_DEFENSE_COVERAGE_MD.read_text(encoding="utf-8")

    if payload.get("report_type") != "challenge_cup_rubric_defense_coverage":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "rubric_defense_coverage_ready_no_award_claim":
        failures.append(f"status={payload.get('status')}")
    if payload.get("completion_claim_allowed") is not False:
        failures.append(f"completion_claim_allowed={payload.get('completion_claim_allowed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")
    for field in (
        "award_guarantee_claimed",
        "expert_approval_claimed",
        "timed_rehearsal_completion_claimed",
    ):
        if payload.get(field) is not False:
            failures.append(f"{field}={payload.get(field)}")
    if payload.get("coverage_complete") is not True:
        failures.append(f"coverage_complete={payload.get('coverage_complete')}")
    if int(payload.get("dimension_count") or -1) != len(RUBRIC_DEFENSE_COVERAGE_REQUIRED_DIMENSIONS):
        failures.append(f"dimension_count={payload.get('dimension_count')}")
    if int(payload.get("covered_dimension_count") or -1) != len(RUBRIC_DEFENSE_COVERAGE_REQUIRED_DIMENSIONS):
        failures.append(f"covered_dimension_count={payload.get('covered_dimension_count')}")
    if payload.get("gaps") != []:
        failures.append(f"gaps={payload.get('gaps')}")

    dimensions = payload.get("dimensions")
    if not isinstance(dimensions, list):
        failures.append("dimensions missing")
        dimensions = []
    dimension_keys = {str(item.get("dimension_key", "")) for item in dimensions if isinstance(item, dict)}
    missing_dimensions = sorted(RUBRIC_DEFENSE_COVERAGE_REQUIRED_DIMENSIONS - dimension_keys)
    if missing_dimensions:
        failures.append(f"missing dimension keys: {missing_dimensions}")
    extra_dimensions = sorted(dimension_keys - RUBRIC_DEFENSE_COVERAGE_REQUIRED_DIMENSIONS)
    if extra_dimensions:
        failures.append(f"unexpected dimension keys: {extra_dimensions}")

    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    report_outputs = set(RUBRIC_DEFENSE_COVERAGE_REQUIRED_PATHS)
    evidence_paths: set[str] = set()
    for index, item in enumerate(dimensions, start=1):
        if not isinstance(item, dict):
            failures.append(f"dimensions[{index}] invalid")
            continue
        key = str(item.get("dimension_key", f"dimensions[{index}]"))
        if item.get("coverage_status") != "covered":
            failures.append(f"{key}: coverage_status={item.get('coverage_status')}")
        if not item.get("official_source_ids"):
            failures.append(f"{key}: official_source_ids missing")
        evidence_files = [str(path) for path in item.get("evidence_files", [])]
        if len(evidence_files) < 2:
            failures.append(f"{key}: fewer than 2 evidence_files")
        for field in ("judge_objection_ids", "claim_ids", "defense_assets"):
            values = item.get(field)
            if not isinstance(values, list) or not values:
                failures.append(f"{key}: {field} missing")
        if not str(item.get("boundary", "")).strip():
            failures.append(f"{key}: boundary missing")

        defense_assets = [str(path) for path in item.get("defense_assets", [])]
        for relative in sorted(set(evidence_files + defense_assets)):
            posix = PurePosixPath(relative)
            if not relative:
                failures.append(f"{key}: empty path")
                continue
            if relative.startswith(("http://", "https://")):
                failures.append(f"{key}: repo path required, got URL: {relative}")
                continue
            if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
                failures.append(f"{key}: unsafe path: {relative}")
                continue
            if not relative.startswith(("docs/", "evaluation/")):
                failures.append(f"{key}: path outside allowed scope: {relative}")
                continue
            if relative in report_outputs:
                failures.append(f"{key}: self-references rubric defense coverage output: {relative}")
                continue
            evidence_paths.add(relative)
            if relative != self_report and not nonempty(REPO_ROOT / relative):
                failures.append(f"{key}: evidence path missing or empty: {relative}")

    source_reports = payload.get("source_reports", {})
    if not isinstance(source_reports, dict):
        failures.append("source_reports missing")
        source_reports = {}
    for expected in (
        OFFICIAL_RUBRIC_ALIGNMENT_MD_RELATIVE,
        JUDGE_OBJECTION_MATRIX_MD_RELATIVE,
        CLAIM_INTEGRITY_REPORT_MD_RELATIVE,
    ):
        if expected not in {str(value) for value in source_reports.values()}:
            failures.append(f"source report missing: {expected}")

    boundary = str(payload.get("boundary", ""))
    if boundary != RUBRIC_DEFENSE_COVERAGE_BOUNDARY:
        failures.append("boundary mismatch")
    for term in (
        "does not guarantee an award",
        "does not claim expert approval",
        "does not claim timed rehearsal completion",
        "real expert feedback",
        "real timed rehearsal",
    ):
        if term not in boundary:
            failures.append(f"boundary missing {term}")

    output_files = {str(item) for item in payload.get("output_files", [])}
    missing_output_files = sorted(path for path in RUBRIC_DEFENSE_COVERAGE_REQUIRED_PATHS if path not in output_files)
    if missing_output_files:
        failures.append(f"output_files missing: {missing_output_files}")
    missing_markdown_terms = sorted(term for term in RUBRIC_DEFENSE_COVERAGE_MARKDOWN_TERMS if term not in markdown)
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")
    commands = {str(item) for item in payload.get("verification_commands", [])}
    if "python scripts/build_challenge_cup_rubric_defense_coverage.py" not in commands:
        failures.append("verification command missing: build_challenge_cup_rubric_defense_coverage.py")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    missing_manifest = sorted(path for path in RUBRIC_DEFENSE_COVERAGE_REQUIRED_PATHS if path not in manifest_evidence)
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(path for path in RUBRIC_DEFENSE_COVERAGE_REQUIRED_PATHS if path not in hashed_paths)
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(path for path in RUBRIC_DEFENSE_COVERAGE_REQUIRED_PATHS if path not in archived_paths)
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in RUBRIC_DEFENSE_COVERAGE_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(RUBRIC_DEFENSE_COVERAGE_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked rubric defense coverage files: {untracked}")
    if dirty:
        failures.append(f"dirty rubric defense coverage files: {dirty}")

    return GateCheck(
        "rubric defense coverage",
        not failures,
        (
            f"{len(RUBRIC_DEFENSE_COVERAGE_REQUIRED_DIMENSIONS)} rubric dimensions linked to "
            f"{len(evidence_paths)} evidence paths, judge objections, claim ids, and defense assets"
        )
        if not failures
        else "; ".join(failures),
    )


def check_defense_slide_traceability() -> GateCheck:
    failures: list[str] = []
    missing_files = [
        path for path in (DEFENSE_SLIDE_TRACEABILITY_MD, DEFENSE_SLIDE_TRACEABILITY_JSON) if not nonempty(path)
    ]
    if missing_files:
        missing = [display_path(path) for path in missing_files]
        return GateCheck("defense slide traceability", False, f"missing or empty: {missing}")

    try:
        payload = load_json(DEFENSE_SLIDE_TRACEABILITY_JSON)
    except (OSError, json.JSONDecodeError) as exc:
        return GateCheck("defense slide traceability", False, f"invalid defense slide traceability json: {exc}")
    markdown = DEFENSE_SLIDE_TRACEABILITY_MD.read_text(encoding="utf-8")

    if payload.get("report_type") != "challenge_cup_defense_slide_traceability":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "defense_slide_traceability_ready_no_rehearsal_or_award_claim":
        failures.append(f"status={payload.get('status')}")
    if payload.get("completion_claim_allowed") is not False:
        failures.append(f"completion_claim_allowed={payload.get('completion_claim_allowed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")
    for field in (
        "award_guarantee_claimed",
        "expert_approval_claimed",
        "timed_rehearsal_completion_claimed",
    ):
        if payload.get(field) is not False:
            failures.append(f"{field}={payload.get(field)}")
    if payload.get("coverage_complete") is not True:
        failures.append(f"coverage_complete={payload.get('coverage_complete')}")
    if int(payload.get("slide_count") or -1) != len(DEFENSE_SLIDE_TRACEABILITY_REQUIRED_SLIDE_INDEXES):
        failures.append(f"slide_count={payload.get('slide_count')}")
    if int(payload.get("covered_slide_count") or -1) != len(DEFENSE_SLIDE_TRACEABILITY_REQUIRED_SLIDE_INDEXES):
        failures.append(f"covered_slide_count={payload.get('covered_slide_count')}")
    if payload.get("gaps") != []:
        failures.append(f"gaps={payload.get('gaps')}")

    if not nonempty(DEFENSE_DECK_PPTX):
        failures.append(f"defense deck missing or empty: {DEFENSE_DECK_PPTX_RELATIVE}")
    else:
        try:
            actual_slide_count, _ = pptx_text_and_slide_count(DEFENSE_DECK_PPTX)
            if actual_slide_count != len(DEFENSE_SLIDE_TRACEABILITY_REQUIRED_SLIDE_INDEXES):
                failures.append(f"actual defense deck slide count={actual_slide_count}")
        except (OSError, zipfile.BadZipFile, ET.ParseError) as exc:
            failures.append(f"defense deck unreadable: {exc}")
    if not nonempty(DEFENSE_DECK_NOTES):
        failures.append(f"speaker notes missing or empty: {DEFENSE_DECK_NOTES_RELATIVE}")

    slides = payload.get("slides")
    if not isinstance(slides, list):
        failures.append("slides missing")
        slides = []
    slide_indexes: set[int] = set()
    covered_rows = 0
    report_outputs = set(DEFENSE_SLIDE_TRACEABILITY_REQUIRED_PATHS)
    evidence_paths: set[str] = set()
    for row_number, item in enumerate(slides, start=1):
        if not isinstance(item, dict):
            failures.append(f"slides[{row_number}] invalid")
            continue
        try:
            slide_index = int(item.get("slide_index"))
        except (TypeError, ValueError):
            failures.append(f"slides[{row_number}]: slide_index={item.get('slide_index')}")
            continue
        slide_indexes.add(slide_index)
        if item.get("coverage_status") != "covered":
            failures.append(f"slide {slide_index}: coverage_status={item.get('coverage_status')}")
        else:
            covered_rows += 1
        if not str(item.get("title", "")).strip():
            failures.append(f"slide {slide_index}: title missing")
        rubric_dimensions = [str(value) for value in item.get("rubric_dimensions", [])]
        if not rubric_dimensions:
            failures.append(f"slide {slide_index}: rubric_dimensions missing")
        unknown_dimensions = sorted(set(rubric_dimensions) - RUBRIC_DEFENSE_COVERAGE_REQUIRED_DIMENSIONS)
        if unknown_dimensions:
            failures.append(f"slide {slide_index}: unknown rubric dimensions {unknown_dimensions}")
        evidence_files = [str(path) for path in item.get("evidence_files", [])]
        if len(evidence_files) < 2:
            failures.append(f"slide {slide_index}: fewer than 2 evidence_files")
        for field in ("judge_objection_ids", "claim_ids", "notes_anchor_terms"):
            values = item.get(field)
            if not isinstance(values, list) or not values:
                failures.append(f"slide {slide_index}: {field} missing")
        if not str(item.get("boundary", "")).strip():
            failures.append(f"slide {slide_index}: boundary missing")

        for relative in sorted(set(evidence_files)):
            posix = PurePosixPath(relative)
            if not relative:
                failures.append(f"slide {slide_index}: empty path")
                continue
            if relative.startswith(("http://", "https://")):
                failures.append(f"slide {slide_index}: repo path required, got URL: {relative}")
                continue
            if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
                failures.append(f"slide {slide_index}: unsafe path: {relative}")
                continue
            if not relative.startswith(("docs/", "evaluation/")):
                failures.append(f"slide {slide_index}: path outside allowed scope: {relative}")
                continue
            if relative in report_outputs:
                failures.append(f"slide {slide_index}: self-references defense slide traceability output: {relative}")
                continue
            evidence_paths.add(relative)
            if relative != REPORT_MD.relative_to(REPO_ROOT).as_posix() and not nonempty(REPO_ROOT / relative):
                failures.append(f"slide {slide_index}: evidence path missing or empty: {relative}")

    missing_slide_indexes = sorted(DEFENSE_SLIDE_TRACEABILITY_REQUIRED_SLIDE_INDEXES - slide_indexes)
    if missing_slide_indexes:
        failures.append(f"missing slide indexes: {missing_slide_indexes}")
    extra_slide_indexes = sorted(slide_indexes - DEFENSE_SLIDE_TRACEABILITY_REQUIRED_SLIDE_INDEXES)
    if extra_slide_indexes:
        failures.append(f"unexpected slide indexes: {extra_slide_indexes}")
    if covered_rows != len(DEFENSE_SLIDE_TRACEABILITY_REQUIRED_SLIDE_INDEXES):
        failures.append(f"covered slide rows={covered_rows}")

    boundary = str(payload.get("boundary", ""))
    if boundary != DEFENSE_SLIDE_TRACEABILITY_BOUNDARY:
        failures.append("boundary mismatch")
    for term in (
        "does not guarantee an award",
        "does not claim expert approval",
        "does not claim timed rehearsal completion",
        "does not satisfy goal completion",
        "real expert feedback",
        "real timed rehearsal",
    ):
        if term not in boundary:
            failures.append(f"boundary missing {term}")

    output_files = {str(item) for item in payload.get("output_files", [])}
    missing_output_files = sorted(path for path in DEFENSE_SLIDE_TRACEABILITY_REQUIRED_PATHS if path not in output_files)
    if missing_output_files:
        failures.append(f"output_files missing: {missing_output_files}")
    missing_markdown_terms = sorted(
        term for term in DEFENSE_SLIDE_TRACEABILITY_MARKDOWN_TERMS if term not in markdown
    )
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")
    commands = {str(item) for item in payload.get("verification_commands", [])}
    if "python scripts/build_challenge_cup_defense_slide_traceability.py" not in commands:
        failures.append("verification command missing: build_challenge_cup_defense_slide_traceability.py")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    missing_manifest = sorted(path for path in DEFENSE_SLIDE_TRACEABILITY_REQUIRED_PATHS if path not in manifest_evidence)
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(path for path in DEFENSE_SLIDE_TRACEABILITY_REQUIRED_PATHS if path not in hashed_paths)
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(path for path in DEFENSE_SLIDE_TRACEABILITY_REQUIRED_PATHS if path not in archived_paths)
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in DEFENSE_SLIDE_TRACEABILITY_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(DEFENSE_SLIDE_TRACEABILITY_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked defense slide traceability files: {untracked}")
    if dirty:
        failures.append(f"dirty defense slide traceability files: {dirty}")

    return GateCheck(
        "defense slide traceability",
        not failures,
        f"{len(DEFENSE_SLIDE_TRACEABILITY_REQUIRED_SLIDE_INDEXES)} slides linked to {len(evidence_paths)} evidence paths, judge objections, claim ids, and no-overclaim boundaries"
        if not failures
        else "; ".join(failures),
    )


def check_runtime_reproducibility_snapshot() -> GateCheck:
    failures: list[str] = []
    missing_files = [
        path
        for path in (RUNTIME_REPRODUCIBILITY_SNAPSHOT_MD, RUNTIME_REPRODUCIBILITY_SNAPSHOT_JSON)
        if not nonempty(path)
    ]
    if missing_files:
        missing = [display_path(path) for path in missing_files]
        return GateCheck("runtime reproducibility snapshot", False, f"missing or empty: {missing}")

    payload = load_json(RUNTIME_REPRODUCIBILITY_SNAPSHOT_JSON)
    markdown = RUNTIME_REPRODUCIBILITY_SNAPSHOT_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_runtime_reproducibility_snapshot":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "runtime_snapshot_ready_no_environment_portability_claim":
        failures.append(f"status={payload.get('status')}")
    if payload.get("completion_claim_allowed") is not False:
        failures.append(f"completion_claim_allowed={payload.get('completion_claim_allowed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")
    if payload.get("external_validation_claimed") is not False:
        failures.append(f"external_validation_claimed={payload.get('external_validation_claimed')}")
    if payload.get("runtime_scope") != "local challenge-cup package reproduction environment":
        failures.append(f"runtime_scope={payload.get('runtime_scope')}")

    python_payload = payload.get("python", {})
    if not isinstance(python_payload, dict):
        failures.append("python section missing")
        python_payload = {}
    if python_payload.get("project_python") != ".venv/Scripts/python.exe":
        failures.append(f"project_python={python_payload.get('project_python')}")
    for field in ("current_executable", "current_version", "pytest_probe"):
        if not has_value(python_payload.get(field)):
            failures.append(f"python.{field} missing")

    node_payload = payload.get("node", {})
    if not isinstance(node_payload, dict):
        failures.append("node section missing")
        node_payload = {}
    for field in ("node_available", "node_version", "package_json_present", "package_lock_present", "node_modules_present"):
        if field not in node_payload:
            failures.append(f"node.{field} missing")

    browser_payload = payload.get("browser_automation", {})
    if not isinstance(browser_payload, dict):
        failures.append("browser_automation section missing")
        browser_payload = {}
    if browser_payload.get("source_report") != "docs/challenge_cup/reproducibility/browser_demo_smoke_report.json":
        failures.append(f"browser source_report={browser_payload.get('source_report')}")
    for field in ("playwright_source", "frontend_url", "browser_smoke_status"):
        if not has_value(browser_payload.get(field)):
            failures.append(f"browser_automation.{field} missing")

    commands = {str(item) for item in payload.get("verification_commands", [])}
    for command in (
        ".\\.venv\\Scripts\\python.exe docs/challenge_cup/reproducibility/verify_submission_package.py --root .",
        ".\\.venv\\Scripts\\python.exe scripts/check_challenge_cup_readiness.py",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit -q",
    ):
        if command not in commands:
            failures.append(f"verification command missing: {command}")

    boundary = str(payload.get("boundary", ""))
    if boundary != RUNTIME_REPRODUCIBILITY_SNAPSHOT_BOUNDARY:
        failures.append("boundary mismatch")
    for term in (
        "not a production deployment certification",
        "does not guarantee a special-prize result",
        "does not replace real expert feedback or real timed rehearsal evidence",
    ):
        if term not in boundary:
            failures.append(f"boundary missing {term}")

    output_files = {str(item) for item in payload.get("output_files", [])}
    missing_output_files = sorted(
        path for path in RUNTIME_REPRODUCIBILITY_SNAPSHOT_REQUIRED_PATHS if path not in output_files
    )
    if missing_output_files:
        failures.append(f"output_files missing: {missing_output_files}")
    missing_markdown_terms = sorted(
        term
        for term in (
            "Runtime Reproducibility Snapshot",
            "Python Runtime",
            "Node And Browser Automation",
            "Repository Controls",
            "not a production deployment certification",
        )
        if term not in markdown
    )
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    missing_manifest = sorted(
        path for path in RUNTIME_REPRODUCIBILITY_SNAPSHOT_REQUIRED_PATHS if path not in manifest_evidence
    )
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(path for path in RUNTIME_REPRODUCIBILITY_SNAPSHOT_REQUIRED_PATHS if path not in hashed_paths)
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(
        path for path in RUNTIME_REPRODUCIBILITY_SNAPSHOT_REQUIRED_PATHS if path not in archived_paths
    )
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in RUNTIME_REPRODUCIBILITY_SNAPSHOT_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(RUNTIME_REPRODUCIBILITY_SNAPSHOT_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked runtime reproducibility snapshot files: {untracked}")
    if dirty:
        failures.append(f"dirty runtime reproducibility snapshot files: {dirty}")

    return GateCheck(
        "runtime reproducibility snapshot",
        not failures,
        "local Python, Node, Playwright, verification commands, and no-portability-claim boundary verified"
        if not failures
        else "; ".join(failures),
    )


def check_verification_transcript() -> GateCheck:
    failures: list[str] = []
    missing_files = [
        path
        for path in (VERIFICATION_TRANSCRIPT_MD, VERIFICATION_TRANSCRIPT_JSON)
        if not nonempty(path)
    ]
    if missing_files:
        missing = [display_path(path) for path in missing_files]
        return GateCheck("verification transcript", False, f"missing or empty: {missing}")

    payload = load_json(VERIFICATION_TRANSCRIPT_JSON)
    markdown = VERIFICATION_TRANSCRIPT_MD.read_text(encoding="utf-8")
    if payload.get("report_type") != "challenge_cup_verification_transcript":
        failures.append(f"report_type={payload.get('report_type')}")
    if payload.get("status") != "package_verification_transcript_ready_goal_still_blocked":
        failures.append(f"status={payload.get('status')}")
    if payload.get("completion_claim_allowed") is not False:
        failures.append(f"completion_claim_allowed={payload.get('completion_claim_allowed')}")
    if payload.get("does_not_satisfy_goal_completion") is not True:
        failures.append(f"does_not_satisfy_goal_completion={payload.get('does_not_satisfy_goal_completion')}")
    if payload.get("external_validation_claimed") is not False:
        failures.append(f"external_validation_claimed={payload.get('external_validation_claimed')}")

    readiness = payload.get("readiness_gate", {})
    if not isinstance(readiness, dict):
        failures.append("readiness_gate missing")
        readiness = {}
    if readiness.get("status") != "pass":
        failures.append(f"readiness.status={readiness.get('status')}")
    if int(readiness.get("passed") or -1) != CURRENT_READINESS_GATE_COUNT:
        failures.append(f"readiness.passed={readiness.get('passed')}")
    if int(readiness.get("total") or -1) != CURRENT_READINESS_GATE_COUNT:
        failures.append(f"readiness.total={readiness.get('total')}")
    if int(readiness.get("current_gate_count") or -1) != CURRENT_READINESS_GATE_COUNT:
        failures.append(f"readiness.current_gate_count={readiness.get('current_gate_count')}")

    final_acceptance = payload.get("final_acceptance", {})
    if not isinstance(final_acceptance, dict):
        failures.append("final_acceptance missing")
        final_acceptance = {}
    if final_acceptance.get("status") != "package_ready_awaiting_external_hard_evidence":
        failures.append(f"final_acceptance.status={final_acceptance.get('status')}")
    if final_acceptance.get("can_submit_for_package_review") is not True:
        failures.append(f"can_submit_for_package_review={final_acceptance.get('can_submit_for_package_review')}")
    if final_acceptance.get("can_mark_goal_complete") is not False:
        failures.append(f"can_mark_goal_complete={final_acceptance.get('can_mark_goal_complete')}")

    goal_completion = payload.get("goal_completion", {})
    if not isinstance(goal_completion, dict):
        failures.append("goal_completion missing")
        goal_completion = {}
    if goal_completion.get("status") != "fail":
        failures.append(f"goal_completion.status={goal_completion.get('status')}")
    if goal_completion.get("completion_claim_allowed") is not False:
        failures.append(f"goal_completion.completion_claim_allowed={goal_completion.get('completion_claim_allowed')}")
    if goal_completion.get("expected_failure") is not True:
        failures.append(f"goal_completion.expected_failure={goal_completion.get('expected_failure')}")

    blocking_categories = {
        str(item.get("category"))
        for item in payload.get("blocking_items", [])
        if isinstance(item, dict)
    }
    if blocking_categories != {"expert_feedback", "timed_rehearsal"}:
        failures.append(f"blocking_items={sorted(blocking_categories)}")

    commands = {
        str(item.get("command")): item
        for item in payload.get("verification_commands", [])
        if isinstance(item, dict)
    }
    expected_commands = {
        ".\\.venv\\Scripts\\python.exe scripts/check_challenge_cup_readiness.py": (0, "pass"),
        ".\\.venv\\Scripts\\python.exe docs/challenge_cup/reproducibility/verify_submission_package.py --root .": (
            0,
            "pass",
        ),
        ".\\.venv\\Scripts\\python.exe scripts/build_challenge_cup_final_acceptance_audit.py": (
            0,
            "package_ready_awaiting_external_hard_evidence",
        ),
        ".\\.venv\\Scripts\\python.exe scripts/check_challenge_cup_goal_completion.py": (1, "fail"),
    }
    for command, (expected_exit, expected_status) in expected_commands.items():
        item = commands.get(command)
        if not item:
            failures.append(f"verification command missing: {command}")
            continue
        try:
            actual_exit = int(item.get("expected_exit_code"))
        except (TypeError, ValueError):
            actual_exit = None
        if actual_exit != expected_exit:
            failures.append(f"{command} expected_exit_code={item.get('expected_exit_code')}")
        if item.get("observed_status") != expected_status:
            failures.append(f"{command} observed_status={item.get('observed_status')}")
    goal_command = commands.get(".\\.venv\\Scripts\\python.exe scripts/check_challenge_cup_goal_completion.py", {})
    if goal_command.get("expected_failure_reason") != "awaiting_real_external_hard_evidence":
        failures.append(f"goal expected_failure_reason={goal_command.get('expected_failure_reason')}")

    boundary = str(payload.get("boundary", ""))
    if boundary != VERIFICATION_TRANSCRIPT_BOUNDARY:
        failures.append("boundary mismatch")
    for term in (
        "does not claim goal completion",
        "does not claim expert approval or timed rehearsal completion",
        "does not replace real expert feedback or real timed rehearsal evidence",
    ):
        if term not in boundary:
            failures.append(f"boundary missing {term}")

    output_files = {str(item) for item in payload.get("output_files", [])}
    missing_output_files = sorted(path for path in VERIFICATION_TRANSCRIPT_REQUIRED_PATHS if path not in output_files)
    if missing_output_files:
        failures.append(f"output_files missing: {missing_output_files}")
    missing_markdown_terms = sorted(
        term
        for term in (
            "Verification Transcript",
            "Expected Failure",
            f"readiness gate pass {CURRENT_READINESS_GATE_COUNT}/{CURRENT_READINESS_GATE_COUNT}",
            "does not claim goal completion",
        )
        if term not in markdown
    )
    if missing_markdown_terms:
        failures.append(f"markdown missing terms: {missing_markdown_terms}")

    manifest = load_json(PACKAGE_MANIFEST) if PACKAGE_MANIFEST.exists() else {}
    manifest_evidence = {str(item) for item in manifest.get("evidence_files", [])}
    missing_manifest = sorted(path for path in VERIFICATION_TRANSCRIPT_REQUIRED_PATHS if path not in manifest_evidence)
    if missing_manifest:
        failures.append(f"missing manifest entries: {missing_manifest}")

    hashes = load_json(EVIDENCE_HASHES) if EVIDENCE_HASHES.exists() else {"files": []}
    hashed_paths = {str(item.get("path", "")) for item in hashes.get("files", [])}
    missing_hashes = sorted(path for path in VERIFICATION_TRANSCRIPT_REQUIRED_PATHS if path not in hashed_paths)
    if missing_hashes:
        failures.append(f"missing hash entries: {missing_hashes}")

    archive_manifest = load_json(SUBMISSION_ARCHIVE_MANIFEST) if SUBMISSION_ARCHIVE_MANIFEST.exists() else {
        "included_files": []
    }
    archived_paths = {str(item) for item in archive_manifest.get("included_files", [])}
    missing_archive = sorted(path for path in VERIFICATION_TRANSCRIPT_REQUIRED_PATHS if path not in archived_paths)
    if SUBMISSION_ARCHIVE_MANIFEST.exists() and missing_archive:
        failures.append(f"missing archive entries: {missing_archive}")

    tracked = git_tracked_paths()
    untracked = [path for path in VERIFICATION_TRANSCRIPT_REQUIRED_PATHS if path not in tracked]
    dirty = sorted(git_dirty_paths(VERIFICATION_TRANSCRIPT_REQUIRED_PATHS))
    if untracked:
        failures.append(f"untracked verification transcript files: {untracked}")
    if dirty:
        failures.append(f"dirty verification transcript files: {dirty}")

    return GateCheck(
        "verification transcript",
        not failures,
        "current verifier, readiness, final audit, and expected goal-completion failure summarized"
        if not failures
        else "; ".join(failures),
    )


def check_scenario_demo_evidence() -> GateCheck:
    if not BROWSER_SMOKE_JSON.exists():
        return GateCheck("scenario demo evidence", False, "browser_demo_smoke_report.json missing")
    payload = load_json(BROWSER_SMOKE_JSON)
    browser = payload.get("browser", {})
    query = str(browser.get("query", ""))
    search_meta = str(browser.get("search_meta", ""))
    results_preview = str(browser.get("results_preview", ""))
    application_text = APPLICATION_VALIDATION_REPORT.read_text(encoding="utf-8") if APPLICATION_VALIDATION_REPORT.exists() else ""
    failures: list[str] = []
    if payload.get("status") != "pass":
        failures.append(f"browser smoke status={payload.get('status')}")
    if query != REQUIRED_SCENARIO_QUERY:
        failures.append(f"query mismatch: {query}")
    for term in ("结果 5", "延迟", "gas_turbine_ocr_demo_snapshot"):
        if term not in search_meta:
            failures.append(f"search_meta missing {term}")
    for term in sorted(REQUIRED_SCENARIO_TERMS):
        if term not in results_preview:
            failures.append(term)
    for term in sorted(REQUIRED_SCENARIO_BOUNDARY_TERMS):
        if term not in application_text:
            failures.append(f"boundary missing {term}")
    return GateCheck(
        "scenario demo evidence",
        not failures,
        "fixed abnormal-vibration query returns 5 GT-07 evidence records with human-confirmation boundary"
        if not failures
        else f"missing scenario demo terms: {', '.join(failures)}",
    )


def check_scenario_walkthrough_script() -> GateCheck:
    if not DEMO_SCRIPT.exists():
        return GateCheck("scenario walkthrough script", False, "04_系统演示脚本.md missing")
    text = DEMO_SCRIPT.read_text(encoding="utf-8")
    missing = sorted(term for term in REQUIRED_SCENARIO_WALKTHROUGH_TERMS if term not in text)
    evidence_paths = extract_markdown_code_span_paths(text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    missing.extend(missing_paths)
    return GateCheck(
        "scenario walkthrough script",
        not missing,
        f"fixed scenario walkthrough, fallback screenshot, evidence records, and human-confirmation boundary verified; {len(evidence_paths)} evidence links verified"
        if not missing
        else f"missing scenario walkthrough terms or evidence paths: {', '.join(missing)}",
    )


def check_expert_feedback_protocol() -> GateCheck:
    if not EXPERT_FEEDBACK_PROTOCOL.exists():
        return GateCheck("expert feedback protocol", False, "12_专家反馈采集与整改闭环.md missing")
    if not EXPERT_FEEDBACK_FORM.exists():
        return GateCheck("expert feedback protocol", False, "expert_feedback_form.md missing")
    protocol_text = EXPERT_FEEDBACK_PROTOCOL.read_text(encoding="utf-8")
    form_text = EXPERT_FEEDBACK_FORM.read_text(encoding="utf-8")
    missing = sorted(term for term in REQUIRED_EXPERT_FEEDBACK_PROTOCOL_TERMS if term not in protocol_text)
    missing.extend(sorted(term for term in REQUIRED_EXPERT_FEEDBACK_FORM_TERMS if term not in form_text))
    evidence_paths = extract_markdown_code_span_paths(protocol_text + "\n" + form_text)
    self_report = REPORT_MD.relative_to(REPO_ROOT).as_posix()
    missing_paths = sorted(path for path in evidence_paths if path != self_report and not nonempty(REPO_ROOT / path))
    missing.extend(missing_paths)
    return GateCheck(
        "expert feedback protocol",
        not missing,
        f"feedback form, integrity boundary, archival rule, and remediation loop verified; {len(evidence_paths)} evidence links verified"
        if not missing
        else f"missing expert feedback protocol terms or evidence paths: {', '.join(missing)}",
    )


def run_gate() -> list[GateCheck]:
    return [
        check_package_docs(),
        check_challenge_cup_chinese_readability(),
        check_package_control_files(),
        check_eval_dataset(),
        check_evaluation_coverage_profile(),
        check_package_manifest(),
        check_evidence_hashes(),
        check_defense_deck(),
        check_submission_archive(),
        check_submission_package_verifier(),
        check_final_acceptance_audit(),
        check_numeric_consistency(),
        check_graphrag_same_question_evidence(),
        check_graphrag_context_demo(),
        check_graphrag_answer_benchmark(),
        check_graphrag_gap_remediation_plan(),
        check_failure_remediation_before_after(),
        check_claim_evidence_matrix(),
        check_acceptance_checklist(),
        check_award_self_eval(),
        check_official_rubric_alignment(),
        check_judge_objection_response_matrix(),
        check_special_prize_readiness_dashboard(),
        check_judge_briefing_card(),
        check_onsite_defense_runbook(),
        check_project_handoff_checklist(),
        check_defense_qa_remediation_ledger(),
        check_review_risk_response_plan(),
        check_special_prize_scoring_drill(),
        check_poster_booth_qa_pack(),
        check_commercialization_roadmap(),
        check_poster_board_asset(),
        check_defense_control_console(),
        check_ip_open_source_compliance(),
        check_local_baseline_differentiation_evidence(),
        check_final_submission_handoff_sheet(),
        check_expert_review_index(),
        check_defense_rehearsal_card(),
        check_defense_rehearsal_scorecard(),
        check_defense_rehearsal_result_packet(),
        check_expert_feedback_request_packet(),
        check_expert_feedback_outreach_ledger(),
        check_timed_rehearsal_schedule_ledger(),
        check_hard_evidence_closure_board(),
        check_hard_evidence_action_pack(),
        check_external_evidence_execution_kit(),
        check_hard_evidence_ledger(),
        check_application_validation_evidence(),
        check_application_value_quantification(),
        check_numeric_traceability_report(),
        check_no_answer_boundary_evaluation(),
        check_claim_integrity_report(),
        check_rubric_defense_coverage(),
        check_defense_slide_traceability(),
        check_runtime_reproducibility_snapshot(),
        check_verification_transcript(),
        check_scenario_demo_evidence(),
        check_scenario_walkthrough_script(),
        check_expert_feedback_protocol(),
        check_report_payload(LIVE_SMOKE_JSON, REQUIRED_LIVE_CHECKS, "live demo smoke checks"),
        check_report_payload(BROWSER_SMOKE_JSON, REQUIRED_BROWSER_CHECKS, "browser smoke checks"),
        check_browser_evidence_files(),
    ]


def write_report(checks: list[GateCheck]) -> dict[str, Any]:
    passed = sum(1 for item in checks if item.passed)
    payload = {
        "status": "pass" if passed == len(checks) else "fail",
        "passed": passed,
        "total": len(checks),
    }
    lines = [
        "# Challenge Cup Readiness Gate",
        "",
        f"- Status: `{payload['status']}`",
        f"- Passed: {passed}/{len(checks)}",
        "- Scope: challenge-cup package docs, Chinese readability, control files, defense deck, submission archive, submission package verifier, final acceptance audit, numeric consistency, GraphRAG evidence audit, GraphRAG context demo, GraphRAG answer benchmark, GraphRAG gap remediation plan, failure remediation before/after, claim-evidence matrix, acceptance checklist, special-prize rubric, official rubric alignment, judge objection response matrix, special prize readiness dashboard, judge briefing card, onsite defense runbook, project handoff checklist, defense q&a remediation ledger, review risk response plan, special prize scoring drill, poster booth q&a pack, commercialization roadmap, poster board asset, defense control console, ip and open-source compliance, local baseline differentiation evidence, final submission handoff sheet, expert review index, defense rehearsal pack, defense rehearsal scorecard, defense rehearsal result packet, expert feedback request packet, expert feedback outreach ledger, timed rehearsal schedule ledger, hard evidence closure board, hard evidence action pack, external evidence execution kit, hard evidence ledger, application validation, application value quantification, numeric traceability, no-answer boundary, claim integrity, rubric defense coverage, runtime reproducibility snapshot, verification transcript, fixed scenario demo, scenario walkthrough script, expert feedback protocol, evaluation dataset, evaluation coverage profile, evidence manifest, evidence hashes, live smoke, browser smoke, screenshots, KG artifact links",
        "",
        "| Gate | Result | Evidence |",
        "| --- | --- | --- |",
    ]
    for item in checks:
        result = "pass" if item.passed else "fail"
        lines.append(f"| {item.name} | {result} | {item.detail.replace('|', '/')} |")
    lines.extend(
        [
            "",
            "## Required Browser Checks",
            "",
            ", ".join(sorted(REQUIRED_BROWSER_CHECKS)),
            "",
            "## Boundary",
            "",
            "This gate proves package readiness and demo evidence completeness. It does not claim final award probability; judges still evaluate innovation, presentation, and live defense quality.",
        ]
    )
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return payload


def main() -> int:
    checks = run_gate()
    payload = write_report(checks)
    print(f"Wrote {REPORT_MD.relative_to(REPO_ROOT)}")
    print(f"Status: {payload['status']} ({payload['passed']}/{payload['total']} gates)")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
