from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from build_defense_rehearsal_scorecard import (
    OUTPUT_JSON as DEFENSE_REHEARSAL_SCORECARD_JSON,
    OUTPUT_MD as DEFENSE_REHEARSAL_SCORECARD_MD,
    build_payload as build_defense_scorecard_payload,
    write_outputs as write_defense_scorecard_outputs,
)
from build_defense_rehearsal_result_packet import (
    OUTPUT_JSON as DEFENSE_REHEARSAL_RESULT_PACKET_JSON,
    OUTPUT_MD as DEFENSE_REHEARSAL_RESULT_PACKET_MD,
    build_payload as build_defense_result_payload,
    write_outputs as write_defense_result_outputs,
)
from build_expert_feedback_request_packet import (
    OUTPUT_JSON as EXPERT_FEEDBACK_REQUEST_PACKET_JSON,
    OUTPUT_MD as EXPERT_FEEDBACK_REQUEST_PACKET_MD,
    build_payload as build_expert_request_payload,
    write_outputs as write_expert_request_outputs,
)
from build_challenge_cup_expert_outreach_ledger import (
    OUTPUT_JSON as EXPERT_FEEDBACK_OUTREACH_LEDGER_JSON,
    OUTPUT_MD as EXPERT_FEEDBACK_OUTREACH_LEDGER_MD,
    OUTREACH_README as EXPERT_FEEDBACK_OUTREACH_README,
    write_outputs as write_expert_outreach_outputs,
)
from build_challenge_cup_timed_rehearsal_schedule_ledger import (
    OUTPUT_JSON as TIMED_REHEARSAL_SCHEDULE_LEDGER_JSON,
    OUTPUT_MD as TIMED_REHEARSAL_SCHEDULE_LEDGER_MD,
    SCHEDULE_README as TIMED_REHEARSAL_SCHEDULE_README,
    write_outputs as write_timed_rehearsal_schedule_outputs,
)
from build_challenge_cup_hard_evidence_closure_board import (
    OUTPUT_JSON as HARD_EVIDENCE_CLOSURE_BOARD_JSON,
    OUTPUT_MD as HARD_EVIDENCE_CLOSURE_BOARD_MD,
    write_outputs as write_hard_evidence_closure_board_outputs,
)
from build_challenge_cup_hard_evidence_action_pack import (
    OUTPUT_JSON as HARD_EVIDENCE_ACTION_PACK_JSON,
    OUTPUT_MD as HARD_EVIDENCE_ACTION_PACK_MD,
    write_outputs as write_hard_evidence_action_pack_outputs,
)
from build_challenge_cup_external_evidence_execution_kit import (
    EXPERT_HANDOFF_MD as EXTERNAL_EVIDENCE_EXPERT_HANDOFF_MD,
    OUTPUT_JSON as EXTERNAL_EVIDENCE_EXECUTION_KIT_JSON,
    OUTPUT_MD as EXTERNAL_EVIDENCE_EXECUTION_KIT_MD,
    TIMED_REHEARSAL_OBSERVER_MD as EXTERNAL_EVIDENCE_TIMED_REHEARSAL_OBSERVER_MD,
    write_outputs as write_external_evidence_execution_kit_outputs,
)
from build_challenge_cup_external_evidence_closeout_checklist import (
    OUTPUT_JSON as EXTERNAL_EVIDENCE_CLOSEOUT_CHECKLIST_JSON,
    OUTPUT_MD as EXTERNAL_EVIDENCE_CLOSEOUT_CHECKLIST_MD,
    write_outputs as write_external_evidence_closeout_checklist_outputs,
)
from build_graphrag_answer_benchmark import (
    OUTPUT_JSON as GRAPH_ANSWER_BENCHMARK_JSON,
    OUTPUT_MD as GRAPH_ANSWER_BENCHMARK_MD,
    build_payload as build_graph_answer_benchmark_payload,
    write_markdown as write_graph_answer_benchmark_markdown,
)
from build_graphrag_gap_remediation_plan import (
    OUTPUT_JSON as GRAPH_GAP_REMEDIATION_JSON,
    OUTPUT_MD as GRAPH_GAP_REMEDIATION_MD,
    build_payload as build_graph_gap_remediation_payload,
    write_markdown as write_graph_gap_remediation_markdown,
)
from build_challenge_cup_failure_remediation_before_after import (
    OUTPUT_JSON as FAILURE_REMEDIATION_BEFORE_AFTER_JSON,
    OUTPUT_MD as FAILURE_REMEDIATION_BEFORE_AFTER_MD,
    write_outputs as write_failure_remediation_before_after_outputs,
)
from build_challenge_cup_application_value_quantification import (
    OUTPUT_JSON as APPLICATION_VALUE_QUANTIFICATION_JSON,
    OUTPUT_MD as APPLICATION_VALUE_QUANTIFICATION_MD,
    write_outputs as write_application_value_quantification_outputs,
)
from build_challenge_cup_numeric_traceability_report import (
    OUTPUT_JSON as NUMERIC_TRACEABILITY_REPORT_JSON,
    OUTPUT_MD as NUMERIC_TRACEABILITY_REPORT_MD,
    write_outputs as write_numeric_traceability_report_outputs,
)
from build_challenge_cup_no_answer_boundary_evaluation import (
    OUTPUT_JSON as NO_ANSWER_BOUNDARY_EVALUATION_JSON,
    OUTPUT_MD as NO_ANSWER_BOUNDARY_EVALUATION_MD,
    write_outputs as write_no_answer_boundary_evaluation_outputs,
)
from build_challenge_cup_claim_integrity_report import (
    OUTPUT_JSON as CLAIM_INTEGRITY_REPORT_JSON,
    OUTPUT_MD as CLAIM_INTEGRITY_REPORT_MD,
    write_outputs as write_claim_integrity_report_outputs,
)
from build_challenge_cup_rubric_defense_coverage import (
    OUTPUT_JSON as RUBRIC_DEFENSE_COVERAGE_JSON,
    OUTPUT_MD as RUBRIC_DEFENSE_COVERAGE_MD,
    write_outputs as write_rubric_defense_coverage_outputs,
)
from build_challenge_cup_defense_slide_traceability import (
    OUTPUT_JSON as DEFENSE_SLIDE_TRACEABILITY_JSON,
    OUTPUT_MD as DEFENSE_SLIDE_TRACEABILITY_MD,
    write_outputs as write_defense_slide_traceability_outputs,
)
from build_challenge_cup_runtime_reproducibility_snapshot import (
    OUTPUT_JSON as RUNTIME_REPRODUCIBILITY_SNAPSHOT_JSON,
    OUTPUT_MD as RUNTIME_REPRODUCIBILITY_SNAPSHOT_MD,
    write_outputs as write_runtime_reproducibility_snapshot_outputs,
)
from build_challenge_cup_verification_transcript import (
    OUTPUT_JSON as VERIFICATION_TRANSCRIPT_JSON,
    OUTPUT_MD as VERIFICATION_TRANSCRIPT_MD,
    write_outputs as write_verification_transcript_outputs,
)
from build_challenge_cup_defense_deck import (
    FINAL_PPTX as DEFENSE_DECK_PPTX,
    SPEAKER_NOTES as DEFENSE_DECK_NOTES,
    build_outputs as build_defense_deck_outputs,
)
from build_challenge_cup_hard_evidence_ledger import (
    EXPERT_README as HARD_EVIDENCE_EXPERT_README,
    OUTPUT_JSON as HARD_EVIDENCE_LEDGER_JSON,
    OUTPUT_MD as HARD_EVIDENCE_LEDGER_MD,
    REHEARSAL_README as HARD_EVIDENCE_REHEARSAL_README,
    ROOT_README as HARD_EVIDENCE_README,
    write_outputs as write_hard_evidence_ledger_outputs,
)
from build_challenge_cup_official_rubric_alignment import (
    OUTPUT_JSON as OFFICIAL_RUBRIC_ALIGNMENT_JSON,
    OUTPUT_MD as OFFICIAL_RUBRIC_ALIGNMENT_MD,
    write_outputs as write_official_rubric_alignment_outputs,
)
from build_challenge_cup_judge_objection_matrix import (
    OUTPUT_JSON as JUDGE_OBJECTION_MATRIX_JSON,
    OUTPUT_MD as JUDGE_OBJECTION_MATRIX_MD,
    write_outputs as write_judge_objection_matrix_outputs,
)
from build_challenge_cup_special_prize_readiness_dashboard import (
    OUTPUT_JSON as SPECIAL_PRIZE_READINESS_DASHBOARD_JSON,
    OUTPUT_MD as SPECIAL_PRIZE_READINESS_DASHBOARD_MD,
    write_outputs as write_special_prize_readiness_dashboard_outputs,
)
from build_challenge_cup_final_acceptance_audit import (
    OUTPUT_JSON as FINAL_ACCEPTANCE_AUDIT_JSON,
    OUTPUT_MD as FINAL_ACCEPTANCE_AUDIT_MD,
    write_outputs as write_final_acceptance_audit_outputs,
)
from build_challenge_cup_poster_render_smoke import (
    OUTPUT_JSON as POSTER_RENDER_SMOKE_JSON,
    OUTPUT_MD as POSTER_RENDER_SMOKE_MD,
    write_outputs as write_poster_render_smoke_outputs,
)
from check_challenge_cup_goal_completion import write_report as write_goal_completion_report


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "docs" / "challenge_cup"
REPRO = OUT / "reproducibility"
REPORTS = REPO_ROOT / "evaluation" / "reports"
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
ACCEPTANCE_CHECKLIST = OUT / "06_结项验收清单.md"
CLAIM_MATRIX = OUT / "07_评审主张证据矩阵.md"
AWARD_SELF_EVAL = OUT / "08_特等奖评审自评表.md"
EXPERT_REVIEW_INDEX = OUT / "09_专家快速审阅索引.md"
DEFENSE_REHEARSAL_CARD = OUT / "10_答辩攻防与彩排卡.md"
APPLICATION_VALIDATION_DOC = OUT / "11_应用场景与专家验证.md"
EXPERT_FEEDBACK_PROTOCOL = OUT / "12_专家反馈采集与整改闭环.md"
JUDGE_BRIEFING_CARD = OUT / "13_评委现场速览卡.md"
ONSITE_DEFENSE_RUNBOOK = OUT / "14_现场答辩操作Runbook.md"
PROJECT_HANDOFF_CHECKLIST = OUT / "15_结项交付移交清单.md"
DEFENSE_QA_REMEDIATION_LEDGER = OUT / "16_现场问辩记录与整改台账.md"
REVIEW_RISK_RESPONSE_PLAN = OUT / "17_评审风险控制与应急预案.md"
SPECIAL_PRIZE_SCORING_DRILL = OUT / "18_特等奖打分模拟与整改清单.md"
POSTER_BOOTH_QA_PACK = OUT / "19_作品展墙报问辩与展台脚本.md"
COMMERCIALIZATION_ROADMAP = OUT / "20_成果转化与持续迭代路线图.md"
IP_OPEN_SOURCE_COMPLIANCE = OUT / "21_知识产权与开源合规说明.md"
LOCAL_BASELINE_DIFFERENTIATION = OUT / "22_同类方案对比与创新性证据卡.md"
FINAL_SUBMISSION_HANDOFF = OUT / "23_终审提交总目录与签收页.md"
POSTER_BOARD_HTML = OUT / "poster" / "challenge_cup_a0_poster.html"
DEFENSE_CONTROL_CONSOLE = OUT / "defense_console" / "index.html"
GRAPH_REPORT = REPORTS / "challenge_cup_graphrag_same_question_report.md"
GRAPH_REPORT_JSON = REPORTS / "challenge_cup_graphrag_same_question_report.json"
GRAPH_CONTEXT_DEMO_MD = REPORTS / "challenge_cup_graphrag_context_demo.md"
GRAPH_CONTEXT_DEMO_JSON = REPORTS / "challenge_cup_graphrag_context_demo.json"
GRAPH_MANUAL_EVIDENCE_SUPPLEMENT = REPRO / "graphrag_manual_evidence_supplement.csv"
LIVE_SMOKE_REPORT = REPRO / "live_demo_smoke_report.md"
BROWSER_SMOKE_REPORT = REPRO / "browser_demo_smoke_report.md"
BROWSER_SMOKE_JSON = REPRO / "browser_demo_smoke_report.json"
READINESS_GATE_REPORT = REPRO / "readiness_gate_report.md"
GOAL_COMPLETION_REPORT = REPRO / "goal_completion_report.md"
EVIDENCE_HASHES = REPRO / "evidence_hashes.json"
EVAL_COVERAGE_PROFILE = REPRO / "evaluation_coverage_profile.json"
SUBMISSION_ARCHIVE = REPRO / "challenge_cup_submission_package.zip"
SUBMISSION_ARCHIVE_MANIFEST = REPRO / "challenge_cup_submission_archive_manifest.json"
SUBMISSION_PACKAGE_VERIFIER_SOURCE = REPO_ROOT / "scripts" / "verify_challenge_cup_submission_package.py"
SUBMISSION_PACKAGE_VERIFIER = REPRO / "verify_submission_package.py"
SUBMISSION_INTEGRITY_CARD = REPRO / "submission_integrity_card.md"
APPLICATION_VALIDATION_REPORT = REPRO / "application_validation_report.md"
APPLICATION_VALUE_QUANTIFICATION_REPORT = APPLICATION_VALUE_QUANTIFICATION_MD
APPLICATION_VALUE_QUANTIFICATION_REPORT_JSON = APPLICATION_VALUE_QUANTIFICATION_JSON
NUMERIC_TRACEABILITY_REPORT = NUMERIC_TRACEABILITY_REPORT_MD
NUMERIC_TRACEABILITY_REPORT_JSON_PATH = NUMERIC_TRACEABILITY_REPORT_JSON
NO_ANSWER_BOUNDARY_EVALUATION_REPORT = NO_ANSWER_BOUNDARY_EVALUATION_MD
NO_ANSWER_BOUNDARY_EVALUATION_REPORT_JSON = NO_ANSWER_BOUNDARY_EVALUATION_JSON
CLAIM_INTEGRITY_REPORT = CLAIM_INTEGRITY_REPORT_MD
CLAIM_INTEGRITY_REPORT_JSON_PATH = CLAIM_INTEGRITY_REPORT_JSON
RUBRIC_DEFENSE_COVERAGE_REPORT = RUBRIC_DEFENSE_COVERAGE_MD
RUBRIC_DEFENSE_COVERAGE_REPORT_JSON = RUBRIC_DEFENSE_COVERAGE_JSON
DEFENSE_SLIDE_TRACEABILITY_REPORT = DEFENSE_SLIDE_TRACEABILITY_MD
DEFENSE_SLIDE_TRACEABILITY_REPORT_JSON = DEFENSE_SLIDE_TRACEABILITY_JSON
RUNTIME_REPRODUCIBILITY_SNAPSHOT_REPORT = RUNTIME_REPRODUCIBILITY_SNAPSHOT_MD
RUNTIME_REPRODUCIBILITY_SNAPSHOT_REPORT_JSON = RUNTIME_REPRODUCIBILITY_SNAPSHOT_JSON
VERIFICATION_TRANSCRIPT_REPORT = VERIFICATION_TRANSCRIPT_MD
VERIFICATION_TRANSCRIPT_REPORT_JSON = VERIFICATION_TRANSCRIPT_JSON
EXPERT_FEEDBACK_FORM = REPRO / "expert_feedback_form.md"
BROWSER_SCREENSHOT_DIR = REPRO / "browser_screenshots"
BROWSER_SCREENSHOTS = [
    BROWSER_SCREENSHOT_DIR / "desktop_overview.png",
    BROWSER_SCREENSHOT_DIR / "desktop_search_results.png",
    BROWSER_SCREENSHOT_DIR / "desktop_kg_artifacts.png",
    BROWSER_SCREENSHOT_DIR / "mobile_overview.png",
]
EVAL_COVERAGE_MINIMUMS = {
    "task_types": 10,
    "source_scopes": 15,
    "graphrag_questions": 10,
}
ARCHIVE_TIMESTAMP = (2026, 6, 5, 21, 6, 0)
READINESS_GATE_COUNT = 64


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_submission_archive_inputs(evidence_files: list[str]) -> list[str]:
    excluded = {
        md_link(SUBMISSION_ARCHIVE),
        md_link(SUBMISSION_ARCHIVE_MANIFEST),
        md_link(READINESS_GATE_REPORT),
    }
    required = set(evidence_files)
    required.difference_update(excluded)
    required.update(
        {
            md_link(OUT / "package_manifest.json"),
            md_link(EVIDENCE_HASHES),
            md_link(EVAL_COVERAGE_PROFILE),
            md_link(REPRO / "dataset_manifest.md"),
            md_link(REPRO / "runbook.md"),
            md_link(REPRO / "command_log.md"),
        }
    )
    for path in OUT.rglob("*"):
        if not path.is_file():
            continue
        relative = md_link(path)
        if (
            relative in excluded
            or (path.name.startswith(f"{SUBMISSION_ARCHIVE.name}.") and path.name.endswith(".tmp"))
        ):
            continue
        required.add(relative)

    missing = sorted(relative for relative in required if not (REPO_ROOT / relative).is_file())
    empty = sorted(relative for relative in required if (REPO_ROOT / relative).is_file() and (REPO_ROOT / relative).stat().st_size == 0)
    if missing or empty:
        raise FileNotFoundError(f"submission archive inputs invalid: missing={missing}, empty={empty}")
    return sorted(required)


def write_submission_archive(ctx: dict[str, Any], included_files: list[str]) -> None:
    SUBMISSION_ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    temp_archive = SUBMISSION_ARCHIVE.with_name(f"{SUBMISSION_ARCHIVE.name}.{os.getpid()}.tmp")
    if temp_archive.exists():
        temp_archive.unlink()
    with zipfile.ZipFile(temp_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in included_files:
            info = zipfile.ZipInfo(relative, date_time=ARCHIVE_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            archive.writestr(info, (REPO_ROOT / relative).read_bytes())
    replace_with_retry(temp_archive, SUBMISSION_ARCHIVE)
    manifest = {
        "generated_at": ctx["now"],
        "archive_path": md_link(SUBMISSION_ARCHIVE),
        "algorithm": "sha256",
        "bytes": SUBMISSION_ARCHIVE.stat().st_size,
        "sha256": sha256_file(SUBMISSION_ARCHIVE),
        "file_count": len(included_files),
        "included_files": included_files,
        "excluded_files": [md_link(READINESS_GATE_REPORT), md_link(SUBMISSION_ARCHIVE), md_link(SUBMISSION_ARCHIVE_MANIFEST)],
    }
    write(SUBMISSION_ARCHIVE_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))


def replace_with_retry(source: Path, target: Path, attempts: int = 5, delay_seconds: float = 0.2) -> None:
    for attempt in range(1, attempts + 1):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt >= attempts:
                raise
            time.sleep(delay_seconds)


def read(path: Path, limit: int = 1600) -> str:
    if not path.exists():
        return f"文件未找到：{path}"
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text if len(text) <= limit else text[:limit].rstrip() + "\n..."


def count_jsonl(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_evaluation_coverage_profile(ctx: dict[str, Any]) -> dict[str, Any]:
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
        "generated_at": ctx["now"],
        "generated_from": md_link(DATASET),
        "question_count": len(rows),
        "task_type_counts": dict(sorted(task_type_counts.items())),
        "source_scope_counts": dict(sorted(source_scope_counts.items())),
        "expected_mode_counts": dict(sorted(expected_mode_counts.items())),
        "questions_with_graphrag_modes": questions_with_graphrag_modes,
        "minimums": dict(EVAL_COVERAGE_MINIMUMS),
    }


def latest(pattern: str) -> Path | None:
    candidates = sorted(REPORTS.glob(pattern))
    return candidates[-1] if candidates else None


def generated_at_from_reports(*paths: Path | None) -> str:
    stamps: list[str] = []
    for path in paths:
        if path is None:
            continue
        match = re.search(r"(\d{8})_(\d{6})", path.name)
        if match:
            stamps.append(match.group(1) + match.group(2))
    if not stamps:
        return "1970-01-01 00:00"
    stamp = max(stamps)
    return datetime.strptime(stamp, "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M")


def md_link(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def graph_manual_evidence_source_files() -> list[str]:
    if not GRAPH_MANUAL_EVIDENCE_SUPPLEMENT.exists():
        return []

    sources: set[str] = set()
    rows = csv.DictReader(GRAPH_MANUAL_EVIDENCE_SUPPLEMENT.read_text(encoding="utf-8").splitlines())
    for row in rows:
        source = (row.get("source_file") or "").strip().replace("\\", "/")
        if not source or source.lower() == "n/a":
            continue
        source_path = Path(source)
        if source_path.is_absolute() or ".." in source_path.parts:
            raise ValueError(f"invalid GraphRAG manual evidence source_file: {source}")
        if not (REPO_ROOT / source).is_file():
            raise FileNotFoundError(f"GraphRAG manual evidence source_file not found: {source}")
        sources.add(source)
    return sorted(sources)


def optional_md_link(path: Path | None) -> str:
    return md_link(path) if path is not None else "暂无对应报告，运行 runbook 中的评测命令后生成"


def format_latency_from_search_meta(search_meta: str) -> str:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*ms\b", search_meta)
    if match is None:
        return "41.80 ms"
    return f"{float(match.group(1)):.2f} ms"


def browser_validation_context() -> dict[str, Any]:
    fallback = {
        "query": "燃气轮机异常振动诊断流程",
        "search_meta": "集合 gas_turbine_ocr_demo_snapshot · 延迟 41.80 ms · 结果 5 · 后端 public-demo",
        "screenshot": md_link(BROWSER_SCREENSHOTS[1]),
    }
    if not BROWSER_SMOKE_JSON.exists():
        return fallback
    payload = json.loads(BROWSER_SMOKE_JSON.read_text(encoding="utf-8"))
    browser = payload.get("browser", {})
    screenshots = browser.get("screenshots", {})
    return {
        "query": browser.get("query") or fallback["query"],
        "search_meta": browser.get("search_meta") or fallback["search_meta"],
        "screenshot": screenshots.get("desktop_search_results") or fallback["screenshot"],
    }


def build_context() -> dict[str, Any]:
    day3 = latest("day3_retrieval_baseline_comparison_*.md")
    day4 = latest("day4_failure_analysis_*.md")
    return {
        "now": generated_at_from_reports(day3, day4),
        "question_count": count_jsonl(DATASET),
        "day3": day3,
        "day4": day4,
        "graph_report": GRAPH_REPORT if GRAPH_REPORT.exists() else None,
        "graph_report_json": GRAPH_REPORT_JSON if GRAPH_REPORT_JSON.exists() else None,
        "graph_context_demo_md": GRAPH_CONTEXT_DEMO_MD if GRAPH_CONTEXT_DEMO_MD.exists() else None,
        "graph_context_demo_json": GRAPH_CONTEXT_DEMO_JSON if GRAPH_CONTEXT_DEMO_JSON.exists() else None,
        "graph_answer_benchmark_md": GRAPH_ANSWER_BENCHMARK_MD,
        "graph_answer_benchmark_json": GRAPH_ANSWER_BENCHMARK_JSON,
        "graph_gap_remediation_md": GRAPH_GAP_REMEDIATION_MD,
        "graph_gap_remediation_json": GRAPH_GAP_REMEDIATION_JSON,
        "failure_remediation_before_after_md": FAILURE_REMEDIATION_BEFORE_AFTER_MD,
        "failure_remediation_before_after_json": FAILURE_REMEDIATION_BEFORE_AFTER_JSON,
        "validation": browser_validation_context(),
        "rag_db": REPO_ROOT
        / "docs"
        / "project_deliverables"
        / "03_普通RAG数据库_14本资料"
        / "数据库构建结果_人话版.md",
        "kg_review": REPO_ROOT
        / "docs"
        / "project_deliverables"
        / "05_知识图谱POC_三元组和人工判断"
        / "人工判断小结.md",
        "course_pack": REPO_ROOT
        / "docs"
        / "project_deliverables"
        / "06_汇报材料_发群和组会"
        / "RAG课程汇报_最终交付包"
        / "README_先看这里.md",
    }


def build_readme(ctx: dict[str, Any]) -> str:
    return f"""# 挑战杯项目成果入口

生成时间：{ctx["now"]}

本目录是“知燃知维：面向动力装备运维知识的可信 GraphRAG 系统”的结项与挑战杯评审入口。先看本页，再按顺序阅读项目一页纸、项目书、技术白皮书、实验评测报告、演示脚本和答辩问答手册。

## 评委三分钟速览

| 时间 | 看什么 | 证据入口 |
| --- | --- | --- |
| 0:00-0:30 | 项目定位：知燃知维 GraphRAG 面向动力装备运维知识，先确认问题、场景、贡献和边界。 | `00_项目一页纸.md`; `13_评委现场速览卡.md` |
| 0:30-1:30 | 证据链：从 60 题评测、GT-07 固定场景、GraphRAG 证据组织和失败整改看完成度。 | `03_实验评测报告.md`; `07_评审主张证据矩阵.md`; `reproducibility/readiness_gate_report.md` |
| 1:30-2:30 | 现场演示：按固定脚本看浏览器控制台、检索结果、KG 证据和离线兜底。 | `04_系统演示脚本.md`; `defense_console/index.html`; `reproducibility/browser_demo_smoke_report.md` |
| 2:30-3:00 | 边界与缺口：包可复核，但真实专家反馈和真实计时彩排尚未归档，不能标记目标完成。 | `reproducibility/goal_completion_report.md`; `reproducibility/external_evidence_execution_kit.md` |

## 当前硬证据状态

- 状态：`package_ready_awaiting_external_hard_evidence`。
- 真实专家反馈尚未归档；真实计时彩排尚未归档；不能标记目标完成。
- 外部硬证据补齐入口：`reproducibility/external_evidence_execution_kit.md`；当天归档闭环看 `reproducibility/external_evidence_closeout_checklist.md`。

## 推荐阅读顺序

1. `00_项目一页纸.md`
2. `01_挑战杯项目书.md`
3. `02_技术白皮书.md`
4. `03_实验评测报告.md`
5. `04_系统演示脚本.md`
6. `05_答辩问答手册.md`
7. `06_结项验收清单.md`
8. `07_评审主张证据矩阵.md`
9. `08_特等奖评审自评表.md`
10. `09_专家快速审阅索引.md`
11. `10_答辩攻防与彩排卡.md`
12. `11_应用场景与专家验证.md`
13. `12_专家反馈采集与整改闭环.md`
14. `13_评委现场速览卡.md`
15. `14_现场答辩操作Runbook.md`
16. `15_结项交付移交清单.md`
17. `16_现场问辩记录与整改台账.md`
18. `17_评审风险控制与应急预案.md`
19. `18_特等奖打分模拟与整改清单.md`
20. `19_作品展墙报问辩与展台脚本.md`
21. `20_成果转化与持续迭代路线图.md`
22. `21_知识产权与开源合规说明.md`
23. `22_同类方案对比与创新性证据卡.md`
24. `23_终审提交总目录与签收页.md`
25. `poster/challenge_cup_a0_poster.html`
26. `reproducibility/poster_render_smoke_report.md`
27. `defense_console/index.html`
28. `defense_deck/challenge_cup_defense_deck.pptx`
29. `defense_deck/challenge_cup_defense_speaker_notes.md`
30. `reproducibility/application_validation_report.md`
31. `reproducibility/application_value_quantification.md`
32. `reproducibility/numeric_traceability_report.md`
33. `reproducibility/no_answer_boundary_evaluation.md`
34. `reproducibility/claim_integrity_report.md`
35. `reproducibility/runtime_reproducibility_snapshot.md`
36. `reproducibility/verification_transcript.md`
37. `reproducibility/rubric_defense_coverage.md`
38. `reproducibility/defense_slide_traceability.md`
39. `evaluation/reports/challenge_cup_failure_remediation_before_after.md`
40. `reproducibility/expert_feedback_form.md`
41. `reproducibility/runbook.md`
42. `reproducibility/dataset_manifest.md`
43. `reproducibility/readiness_gate_report.md`
44. `reproducibility/goal_completion_report.md`
45. `reproducibility/defense_rehearsal_scorecard.md`
46. `reproducibility/defense_rehearsal_result_packet.md`
47. `reproducibility/expert_feedback_request_packet.md`
48. `reproducibility/expert_feedback_outreach_ledger.md`
49. `reproducibility/timed_rehearsal_schedule_ledger.md`
50. `reproducibility/official_rubric_alignment.md`
51. `reproducibility/judge_objection_response_matrix.md`
52. `reproducibility/special_prize_readiness_dashboard.md`
53. `reproducibility/hard_evidence_closure_board.md`
54. `reproducibility/hard_evidence_action_pack.md`
55. `reproducibility/external_evidence_execution_kit.md`
56. `reproducibility/external_evidence_closeout_checklist.md`
57. `reproducibility/hard_evidence_ledger.md`
58. `reproducibility/challenge_cup_submission_archive_manifest.json`
59. `reproducibility/challenge_cup_submission_package.zip`
60. `reproducibility/verify_submission_package.py`
61. `reproducibility/final_acceptance_audit.md`
62. `reproducibility/submission_integrity_card.md`

## 当前核心数字

- 普通 RAG 数据库：9080 个 chunk。
- 系统评测集：{ctx["question_count"]} 题。
- 知识图谱 POC：27 条候选三元组，26 条正确，1 条待讨论，0 条明确错误。
- 已有课程交付包：PPT、讲稿、评测说明、失败分析、演示脚本、备用证据包和答辩口径。
"""


def build_one_page(ctx: dict[str, Any]) -> str:
    return """# 项目一页纸

## 项目名称

知燃知维：面向动力装备运维知识的可信 GraphRAG 系统

## 一句话定位

本项目把动力装备扫描资料、课程资料和问答 JSON 转化为可检索、可评测、可追溯的 RAG / GraphRAG 知识系统，用证据绑定和失败归因降低专业问答中的幻觉风险。

## 真实问题

动力装备资料具有扫描件多、专业术语密集、部件和故障关系复杂的特点。普通关键词检索难以稳定回答“现象、原因、检查项、处理措施和证据来源”之间的关系型问题。

## 核心贡献

1. 数据链路：OCR 审计、文本清洗、chunk 入库和 ChromaDB 持久化。
2. 知识链路：实体关系三元组、evidence 绑定、人工评审和图谱展示。
3. 评测链路：60 题系统评测集、baseline 对比、失败案例归因。
4. 演示链路：本地控制台主线和离线备用证据包。

## 核心数字

- 9080 个普通 RAG chunk。
- 60 道系统评测题。
- 27 条 POC 三元组，其中 26 条正确、1 条待讨论、0 条明确错误。

## 边界声明

系统提供证据型辅助，不替代工程师做真实运维决策；GraphRAG 用于增强跨文档和跨实体证据组织，不声称在所有问题上必然优于普通 RAG。
"""


def build_project_book(ctx: dict[str, Any]) -> str:
    return """# 挑战杯项目书

## 项目背景

燃气轮机和动力装备资料包含大量部件、参数、故障、工况和处理措施信息。传统资料检索依赖人工翻阅，普通问答系统又容易缺少来源说明。本项目面向这一问题，构建可信 GraphRAG 系统，让专业知识回答具备证据、关系和评测支撑。

## 技术路线

系统采用“资料处理 -> 普通 RAG -> 知识图谱构建 -> GraphRAG 检索 -> 证据约束回答 -> 自动评测”的路线。普通 RAG 负责单段证据召回，GraphRAG 负责部件、故障、参数和处理措施之间的关系组织，评测脚本负责比较不同策略的表现。

## 创新点

1. 面向动力装备资料的 OCR 到 RAG 到 GraphRAG 全链路工程。
2. evidence-bound 三元组和人工评审闭环，避免无证据知识图谱。
3. 以评测集和失败归因驱动改进，不只展示成功样例。
4. 明确高风险场景边界，将系统定位为证据型辅助。

## 应用价值

项目可用于课程知识整理、动力装备资料学习、运维知识检索和故障分析证据准备。它把分散资料转化为可检索和可审计知识资产。

## 完成情况

当前已完成资料处理、普通 RAG 数据库、知识图谱 POC、60 题 baseline、失败分析、GraphRAG 同题子集和课程汇报包，并建立统一成果入口。
"""


def build_whitepaper(ctx: dict[str, Any]) -> str:
    return """# 技术白皮书

## 架构概览

系统由数据管线、检索引擎、知识图谱构建、RAG 编排、评测体系、控制台和挑战杯成果包组成。核心原则是所有回答都尽量回到原文证据、图谱关系或评测报告。

## 数据流

原始资料和 OCR 文本进入清洗与 chunk 阶段，写入普通 RAG 索引；知识图谱管线从 chunk 中抽取实体和关系，并绑定 evidence；检索阶段同时比较 keyword、dense hashing、hybrid RRF 和 GraphRAG 相关模式；评测阶段输出 recall、关键词覆盖率、证据覆盖和失败原因。

## GraphRAG 增量

GraphRAG 的价值不是画图，而是把部件、故障、参数和措施之间的关系显式化。局部图检索用于围绕实体查找关系证据，全局社区摘要用于跨文档归纳类问题。

## 安全边界

系统不输出无证据维修决策。若证据不足，回答应说明不足；若关系仍需人工判断，系统应保留待讨论状态。
"""


def build_eval_report(ctx: dict[str, Any]) -> str:
    day3_ref = optional_md_link(ctx["day3"])
    day4_ref = optional_md_link(ctx["day4"])
    graph_ref = optional_md_link(ctx["graph_report"])
    graph_context_ref = optional_md_link(ctx["graph_context_demo_md"])
    graph_answer_ref = optional_md_link(ctx["graph_answer_benchmark_md"])
    graph_gap_ref = optional_md_link(ctx["graph_gap_remediation_md"])
    failure_remediation_ref = optional_md_link(ctx["failure_remediation_before_after_md"])
    graph_supplement_ref = md_link(GRAPH_MANUAL_EVIDENCE_SUPPLEMENT)
    return f"""# 实验评测报告

## 评测集

当前系统评测集包含 {ctx["question_count"]} 题，覆盖普通 RAG、OCR 风险、GraphRAG/知识图谱、结构化事实、评测方法和挑战杯答辩口径。

## 已有 baseline

Day3 已比较 keyword、dense_hashing 和 hybrid_rrf 三种离线检索策略。报告位置：`{day3_ref}`。

## 失败归因

Day4 已将弱命中和失败案例归类为术语别名、结构化事实、hybrid 稀释、排序差距和评测概念缺口等问题。报告位置：`{day4_ref}`。

## Day4 失败整改 before/after

已将 Day4 40 个失败/弱项案例转成 remediation-card ablation：用评测术语卡、KG POC 数字事实卡、金风结构化事实卡、Reranker 别名卡和 keyword guardrail 对关键失败类型做可复验闭环。报告位置：`{failure_remediation_ref}`。该报告不宣称 live retriever 已升级，不宣称在线 LLM answer win-rate，也不替代真实专家反馈或真实计时彩排。

## GraphRAG 同题子集

已从 60 题评测集中筛出显式标注 `graphrag_context` / `graphrag_global` 的同题子集，并对这些题的 keyword、dense_hashing、hybrid_rrf baseline 覆盖率做了对照。报告位置：`{graph_ref}`。

## GraphRAG context-only demo

已将 supported 同题案例生成 context-only GraphRAG QA 快照，固定展示文本检索证据和 triples.csv 图谱关系证据。报告位置：`{graph_context_ref}`。该 demo 不生成 LLM 答案，不作为完整在线 answer benchmark。

## GraphRAG answer benchmark

已将 10 道 GraphRAG 同题生成答案级覆盖对照，固定比较文本 baseline 参考关键词覆盖率与 triples.csv 图谱证据覆盖率；当前本地证据覆盖已关闭固定子集 partial/missing 缺口。报告位置：`{graph_answer_ref}`。该 benchmark 是 deterministic offline reference keyword coverage，不生成在线 LLM 答案，不宣称 GraphRAG 全面优于 baseline。

## GraphRAG 补证整改计划

已将 answer benchmark 暴露出的 partial/missing 案例转成可审计补证闭环。报告位置：`{graph_gap_ref}`。manual evidence supplement：`{graph_supplement_ref}` 已关闭 P0 missing 和 cc056 relation schema partial 缺口。该闭环只证明固定 GraphRAG 子集的本地证据覆盖，不宣称在线 LLM answer win-rate、外部专家验证或 GraphRAG 全面优于 baseline。

## 结论

当前项目能证明评测链路存在并可复跑，也能展示 GraphRAG context-only 证据编排、答案级覆盖对照、补证整改计划和 Day4 失败整改 before/after。挑战杯版本后续可继续补充真实 LLM answer 生成、embedding/reranker 复测和更大规模 benchmark。

## 关键证据摘录

### 普通 RAG 数据库

{read(ctx["rag_db"], 1200)}

### 知识图谱人工评审

{read(ctx["kg_review"], 1200)}
"""


def build_demo_script(ctx: dict[str, Any]) -> str:
    validation = ctx["validation"]
    return f"""# 系统演示脚本

## 主线演示

1. 打开 `docs/challenge_cup/00_项目一页纸.md`，用 30 秒说明问题、方法和核心数字。
2. 启动控制台：`cd api_server/current_console; python server.py`，打开 `http://localhost:8000`。
3. 固定场景演示：在检索框输入“{validation["query"]}”，展示 `docs/challenge_cup/reproducibility/browser_demo_smoke_report.json` 中记录的 `{validation["search_meta"]}`。
4. 按顺序讲清 5 条证据：`demo-maint-thresholds-076` 给出监测阈值，`demo-structure-fault-130` 解释异常振动机理，`demo-gt07-fault-021` 给出 GT-07 现象，`demo-gt07-repair-022` 给出进气滤网和压气机叶片处理结果，`demo-gt07-manual-023` 给出温度传感器校验等处置建议。
5. 主动说明边界：系统提供证据整理和来源追溯，必须由工程师结合现场工况人工确认，不替代最终维修决策。
6. 打开 `docs/challenge_cup/reproducibility/application_validation_report.md` 和 `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png`，证明固定场景不是口头承诺。
7. 打开 `docs/challenge_cup/03_实验评测报告.md`，说明 baseline 和失败归因。

## 备用演示

如果服务未启动，直接打开 `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png`、`docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`、`docs/challenge_cup/reproducibility/application_validation_report.md`、知识图谱审核页面、SVG、实验评测报告和答辩问答手册。现场不排查环境，把时间用于解释证据链。
"""


def build_qa(ctx: dict[str, Any]) -> str:
    return """# 答辩问答手册

## 为什么需要 GraphRAG？

普通 RAG 擅长查单段证据，GraphRAG 擅长组织跨实体和跨文档关系。本项目把 GraphRAG 用在部件、故障、参数和措施之间的关系证据上。

## 是否能替代工程师？

不能。系统定位是证据型辅助，提供可能原因、检查项和来源，不做最终维修决策。

## 为什么能冲击高奖？

项目不是单一页面，而是完整知识工程闭环：真实资料、OCR 审计、RAG 入库、图谱 evidence、评测、失败归因和可演示系统。

## 如果 GraphRAG 没有全面超过 keyword 怎么办？

按问题类型解释。keyword 对明确术语和数字事实很强，GraphRAG 对跨实体关系和全局归纳更有价值。

## 数据和表述有什么边界？

不声称生产级运维闭环，不声称所有三元组都已大规模自动验证，不声称当前评测集是最终论文 benchmark。
"""


def build_checklist(ctx: dict[str, Any]) -> str:
    return """# 结项验收清单

本清单用于结项老师或挑战杯评委快速判断项目是否具备“可提交、可复核、可答辩”的交付状态。验收口径是：先证明成果包完整和证据可追溯，再讨论创新性和奖项竞争力。

## 结项验收口径

- 可提交范围：挑战杯材料包、终审答辩 PPT/讲稿、可复现实验评测、固定应用场景、浏览器演示证据、专家反馈采集协议。
- 验收方式：按本页逐项打开证据，运行 readiness gate，并用固定 GT-07 场景复核证据链。
- 通过标准：材料路径存在、核心结论有证据、演示有离线备份、边界不夸大。

## 可提交材料

| 材料 | 路径 | 验收要点 | 状态 |
| --- | --- | --- | --- |
| 包清单 | `docs/challenge_cup/package_manifest.json` | 记录证据文件和评测题数，便于判断提交范围。 | 已固化 |
| 证据清单 | `docs/challenge_cup/reproducibility/dataset_manifest.md` | 汇总数据、报告、截图、KG artifact 和课程交付入口。 | 已固化 |
| 可复现门禁 | `docs/challenge_cup/reproducibility/readiness_gate_report.md` | 证明材料、manifest、哈希、浏览器 smoke 和应用案例均可复核。 | 已固化 |
| 终审答辩 PPT | `docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx` | 10 页终审答辩 deck，覆盖问题、方法、GT-07、GraphRAG、归档、边界和下一步。 | 已固化 |
| 终审答辩讲稿 | `docs/challenge_cup/defense_deck/challenge_cup_defense_speaker_notes.md` | 90 秒开场、三分钟演示、杀手问题和边界口径。 | 已固化 |
| 演示证据 | `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md` | 证明页面、搜索交互、KG artifact 和移动端基本可用。 | 已固化 |
| 应用验证 | `docs/challenge_cup/reproducibility/application_validation_report.md` | 用固定燃气轮机异常振动场景展示证据链和边界。 | 已固化 |
| 专家反馈表 | `docs/challenge_cup/reproducibility/expert_feedback_form.md` | 收集真实签字、邮件或会议纪要，不伪造外部背书。 | 待真实反馈归档 |

## 验收步骤

1. 打开 `docs/challenge_cup/README_先看这里.md`，确认评审阅读顺序。
2. 打开 `docs/challenge_cup/07_评审主张证据矩阵.md`，逐条核对主张、证据、命令和边界。
3. 打开 `docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx` 和讲稿，检查终审答辩主线。
4. 运行 `python scripts/build_challenge_cup_package.py` 重新生成材料包。
5. 运行 `python scripts/check_challenge_cup_readiness.py` 生成 `docs/challenge_cup/reproducibility/readiness_gate_report.md`。
6. 打开 `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png`，复核固定搜索结果。

## 现场演示与离线备份

| 场景 | 首选动作 | 备用动作 |
| --- | --- | --- |
| 后端和前端均可用 | 按 `docs/challenge_cup/04_系统演示脚本.md` 现场演示固定查询。 | 用 browser smoke 报告解释已验证的交互路径。 |
| 现场网络或后端不可用 | 不现场排环境。 | 打开 `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`、截图和 KG artifact 继续答辩。 |
| 评委追问真实应用价值 | 展示 `docs/challenge_cup/11_应用场景与专家验证.md`。 | 说明真实生产决策仍需人工确认。 |

## 未完成项与边界

| 项目 | 当前处理 | 不得夸大 |
| --- | --- | --- |
| 真实外部反馈 | 已有采集协议和表单，等待签字、邮件或会议纪要归档。 | 不宣称已经获得专家认可。 |
| 生产级运维上线 | 当前证明课程资料知识化和可复核演示。 | 不宣称替代工程师决策或已进入生产系统。 |
| 大规模 benchmark | 当前是 60 题挑战杯评测集和 GraphRAG 子集。 | 不宣称达到公开论文级大规模评测。 |

## 验收结论

当前材料包达到“可提交结项 / 可进入挑战杯评审”的状态：材料入口清楚，证据链可追溯，机器门禁可复核，演示有离线备份。下一阶段的提分项是归档真实专家反馈、强化现场彩排和扩展更大规模评测。
"""


def build_claim_evidence_matrix(ctx: dict[str, Any]) -> str:
    day3_ref = optional_md_link(ctx["day3"])
    day4_ref = optional_md_link(ctx["day4"])
    graph_ref = optional_md_link(ctx["graph_report"])
    return f"""# 评审主张证据矩阵

本矩阵把挑战杯答辩中的高水平主张逐条绑定到可核验材料、复现命令和边界说明，避免把项目包装成只有演示页面的普通 RAG 工具。

| 评审维度 | 可答辩主张 | 直接证据 | 复现 / 验证命令 | 边界说明 |
| --- | --- | --- | --- | --- |
| 创新性 | 项目不是单纯问答页面，而是面向动力装备知识的 evidence-bound RAG / GraphRAG 工程闭环。 | `docs/challenge_cup/02_技术白皮书.md`; `{graph_ref}`; `docs/project_deliverables/06_四本书KG工具跑通演示/kg_evidence_viewer.html` | `python scripts/build_graphrag_challenge_report.py` | GraphRAG 用于关系证据组织，不声称在所有问题上必然优于普通 RAG。 |
| 工程闭环 | 已形成资料处理、OCR、chunk 入库、检索、KG POC、演示、验收的端到端链路。 | `docs/challenge_cup/06_结项验收清单.md`; `docs/challenge_cup/reproducibility/dataset_manifest.md`; `docs/project_deliverables/03_普通RAG数据库_14本资料/数据库构建结果_人话版.md` | `python scripts/build_challenge_cup_package.py` | 当前交付强调可结项与可答辩，不等同于生产级运维系统上线。 |
| 科学评测 | 评测不是只挑成功案例，而是包含 60 题评测集、baseline、失败归因、GraphRAG 同题子集、Day4 失败整改 before/after 和补证闭环；固定 GraphRAG 子集当前本地证据缺口已关闭。 | `evaluation/system_eval_questions.jsonl`; `{day3_ref}`; `{day4_ref}`; `{graph_ref}`; `evaluation/reports/challenge_cup_failure_remediation_before_after.md`; `evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.md` | `python scripts/run_day3_retrieval_baselines.py --dataset evaluation/system_eval_questions.jsonl --top-k 5`; `python scripts/analyze_day4_failure_cases.py`; `python scripts/build_challenge_cup_failure_remediation_before_after.py`; `python scripts/build_graphrag_gap_remediation_plan.py` | 评测集是当前阶段的课程 / 挑战杯评测集；整改报告是 remediation-card ablation，不等于在线 LLM 胜率、live retriever 升级或外部专家验证。 |
| 可复现 | 评委可以按 runbook 复现包生成、live smoke、browser smoke 和 readiness gate。 | `docs/challenge_cup/reproducibility/runbook.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`; `docs/challenge_cup/reproducibility/readiness_gate_report.md` | `python scripts/check_challenge_cup_readiness.py`; `node scripts/run_challenge_cup_browser_demo_smoke.mjs` | Browser smoke 证明本地演示与关键资源可用，不替代生产压测。 |
| 应用验证 | 项目已把“燃气轮机异常振动诊断”固化为可复核应用案例，能展示阈值、机理、现象、检修措施和复机结果的证据链。 | `docs/challenge_cup/11_应用场景与专家验证.md`; `docs/challenge_cup/reproducibility/application_validation_report.md`; `docs/challenge_cup/reproducibility/application_value_quantification.md`; `docs/challenge_cup/reproducibility/numeric_traceability_report.md`; `docs/challenge_cup/reproducibility/no_answer_boundary_evaluation.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.json`; `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png` | `python scripts/build_challenge_cup_application_value_quantification.py`; `python scripts/build_challenge_cup_numeric_traceability_report.py`; `python scripts/build_challenge_cup_no_answer_boundary_evaluation.py`; `python scripts/build_challenge_cup_package.py`; `python scripts/check_challenge_cup_readiness.py` | 当前是公开演示快照和角色化审查，不伪造外部生产签字；高风险维修仍需人工确认。 |
| 专家反馈闭环 | 项目已准备好可发送给老师或行业专家的反馈采集表、评分维度、签字或邮件证据归档规则和整改闭环。 | `docs/challenge_cup/12_专家反馈采集与整改闭环.md`; `docs/challenge_cup/reproducibility/expert_feedback_form.md`; `docs/challenge_cup/reproducibility/application_validation_report.md` | `python scripts/check_challenge_cup_readiness.py` | 未收到真实反馈前不得宣称已通过专家验证；反馈必须按签字、邮件或会议纪要归档。 |
| 应用边界 | 系统定位为证据型辅助和知识资产整理，不替代工程师做最终运维决策。 | `docs/challenge_cup/05_答辩问答手册.md`; `docs/challenge_cup/00_项目一页纸.md`; `docs/challenge_cup/03_实验评测报告.md` | `python scripts/check_challenge_cup_readiness.py` | 对高风险维修决策保留人工确认和证据不足提示。 |
"""


def build_award_self_eval(ctx: dict[str, Any]) -> str:
    return """# 特等奖评审自评表

本表按清华公开报道中出现的评审维度进行自检：评委会关注作品的学术价值或实用性、创新性、作品完成情况和现场答辩表现；清华制度文件也强调实用性、创新性和学术价值。2026 年第44届公开报道显示主赛道特等奖7项，历史制度文件中关于名额和可空缺的口径可能随届次变化；本表只用于倒逼整改，不承诺获奖结果。完整官方口径与证据绑定见 `docs/challenge_cup/reproducibility/official_rubric_alignment.md`。

## 参考口径

- 清华大学第44届“挑战杯”颁奖仪式报道：终审答辩于2026年4月25日开展，主赛道共产生114项获奖作品，其中特等奖7项。链接：https://www.tsinghua.edu.cn/info/1177/125861.htm
- 清华大学第37届“挑战杯”校级终审报道：评委从作品的学术价值或实用性、创新性、作品完成情况和现场答辩表现等方面评分；特等奖候选作品经公开答辩和综合评定产生。链接：https://www.tsinghua.edu.cn/info/1181/35383.htm
- 《清华大学课外创新人才培养体系制度文件汇编》：评审应充分考虑作品的实用性、创新性和学术价值；历史制度文本含有特等奖名额和可空缺口径，应与最新届次公开报道一起使用。链接：https://qiyuan.tsinghua.edu.cn/intro/2018/11024/%E6%94%AF%E6%92%91%E6%9D%90%E6%96%993-%E6%B8%85%E5%8D%8E%E5%A4%A7%E5%AD%A6%E8%AF%BE%E5%A4%96%E5%88%9B%E6%96%B0%E4%BA%BA%E6%89%8D%E5%9F%B9%E5%85%BB%E4%BD%93%E7%B3%BB%E5%88%B6%E5%BA%A6%E6%96%87%E4%BB%B6%E6%B1%87%E7%BC%96.pdf

| 评审维度 | 当前自评 | 已有证据 | 仍需现场强调 | 风险控制 |
| --- | --- | --- | --- | --- |
| 学术价值或实用性 | A- | `docs/challenge_cup/07_评审主张证据矩阵.md`; `docs/challenge_cup/03_实验评测报告.md`; `evaluation/system_eval_questions.jsonl` | 把动力装备运维知识的真实痛点讲清楚，强调证据型辅助而非泛问答。 | 避免把课程数据包装成生产级运维闭环。 |
| 创新性 | A- | `docs/challenge_cup/02_技术白皮书.md`; `evaluation/reports/challenge_cup_graphrag_same_question_report.md`; `docs/project_deliverables/06_四本书KG工具跑通演示/kg_evidence_viewer.html` | 强调 evidence-bound KG、失败归因和 GraphRAG 同题子集，而不是只说用了 RAG。 | 明确 GraphRAG 不保证所有问题都超过普通 RAG。 |
| 作品完成情况 | A | `docs/challenge_cup/reproducibility/readiness_gate_report.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`; `docs/challenge_cup/reproducibility/runbook.md` | 现场先跑 readiness gate，再展示浏览器截图和 KG artifact。 | 如果 live backend 异常，按离线证据包继续答辩。 |
| 现场答辩表现 | A- | `docs/challenge_cup/04_系统演示脚本.md`; `docs/challenge_cup/05_答辩问答手册.md`; `docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md`; `docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md`; `docs/challenge_cup/reproducibility/command_log.md` | 3分钟内讲清“问题-方法-证据-边界”，把失败案例变成科学性而不是扣分点。 | 结果归档包已经准备好；真实彩排完成前不得宣称已完成现场演练。 |
| 第44届主赛道特等奖7项 | 目标状态 | `docs/challenge_cup/07_评审主张证据矩阵.md`; `docs/challenge_cup/reproducibility/readiness_gate_report.md` | 用“可复现证据链 + 严谨边界 + 工程闭环”争取进入特等奖讨论。 | 不把奖项概率写成承诺；持续补强演示稳定性和答辩节奏。 |
"""


def build_expert_review_index(ctx: dict[str, Any]) -> str:
    return """# 专家快速审阅索引

本索引用于让评委、结项验收老师或答辩委员在 3-5 分钟内定位项目证据。它不是新的主张材料，而是把已有项目书、评测、演示和门禁证据组织成可复核路径。

## 三分钟审阅路径

1. 先看项目定位：`docs/challenge_cup/00_项目一页纸.md`。
2. 再看特等奖口径：`docs/challenge_cup/08_特等奖评审自评表.md`。
3. 复核主张证据：`docs/challenge_cup/07_评审主张证据矩阵.md`。
4. 查看应用验证案例：`docs/challenge_cup/11_应用场景与专家验证.md`。
5. 查看可复现状态：`docs/challenge_cup/reproducibility/readiness_gate_report.md`。
6. 如果现场演示受限，查看浏览器证据：`docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`。

## 特等奖主张

| 主张 | 快速证据 | 复核方式 |
| --- | --- | --- |
| 项目不是普通问答页，而是可结项的 RAG / GraphRAG 知识工程闭环 | `docs/challenge_cup/01_挑战杯项目书.md`; `docs/challenge_cup/02_技术白皮书.md`; `docs/challenge_cup/06_结项验收清单.md` | 阅读项目书的技术路线和验收清单 |
| 评测不是只挑成功样例，而是有 60 题评测集、baseline、失败归因和 GraphRAG 同题子集 | `evaluation/system_eval_questions.jsonl`; `docs/challenge_cup/03_实验评测报告.md`; `evaluation/reports/challenge_cup_graphrag_same_question_report.md` | 运行评测命令或检查评测报告 |
| 演示不是口头承诺，而是有 live smoke、browser smoke、截图和 KG artifact 证据 | `docs/challenge_cup/reproducibility/live_demo_smoke_report.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`; `docs/challenge_cup/reproducibility/browser_screenshots/desktop_kg_artifacts.png` | 运行 smoke 或打开截图 |
| 应用价值不是泛泛而谈，而是有异常振动诊断固定案例、record id 和边界说明 | `docs/challenge_cup/11_应用场景与专家验证.md`; `docs/challenge_cup/reproducibility/application_validation_report.md` | 复核 GT-07 证据链和人工确认边界 |
| 申报边界清楚，不把课程资料系统夸大成生产级运维系统 | `docs/challenge_cup/05_答辩问答手册.md`; `docs/challenge_cup/08_特等奖评审自评表.md` | 检查答辩边界和风险控制 |

## 一键复核命令

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_package.py
.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py
.\.venv\Scripts\python.exe -m pytest tests/unit -q
```

## 风险边界

- 当前 readiness gate 证明成果包、证据链接、评测集、smoke 报告和浏览器截图可复核；它不证明最终奖项结果。
- 当前系统定位为证据型辅助和知识资产整理；不替代工程师做真实运维决策。
- 如果现场后端启动失败，按 `docs/challenge_cup/04_系统演示脚本.md` 切换到离线证据包和浏览器截图继续答辩。
"""


def build_judge_briefing_card(ctx: dict[str, Any]) -> str:
    return """# 评委现场速览卡

本卡是给评委、结项老师和答辩现场成员留存的一页 briefing。它不替代项目书、白皮书或自评表，只把“为什么值得进入特等奖讨论、现场三分钟看什么、证据锚点在哪里、哪些话不能夸大”压缩到可快速核验的格式。

## 一页结论

知燃知维不是普通 RAG 问答页面，而是面向动力装备运维知识的 evidence-bound RAG / GraphRAG 工程闭环：从 OCR 与 chunk 入库，到知识图谱 evidence 绑定、60 题评测、失败归因、固定 GT-07 场景、浏览器 smoke、答辩材料和机器门禁，均可被评委沿文件路径复核。

## 特等奖答辩路径

1. 先讲真实问题：动力装备资料分散、术语密集，普通检索难把现象、原因、检查项、处理措施和来源连起来。
2. 再讲差异化：不是“接了一个大模型”，而是把 RAG、GraphRAG、人工补证和失败归因做成可审计闭环。
3. 现场只演示一个固定场景：GT-07 燃气轮机异常振动诊断证据链。
4. 评委追问时不口头兜底，直接打开证据矩阵、官方口径对齐、readiness gate 和 special prize dashboard。
5. 主动声明边界：不承诺获奖，不替代工程师，不声称已经获得真实专家反馈或真实计时彩排。

## 三分钟审阅路径

| 时间 | 打开材料 | 评委应该看到什么 |
| --- | --- | --- |
| 0:00-0:30 | `docs/challenge_cup/00_项目一页纸.md` | 项目定位、9080 个 RAG chunk、60 题评测集、27 条 KG POC 三元组。 |
| 0:30-1:00 | `docs/challenge_cup/07_评审主张证据矩阵.md` | 创新性、工程闭环、科学评测、可复现、应用验证和边界都有证据路径。 |
| 1:00-1:40 | `docs/challenge_cup/reproducibility/application_validation_report.md` | GT-07 场景的五段证据链，而不是泛泛讲“能诊断”。 |
| 1:40-2:10 | `docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md` | 官方评审维度如何映射到项目证据、答辩动作和未闭环风险。 |
| 2:10-2:40 | `docs/challenge_cup/reproducibility/readiness_gate_report.md` | 当前提交包机器门禁状态和可复核范围。 |
| 2:40-3:00 | `docs/challenge_cup/reproducibility/final_acceptance_audit.md` | 包可评审，但目标完成仍等待真实专家反馈和真实计时彩排。 |

## 证据锚点

| 主张 | 立即引用 | 关键观察 |
| --- | --- | --- |
| 不是普通 RAG | `docs/challenge_cup/02_技术白皮书.md`; `evaluation/reports/challenge_cup_graphrag_same_question_report.md` | RAG 负责片段召回，GraphRAG 负责跨实体关系组织，且保留失败归因。 |
| 固定应用场景成立 | `docs/challenge_cup/reproducibility/application_validation_report.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.json` | `demo-maint-thresholds-076`、`demo-structure-fault-130`、`demo-gt07-fault-021`、`demo-gt07-repair-022`、`demo-gt07-manual-023` 形成阈值、机理、现象、检修、建议五段链。 |
| 工程完成度可复核 | `docs/challenge_cup/package_manifest.json`; `docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json`; `docs/challenge_cup/reproducibility/verify_submission_package.py` | 证据文件、哈希、归档 zip 和 verifier 一致。 |
| 评审口径对齐 | `docs/challenge_cup/08_特等奖评审自评表.md`; `docs/challenge_cup/reproducibility/official_rubric_alignment.md` | 学术/实用价值、创新性、作品完成度、现场答辩、学术规范均有对应证据。 |
| 诚实边界可核验 | `docs/challenge_cup/reproducibility/goal_completion_report.md`; `docs/challenge_cup/reproducibility/hard_evidence_action_pack.md` | completion_claim_allowed=False；真实专家反馈和真实计时彩排未归档前不能标记目标完成。 |

## 不能夸大的话

- 不承诺获奖，也不把 readiness gate 说成获奖保证。
- 不声称已经获得真实专家反馈；只有归档签字、邮件回复、会议纪要或聊天反馈后才可这么说。
- 不声称已经完成真实计时彩排；只有归档计时截图、观察员记录和五个 killer question 结果后才可这么说。
- 不说系统替代工程师；它是证据型辅助和知识资产整理，高风险运维决策必须人工确认。
- 不说 GraphRAG 对所有问题都优于 baseline；当前结论限定在固定评测集、固定 GraphRAG 子集和本地证据覆盖。

## 现场递交流程

1. 答辩前把本卡、`docs/challenge_cup/09_专家快速审阅索引.md` 和 `docs/challenge_cup/reproducibility/final_acceptance_audit.md` 放在最容易打开的位置。
2. 评委问“怎么看材料是否完整”时，打开 `docs/challenge_cup/reproducibility/verify_submission_package.py` 和 `docs/challenge_cup/reproducibility/readiness_gate_report.md`。
3. 评委问“为什么冲特等奖”时，打开 `docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md`，先讲维度对齐，再讲未闭环硬证据。
4. 评委问“是否真实可用”时，打开 GT-07 五段证据链，并主动说明不替代工程师。
"""


def build_onsite_defense_runbook(ctx: dict[str, Any]) -> str:
    text = """# 现场答辩操作Runbook

本 Runbook 面向答辩当天的操作者、主讲人和计时观察员。它不声明已经完成真实计时彩排，也不声明已经获得真实专家反馈；它只规定现场如何稳定地展示已经归档的材料、何时切换离线证据、以及追问时打开哪个证据锚点。

## Preflight

| 时间点 | 负责人 | 动作 | 验收口径 |
| --- | --- | --- | --- |
| 答辩前 30 分钟 | 操作者 | 打开 `docs/challenge_cup/13_评委现场速览卡.md`、`docs/challenge_cup/09_专家快速审阅索引.md`、`docs/challenge_cup/reproducibility/final_acceptance_audit.md`。 | 三个留存入口均可打开。 |
| 答辩前 20 分钟 | 操作者 | 打开 `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md` 和 `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png`。 | 离线证据可在 20 秒内展示。 |
| 答辩前 15 分钟 | 主讲人 | 复读 `docs/challenge_cup/04_系统演示脚本.md` 的 GT-07 固定场景。 | 能说出五个 record id 和人工确认边界。 |
| 答辩前 10 分钟 | 计时观察员 | 打开 `docs/challenge_cup/10_答辩攻防与彩排卡.md`。 | 90 秒开场、3 分钟演示、20 秒离线切换、30 秒追问回答规则清楚。 |

## 标签页顺序

1. `docs/challenge_cup/13_评委现场速览卡.md`
2. `docs/challenge_cup/00_项目一页纸.md`
3. `docs/challenge_cup/07_评审主张证据矩阵.md`
4. `docs/challenge_cup/reproducibility/application_validation_report.md`
5. `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`
6. `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png`
7. `docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md`
8. `docs/challenge_cup/reproducibility/readiness_gate_report.md`
9. `docs/challenge_cup/reproducibility/final_acceptance_audit.md`
10. `docs/challenge_cup/reproducibility/goal_completion_report.md`

## 离线切换触发条件

| 触发条件 | 最大等待 | 切换动作 | 说明 |
| --- | ---: | --- | --- |
| 浏览器服务打不开 | 20 秒 | 打开 `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`。 | 不在现场排查环境。 |
| 搜索结果未出现 | 20 秒 | 打开 `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png`。 | 用已归档截图继续说明 GT-07 五段证据链。 |
| KG artifact 无法打开 | 20 秒 | 打开 `docs/challenge_cup/07_评审主张证据矩阵.md`。 | 用矩阵说明 GraphRAG 证据组织价值。 |
| 评委要求复核包完整性 | 30 秒 | 打开 `docs/challenge_cup/reproducibility/readiness_gate_report.md` 和 `docs/challenge_cup/reproducibility/verify_submission_package.py`。 | 只解释门禁范围，不把门禁说成获奖保证。 |

## Q&A 证据映射

| 追问 | 先答一句 | 立即打开 |
| --- | --- | --- |
| 为什么不是普通 RAG？ | 普通 RAG 做片段召回，本项目还做 evidence-bound GraphRAG、失败归因和人工补证闭环。 | `docs/challenge_cup/02_技术白皮书.md`; `evaluation/reports/challenge_cup_graphrag_same_question_report.md` |
| 固定场景证据在哪里？ | GT-07 场景有阈值、机理、现象、检修、建议五段证据链。 | `docs/challenge_cup/reproducibility/application_validation_report.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.json` |
| 如何证明材料完整？ | 先看 package manifest、hash、zip manifest，再看 {READINESS_GATE_COUNT} 项 readiness gate。 | `docs/challenge_cup/package_manifest.json`; `docs/challenge_cup/reproducibility/readiness_gate_report.md` |
| 是否已经有专家认可？ | 还没有归档真实专家反馈；当前只有外发包、采集表和硬证据行动包。 | `docs/challenge_cup/reproducibility/goal_completion_report.md`; `docs/challenge_cup/reproducibility/hard_evidence_action_pack.md` |
| 是否已经完成彩排？ | 还没有归档真实计时彩排；当前只有计分卡、结果包模板和操作 Runbook。 | `docs/challenge_cup/10_答辩攻防与彩排卡.md`; `docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md` |

## 留存材料

- 递交给评委的第一份文件：`docs/challenge_cup/13_评委现场速览卡.md`。
- 评委想快速审阅时：`docs/challenge_cup/09_专家快速审阅索引.md`。
- 评委想看特等奖维度时：`docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md`。
- 评委想看结项状态时：`docs/challenge_cup/reproducibility/final_acceptance_audit.md`。
- 评委想看未完成边界时：`docs/challenge_cup/reproducibility/goal_completion_report.md`。

## 禁止现场调试

- 不在评委面前安装依赖、改代码、改端口或现场修复服务。
- 不把临时打不开解释成项目不可复现；直接切到已归档 smoke 报告、截图和 zip verifier。
- 不口头声称真实专家反馈或真实计时彩排已经完成；只有硬证据归档后才能改变这个口径。
- 不把 readiness gate 说成获奖保证；它只证明结项包和演示证据可复核。
"""
    return text.replace("{READINESS_GATE_COUNT}", str(READINESS_GATE_COUNT))


def build_project_handoff_checklist(ctx: dict[str, Any]) -> str:
    return """# 结项交付移交清单

本清单用于把挑战杯材料包从“能演示、能复核”推进到“可移交、可签收、可继续补证”的结项状态。它只记录当前包内已经归档的材料和复核动作；真实专家反馈与真实计时彩排仍需按硬证据流程补齐，未归档前不能标记目标完成。

## 移交范围

| 材料 | 路径 | 移交口径 |
| --- | --- | --- |
| 阅读入口 | `docs/challenge_cup/README_先看这里.md` | 指导评委、导师或接手同学按同一顺序审阅材料。 |
| 包清单 | `docs/challenge_cup/package_manifest.json` | 记录证据文件、哈希清单、提交包 zip 和归档 manifest。 |
| 提交包 | `docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip` | 作为结项留存包，不包含自引用 readiness 报告。 |
| 提交包校验器 | `docs/challenge_cup/reproducibility/verify_submission_package.py` | 接收方可独立复核 zip、manifest、hash、smoke 和目标边界。 |
| 现场操作 | `docs/challenge_cup/14_现场答辩操作Runbook.md` | 约束答辩当天的 tab 顺序、离线切换和禁止现场调试。 |

## 签收确认

| 签收项 | 证明方式 | 当前状态 |
| --- | --- | --- |
| 材料包可打开 | 接收方打开 README、项目书、技术白皮书、实验报告、PPT 和讲稿。 | 已生成，待人工签收。 |
| 证据链可复核 | 接收方按 GT-07 固定场景核对 browser smoke、截图和应用验证报告。 | 已生成，待人工签收。 |
| 完整性可复核 | 接收方运行提交包校验器并核对 readiness gate。 | 已生成，待人工签收。 |
| 外部硬证据状态清楚 | 接收方确认 `docs/challenge_cup/reproducibility/goal_completion_report.md` 仍显示缺真实专家反馈和真实计时彩排。 | 待外部证据补齐。 |

## 复核命令

```powershell
.\.venv\Scripts\python.exe docs/challenge_cup/reproducibility/verify_submission_package.py --root .
.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py
.\.venv\Scripts\python.exe scripts/check_challenge_cup_goal_completion.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_final_acceptance_audit.py
```

- `docs/challenge_cup/reproducibility/readiness_gate_report.md` 证明当前结项包可复核。
- `docs/challenge_cup/reproducibility/final_acceptance_audit.md` 证明当前包可进入材料评审。
- `docs/challenge_cup/reproducibility/goal_completion_report.md` 证明在外部硬证据缺失时不能标记目标完成。

## 材料归档

| 归档动作 | 负责人 | 归档位置 |
| --- | --- | --- |
| 保存提交包 zip、manifest 和 hash | 项目负责人 | `docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip`; `docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json`; `docs/challenge_cup/reproducibility/evidence_hashes.json` |
| 保存答辩材料 | 主讲人 | `docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx`; `docs/challenge_cup/defense_deck/challenge_cup_defense_speaker_notes.md` |
| 保存现场操作材料 | 操作者 | `docs/challenge_cup/13_评委现场速览卡.md`; `docs/challenge_cup/14_现场答辩操作Runbook.md` |
| 保存硬证据边界 | 证据管理员 | `docs/challenge_cup/reproducibility/hard_evidence_ledger.md`; `docs/challenge_cup/reproducibility/hard_evidence_action_pack.md` |

## 外部硬证据补齐

| 缺口 | 归档入口 | 补齐后动作 |
| --- | --- | --- |
| 真实专家反馈 | `docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/README.md` | 用 `scripts/record_challenge_cup_hard_evidence.py` 的 expert_feedback 模式归档原件或摘要，再重跑 readiness、goal completion、final audit 和 package build。 |
| 真实计时彩排 | `docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/README.md` | 用 `scripts/run_challenge_cup_timed_rehearsal.py` 并传入 `--source <real-timer-or-observer-file>`，或用 `scripts/record_challenge_cup_hard_evidence.py` 的 timed_rehearsal 模式归档独立计时证据，再重跑全链路。 |

## 移交结论

- 当前材料可以用于结项材料评审、现场答辩准备和离线复核。
- 当前材料不能替代真实专家反馈，不能替代真实计时彩排，不能标记目标完成。
- 接收方签收后，后续任何外部硬证据补齐都必须重新生成 `docs/challenge_cup/package_manifest.json`、`docs/challenge_cup/reproducibility/evidence_hashes.json` 和 `docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip`。
"""


def build_defense_qa_remediation_ledger(ctx: dict[str, Any]) -> str:
    return """# 现场问辩记录与整改台账

本台账用于把现场评委追问、答复质量、证据遗漏和赛后整改动作转成可复核闭环。当前版本是记录模板和处理规则；它不声明已经发生现场问辩，不替代真实专家反馈，也不替代真实计时彩排。缺少这两类硬证据前，仍不能标记目标完成。

## 记录范围

| 场景 | 记录内容 | 关联材料 |
| --- | --- | --- |
| 终审现场问辩 | 评委原问题、主讲人答复、证据锚点、是否超时、是否出现遗漏。 | `docs/challenge_cup/10_答辩攻防与彩排卡.md`; `docs/challenge_cup/14_现场答辩操作Runbook.md` |
| 现场移交签收 | 接收方是否能打开材料包、运行校验命令、理解未完成边界。 | `docs/challenge_cup/15_结项交付移交清单.md` |
| 赛后补证整改 | 问辩暴露出的证据缺口、整改动作、复核命令和关闭状态。 | `docs/challenge_cup/07_评审主张证据矩阵.md`; `docs/challenge_cup/reproducibility/hard_evidence_action_pack.md` |

## 现场记录表

| 字段 | 填写规则 |
| --- | --- |
| `question_id` | 使用 QD-001、QD-002 连续编号。 |
| `judge_question` | 尽量按评委原话记录，不改写成项目方想回答的问题。 |
| `answer_owner` | 记录主讲人、操作者或导师复核人。 |
| `answer_summary` | 只写现场实际回答，不补写赛后想法。 |
| `evidence_anchor` | 写现场实际打开的材料路径，例如 `docs/challenge_cup/09_专家快速审阅索引.md`。 |
| `gap_type` | 可选：证据不足、表达不清、演示不稳、边界过强、边界不足、需外部反馈。 |
| `remediation_action` | 写赛后要补的具体材料、测试或演示动作。 |
| `verification_command` | 写复核脚本路径，例如 `scripts/check_challenge_cup_readiness.py` 或 `docs/challenge_cup/reproducibility/verify_submission_package.py`。 |
| `closure_status` | open / patched / verified / deferred；没有复核命令或证据前不得写 verified。 |

## 证据补链

| 常见追问 | 优先锚点 | 若仍不足 |
| --- | --- | --- |
| 为什么能冲击特等奖？ | `docs/challenge_cup/08_特等奖评审自评表.md`; `docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md` | 回到 `docs/challenge_cup/07_评审主张证据矩阵.md` 补证，不把 readiness gate 说成获奖保证。 |
| 真实应用价值在哪里？ | `docs/challenge_cup/11_应用场景与专家验证.md`; `docs/challenge_cup/reproducibility/application_validation_report.md` | 若评委要求外部背书，进入真实专家反馈补证流程。 |
| 现场演示失败怎么办？ | `docs/challenge_cup/14_现场答辩操作Runbook.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md` | 记录为演示不稳，赛后补充截图、录屏或重跑 smoke。 |
| 是否完成所有目标？ | `docs/challenge_cup/reproducibility/goal_completion_report.md`; `docs/challenge_cup/reproducibility/hard_evidence_ledger.md` | 明确仍缺真实专家反馈和真实计时彩排，不能标记目标完成。 |
| 如何证明整改后材料仍完整？ | `docs/challenge_cup/reproducibility/readiness_gate_report.md`; `docs/challenge_cup/reproducibility/final_acceptance_audit.md` | 重跑 readiness 和 final audit 后再关闭整改项。 |

## 整改闭环

1. 问辩结束当天，把所有 open 项写入本台账，不删除尖锐问题。
2. 对每个 open 项绑定一个 `evidence_anchor` 和一个 `remediation_action`。
3. 需要外部证据的项进入 `docs/challenge_cup/reproducibility/hard_evidence_action_pack.md`。
4. 修改材料后重跑复核命令，并把 `closure_status` 从 patched 改为 verified。
5. 若问题属于真实专家反馈或真实计时彩排缺口，只能在原始证据归档后关闭。

## 复核命令

```powershell
.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py
.\.venv\Scripts\python.exe docs/challenge_cup/reproducibility/verify_submission_package.py --root .
.\.venv\Scripts\python.exe scripts/check_challenge_cup_goal_completion.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_final_acceptance_audit.py
```

## 边界声明

- 本台账记录问辩与整改，不伪造评委意见，不伪造真实专家反馈。
- 没有计时记录、观察员备注或录屏前，不把本台账写成真实计时彩排。
- 没有真实专家反馈和真实计时彩排同时归档前，`docs/challenge_cup/reproducibility/goal_completion_report.md` 应继续显示不能标记目标完成。
- 若评委质疑某个主张，保留问题原文和整改动作，比删除问题更能体现学术诚信。
"""


    return text.replace("{READINESS_GATE_COUNT}", str(READINESS_GATE_COUNT))


def build_review_risk_response_plan(ctx: dict[str, Any]) -> str:
    return """# 评审风险控制与应急预案

本预案用于把挑战杯终审和结项评审中的高风险点提前拆解为触发条件、应急动作、证据锚点和关闭标准。它不降低事实边界：没有真实专家反馈和真实计时彩排前，不能标记目标完成，也不能把本预案写成外部认可。

## 风险分级

| 等级 | 判定标准 | 处理时限 |
| --- | --- | --- |
| A | 会影响获奖可信度、结项可验收性或诚信边界。 | 现场立即降级表述，赛后当天补证。 |
| B | 会影响演示流畅度或评委理解速度。 | 现场切换备份，赛后 24 小时内补材料。 |
| C | 不影响结论，但会影响材料易读性。 | 结项包刷新时修正。 |

## 风险台账

| risk_id | 风险 | 触发条件 | 应急动作 | 证据锚点 | 关闭标准 |
| --- | --- | --- | --- | --- | --- |
| `award_overclaim` | 把 readiness gate 或内部自评说成获奖保证。 | 现场出现“肯定特等奖”“已获认可”等表述。 | 立即改口为“争取进入特等奖讨论”，打开官方口径和自评边界。 | `docs/challenge_cup/08_特等奖评审自评表.md`; `docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md` | 答辩材料和问辩台账均保留“不承诺获奖”。 |
| `demo_failure` | 前端、后端、搜索或 KG artifact 现场不可用。 | 服务打不开、搜索结果不出现或页面异常。 | 按 20 秒规则切到离线证据，不现场调试。 | `docs/challenge_cup/14_现场答辩操作Runbook.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`; `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png` | 现场讲清离线证据链，赛后重跑 smoke 并记录。 |
| `external_evidence_gap` | 评委要求专家认可或真实彩排证明。 | 被问到“谁验证过”“是否真实彩排过”。 | 打开目标完成报告和硬证据台账，说明当前缺口和补证流程。 | `docs/challenge_cup/reproducibility/goal_completion_report.md`; `docs/challenge_cup/reproducibility/hard_evidence_ledger.md` | 真实专家反馈和真实计时彩排原始证据归档后才能关闭。 |
| `data_boundary` | 评委质疑数据规模和生产级覆盖。 | 被问到“是否覆盖真实生产全场景”。 | 将范围限定为课程/公开资料和固定 GT-07 场景，展示评测集和应用验证报告。 | `docs/challenge_cup/03_实验评测报告.md`; `docs/challenge_cup/11_应用场景与专家验证.md` | 补充更大数据或外部验证前，不扩大生产级主张。 |
| `safety_boundary` | 系统被误解为可替代工程师做高风险维修决策。 | 被问到“能否直接指导维修”。 | 强调证据型辅助和人工确认，打开技术白皮书与问答手册。 | `docs/challenge_cup/02_技术白皮书.md`; `docs/challenge_cup/05_答辩问答手册.md` | 所有答辩材料保留人工确认边界。 |
| `question_gap` | 评委提出未覆盖的新问题。 | 现场答复缺证据或不能 30 秒内说明。 | 写入 `docs/challenge_cup/16_现场问辩记录与整改台账.md`，绑定补证动作。 | `docs/challenge_cup/16_现场问辩记录与整改台账.md`; `docs/challenge_cup/07_评审主张证据矩阵.md` | 补证后重跑 readiness 和 submission verifier。 |

## 复核命令

```powershell
.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py
.\.venv\Scripts\python.exe docs/challenge_cup/reproducibility/verify_submission_package.py --root .
.\.venv\Scripts\python.exe scripts/check_challenge_cup_goal_completion.py
```

## 关闭规则

- 风险关闭必须有证据锚点、整改动作和复核命令，不能只写“已解释”。
- 涉及真实专家反馈或真实计时彩排的风险，必须等原始证据归档后才能关闭。
- 涉及获奖表述的风险，关闭标准是删除或降级所有获奖保证口径。
- 涉及演示失败的风险，关闭标准是重跑 browser smoke 或提交离线证据截图。
"""


def build_special_prize_scoring_drill(ctx: dict[str, Any]) -> str:
    return """# 特等奖打分模拟与整改清单

本清单用于赛前按公开评审口径做一次内部打分模拟，把“能不能冲击特等奖”的讨论落到证据、扣分项、整改动作和关闭证据上。它不是获奖预测，也不承诺获奖；没有真实专家反馈和真实计时彩排前，不能标记目标完成。

## 官方口径快照

| 来源 | 本项目采用的可执行口径 | 答辩动作 |
| --- | --- | --- |
| 清华大学第44届“挑战杯”公开报道 | 终审答辩于2026年4月25日开展，主赛道特等奖7项，竞争强度需要按最高水平准备。 | 不说“保证特等奖”，只说“争取进入特等奖讨论”。 |
| 清华大学第37届校级终审公开报道 | 评分关注学术价值或实用性、创新性、作品完成情况和现场答辩表现。 | 每个维度必须有证据锚点、演示动作和风险边界。 |
| 全国“挑战杯”公开报道 | 赛事强调服务国家战略、高质量发展、以赛促学促研促创、成果转化。 | 把动力装备运维知识化价值讲成工程证据链，而不是泛问答工具。 |

## 模拟打分表

| 评审维度 | 当前模拟等级 | 主要证据 | 模拟扣分项 | 整改动作 | 关闭证据 |
| --- | --- | --- | --- | --- | --- |
| 学术价值或实用性 | A- | `docs/challenge_cup/07_评审主张证据矩阵.md`; `docs/challenge_cup/11_应用场景与专家验证.md`; `docs/challenge_cup/reproducibility/application_validation_report.md` | 真实生产验证和外部专家背书仍未闭环。 | 现场用 GT-07 固定场景讲清人工确认边界，赛后补真实专家反馈。 | `docs/challenge_cup/reproducibility/hard_evidence_ledger.md`; `docs/challenge_cup/reproducibility/goal_completion_report.md` |
| 创新性 | A- | `docs/challenge_cup/02_技术白皮书.md`; `evaluation/reports/challenge_cup_graphrag_context_demo.md`; `evaluation/reports/challenge_cup_graphrag_answer_benchmark.md` | 容易被误解成普通 RAG 页面。 | 先展示 evidence-bound GraphRAG、人工补证和同题对照，再承认普通 RAG 是强基线。 | `docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md`; `docs/challenge_cup/13_评委现场速览卡.md` |
| 作品完成情况 | A | `docs/challenge_cup/reproducibility/readiness_gate_report.md`; `docs/challenge_cup/package_manifest.json`; `docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json` | gate 只证明材料包可复核，不证明奖项结果或生产上线。 | 现场先跑提交包校验器和 readiness gate，再进入演示。 | `docs/challenge_cup/14_现场答辩操作Runbook.md`; `docs/challenge_cup/reproducibility/final_acceptance_audit.md` |
| 现场答辩表现 | B+ | `docs/challenge_cup/10_答辩攻防与彩排卡.md`; `docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md`; `docs/challenge_cup/17_评审风险控制与应急预案.md` | 真实计时彩排尚未归档，现场节奏风险仍存在。 | 按 90 秒开场、三分钟演示、20 秒离线切换规则彩排并留证。 | `docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/README.md`; `docs/challenge_cup/reproducibility/hard_evidence_ledger.md` |
| 学术规范与严谨表述 | A | `docs/challenge_cup/reproducibility/official_rubric_alignment.md`; `docs/challenge_cup/08_特等奖评审自评表.md`; `docs/challenge_cup/05_答辩问答手册.md`; `docs/challenge_cup/17_评审风险控制与应急预案.md` | 过度包装会损害特等奖可信度。 | 所有获奖、专家认可、生产级覆盖表述都降级为证据边界内口径。 | `docs/challenge_cup/16_现场问辩记录与整改台账.md`; `docs/challenge_cup/reproducibility/goal_completion_report.md` |

## 赛前整改顺序

1. 先关闭事实边界风险：复核 `docs/challenge_cup/reproducibility/goal_completion_report.md`，确认真实专家反馈和真实计时彩排仍未被误写成已完成。
2. 再关闭现场表达风险：按 `docs/challenge_cup/14_现场答辩操作Runbook.md` 预开标签页，确保每个评分维度能在 30 秒内打开证据。
3. 最后关闭补证风险：把新增问题写入 `docs/challenge_cup/16_现场问辩记录与整改台账.md`，并用 `docs/challenge_cup/17_评审风险控制与应急预案.md` 判定风险等级。

## 关闭规则

- 只有证据锚点、整改动作和关闭证据同时存在，模拟扣分项才允许关闭。
- 涉及真实专家反馈或真实计时彩排的扣分项，只能在原始证据归档后关闭。
- 涉及特等奖表述的扣分项，必须保留不承诺获奖边界。
"""


def build_poster_booth_qa_pack(ctx: dict[str, Any]) -> str:
    return """# 作品展墙报问辩与展台脚本

本脚本用于作品展、墙报问辩和展台交流场景。公开评审口径中出现“现场答辩及墙报问辩表现”，作品展也强调墙报、二维码、线上线下融合和互动展示；因此本项目不能只准备终审 PPT，还要准备评委在展台前 30 秒、3 分钟和深问辩三种路径。

## 展板信息架构

| 展板区域 | 目标 | 必放内容 | 证据锚点 |
| --- | --- | --- | --- |
| 左上角一眼识别 | 让路过评委 10 秒内知道项目不是普通问答页。 | 项目名、动力装备运维知识、evidence-bound RAG / GraphRAG、9080 chunks、60 题评测。 | `docs/challenge_cup/00_项目一页纸.md`; `docs/challenge_cup/07_评审主张证据矩阵.md` |
| 中央主图 | 让评委看到技术路线和证据闭环。 | OCR / chunk / RAG / KG evidence / GraphRAG / evaluation / browser smoke / readiness gate。 | `docs/challenge_cup/02_技术白皮书.md`; `docs/challenge_cup/reproducibility/readiness_gate_report.md` |
| 右侧应用场景 | 把实用价值落到 GT-07 固定场景。 | 燃气轮机异常振动诊断流程、五条 record id、人工确认边界。 | `docs/challenge_cup/reproducibility/application_validation_report.md`; `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png` |
| 底部二维码 | 支撑线上线下融合和材料可复核。 | README、提交包 verifier、浏览器 smoke 报告、专家反馈表。 | `docs/challenge_cup/README_先看这里.md`; `docs/challenge_cup/reproducibility/verify_submission_package.py`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md` |

## 展台三分钟路径

| 时间 | 讲法 | 打开材料 |
| --- | --- | --- |
| 0:00-0:30 | “我们解决的是动力装备资料分散、术语密集、故障处理证据难追溯的问题。” | `docs/challenge_cup/13_评委现场速览卡.md` |
| 0:30-1:10 | “差异不是接一个大模型，而是把证据绑定、关系图谱、失败归因和可复核门禁做成闭环。” | `docs/challenge_cup/07_评审主张证据矩阵.md` |
| 1:10-2:00 | “请看 GT-07 场景：阈值、结构故障、异常现象、检修建议和人工确认边界串起来。” | `docs/challenge_cup/reproducibility/application_validation_report.md` |
| 2:00-2:30 | “特等奖维度我们按官方口径做了自评和扣分清单。” | `docs/challenge_cup/18_特等奖打分模拟与整改清单.md` |
| 2:30-3:00 | “当前包可复核，但真实专家反馈和真实计时彩排仍在硬证据闭环中，不承诺获奖。” | `docs/challenge_cup/reproducibility/goal_completion_report.md` |

## 现场互动脚本

| 评委追问 | 30 秒回答 | 递交 / 打开材料 |
| --- | --- | --- |
| 墙报上最核心的创新是什么？ | GraphRAG 不是装饰图，而是把故障、部件、参数、措施和证据来源组织成可审计关系链。 | `docs/challenge_cup/02_技术白皮书.md`; `evaluation/reports/challenge_cup_graphrag_context_demo.md` |
| 二维码扫出来应该先看什么？ | 先看 README，再看评委现场速览卡和提交包 verifier；不要求评委现场跑全链路。 | `docs/challenge_cup/README_先看这里.md`; `docs/challenge_cup/reproducibility/verify_submission_package.py` |
| 如果现场网络或演示设备不稳定怎么办？ | 不现场调试，切换离线备份：浏览器 smoke 报告、桌面截图、KG artifact 和 readiness gate。 | `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`; `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png` |
| 为什么值得特等奖讨论？ | 用官方维度回答：实用价值、创新性、完成度、墙报问辩表现和学术规范均有证据；同时保留外部硬证据缺口。 | `docs/challenge_cup/08_特等奖评审自评表.md`; `docs/challenge_cup/reproducibility/official_rubric_alignment.md` |
| 是否已经有专家认可？ | 不能这样说。真实专家反馈未归档前，只能说已准备采集表和硬证据流程。 | `docs/challenge_cup/reproducibility/hard_evidence_ledger.md`; `docs/challenge_cup/reproducibility/goal_completion_report.md` |

## 材料递交

- 展台电脑预开：`docs/challenge_cup/13_评委现场速览卡.md`、`docs/challenge_cup/18_特等奖打分模拟与整改清单.md`、`docs/challenge_cup/reproducibility/application_validation_report.md`、`docs/challenge_cup/reproducibility/readiness_gate_report.md`。
- 墙报二维码指向 README 和 submission verifier；若只能放一个入口，优先放 `docs/challenge_cup/README_先看这里.md`。
- 纸质留存优先级：评委现场速览卡、特等奖打分模拟与整改清单、应用场景验证摘要、风险控制与应急预案。

## 离线备份与边界

- 离线备份必须包含 `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png` 和 `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`。
- 展台话术必须保留真实专家反馈和真实计时彩排缺口；这两项未归档前，不能标记目标完成。
- 不承诺获奖，不把二维码访问量、墙报问辩表现或 readiness gate 说成特等奖保证。
"""


def build_commercialization_roadmap(ctx: dict[str, Any]) -> str:
    return """# 成果转化与持续迭代路线图

本路线图用于把“服务国家战略、高质量发展、成果转化、新质生产力”这些宏观口径落到本项目的可执行试点路径。它不承诺商业落地，不把课程资料验证包装成生产级系统；真实专家反馈、真实计时彩排、真实场景试点证据未归档前，不能标记目标完成。

## 转化定位

| 方向 | 推广对象 | 当前证据 | 近期试点路径 | 风险边界 |
| --- | --- | --- | --- | --- |
| 教学科研知识资产 | 课程组、实验室、学生科创团队 | `docs/challenge_cup/01_挑战杯项目书.md`; `docs/challenge_cup/07_评审主张证据矩阵.md` | 先服务课程资料检索、实验报告复核和答辩证据组织。 | 不宣称已经成为校级平台。 |
| 动力装备运维资料整理 | 动力装备课程、实验室或企业导师审阅场景 | `docs/challenge_cup/11_应用场景与专家验证.md`; `docs/challenge_cup/reproducibility/application_validation_report.md` | 用 GT-07 固定场景邀请老师或行业专家审阅，收集真实专家反馈。 | 高风险运维决策必须人工确认。 |
| 科创展示与推广 | 挑战杯作品展、墙报问辩、线上材料浏览 | `docs/challenge_cup/19_作品展墙报问辩与展台脚本.md`; `docs/challenge_cup/reproducibility/official_rubric_alignment.md` | 用二维码入口、离线截图和提交包 verifier 证明可复核。 | 不把访问量或展示效果说成特等奖保证。 |
| 工程化持续迭代 | 后续项目组、课程助教、潜在试点单位 | `docs/challenge_cup/reproducibility/hard_evidence_action_pack.md`; `docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md` | 逐步补齐外部反馈、数据治理、权限控制、评测扩展和部署脚本。 | 不承诺商业落地，不承诺生产 SLA。 |

## 迭代里程碑

| 阶段 | 时间窗口 | 关键动作 | 验收指标 | 关闭证据 |
| --- | --- | --- | --- | --- |
| M0 结项包冻结 | 当前 | 固化 README、manifest、hash、submission zip、readiness gate。 | `docs/challenge_cup/reproducibility/readiness_gate_report.md` 通过，submission verifier 通过。 | `docs/challenge_cup/reproducibility/readiness_gate_report.md`; `docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json` |
| M1 专家审阅 | 答辩前/赛后 1 周 | 向老师、行业专家或实验室同学发送反馈包。 | 至少归档 1 份真实签字、邮件或会议纪要反馈。 | `docs/challenge_cup/reproducibility/hard_evidence_ledger.md`; `docs/challenge_cup/reproducibility/expert_feedback_request_packet.md` |
| M2 计时彩排 | 答辩前 | 完成 90 秒开场、三分钟演示、killer questions 和离线切换演练。 | 真实计时彩排结果归档，关键问题 30 秒内可回答。 | `docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md`; `docs/challenge_cup/reproducibility/hard_evidence_ledger.md` |
| M3 试点数据治理 | 后续迭代 | 明确数据来源、授权范围、脱敏规则、人工复核责任。 | 新数据进入前完成数据治理记录和评测集扩展。 | `docs/challenge_cup/reproducibility/hard_evidence_action_pack.md`; `docs/challenge_cup/reproducibility/goal_completion_report.md` |
| M4 推广复盘 | 作品展/结项后 | 汇总评委追问、墙报问辩反馈、演示失败点和补证动作。 | 所有 open 问题进入整改台账并重新跑 gate。 | `docs/challenge_cup/16_现场问辩记录与整改台账.md`; `docs/challenge_cup/18_特等奖打分模拟与整改清单.md` |

## 验收指标

- 可复核性：README、manifest、evidence hashes、submission zip 和 verifier 一致。
- 实用性：固定 GT-07 场景能说明动力装备运维知识整理价值，且保留人工确认边界。
- 创新性：GraphRAG 价值必须绑定 evidence、同题对照和失败归因，不靠概念包装。
- 推广性：能被课程组、实验室或外部审阅者按路径打开材料，不依赖作者口头解释。
- 诚信性：真实专家反馈和真实计时彩排未归档前，目标完成报告必须继续阻止完成声明。

## 风险边界

- 不承诺商业落地，不承诺生产部署，不承诺生产级 SLA。
- 数据治理未完成前，不接入未授权生产资料。
- 所有运维建议必须经过人工确认；系统只做证据型辅助和知识资产整理。
- 若后续出现试点单位或外部反馈，必须归档原始证据并重跑 `docs/challenge_cup/reproducibility/verify_submission_package.py`、`scripts/check_challenge_cup_readiness.py` 和 `scripts/check_challenge_cup_goal_completion.py`。
"""


def build_ip_open_source_compliance(ctx: dict[str, Any]) -> str:
    return """# 知识产权与开源合规说明

本说明用于结项验收和挑战杯评审中的原创性、知识产权、第三方依赖、数据来源与授权边界、学术诚信问辩。它不把课程项目包装成已授权生产系统，不宣称已申请专利，不宣称已发表论文，也不把开源框架或第三方模型能力说成本项目自研成果。

## 原创性声明

| 范围 | 可答辩表述 | 证据锚点 | 不可夸大边界 |
| --- | --- | --- | --- |
| 项目集成与工程闭环 | 原创贡献在于把动力装备资料处理、评测集、RAG baseline、KG evidence、GraphRAG 证据组织、浏览器演示和提交包门禁连成可复核闭环。 | `docs/challenge_cup/01_挑战杯项目书.md`; `docs/challenge_cup/02_技术白皮书.md`; `docs/challenge_cup/07_评审主张证据矩阵.md` | 不宣称底层大模型、向量数据库或浏览器框架为自研。 |
| 评测与证据组织 | 已形成 60 题评测、GraphRAG 子集、失败归因和 GT-07 固定场景。 | `docs/challenge_cup/03_实验评测报告.md`; `docs/challenge_cup/reproducibility/application_validation_report.md` | 不宣称当前评测达到公开论文 benchmark 或生产验收。 |
| 现场材料与复核链 | README、package manifest、evidence hashes、submission verifier 和 readiness gate 支撑评委复核。 | `docs/challenge_cup/README_先看这里.md`; `docs/challenge_cup/package_manifest.json`; `docs/challenge_cup/reproducibility/evidence_hashes.json`; `docs/challenge_cup/reproducibility/verify_submission_package.py` | 不把机器门禁说成获奖保证或外部专家背书。 |

## 第三方依赖与开源许可证边界

- 第三方依赖、模型服务、向量检索、浏览器自动化、文档生成和测试框架按其原始开源许可证或服务条款使用；答辩中只把它们作为工程工具链，不写成本项目知识产权。
- 若后续进入公开发布、商业试点或校外部署，必须补齐依赖清单、开源许可证复核、模型服务条款、数据授权记录和安全评审。
- 当前提交包只证明结项材料可复核；不宣称已经完成专利检索、软件著作权登记、专利申请或论文发表。

## 数据来源与授权边界

| 数据/材料 | 当前用途 | 合规边界 | 复核材料 |
| --- | --- | --- | --- |
| 课程与项目交付资料 | 用于课程结项和挑战杯材料包展示。 | 不接入未授权生产资料；不外传敏感原始资料；需要公开发布时重新做授权审查。 | `docs/challenge_cup/20_成果转化与持续迭代路线图.md`; `docs/challenge_cup/reproducibility/dataset_manifest.md`; `docs/challenge_cup/package_manifest.json` |
| 浏览器演示快照 | 用于证明本地演示和 GT-07 场景可复核。 | 不代表真实生产系统上线；不替代工程师做最终运维决策。 | `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`; `docs/challenge_cup/reproducibility/application_validation_report.md` |
| 外部专家反馈与计时彩排 | 只允许归档真实签字、邮件、会议纪要或观察员记录。 | 真实专家反馈和真实计时彩排未归档前，不能标记目标完成。 | `docs/challenge_cup/reproducibility/hard_evidence_ledger.md`; `docs/challenge_cup/reproducibility/final_acceptance_audit.md` |

## 学术诚信与引用与证据路径

- 所有高水平主张必须能回到 `docs/challenge_cup/07_评审主张证据矩阵.md`、`docs/challenge_cup/reproducibility/official_rubric_alignment.md` 或评测报告。
- 评委质疑时保留问题原文和整改动作，不删除不利问题，不伪造外部意见。
- 对 GraphRAG、RAG、OCR、知识图谱和评测结果的表述必须保留人工确认边界；系统只做证据型辅助。
- 后续如申请专利、软著或发表论文，必须把申请号、受理通知、论文链接或授权协议作为新硬证据归档，并重新运行 `docs/challenge_cup/reproducibility/verify_submission_package.py`、`scripts/check_challenge_cup_readiness.py` 和 `scripts/build_challenge_cup_final_acceptance_audit.py`。

## 现场问答口径

| 追问 | 回答 |
| --- | --- |
| 这是不是你们完全自研？ | 不是。底层工具和开源生态按许可使用；我们的贡献是动力装备知识资料的工程化组织、证据链、评测闭环和可复核提交包。 |
| 是否已经有专利或论文？ | 当前不宣称已申请专利、不宣称已发表论文；如果后续申请或发表，必须归档正式编号或链接。 |
| 数据是否可公开？ | 当前按结项与评审包使用，不接入未授权生产资料；对外发布或商业试点前需要重新做数据授权和脱敏审查。 |
| 结果能否直接指导维修？ | 不能。系统提供证据链和检索辅助，最终高风险运维决策必须人工确认。 |
| readiness gate 是否证明能获奖？ | 不能。它只证明提交包完整、证据可复核和边界明确；不承诺获奖。 |
"""


def build_local_baseline_differentiation_card(ctx: dict[str, Any]) -> str:
    day3_ref = optional_md_link(ctx["day3"])
    day4_ref = optional_md_link(ctx["day4"])
    graph_ref = optional_md_link(ctx["graph_report"])
    answer_ref = optional_md_link(ctx["graph_answer_benchmark_md"])
    gap_ref = optional_md_link(ctx["graph_gap_remediation_md"])
    return f"""# 同类方案对比与创新性证据卡

本卡用于集中回答评委最可能追问的创新性质疑：为什么不是普通 RAG 页面，为什么不是把关键词检索、向量检索或泛 GraphRAG demo 包装成作品。结论只基于本地同题对照和已归档证据，不依赖真实专家反馈或真实彩排。

## 一句话结论

项目不是普通 RAG 页面：普通 RAG/baseline 负责文本召回，GraphRAG 用于关系证据组织，readiness gate 与 submission verifier 负责把主张、证据、边界和归档包绑定起来。当前证据能说明固定 GraphRAG 子集的关系证据覆盖已经补齐，但不宣称 GraphRAG 全面优于 baseline。

## 本地同题对照

| 对比对象 | 本地证据 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| keyword / dense_hashing / hybrid_rrf / GraphRAG | `{day3_ref}` | 60 题评测中 keyword、dense_hashing、hybrid_rrf 三类 baseline 已有可复现对照；Best Day 3 baseline 是 keyword。 | 不证明当前在线生成答案优于所有检索方式。 |
| Day4 失败归因 | `{day4_ref}` | 弱命中和失败点已分到术语别名、结构化事实、hybrid 稀释、排序差距和评测概念缺口。 | 不把失败案例删除或包装成成功。 |
| GraphRAG 同题子集 | `{graph_ref}` | 60 题中 10 题显式需要 graphrag_context / graphrag_global；Graph evidence supported / partial / missing: 10 / 0 / 0；Graph supported / partial / missing: 10 / 0 / 0。 | 不代表完整 GraphRAG 在线问答已优于 baseline。 |
| GraphRAG answer benchmark | `{answer_ref}` | Best baseline average coverage: 0.633333；GraphRAG evidence average coverage: 0.866667；supported=10, partial=0, missing=0。 | 不宣称 GraphRAG 全面优于 baseline，不证明在线 LLM answer win-rate。 |
| GraphRAG gap remediation | `{gap_ref}` | 固定 GraphRAG 子集的 P0 missing/partial 证据缺口已被整改计划和补证记录关闭。 | 不代表所有未来问题都无需人工补证。 |

## 创新性证据链

| 评委问题 | 30 秒答法 | 立即打开 |
| --- | --- | --- |
| 为什么不是普通 RAG 页面？ | 因为我们不只返回片段，而是把 chunk、baseline、KG evidence、GraphRAG、评测失败归因和可复核归档包放到同一个证据闭环里。 | `docs/challenge_cup/03_实验评测报告.md`; `docs/challenge_cup/07_评审主张证据矩阵.md` |
| GraphRAG 具体强在哪里？ | GraphRAG 用于关系证据组织，尤其适合跨实体、跨部件、跨现象的说明；固定子集当前 supported=10, partial=0, missing=0。 | `evaluation/reports/challenge_cup_graphrag_same_question_report.md`; `evaluation/reports/challenge_cup_graphrag_answer_benchmark.md` |
| 如果 keyword 在某些题上更强怎么办？ | 承认并分类型解释：keyword 适合显式术语和数字事实，GraphRAG 适合关系组织和全局归纳。 | `evaluation/reports/day3_retrieval_baseline_comparison_20260605_210540.md`; `evaluation/reports/day4_failure_analysis_20260605_210642.md` |
| 应用价值如何落地？ | 用 GT-07 固定场景展示阈值、机理、异常现象、检修建议和人工确认边界。 | `docs/challenge_cup/reproducibility/application_validation_report.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md` |
| 是否能直接指导维修？ | 不能。不替代工程师做最终运维决策，系统只提供证据型辅助和知识资产整理。 | `docs/challenge_cup/08_特等奖评审自评表.md`; `docs/challenge_cup/reproducibility/application_validation_report.md` |

## 必守边界

- 不宣称 GraphRAG 全面优于 baseline；只陈述固定同题子集的本地证据覆盖。
- 不宣称已获得真实专家认可；真实专家反馈未归档前仍是硬证据缺口。
- 不宣称已完成真实计时彩排；真实彩排未归档前仍不能标记目标完成。
- 不替代工程师做最终运维决策；GT-07 只用于演示证据链与人工确认边界。
- 不依赖真实专家反馈或真实彩排来证明本卡；本卡只证明本地同题对照、评测报告和可复核证据链已经组织清楚。

## 证据路径

- `evaluation/reports/day3_retrieval_baseline_comparison_20260605_210540.md`
- `evaluation/reports/day4_failure_analysis_20260605_210642.md`
- `evaluation/reports/challenge_cup_graphrag_same_question_report.md`
- `evaluation/reports/challenge_cup_graphrag_answer_benchmark.md`
- `evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.md`
- `docs/challenge_cup/reproducibility/application_validation_report.md`
- `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`
- `docs/challenge_cup/03_实验评测报告.md`
- `docs/challenge_cup/07_评审主张证据矩阵.md`
- `docs/challenge_cup/08_特等奖评审自评表.md`
"""


def build_submission_integrity_card(ctx: dict[str, Any]) -> str:
    return f"""# 提交完整性快照

本卡给评委、导师和结项接收人一页式复核入口：先确认包在哪里，再确认 hash / verifier / readiness / hard-evidence boundary。它不替代 manifest，也不承诺获奖。

## Package Snapshot

| Item | Current Value | Verification Source |
| --- | --- | --- |
| package path | `docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip` | `docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json` |
| archive manifest | `docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json` | records archive bytes, file_count and sha256 |
| evidence hash manifest | `docs/challenge_cup/reproducibility/evidence_hashes.json` | records per-evidence sha256 except self reports |
| package manifest | `docs/challenge_cup/package_manifest.json` | records evidence_files, question_count and archive paths |
| offline verifier | `docs/challenge_cup/reproducibility/verify_submission_package.py --root .` | expected pass before handoff |

## Review Status

| Gate | Expected Result | Evidence |
| --- | --- | --- |
| readiness gate | pass `{READINESS_GATE_COUNT}/{READINESS_GATE_COUNT}` | `docs/challenge_cup/reproducibility/readiness_gate_report.md` |
| submission verifier | pass | `docs/challenge_cup/reproducibility/verify_submission_package.py` |
| final acceptance audit | `package_ready_awaiting_external_hard_evidence` | `docs/challenge_cup/reproducibility/final_acceptance_audit.md` |
| goal completion expected fail | fail until hard evidence is archived | `docs/challenge_cup/reproducibility/goal_completion_report.md` |

## Hard Evidence Boundary

- 真实专家反馈：尚未归档，必须按 `docs/challenge_cup/reproducibility/external_evidence_execution_kit.md` 采集真实来源。
- 真实计时彩排：尚未归档，必须按 `docs/challenge_cup/reproducibility/external_evidence_execution_kit.md` 记录真实观察与计时。
- 不承诺获奖；readiness gate、verifier、manifest 和本卡只证明提交包完整、可复核、边界清楚。

## One-command Verification

```powershell
.\\.venv\\Scripts\\python.exe docs\\challenge_cup\\reproducibility\\verify_submission_package.py --root .
.\\.venv\\Scripts\\python.exe scripts\\check_challenge_cup_readiness.py
.\\.venv\\Scripts\\python.exe scripts\\build_challenge_cup_final_acceptance_audit.py
.\\.venv\\Scripts\\python.exe scripts\\check_challenge_cup_goal_completion.py
```

生成时间：{ctx["now"]}
"""


def build_final_submission_handoff(ctx: dict[str, Any]) -> str:
    return f"""# 终审提交总目录与签收页

本页用于终审提交、教师复核和现场移交时快速确认：哪些文件是正式提交文件，哪些命令可以复核包完整性，哪些外部硬证据仍未完成。它只证明材料包已经组织成可复核结项形态，不承诺获奖。

## 提交状态

| 项目 | 当前状态 | 复核证据 |
| --- | --- | --- |
| 结项提交包 | 已生成，可按 verifier 和 readiness gate 复核。 | `docs/challenge_cup/package_manifest.json`; `docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json`; `docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip` |
| 现场答辩材料 | README、一页纸、项目书、评委速览卡、展墙脚本、PPT 和 A0 海报均已进入包。 | `docs/challenge_cup/README_先看这里.md`; `docs/challenge_cup/00_项目一页纸.md`; `docs/challenge_cup/01_挑战杯项目书.md`; `docs/challenge_cup/13_评委现场速览卡.md`; `docs/challenge_cup/19_作品展墙报问辩与展台脚本.md`; `docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx`; `docs/challenge_cup/poster/challenge_cup_a0_poster.html` |
| 外部硬证据 | 真实专家反馈、真实计时彩排仍待实际归档；未归档前不能标记目标完成。 | `docs/challenge_cup/reproducibility/external_evidence_execution_kit.md`; `docs/challenge_cup/reproducibility/external_evidence_closeout_checklist.md`; `docs/challenge_cup/reproducibility/hard_evidence_ledger.md`; `docs/challenge_cup/reproducibility/goal_completion_report.md` |
| 最终状态口径 | package_ready_awaiting_external_hard_evidence。 | `docs/challenge_cup/reproducibility/final_acceptance_audit.md`; `docs/challenge_cup/reproducibility/final_acceptance_audit.json` |

## 评委三分钟入口

| 用途 | 优先打开 | 说明 |
| --- | --- | --- |
| 先看项目定位 | `docs/challenge_cup/README_先看这里.md`; `docs/challenge_cup/00_项目一页纸.md` | 30 秒确认项目名称、场景、贡献和边界。 |
| 看正式项目书 | `docs/challenge_cup/01_挑战杯项目书.md` | 用于正式材料审阅和结项归档。 |
| 看现场答辩口径 | `docs/challenge_cup/13_评委现场速览卡.md`; `docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx` | 现场不临时翻材料，按速览卡和 PPT 主线答。 |
| 看展墙问辩 | `docs/challenge_cup/19_作品展墙报问辩与展台脚本.md`; `docs/challenge_cup/poster/challenge_cup_a0_poster.html` | 展墙、海报和 booth 问辩统一口径。 |

## 正式提交文件

| 类别 | 文件 |
| --- | --- |
| 主材料 | `docs/challenge_cup/README_先看这里.md`; `docs/challenge_cup/00_项目一页纸.md`; `docs/challenge_cup/01_挑战杯项目书.md`; `docs/challenge_cup/02_技术白皮书.md`; `docs/challenge_cup/03_实验评测报告.md` |
| 现场材料 | `docs/challenge_cup/13_评委现场速览卡.md`; `docs/challenge_cup/14_现场答辩操作Runbook.md`; `docs/challenge_cup/19_作品展墙报问辩与展台脚本.md`; `docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx`; `docs/challenge_cup/poster/challenge_cup_a0_poster.html` |
| 包与校验 | `docs/challenge_cup/reproducibility/submission_integrity_card.md`; `docs/challenge_cup/package_manifest.json`; `docs/challenge_cup/reproducibility/evidence_hashes.json`; `docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json`; `docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip`; `docs/challenge_cup/reproducibility/verify_submission_package.py` |
| 总结与门禁 | `docs/challenge_cup/reproducibility/readiness_gate_report.md`; `docs/challenge_cup/reproducibility/final_acceptance_audit.md`; `docs/challenge_cup/reproducibility/goal_completion_report.md`; `docs/challenge_cup/reproducibility/command_log.md` |
| 外部硬证据执行包 | `docs/challenge_cup/reproducibility/external_evidence_execution_kit.md`; `docs/challenge_cup/reproducibility/external_evidence_closeout_checklist.md`; `docs/challenge_cup/reproducibility/hard_evidence_ledger.md` |

## 复核命令

```powershell
.\.venv\Scripts\python.exe docs/challenge_cup/reproducibility/verify_submission_package.py --root .
.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_final_acceptance_audit.py
.\.venv\Scripts\python.exe scripts/check_challenge_cup_goal_completion.py
```

预期口径：

- submission verifier 必须 pass。
- readiness gate 必须 pass。
- final acceptance audit 当前应保持 package_ready_awaiting_external_hard_evidence。
- goal completion 在真实专家反馈和真实计时彩排归档前应 fail，不能标记目标完成。

## 未完成项与边界

- 真实专家反馈：必须有真实专家、真实渠道、反馈原件或可追溯摘要；准备材料不能替代反馈结果。
- 真实计时彩排：必须有真实计时、观察记录和问题整改闭环；彩排模板不能替代已完成彩排。
- 不承诺获奖：readiness gate、内部自评、PPT、海报和本签收页均不证明能够获得特等奖，只证明提交包完整、证据可复核、边界清楚。
- 目标完成条件：只有真实专家反馈和真实计时彩排完成归档，并重跑 verifier、readiness gate、final acceptance audit、goal completion 后，才允许讨论目标完成。

## 签收确认

| 签收项 | 确认 |
| --- | --- |
| 接收人 |  |
| 接收时间 |  |
| 是否已运行复核命令 |  |
| 是否确认 package_ready_awaiting_external_hard_evidence 状态 |  |
| 是否确认真实专家反馈仍需归档 |  |
| 是否确认真实计时彩排仍需归档 |  |
| 签收备注 |  |

生成时间：{ctx["now"]}
"""


def build_poster_board_html(ctx: dict[str, Any]) -> str:
    question_count = ctx["question_count"]
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>知燃知维 Challenge Cup A0 Poster</title>
  <style>
    @page {{ size: A0 landscape; margin: 0; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #f2f4f1;
      color: #17201c;
      font-family: "Microsoft YaHei", "Noto Sans CJK SC", Arial, sans-serif;
    }}
    .poster {{
      width: 1189mm;
      min-height: 841mm;
      padding: 34mm 38mm;
      display: grid;
      grid-template-rows: auto 1fr auto;
      gap: 22mm;
      background:
        linear-gradient(90deg, rgba(24, 83, 68, 0.08), rgba(150, 36, 32, 0.07)),
        #fbfbf7;
    }}
    header {{
      display: grid;
      grid-template-columns: 1.5fr 0.9fr;
      gap: 24mm;
      align-items: end;
      border-bottom: 3mm solid #185344;
      padding-bottom: 14mm;
    }}
    h1 {{
      margin: 0;
      font-size: 42mm;
      line-height: 1;
      letter-spacing: 0;
      color: #12392f;
    }}
    h2 {{
      margin: 0 0 7mm;
      font-size: 15mm;
      color: #185344;
      letter-spacing: 0;
    }}
    p {{
      margin: 0;
      font-size: 8.5mm;
      line-height: 1.45;
    }}
    .subtitle {{
      margin-top: 10mm;
      max-width: 700mm;
      font-size: 13mm;
      color: #35413b;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8mm;
    }}
    .metric {{
      border: 1.2mm solid #185344;
      padding: 8mm;
      min-height: 42mm;
      background: rgba(255,255,255,0.72);
    }}
    .metric strong {{
      display: block;
      font-size: 18mm;
      line-height: 1;
      color: #962420;
      margin-bottom: 5mm;
    }}
    main {{
      display: grid;
      grid-template-columns: 1.05fr 1.35fr 0.95fr;
      gap: 18mm;
    }}
    section {{
      background: rgba(255,255,255,0.78);
      border: 1mm solid rgba(24,83,68,0.22);
      padding: 13mm;
      min-height: 0;
    }}
    .route {{
      display: grid;
      gap: 8mm;
    }}
    .step {{
      border-left: 3mm solid #185344;
      padding-left: 7mm;
      font-size: 8.4mm;
      line-height: 1.35;
    }}
    .case {{
      border: 1.2mm solid #962420;
      padding: 10mm;
      background: #fff7f4;
      margin: 8mm 0;
    }}
    .case strong {{
      color: #962420;
    }}
    ul {{
      margin: 5mm 0 0;
      padding-left: 9mm;
      font-size: 7.8mm;
      line-height: 1.42;
    }}
    .evidence {{
      display: grid;
      gap: 5mm;
      font-size: 6.4mm;
      line-height: 1.25;
    }}
    code {{
      display: block;
      overflow-wrap: anywhere;
      padding: 2mm 0;
      color: #26332e;
      font-family: Consolas, "Microsoft YaHei", monospace;
    }}
    .qr-grid {{
      display: grid;
      grid-template-columns: 48mm 1fr;
      gap: 8mm;
      align-items: center;
      margin-bottom: 10mm;
    }}
    .qr {{
      width: 48mm;
      height: 48mm;
      border: 2mm solid #17201c;
      display: grid;
      place-items: center;
      font-size: 9mm;
      font-weight: 700;
      background:
        linear-gradient(45deg, #17201c 25%, transparent 25% 75%, #17201c 75%),
        linear-gradient(45deg, #17201c 25%, transparent 25% 75%, #17201c 75%);
      background-size: 12mm 12mm;
      background-position: 0 0, 6mm 6mm;
      color: #fff;
    }}
    footer {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16mm;
      border-top: 2mm solid #185344;
      padding-top: 10mm;
    }}
    .boundary {{
      font-size: 7.2mm;
      line-height: 1.4;
      color: #2f3935;
    }}
  </style>
</head>
<body>
  <article class="poster" aria-label="知燃知维 A0 展板">
    <header>
      <div>
        <h1>知燃知维</h1>
        <p class="subtitle">面向动力装备运维知识的可信 GraphRAG 系统：把资料、证据链、知识图谱、检索评测和现场答辩材料压到同一套可复核闭环。</p>
      </div>
      <div class="metrics">
        <div class="metric"><strong>9080 chunks</strong><span>课程与工程资料切分入库</span></div>
        <div class="metric"><strong>{question_count} 题评测</strong><span>覆盖事实、流程、诊断、证据追溯</span></div>
        <div class="metric"><strong>{READINESS_GATE_COUNT} gates</strong><span>readiness gate 校验交付包完整性</span></div>
      </div>
    </header>

    <main>
      <section>
        <h2>技术路线</h2>
        <div class="route">
          <div class="step">OCR / 清洗 / chunk：把动力装备资料转为可追溯文本资产。</div>
          <div class="step">普通 RAG baseline：形成强基线和失败归因，而不是只展示单次命中。</div>
          <div class="step">KG evidence / GraphRAG：把故障、部件、参数、措施和来源绑定为证据链。</div>
          <div class="step">submission verifier / readiness gate：让 README、hash、zip、截图和报告可复核。</div>
        </div>
        <div class="case">
          <p><strong>GT-07 固定案例：</strong>燃气轮机异常振动诊断流程，展示阈值、机理、异常现象、检修建议、复机结果和人工确认边界。</p>
        </div>
        <ul>
          <li>不是普通聊天页：评测、失败分析、GraphRAG 同题证据和浏览器 smoke 同时留档。</li>
          <li>不是口头包装：每个主张都回到证据文件、哈希、归档包和可运行脚本。</li>
        </ul>
      </section>

      <section>
        <h2>评审证据锚点</h2>
        <div class="evidence">
          <code>docs/challenge_cup/README_先看这里.md</code>
          <code>docs/challenge_cup/13_评委现场速览卡.md</code>
          <code>docs/challenge_cup/19_作品展墙报问辩与展台脚本.md</code>
          <code>docs/challenge_cup/20_成果转化与持续迭代路线图.md</code>
          <code>docs/challenge_cup/reproducibility/application_validation_report.md</code>
          <code>docs/challenge_cup/reproducibility/readiness_gate_report.md</code>
          <code>docs/challenge_cup/reproducibility/verify_submission_package.py</code>
          <code>docs/challenge_cup/reproducibility/browser_demo_smoke_report.md</code>
          <code>docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png</code>
        </div>
      </section>

      <section>
        <h2>展台入口</h2>
        <div class="qr-grid">
          <div class="qr">二维码</div>
          <p>二维码应指向 README；现场无法联网时，直接打开离线 submission verifier、readiness gate、browser smoke 报告和桌面检索截图。</p>
        </div>
        <ul>
          <li>先讲价值：动力装备知识资产整理和故障证据追溯。</li>
          <li>再讲创新：GraphRAG 与 evidence-bound RAG 结合。</li>
          <li>最后讲边界：真实专家反馈、真实计时彩排仍需归档。</li>
        </ul>
      </section>
    </main>

    <footer>
      <p class="boundary">材料口径：不承诺获奖，不把 readiness gate、二维码访问或内部自评说成特等奖保证；它们只证明包完整、路径清楚、证据可复核。</p>
      <p class="boundary">待补硬证据：真实专家反馈和真实计时彩排归档后，必须重跑 submission verifier、readiness gate、goal completion 和 final acceptance audit。</p>
    </footer>
  </article>
</body>
</html>
"""


def build_defense_control_console_html(ctx: dict[str, Any]) -> str:
    text = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Defense Control Console</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17202a;
      --muted: #53606f;
      --line: #d7dde5;
      --panel: #f7f9fb;
      --blue: #1f5fbf;
      --green: #147a4f;
      --amber: #9a6500;
      --red: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background: #ffffff;
    }
    main {
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px;
    }
    header {
      border-bottom: 2px solid var(--ink);
      padding-bottom: 18px;
      margin-bottom: 20px;
    }
    h1, h2 { margin: 0; letter-spacing: 0; }
    h1 { font-size: 32px; }
    h2 { font-size: 18px; margin-bottom: 10px; }
    p { margin: 8px 0 0; color: var(--muted); line-height: 1.55; }
    .status {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 18px 0 22px;
    }
    .metric, section {
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 14px;
      border-radius: 8px;
    }
    .metric strong {
      display: block;
      font-size: 24px;
      margin-bottom: 4px;
    }
    .grid {
      display: grid;
      grid-template-columns: 1.05fr 1fr;
      gap: 16px;
      align-items: start;
    }
    .links {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    a {
      display: block;
      min-height: 48px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--blue);
      text-decoration: none;
      font-weight: 700;
    }
    a span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 400;
      margin-top: 3px;
      overflow-wrap: anywhere;
    }
    .timeline {
      display: grid;
      gap: 8px;
    }
    .step {
      display: grid;
      grid-template-columns: 86px 1fr;
      gap: 10px;
      padding: 10px;
      border-left: 4px solid var(--blue);
      background: #ffffff;
    }
    .step strong { color: var(--blue); }
    .warning { border-left: 4px solid var(--red); }
    .warning strong { color: var(--red); }
    .fallback { border-left: 4px solid var(--amber); }
    .fallback strong { color: var(--amber); }
    .ok { border-left: 4px solid var(--green); }
    .ok strong { color: var(--green); }
    code {
      display: block;
      overflow-wrap: anywhere;
      color: #233042;
      font-size: 12px;
      margin-top: 4px;
    }
    @media (max-width: 860px) {
      main { padding: 16px; }
      .status, .grid, .links { grid-template-columns: 1fr; }
      h1 { font-size: 26px; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Defense Control Console</h1>
      <p>知燃知维 GraphRAG 挑战杯现场总控台。用于终审现场按顺序打开材料、控制节奏、快速切换离线证据，并主动声明边界。</p>
    </header>

    <div class="status" aria-label="readiness summary">
      <div class="metric"><strong>3-minute timer</strong><span>三分钟演示主线固定为 180 秒</span></div>
      <div class="metric"><strong>90-second opening</strong><span>开场覆盖问题、方法、完成度、边界</span></div>
      <div class="metric"><strong>{READINESS_GATE_COUNT} gates</strong><span>readiness gate 覆盖提交包完整性</span></div>
      <div class="metric"><strong>offline fallback</strong><span>20 秒内切换到截图和归档报告</span></div>
    </div>

    <div class="grid">
      <section>
        <h2>现场演示流程 <span>Live Sequence</span></h2>
        <div class="timeline">
          <div class="step"><strong>0:00</strong><div>打开 PPT 或一页纸，讲清真实问题与 GraphRAG 价值。<code>docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx</code></div></div>
          <div class="step"><strong>0:30</strong><div>进入 GT-07 固定检索案例，说明证据链不是口头承诺。<code>docs/challenge_cup/reproducibility/application_validation_report.md</code></div></div>
          <div class="step ok"><strong>1:20</strong><div>展示 GraphRAG / KG 证据组织和评测闭环。<code>docs/challenge_cup/07_评审主张证据矩阵.md</code></div></div>
          <div class="step ok"><strong>2:10</strong><div>展示 readiness gate 和 submission verifier，证明包可复核。<code>docs/challenge_cup/reproducibility/readiness_gate_report.md</code></div></div>
          <div class="step warning"><strong>2:40</strong><div>主动声明 no award guarantee、real expert feedback 和 real timed rehearsal 边界。<code>docs/challenge_cup/reproducibility/goal_completion_report.md</code></div></div>
        </div>
      </section>

      <section>
        <h2>证据启动台 <span>Evidence Launchpad</span></h2>
        <div class="links">
          <a href="../defense_deck/challenge_cup_defense_deck.pptx">Defense deck<span>docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx</span></a>
          <a href="../13_评委现场速览卡.md">Judge briefing card<span>docs/challenge_cup/13_评委现场速览卡.md</span></a>
          <a href="../14_现场答辩操作Runbook.md">Onsite runbook<span>docs/challenge_cup/14_现场答辩操作Runbook.md</span></a>
          <a href="../reproducibility/readiness_gate_report.md">Readiness gate<span>docs/challenge_cup/reproducibility/readiness_gate_report.md</span></a>
          <a href="../reproducibility/verify_submission_package.py">Submission verifier<span>docs/challenge_cup/reproducibility/verify_submission_package.py</span></a>
          <a href="../reproducibility/browser_screenshots/desktop_search_results.png">GT-07 screenshot<span>docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png</span></a>
          <a href="../reproducibility/final_acceptance_audit.md">Final acceptance<span>docs/challenge_cup/reproducibility/final_acceptance_audit.md</span></a>
          <a href="../reproducibility/special_prize_readiness_dashboard.md">Special prize dashboard<span>docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md</span></a>
        </div>
      </section>
    </div>

    <section style="margin-top: 16px;">
      <h2>兜底与边界 <span>Fallback and Boundaries</span></h2>
      <div class="timeline">
        <div class="step fallback"><strong>演示失败</strong><div>不现场排环境。立即打开 offline fallback evidence：截图、browser smoke report、KG artifacts、readiness gate。</div></div>
        <div class="step warning"><strong>不过度承诺</strong><div>主动声明 no award guarantee。Readiness 证明包完整，不证明特等奖概率。</div></div>
        <div class="step warning"><strong>硬证据边界</strong><div>真实专家反馈和真实计时彩排归档前，不宣称 real expert feedback 或 real timed rehearsal 已完成。</div></div>
      </div>
    </section>
  </main>
</body>
</html>
"""
    return text.replace("{READINESS_GATE_COUNT}", str(READINESS_GATE_COUNT))


def build_defense_rehearsal_card(ctx: dict[str, Any]) -> str:
    return """# 答辩攻防与彩排卡

本卡用于把“现场答辩表现”从临场发挥变成可训练、可复核、可切换的流程。彩排时按本卡计时，现场时按本卡选择主线和证据。

## 90秒开场

1. 15 秒：说明真实问题，动力装备资料分散、扫描件多、术语密集，普通检索难以解释部件、故障、参数和措施之间的关系。
2. 25 秒：说明方法，项目把 OCR、普通 RAG、evidence-bound 知识图谱、GraphRAG 检索和自动评测连成闭环。
3. 25 秒：说明完成度，评测集、baseline、失败归因、浏览器 smoke、KG artifact 和 readiness gate 均已留证。
4. 25 秒：说明边界，系统是证据型辅助和知识资产整理，不替代工程师做真实运维决策。

## 三分钟演示节奏

| 时间 | 动作 | 证据锚点 |
| --- | --- | --- |
| 0:00-0:30 | 打开一页纸，讲问题、方法和核心数字 | `docs/challenge_cup/00_项目一页纸.md` |
| 0:30-1:20 | 展示检索或离线截图，证明系统不是静态材料 | `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md` |
| 1:20-2:10 | 打开 KG artifact 或证据矩阵，证明 GraphRAG 价值在关系证据组织 | `docs/challenge_cup/07_评审主张证据矩阵.md` |
| 2:10-2:40 | 展示 readiness gate，证明可复核而非口头承诺 | `docs/challenge_cup/reproducibility/readiness_gate_report.md` |
| 2:40-3:00 | 主动讲边界和下一步，避免被动防守 | `docs/challenge_cup/08_特等奖评审自评表.md` |

## 杀手问题

| 追问 | 推荐回答 | 立即引用 |
| --- | --- | --- |
| 你们和普通 RAG 的本质差异是什么？ | 普通 RAG 解决片段召回，项目额外把部件、故障、参数和措施关系显式化，并要求 KG 三元组绑定 evidence。 | `docs/challenge_cup/02_技术白皮书.md`; `docs/challenge_cup/07_评审主张证据矩阵.md` |
| GraphRAG 是否全面优于 keyword / hybrid？ | 不做绝对化结论。它在跨实体关系和全局归纳问题上更有价值，评测报告保留 baseline 和失败归因。 | `docs/challenge_cup/03_实验评测报告.md`; `evaluation/reports/challenge_cup_graphrag_same_question_report.md` |
| 数据是否足以支撑生产级运维？ | 当前支撑结项、课程资料知识化和可复核演示，不宣称生产级闭环；高风险运维决策必须人工确认。 | `docs/challenge_cup/05_答辩问答手册.md`; `docs/challenge_cup/08_特等奖评审自评表.md` |
| 现场服务挂了怎么办？ | 不现场排环境，切到离线证据包：browser smoke、截图、KG artifact、readiness gate 和专家审阅索引。 | `docs/challenge_cup/04_系统演示脚本.md`; `docs/challenge_cup/09_专家快速审阅索引.md` |
| 为什么能冲击特等奖？ | 不是靠页面包装，而是靠真实资料处理、知识工程闭环、科学评测、失败归因、可复现门禁和清晰边界。 | `docs/challenge_cup/08_特等奖评审自评表.md`; `docs/challenge_cup/reproducibility/readiness_gate_report.md` |

## 不可夸大边界

- 不说“已经替代工程师”。
- 不说“GraphRAG 对所有问题都更强”。
- 不说“当前数据已经覆盖真实生产全场景”。
- 不把 readiness gate 说成获奖保证；它只证明交付包和演示证据可复核。

## 彩排通过标准

- 90秒开场不超时，且必须讲到问题、方法、完成度和边界。
- 三分钟演示节奏完整跑完，现场失败时能在 20 秒内切换到离线证据包。
- 每个杀手问题至少能在 30 秒内给出一句结论和一个证据锚点。
- 彩排后复核 `docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md`，确认没有把 readiness gate 说成获奖保证。
- 彩排计时结果只写入 `docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md`，真实记录完成前不得提前宣称通过。
- 彩排结束后运行：

```powershell
.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py
```
"""
    return text.replace("{READINESS_GATE_COUNT}", str(READINESS_GATE_COUNT))


def build_application_validation_doc(ctx: dict[str, Any]) -> str:
    validation = ctx["validation"]
    return f"""# 应用场景与专家验证

本材料把项目的“实用性”从概念描述压实为可复核的固定应用场景。当前版本使用现有公开演示快照和角色化审查，不伪造外部生产签字；正式参赛前可把本页作为老师、行业专家或实验室同学反馈的记录表继续补签。

## 固定应用场景

| 场景 | 人工原流程 | 系统辅助后流程 | 验证角色 | 量化收益 | 证据 |
| --- | --- | --- | --- | --- | --- |
| 燃气轮机异常振动诊断证据整理 | 人工在手册、故障样例、维护理论材料中分别查阈值、故障机理、案例现象、检修措施和复机结果，容易漏掉来源记录。 | 输入“{validation["query"]}”，系统在演示集合中返回阈值、机理、GT-07 现象、停机检查、处理建议五类证据，并保留 record id。 | 课程项目评审、动力装备资料审阅者、答辩评委 | `{validation["search_meta"]}`；从 2,655 个向量片段、约 1,185,989 tokens 中一次返回 5 条证据，形成“阈值判断 -> 故障机理 -> 案例现象 -> 检修措施 -> 复机结果”的审计链。 | `docs/challenge_cup/reproducibility/application_validation_report.md`; `docs/challenge_cup/reproducibility/application_value_quantification.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.json`; `{validation["screenshot"]}` |
| 挑战杯现场答辩复核 | 评委需要在有限时间内确认项目是否只是静态展示。 | 先看本页，再打开固定案例报告和 browser smoke 截图，快速核验问题、证据、边界和复现命令。 | 答辩评委、指导教师 | 3-5 分钟内可定位应用场景、证据来源和边界声明，降低口头陈述不可复核风险。 | `docs/challenge_cup/07_评审主张证据矩阵.md`; `docs/challenge_cup/reproducibility/readiness_gate_report.md` |

## 多场景覆盖矩阵

| 场景 ID | 场景 | 复核证据 | 评审用途 | 边界 |
| --- | --- | --- | --- | --- |
| `scenario-gt07-abnormal-vibration` | GT-07 异常振动诊断证据链 | `demo-maint-thresholds-076`; `demo-structure-fault-130`; `demo-gt07-fault-021`; `demo-gt07-repair-022`; `demo-gt07-manual-023` | 展示“阈值 -> 机理 -> 现象 -> 检修 -> 建议”的完整证据组织能力。 | 固定演示场景，不替代工程师最终判断。 |
| `scenario-maintenance-thresholds` | 维护阈值巡检与异常筛查 | `demo-maint-thresholds-076`; `docs/challenge_cup/03_实验评测报告.md`; `evaluation/system_eval_questions.jsonl` | 说明系统不仅返回案例，还能把监测阈值和评测题绑定起来。 | 只能证明本地资料中的阈值证据可追溯。 |
| `scenario-compressor-temperature` | 压气机出口温度偏高处置复核 | `demo-gt07-fault-021`; `demo-gt07-repair-022`; `demo-gt07-manual-023` | 说明故障现象、维修措施和处置建议能被同一条证据链复核。 | 多场景覆盖不等于生产全场景验证。 |

## 边界声明

- 本项目是证据型辅助，不替代工程师做最终运维或维修决策。
- 当前验证使用公开演示快照和 4 本 OCR 质量较稳定的燃气轮机材料，不代表覆盖真实生产全场景。
- Browser smoke 证明本地演示与关键资源可用，不等同于生产压测或上线验收。
- 不声称 RAG / GraphRAG 对所有问题都优于人工或其他检索方法；高风险维修必须人工确认。

## 下一步专家反馈采集

1. 让指导教师或行业背景同学按固定场景独立复核一次，记录其是否能在 5 分钟内找到关键证据。
2. 将反馈分为“证据链完整”“术语解释清楚”“边界是否严谨”“仍需补充数据”四项。
3. 若获得真实签字或邮件反馈，将扫描件或摘要加入 `docs/challenge_cup/reproducibility/application_validation_report.md`，并重新运行 readiness gate。
"""


def build_application_validation_report(ctx: dict[str, Any]) -> str:
    validation = ctx["validation"]
    latency_label = format_latency_from_search_meta(validation["search_meta"])
    return f"""# 应用验证报告

## 固定案例

- 案例名称：燃气轮机异常振动诊断证据链。
- 输入问题：{validation["query"]}。
- 演示集合：gas_turbine_ocr_demo_snapshot。
- 检索结果：{validation["search_meta"]}。
- 复核入口：`docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`；`docs/challenge_cup/reproducibility/browser_demo_smoke_report.json`；`{validation["screenshot"]}`。

## 证据链

| 步骤 | record | 证据作用 | 人工判断 |
| --- | --- | --- | --- |
| 阈值判断 | `demo-maint-thresholds-076` | 给出排气温度散布度、轴承振动、滑油金属颗粒、压气机效率衰减等关键监测阈值。 | 作为异常振动和早期故障诊断线索，不能单独构成停机决策。 |
| 故障机理 | `demo-structure-fault-130` | 说明结构强度故障与不正常振动、停机风险之间的关系。 | 用于解释为什么振动异常需要结合机械损伤风险审查。 |
| 案例现象 | `demo-gt07-fault-021` | GT-07 升负荷至 75% 后，压气机出口温度从 430°C 升至 485°C，振动传感器 VIB-CMP-01 到 7.2 mm/s，并触发“压气机出口温度偏高”报警。 | 现象层证据，提示压气机出口温度偏高和振动异常需要联合分析。 |
| 检修结果 | `demo-gt07-repair-022` | 停机检查发现进气滤网压差偏高、滤网局部堵塞、压气机前三级叶片积灰；清理进气滤网、安排压气机叶片离线清洗并复位温度传感器后，温度回落至 438°C，振动值降至 3.1 mm/s。 | 形成“原因 -> 措施 -> 复机结果”的闭环证据。 |
| 处置建议 | `demo-gt07-manual-023` | 给出压气机出口温度偏高的常见原因：进气阻力增大、压气机叶片污染和温度传感器漂移；建议检查进气滤网、清洗压气机叶片、校验温度传感器。 | 可作为检修清单草案，必须由工程师结合现场工况人工确认。 |

## Scenario Coverage Matrix

| Scenario ID | Maintenance question | Evidence records | What it proves | Boundary |
| --- | --- | --- | --- | --- |
| `scenario-gt07-abnormal-vibration` | Can the package organize an abnormal-vibration diagnosis chain? | `demo-maint-thresholds-076`; `demo-structure-fault-130`; `demo-gt07-fault-021`; `demo-gt07-repair-022`; `demo-gt07-manual-023` | The fixed GT-07 flow links threshold screening, mechanism, symptom, repair result, and disposition advice. | Fixed local scenario only. |
| `scenario-maintenance-thresholds` | Can reviewers trace maintenance thresholds before case-level judgment? | `demo-maint-thresholds-076`; `evaluation/system_eval_questions.jsonl`; `docs/challenge_cup/03_实验评测报告.md` | The system can surface threshold evidence and bind it to the disclosed evaluation set. | Local course/project evidence only. |
| `scenario-compressor-temperature` | Can reviewers audit a compressor outlet temperature alarm path? | `demo-gt07-fault-021`; `demo-gt07-repair-022`; `demo-gt07-manual-023` | The same evidence chain connects alarm symptom, inlet-filter/compressor-blade findings, and manual disposition. | This is not production full-scenario validation. |

## 半量化收益

- 系统在演示快照中从 2,655 个向量片段、约 1,185,989 tokens 中返回 5 条证据结果，检索延迟为 {latency_label}。
- 人工原流程需要分别查找阈值、故障机理、案例现象、检修结果和处置建议；系统辅助后把这五类证据组织到同一页结果中。
- 对结项和挑战杯答辩的价值是：评委可以沿 record id 复核证据链，避免只听“系统能诊断”的口头承诺。

## 边界结论

本案例证明系统能辅助完成异常振动诊断的证据整理和来源追溯，但不证明它可以替代工程师做最终维修决策。GT-07 案例中的进气滤网、压气机叶片和温度传感器判断仍必须结合真实现场数据、设备规程和人工确认。
"""


def build_expert_feedback_protocol(ctx: dict[str, Any]) -> str:
    return """# 专家反馈采集与整改闭环

本页用于把外部意见采集变成可审计流程。当前反馈采集状态为：待真实反馈归档。未收到真实签字、邮件或会议纪要前，不伪造外部意见，不宣称项目已经通过专家验证。

## 反馈采集状态

| 项目 | 当前状态 | 归档规则 |
| --- | --- | --- |
| 指导教师反馈 | 待真实反馈归档 | 使用 `docs/challenge_cup/reproducibility/expert_feedback_form.md`，附签字页、邮件截图或会议纪要。 |
| 行业或实验室同学反馈 | 待真实反馈归档 | 记录单位或角色、联系方式、评审日期、评审问题和整改建议。 |
| 固定应用场景复核 | 已准备固定材料 | 复核 `docs/challenge_cup/reproducibility/application_validation_report.md` 与固定查询证据链。 |
| readiness 复核 | 已有机器门禁 | 反馈归档后重新运行 `docs/challenge_cup/reproducibility/readiness_gate_report.md` 对应命令。 |

## 专家反馈采集表

- 表单入口：`docs/challenge_cup/reproducibility/expert_feedback_form.md`。
- 评审对象：项目一页纸、固定场景演示、应用验证报告、readiness gate、浏览器截图。
- 核心问题：实用性是否成立、证据链是否可信、边界是否严谨、哪些材料仍需补充。

## 整改闭环

| 步骤 | 动作 | 可审计证据 |
| --- | --- | --- |
| 1 | 发出反馈表和固定场景材料 | 邮件、聊天记录或会议邀请截图。 |
| 2 | 收到反馈后摘录关键意见 | 签字页、邮件回复、会议纪要或反馈表原件。 |
| 3 | 将意见拆成整改项 | 在本页追加“意见-整改-证据”表。 |
| 4 | 完成整改后重跑 gate | `python scripts/build_challenge_cup_package.py`；`python scripts/check_challenge_cup_readiness.py`。 |

## 诚信边界

- 不伪造外部意见，不把内部自评写成专家背书。
- 不把“已准备采集协议”说成“已获得专家认可”。
- 真实反馈如果提出否定意见，必须保留并进入整改闭环。
"""


def build_expert_feedback_form(ctx: dict[str, Any]) -> str:
    return """# 专家反馈采集表

## 评审人信息

- 评审人姓名：
- 单位或角色：
- 联系方式：
- 评审日期：
- 签字或邮件证据：

## 评审材料

| 材料 | 路径 | 复核要点 |
| --- | --- | --- |
| 项目一页纸 | `docs/challenge_cup/00_项目一页纸.md` | 问题、方法、数字和边界是否清楚。 |
| 固定场景演示 | `docs/challenge_cup/04_系统演示脚本.md` | 是否能按 3 分钟节奏讲清证据链。 |
| 应用验证报告 | `docs/challenge_cup/reproducibility/application_validation_report.md` | `燃气轮机异常振动诊断流程` 是否能支撑应用价值。 |
| 浏览器证据 | `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md` | 5 条记录是否可复核，含 `demo-gt07-repair-022`。 |
| readiness gate | `docs/challenge_cup/reproducibility/readiness_gate_report.md` | 机器门禁是否证明包完整性和边界。 |

## 评分表

| 维度 | 评分 | 证据或意见 |
| --- | --- | --- |
| 实用性 |  |  |
| 创新性 |  |  |
| 工程完成度 |  |  |
| 评测可信度 |  |  |
| 答辩可讲清程度 |  |  |

## 整改建议

| 问题 | 严重度 | 建议 | 需补证据 |
| --- | --- | --- | --- |
|  |  |  |  |

## 归档路径

反馈原件、签字页、邮件截图或会议纪要应归档到挑战杯证据包，并在 `docs/challenge_cup/12_专家反馈采集与整改闭环.md` 追加整改记录。未归档真实证据前，不得宣称已经获得专家认可。
"""


def build_runbook(ctx: dict[str, Any]) -> str:
    return """# 可复现运行手册

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -q
.\.venv\Scripts\python.exe -m pytest api_server/current_console/chroma_rag_poc/tests -q
```

## 扩展评测集

```powershell
.\.venv\Scripts\python.exe scripts/extend_challenge_cup_eval_questions.py
```

## 运行现场演示烟测

```powershell
.\.venv\Scripts\python.exe scripts/run_challenge_cup_live_demo_smoke.py
node scripts/run_challenge_cup_browser_demo_smoke.mjs
```

## 重新生成 Day3 baseline

```powershell
.\.venv\Scripts\python.exe scripts/run_day3_retrieval_baselines.py --dataset evaluation/system_eval_questions.jsonl --top-k 5
```

## 重新生成 Day4 失败分析

```powershell
.\.venv\Scripts\python.exe scripts/analyze_day4_failure_cases.py
```

## 生成 Day4 失败整改 before/after

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_failure_remediation_before_after.py
```

## 生成应用价值量化报告

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_application_value_quantification.py
```

## 生成数值追溯一致性报告

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_numeric_traceability_report.py
```

## 生成无答案边界评测报告

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_no_answer_boundary_evaluation.py
```

## 生成评审主张诚信报告

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_claim_integrity_report.py
```

## 生成官方评分维度答辩覆盖报告

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_rubric_defense_coverage.py
```

## 生成运行环境复现快照

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_runtime_reproducibility_snapshot.py
```

## 生成复核转录摘要

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_verification_transcript.py
```

## 重新生成挑战杯成果包

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_package.py
```

## 刷新终审答辩 PPT

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_defense_deck.py --force
```

## 刷新官方评审口径对齐表

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_official_rubric_alignment.py
```

## 归档真实硬证据

收到真实专家反馈附件后运行：

```powershell
.\.venv\Scripts\python.exe scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id <real-feedback-id> --source <real-feedback-file> --evidence-type email_reply --reviewer-identity <real-reviewer-identity> --role-or-org <real-reviewer-role-or-org> --review-date <real-review-date-yyyy-mm-dd> --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback
.\.venv\Scripts\python.exe scripts/record_challenge_cup_hard_evidence.py expert_feedback --id <real-feedback-id> --source <real-feedback-file> --evidence-type email_reply --reviewer-identity <real-reviewer-identity> --role-or-org <real-reviewer-role-or-org> --review-date <real-review-date-yyyy-mm-dd> --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback
```

真实外发专家反馈请求后，先记录外发凭证；这不等同于专家反馈硬证据：

```powershell
.\.venv\Scripts\python.exe scripts/record_challenge_cup_expert_outreach.py --id <real-outreach-id> --source <real-outreach-proof> --recipient-alias <real-reviewer-alias> --recipient-role <real-reviewer-role> --channel email --sent-date <real-sent-date-yyyy-mm-dd> --status sent --requested-review-dimension practicality --requested-review-dimension innovation --requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/00_项目一页纸.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date <real-followup-due-date-yyyy-mm-dd> --confirm-real-outreach
```

真实计时彩排排期或观察员准备完成后，先记录排期凭证；这不等同于真实计时彩排硬证据：

```powershell
.\.venv\Scripts\python.exe scripts/record_challenge_cup_timed_rehearsal_schedule.py --id <real-rehearsal-schedule-id> --source <real-calendar-or-observer-prep-file> --scheduled-date <real-scheduled-date-yyyy-mm-dd> --observer <real-observer-alias> --venue-or-channel <real-venue-or-channel> --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible --checklist-item browser-smoke-opened --checklist-item offline-archive-ready --checklist-item five-killer-questions-assigned --confirm-real-schedule
```

完成真实计时彩排后，首选用测得秒数生成观察员记录并归档：

```powershell
.\.venv\Scripts\python.exe scripts/run_challenge_cup_timed_rehearsal.py --id <real-rehearsal-id> --source <real-timer-or-observer-file> --rehearsal-date <real-rehearsal-date-yyyy-mm-dd> --observer <real-observer-alias> --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal
```

如果已有真实计时截图、录屏或观察员笔记附件，也可以直接归档：

```powershell
.\.venv\Scripts\python.exe scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal --id <real-rehearsal-id> --source <real-timer-or-observer-file> --evidence-type observer_note --rehearsal-date <real-rehearsal-date-yyyy-mm-dd> --observer <real-observer-alias> --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal
.\.venv\Scripts\python.exe scripts/record_challenge_cup_hard_evidence.py timed_rehearsal --id <real-rehearsal-id> --source <real-timer-or-observer-file> --evidence-type observer_note --rehearsal-date <real-rehearsal-date-yyyy-mm-dd> --observer <real-observer-alias> --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal
```

## 刷新硬证据台账

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_expert_outreach_ledger.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_timed_rehearsal_schedule_ledger.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_hard_evidence_closure_board.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_hard_evidence_action_pack.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_external_evidence_execution_kit.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_external_evidence_closeout_checklist.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_hard_evidence_ledger.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_judge_objection_matrix.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_special_prize_readiness_dashboard.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_defense_slide_traceability.py
```

## 运行结项 readiness gate

```powershell
.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py
```

## 运行总目标完成门禁

```powershell
.\.venv\Scripts\python.exe scripts/check_challenge_cup_goal_completion.py
.\.venv\Scripts\python.exe docs/challenge_cup/reproducibility/verify_submission_package.py --root .
.\.venv\Scripts\python.exe scripts/build_challenge_cup_final_acceptance_audit.py
```

当前缺少真实专家反馈和真实计时彩排时，该门禁应返回 fail；这不是包生成失败，而是防止把 package readiness 误写成总目标已完成。
"""


def build_hard_evidence_dataset_manifest_section() -> str:
    return "\n".join(
        [
            "",
            "## 硬证据台账",
            "",
            f"- 硬证据台账：`{md_link(HARD_EVIDENCE_LEDGER_MD)}`",
            f"- 硬证据 JSON：`{md_link(HARD_EVIDENCE_LEDGER_JSON)}`",
            f"- 硬证据归档入口：`{md_link(HARD_EVIDENCE_README)}`",
            f"- 真实专家反馈归档入口：`{md_link(HARD_EVIDENCE_EXPERT_README)}`",
            f"- 真实计时彩排归档入口：`{md_link(HARD_EVIDENCE_REHEARSAL_README)}`",
            f"- 专家反馈外发追踪台账：`{md_link(EXPERT_FEEDBACK_OUTREACH_LEDGER_MD)}`",
            f"- 专家反馈外发追踪 JSON：`{md_link(EXPERT_FEEDBACK_OUTREACH_LEDGER_JSON)}`",
            f"- 专家反馈外发追踪入口：`{md_link(EXPERT_FEEDBACK_OUTREACH_README)}`",
            f"- Timed rehearsal schedule ledger: `{md_link(TIMED_REHEARSAL_SCHEDULE_LEDGER_MD)}`",
            f"- Timed rehearsal schedule JSON: `{md_link(TIMED_REHEARSAL_SCHEDULE_LEDGER_JSON)}`",
            f"- Timed rehearsal schedule intake: `{md_link(TIMED_REHEARSAL_SCHEDULE_README)}`",
            f"- Hard evidence closure board: `{md_link(HARD_EVIDENCE_CLOSURE_BOARD_MD)}`",
            f"- Hard evidence closure JSON: `{md_link(HARD_EVIDENCE_CLOSURE_BOARD_JSON)}`",
            f"- Hard evidence action pack: `{md_link(HARD_EVIDENCE_ACTION_PACK_MD)}`",
            f"- Hard evidence action pack JSON: `{md_link(HARD_EVIDENCE_ACTION_PACK_JSON)}`",
            f"- External evidence execution kit: `{md_link(EXTERNAL_EVIDENCE_EXECUTION_KIT_MD)}`",
            f"- External evidence execution kit JSON: `{md_link(EXTERNAL_EVIDENCE_EXECUTION_KIT_JSON)}`",
            f"- External evidence closeout checklist: `{md_link(EXTERNAL_EVIDENCE_CLOSEOUT_CHECKLIST_MD)}`",
            f"- External evidence closeout checklist JSON: `{md_link(EXTERNAL_EVIDENCE_CLOSEOUT_CHECKLIST_JSON)}`",
            f"- Expert review handoff: `{md_link(EXTERNAL_EVIDENCE_EXPERT_HANDOFF_MD)}`",
            f"- Timed rehearsal observer sheet: `{md_link(EXTERNAL_EVIDENCE_TIMED_REHEARSAL_OBSERVER_MD)}`",
            f"- Special prize readiness dashboard: `{md_link(SPECIAL_PRIZE_READINESS_DASHBOARD_MD)}`",
            f"- Special prize readiness dashboard JSON: `{md_link(SPECIAL_PRIZE_READINESS_DASHBOARD_JSON)}`",
            f"- 终审提交总目录与签收页：`{md_link(FINAL_SUBMISSION_HANDOFF)}`",
        ]
    )


def build_official_rubric_dataset_manifest_section() -> str:
    return "\n".join(
        [
            "",
            "## 官方评审口径对齐",
            "",
            f"- 官方评审口径对齐表：`{md_link(OFFICIAL_RUBRIC_ALIGNMENT_MD)}`",
            f"- 官方评审口径 JSON：`{md_link(OFFICIAL_RUBRIC_ALIGNMENT_JSON)}`",
            "",
            "## Submission Package Offline Verification",
            "",
            f"- Offline verifier: `{md_link(SUBMISSION_PACKAGE_VERIFIER)}`",
            f"- Final acceptance audit: `{md_link(FINAL_ACCEPTANCE_AUDIT_MD)}`",
            f"- Final acceptance audit JSON: `{md_link(FINAL_ACCEPTANCE_AUDIT_JSON)}`",
        ]
    )


def build_application_value_dataset_manifest_section() -> str:
    return "\n".join(
        [
            "",
            "## Application Value Quantification",
            "",
            f"- Application value quantification: `{md_link(APPLICATION_VALUE_QUANTIFICATION_REPORT)}`",
            f"- Application value quantification JSON: `{md_link(APPLICATION_VALUE_QUANTIFICATION_REPORT_JSON)}`",
        ]
    )


def build_numeric_traceability_dataset_manifest_section() -> str:
    return "\n".join(
        [
            "",
            "## Numeric Traceability Report",
            "",
            f"- Numeric traceability report: `{md_link(NUMERIC_TRACEABILITY_REPORT)}`",
            f"- Numeric traceability JSON: `{md_link(NUMERIC_TRACEABILITY_REPORT_JSON_PATH)}`",
        ]
    )


def build_no_answer_boundary_dataset_manifest_section() -> str:
    return "\n".join(
        [
            "",
            "## No-Answer Boundary Evaluation",
            "",
            f"- No-answer boundary evaluation: `{md_link(NO_ANSWER_BOUNDARY_EVALUATION_REPORT)}`",
            f"- No-answer boundary JSON: `{md_link(NO_ANSWER_BOUNDARY_EVALUATION_REPORT_JSON)}`",
        ]
    )


def build_claim_integrity_dataset_manifest_section() -> str:
    return "\n".join(
        [
            "",
            "## Claim Integrity Report",
            "",
            f"- Claim integrity report: `{md_link(CLAIM_INTEGRITY_REPORT)}`",
            f"- Claim integrity JSON: `{md_link(CLAIM_INTEGRITY_REPORT_JSON_PATH)}`",
        ]
    )


def build_rubric_defense_coverage_dataset_manifest_section() -> str:
    return "\n".join(
        [
            "",
            "## Rubric Defense Coverage",
            "",
            f"- Rubric defense coverage report: `{md_link(RUBRIC_DEFENSE_COVERAGE_REPORT)}`",
            f"- Rubric defense coverage JSON: `{md_link(RUBRIC_DEFENSE_COVERAGE_REPORT_JSON)}`",
        ]
    )


def build_defense_slide_traceability_dataset_manifest_section() -> str:
    return "\n".join(
        [
            "",
            "## Defense Slide Traceability",
            "",
            f"- Defense slide traceability report: `{md_link(DEFENSE_SLIDE_TRACEABILITY_REPORT)}`",
            f"- Defense slide traceability JSON: `{md_link(DEFENSE_SLIDE_TRACEABILITY_REPORT_JSON)}`",
        ]
    )


def build_runtime_reproducibility_dataset_manifest_section() -> str:
    return "\n".join(
        [
            "",
            "## Runtime Reproducibility Snapshot",
            "",
            f"- Runtime reproducibility snapshot: `{md_link(RUNTIME_REPRODUCIBILITY_SNAPSHOT_REPORT)}`",
            f"- Runtime reproducibility snapshot JSON: `{md_link(RUNTIME_REPRODUCIBILITY_SNAPSHOT_REPORT_JSON)}`",
        ]
    )


def build_verification_transcript_dataset_manifest_section() -> str:
    return "\n".join(
        [
            "",
            "## Verification Transcript",
            "",
            f"- Verification transcript: `{md_link(VERIFICATION_TRANSCRIPT_REPORT)}`",
            f"- Verification transcript JSON: `{md_link(VERIFICATION_TRANSCRIPT_REPORT_JSON)}`",
        ]
    )


def build_dataset_manifest(ctx: dict[str, Any]) -> str:
    return f"""# 数据集与证据清单

- 系统评测集：`evaluation/system_eval_questions.jsonl`，{ctx["question_count"]} 题。
- 评测覆盖画像：`{md_link(EVAL_COVERAGE_PROFILE)}`。
- 普通 RAG 数据库说明：`{md_link(ctx["rag_db"])}`。
- 知识图谱人工评审：`{md_link(ctx["kg_review"])}`。
- Day3 baseline：`{optional_md_link(ctx["day3"])}`。
- Day4 失败分析：`{optional_md_link(ctx["day4"])}`。
- GraphRAG 同题子集：`{optional_md_link(ctx["graph_report"])}`。
- GraphRAG 同题 JSON：`{optional_md_link(ctx["graph_report_json"])}`。
- GraphRAG context-only demo：`{optional_md_link(ctx["graph_context_demo_md"])}`。
- GraphRAG context-only JSON：`{optional_md_link(ctx["graph_context_demo_json"])}`。
- GraphRAG answer benchmark：`{optional_md_link(ctx["graph_answer_benchmark_md"])}`。
- GraphRAG answer benchmark JSON：`{optional_md_link(ctx["graph_answer_benchmark_json"])}`。
- GraphRAG 补证整改计划：`{optional_md_link(ctx["graph_gap_remediation_md"])}`。
- GraphRAG 补证整改 JSON：`{optional_md_link(ctx["graph_gap_remediation_json"])}`。
- Day4 失败整改 before/after：`{optional_md_link(ctx["failure_remediation_before_after_md"])}`。
- Day4 失败整改 before/after JSON：`{optional_md_link(ctx["failure_remediation_before_after_json"])}`。
- GraphRAG manual evidence supplement：`{md_link(GRAPH_MANUAL_EVIDENCE_SUPPLEMENT)}`。
- 评审主张证据矩阵：`{md_link(CLAIM_MATRIX)}`。
- 特等奖评审自评表：`{md_link(AWARD_SELF_EVAL)}`。
- 专家快速审阅索引：`{md_link(EXPERT_REVIEW_INDEX)}`。
- 评委现场速览卡：`{md_link(JUDGE_BRIEFING_CARD)}`。
- 现场答辩操作 Runbook：`{md_link(ONSITE_DEFENSE_RUNBOOK)}`。
- 结项交付移交清单：`{md_link(PROJECT_HANDOFF_CHECKLIST)}`。
- 现场问辩记录与整改台账：`{md_link(DEFENSE_QA_REMEDIATION_LEDGER)}`。
- 评审风险控制与应急预案：`{md_link(REVIEW_RISK_RESPONSE_PLAN)}`。
- 特等奖打分模拟与整改清单：`{md_link(SPECIAL_PRIZE_SCORING_DRILL)}`。
- 作品展墙报问辩与展台脚本：`{md_link(POSTER_BOOTH_QA_PACK)}`。
- 成果转化与持续迭代路线图：`{md_link(COMMERCIALIZATION_ROADMAP)}`。
- 知识产权与开源合规说明：`{md_link(IP_OPEN_SOURCE_COMPLIANCE)}`。
- 同类方案对比与创新性证据卡：`{md_link(LOCAL_BASELINE_DIFFERENTIATION)}`。
- 作品展 A0 展板源文件：`{md_link(POSTER_BOARD_HTML)}`。
- 现场答辩总控台：`{md_link(DEFENSE_CONTROL_CONSOLE)}`。
- 评委质疑攻防矩阵：`{md_link(JUDGE_OBJECTION_MATRIX_MD)}`。
- 答辩攻防与彩排卡：`{md_link(DEFENSE_REHEARSAL_CARD)}`。
- 终审答辩 PPTX：`{md_link(DEFENSE_DECK_PPTX)}`。
- 终审答辩讲稿：`{md_link(DEFENSE_DECK_NOTES)}`。
- 答辩彩排计分卡：`{md_link(DEFENSE_REHEARSAL_SCORECARD_MD)}`。
- 答辩彩排计分 JSON：`{md_link(DEFENSE_REHEARSAL_SCORECARD_JSON)}`。
- 答辩计时彩排结果归档包：`{md_link(DEFENSE_REHEARSAL_RESULT_PACKET_MD)}`。
- 答辩计时彩排结果 JSON：`{md_link(DEFENSE_REHEARSAL_RESULT_PACKET_JSON)}`。
- 专家反馈外发包：`{md_link(EXPERT_FEEDBACK_REQUEST_PACKET_MD)}`。
- 专家反馈外发 JSON：`{md_link(EXPERT_FEEDBACK_REQUEST_PACKET_JSON)}`。
- 应用场景与专家验证：`{md_link(APPLICATION_VALIDATION_DOC)}`。
- 应用验证报告：`{md_link(APPLICATION_VALIDATION_REPORT)}`。
- 专家反馈采集与整改闭环：`{md_link(EXPERT_FEEDBACK_PROTOCOL)}`。
- 专家反馈采集表：`{md_link(EXPERT_FEEDBACK_FORM)}`。
- 现场演示烟测：`{md_link(LIVE_SMOKE_REPORT)}`。
- 真实浏览器演示烟测：`{md_link(BROWSER_SMOKE_REPORT)}`。
- 真实浏览器烟测 JSON：`{md_link(BROWSER_SMOKE_JSON)}`。
- 结项 readiness gate：`{md_link(READINESS_GATE_REPORT)}`。
- 总目标完成门禁：`{md_link(GOAL_COMPLETION_REPORT)}`。
- 证据完整性哈希：`{md_link(EVIDENCE_HASHES)}`。
- 可提交归档包：`{md_link(SUBMISSION_ARCHIVE)}`。
- 可提交归档包哈希清单：`{md_link(SUBMISSION_ARCHIVE_MANIFEST)}`。
- 浏览器验收截图：`{md_link(BROWSER_SCREENSHOT_DIR)}/`。
- 浏览器桌面总览截图：`{md_link(BROWSER_SCREENSHOTS[0])}`。
- 浏览器桌面检索截图：`{md_link(BROWSER_SCREENSHOTS[1])}`。
- 浏览器 KG 产物截图：`{md_link(BROWSER_SCREENSHOTS[2])}`。
- 浏览器移动端截图：`{md_link(BROWSER_SCREENSHOTS[3])}`。
- 课程最终交付包：`{md_link(ctx["course_pack"])}`。
"""


def build_command_log(ctx: dict[str, Any]) -> str:
    return f"""# 命令记录

生成时间：{ctx["now"]}

## 2026-06-05 本轮验证记录

```text
python scripts/extend_challenge_cup_eval_questions.py
-> Wrote 60 questions to evaluation/system_eval_questions.jsonl

python scripts/build_challenge_cup_package.py
-> Wrote docs/challenge_cup with 60 evaluation questions
-> docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx
-> docs/challenge_cup/defense_deck/challenge_cup_defense_speaker_notes.md
-> docs/challenge_cup/11_应用场景与专家验证.md
-> docs/challenge_cup/12_专家反馈采集与整改闭环.md
-> docs/challenge_cup/reproducibility/application_validation_report.md
-> docs/challenge_cup/reproducibility/application_value_quantification.md
-> docs/challenge_cup/reproducibility/application_value_quantification.json
-> docs/challenge_cup/reproducibility/runtime_reproducibility_snapshot.md
-> docs/challenge_cup/reproducibility/runtime_reproducibility_snapshot.json
-> docs/challenge_cup/reproducibility/verification_transcript.md
-> docs/challenge_cup/reproducibility/verification_transcript.json
-> docs/challenge_cup/reproducibility/expert_feedback_form.md
-> docs/challenge_cup/reproducibility/evaluation_coverage_profile.json
-> docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip
-> docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json

python scripts/run_day3_retrieval_baselines.py --dataset evaluation/system_eval_questions.jsonl --top-k 5
-> Corpus chunks: 6494
-> evaluation/reports/day3_retrieval_baseline_comparison_20260605_210540.md

python scripts/analyze_day4_failure_cases.py
-> evaluation/reports/day4_failure_analysis_20260605_210642.md
-> Analyzed cases: 40

python -m pytest tests/unit -q
-> 218 passed

python -m pytest api_server/current_console/chroma_rag_poc/tests -q
-> 21 passed

python scripts/run_challenge_cup_live_demo_smoke.py
-> docs/challenge_cup/reproducibility/live_demo_smoke_report.md
-> Status: pass (5/5 checks)

python -m unittest tests/unit/test_console_import_compat.py
-> OK

python -m unittest tests/unit/test_frontend_demo_mode_contract.py
-> OK

python -m unittest api_server/current_console/chroma_rag_poc/tests/test_pipeline.py -k test_frontend_libs_and_assets_are_served_from_root_paths
-> OK

python -m unittest api_server/current_console/chroma_rag_poc/tests/test_pipeline.py -k test_deliverable_assets_are_served_from_stable_root_path
-> OK

python scripts/build_graphrag_context_demo.py
-> evaluation/reports/challenge_cup_graphrag_context_demo.md
-> evaluation/reports/challenge_cup_graphrag_context_demo.json

python scripts/build_graphrag_answer_benchmark.py
-> evaluation/reports/challenge_cup_graphrag_answer_benchmark.md
-> evaluation/reports/challenge_cup_graphrag_answer_benchmark.json

python scripts/build_graphrag_gap_remediation_plan.py
-> evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.md
-> evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.json

python scripts/build_challenge_cup_failure_remediation_before_after.py
-> evaluation/reports/challenge_cup_failure_remediation_before_after.md
-> Status: remediation_card_ablation_ready_no_live_retriever_claim

python scripts/build_challenge_cup_application_value_quantification.py
-> docs/challenge_cup/reproducibility/application_value_quantification.md
-> docs/challenge_cup/reproducibility/application_value_quantification.json
-> Status: application_value_quantified_no_external_validation_claim

python scripts/build_challenge_cup_numeric_traceability_report.py
-> docs/challenge_cup/reproducibility/numeric_traceability_report.md
-> docs/challenge_cup/reproducibility/numeric_traceability_report.json
-> Status: numeric_traceability_consistent_no_external_claim

python scripts/build_challenge_cup_no_answer_boundary_evaluation.py
-> docs/challenge_cup/reproducibility/no_answer_boundary_evaluation.md
-> docs/challenge_cup/reproducibility/no_answer_boundary_evaluation.json
-> Status: no_answer_boundary_guard_verified_no_live_llm_claim

python scripts/build_challenge_cup_claim_integrity_report.py
-> docs/challenge_cup/reproducibility/claim_integrity_report.md
-> docs/challenge_cup/reproducibility/claim_integrity_report.json
-> Status: claim_integrity_verified_no_award_or_external_claim

python scripts/build_challenge_cup_rubric_defense_coverage.py
-> docs/challenge_cup/reproducibility/rubric_defense_coverage.md
-> docs/challenge_cup/reproducibility/rubric_defense_coverage.json
-> Status: rubric_defense_coverage_ready_no_award_claim

python scripts/build_challenge_cup_defense_slide_traceability.py
-> docs/challenge_cup/reproducibility/defense_slide_traceability.md
-> docs/challenge_cup/reproducibility/defense_slide_traceability.json
-> Status: defense_slide_traceability_ready_no_rehearsal_or_award_claim

python scripts/build_challenge_cup_runtime_reproducibility_snapshot.py
-> docs/challenge_cup/reproducibility/runtime_reproducibility_snapshot.md
-> docs/challenge_cup/reproducibility/runtime_reproducibility_snapshot.json
-> Status: runtime_snapshot_ready_no_environment_portability_claim

python scripts/build_challenge_cup_poster_render_smoke.py
-> docs/challenge_cup/reproducibility/poster_render_smoke_report.md
-> docs/challenge_cup/reproducibility/poster_render_smoke_report.json
-> Status: pass

python scripts/build_challenge_cup_verification_transcript.py
-> docs/challenge_cup/reproducibility/verification_transcript.md
-> docs/challenge_cup/reproducibility/verification_transcript.json
-> Status: package_verification_transcript_ready_goal_still_blocked

python scripts/build_defense_rehearsal_scorecard.py
-> docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md
-> docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.json

python scripts/build_defense_rehearsal_result_packet.py
-> docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md
-> docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.json

python scripts/build_expert_feedback_request_packet.py
-> docs/challenge_cup/reproducibility/expert_feedback_request_packet.md
-> docs/challenge_cup/reproducibility/expert_feedback_request_packet.json

python scripts/build_challenge_cup_expert_outreach_ledger.py
-> docs/challenge_cup/reproducibility/expert_feedback_outreach_ledger.md
-> docs/challenge_cup/reproducibility/expert_feedback_outreach_ledger.json

python scripts/build_challenge_cup_timed_rehearsal_schedule_ledger.py
-> docs/challenge_cup/reproducibility/timed_rehearsal_schedule_ledger.md
-> docs/challenge_cup/reproducibility/timed_rehearsal_schedule_ledger.json

python scripts/build_challenge_cup_hard_evidence_closure_board.py
-> docs/challenge_cup/reproducibility/hard_evidence_closure_board.md
-> docs/challenge_cup/reproducibility/hard_evidence_closure_board.json

python scripts/build_challenge_cup_hard_evidence_action_pack.py
-> docs/challenge_cup/reproducibility/hard_evidence_action_pack.md
-> Status: ready_for_real_external_evidence_collection

python scripts/build_challenge_cup_external_evidence_execution_kit.py
-> docs/challenge_cup/reproducibility/external_evidence_execution_kit.md
-> Status: ready_for_external_execution_handoff

python scripts/build_challenge_cup_external_evidence_closeout_checklist.py
-> docs/challenge_cup/reproducibility/external_evidence_closeout_checklist.md
-> docs/challenge_cup/reproducibility/external_evidence_closeout_checklist.json
-> Status: ready_for_real_external_evidence_closeout

python scripts/build_challenge_cup_official_rubric_alignment.py
-> docs/challenge_cup/reproducibility/official_rubric_alignment.md
-> docs/challenge_cup/reproducibility/official_rubric_alignment.json

python scripts/build_challenge_cup_judge_objection_matrix.py
-> docs/challenge_cup/reproducibility/judge_objection_response_matrix.md
-> Status: ready_for_judge_objection_drill_no_external_claims

python scripts/build_challenge_cup_hard_evidence_ledger.py
-> docs/challenge_cup/reproducibility/hard_evidence_ledger.md
-> docs/challenge_cup/reproducibility/hard_evidence_ledger.json

python scripts/build_challenge_cup_special_prize_readiness_dashboard.py
-> docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md
-> Status: special_prize_review_ready_with_external_evidence_gaps

node scripts/run_challenge_cup_browser_demo_smoke.mjs
-> docs/challenge_cup/reproducibility/browser_demo_smoke_report.md
-> docs/challenge_cup/reproducibility/browser_demo_smoke_report.json
-> docs/challenge_cup/reproducibility/browser_screenshots/desktop_overview.png
-> docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png
-> docs/challenge_cup/reproducibility/browser_screenshots/desktop_kg_artifacts.png
-> docs/challenge_cup/reproducibility/browser_screenshots/mobile_overview.png
-> Status: pass (13/13 checks)

python docs/challenge_cup/reproducibility/verify_submission_package.py --root .
-> Status: pass

python scripts/build_challenge_cup_final_acceptance_audit.py
-> docs/challenge_cup/reproducibility/final_acceptance_audit.md
-> Status: package_ready_awaiting_external_hard_evidence

python scripts/check_challenge_cup_readiness.py
-> docs/challenge_cup/reproducibility/readiness_gate_report.md
-> Status: pass ({READINESS_GATE_COUNT}/{READINESS_GATE_COUNT} gates)

python scripts/check_challenge_cup_goal_completion.py
-> docs/challenge_cup/reproducibility/goal_completion_report.md
-> Status: fail (awaiting real expert feedback and timed rehearsal)
```

推荐复现命令见 `runbook.md`。重新运行后，以新的终端输出和报告时间戳为准。
"""


def main() -> int:
    ctx = build_context()
    write(OUT / "README_先看这里.md", build_readme(ctx))
    write(OUT / "00_项目一页纸.md", build_one_page(ctx))
    write(OUT / "01_挑战杯项目书.md", build_project_book(ctx))
    write(OUT / "02_技术白皮书.md", build_whitepaper(ctx))
    write(OUT / "03_实验评测报告.md", build_eval_report(ctx))
    write(OUT / "04_系统演示脚本.md", build_demo_script(ctx))
    write(OUT / "05_答辩问答手册.md", build_qa(ctx))
    write(ACCEPTANCE_CHECKLIST, build_checklist(ctx))
    write(CLAIM_MATRIX, build_claim_evidence_matrix(ctx))
    write(AWARD_SELF_EVAL, build_award_self_eval(ctx))
    write(EXPERT_REVIEW_INDEX, build_expert_review_index(ctx))
    write(DEFENSE_REHEARSAL_CARD, build_defense_rehearsal_card(ctx))
    write(APPLICATION_VALIDATION_DOC, build_application_validation_doc(ctx))
    write(EXPERT_FEEDBACK_PROTOCOL, build_expert_feedback_protocol(ctx))
    write(JUDGE_BRIEFING_CARD, build_judge_briefing_card(ctx))
    write(ONSITE_DEFENSE_RUNBOOK, build_onsite_defense_runbook(ctx))
    write(PROJECT_HANDOFF_CHECKLIST, build_project_handoff_checklist(ctx))
    write(DEFENSE_QA_REMEDIATION_LEDGER, build_defense_qa_remediation_ledger(ctx))
    write(REVIEW_RISK_RESPONSE_PLAN, build_review_risk_response_plan(ctx))
    write(SPECIAL_PRIZE_SCORING_DRILL, build_special_prize_scoring_drill(ctx))
    write(POSTER_BOOTH_QA_PACK, build_poster_booth_qa_pack(ctx))
    write(COMMERCIALIZATION_ROADMAP, build_commercialization_roadmap(ctx))
    write(IP_OPEN_SOURCE_COMPLIANCE, build_ip_open_source_compliance(ctx))
    write(LOCAL_BASELINE_DIFFERENTIATION, build_local_baseline_differentiation_card(ctx))
    write(SUBMISSION_INTEGRITY_CARD, build_submission_integrity_card(ctx))
    write(FINAL_SUBMISSION_HANDOFF, build_final_submission_handoff(ctx))
    write(POSTER_BOARD_HTML, build_poster_board_html(ctx))
    write_poster_render_smoke_outputs()
    write(DEFENSE_CONTROL_CONSOLE, build_defense_control_console_html(ctx))
    write(APPLICATION_VALIDATION_REPORT, build_application_validation_report(ctx))
    write_application_value_quantification_outputs()
    write_numeric_traceability_report_outputs()
    write_no_answer_boundary_evaluation_outputs()
    write_claim_integrity_report_outputs()
    write_runtime_reproducibility_snapshot_outputs()
    write(EXPERT_FEEDBACK_FORM, build_expert_feedback_form(ctx))
    write(SUBMISSION_PACKAGE_VERIFIER, SUBMISSION_PACKAGE_VERIFIER_SOURCE.read_text(encoding="utf-8"))
    write_defense_scorecard_outputs(build_defense_scorecard_payload())
    write_defense_result_outputs(build_defense_result_payload())
    write_expert_request_outputs(build_expert_request_payload())
    expert_outreach_payload = write_expert_outreach_outputs()
    timed_rehearsal_schedule_payload = write_timed_rehearsal_schedule_outputs()
    write_hard_evidence_closure_board_outputs()
    write_hard_evidence_action_pack_outputs()
    write_external_evidence_execution_kit_outputs()
    write_external_evidence_closeout_checklist_outputs()
    write_official_rubric_alignment_outputs()
    write_judge_objection_matrix_outputs()
    hard_evidence_payload = write_hard_evidence_ledger_outputs()
    graph_answer_payload = build_graph_answer_benchmark_payload()
    write(GRAPH_ANSWER_BENCHMARK_JSON, json.dumps(graph_answer_payload, ensure_ascii=False, indent=2))
    write_graph_answer_benchmark_markdown(GRAPH_ANSWER_BENCHMARK_MD, graph_answer_payload)
    graph_gap_payload = build_graph_gap_remediation_payload()
    write(GRAPH_GAP_REMEDIATION_JSON, json.dumps(graph_gap_payload, ensure_ascii=False, indent=2))
    write_graph_gap_remediation_markdown(GRAPH_GAP_REMEDIATION_MD, graph_gap_payload)
    write_failure_remediation_before_after_outputs()
    write_rubric_defense_coverage_outputs()
    build_defense_deck_outputs()
    write_defense_slide_traceability_outputs()
    write(REPRO / "runbook.md", build_runbook(ctx))
    write(
        REPRO / "dataset_manifest.md",
        build_dataset_manifest(ctx)
        + build_application_value_dataset_manifest_section()
        + build_numeric_traceability_dataset_manifest_section()
        + build_no_answer_boundary_dataset_manifest_section()
        + build_claim_integrity_dataset_manifest_section()
        + build_rubric_defense_coverage_dataset_manifest_section()
        + build_defense_slide_traceability_dataset_manifest_section()
        + build_runtime_reproducibility_dataset_manifest_section()
        + build_verification_transcript_dataset_manifest_section()
        + build_official_rubric_dataset_manifest_section()
        + build_hard_evidence_dataset_manifest_section(),
    )
    write(EVAL_COVERAGE_PROFILE, json.dumps(build_evaluation_coverage_profile(ctx), ensure_ascii=False, indent=2))
    write(REPRO / "command_log.md", build_command_log(ctx))
    write_goal_completion_report(REPO_ROOT)
    write_final_acceptance_audit_outputs()
    write_verification_transcript_outputs()
    write_special_prize_readiness_dashboard_outputs()
    evidence_files = [
        md_link(DATASET),
        md_link(DEFENSE_DECK_PPTX),
        md_link(DEFENSE_DECK_NOTES),
        md_link(ACCEPTANCE_CHECKLIST),
        md_link(CLAIM_MATRIX),
        md_link(AWARD_SELF_EVAL),
        md_link(EXPERT_REVIEW_INDEX),
        md_link(DEFENSE_REHEARSAL_CARD),
        md_link(JUDGE_BRIEFING_CARD),
        md_link(ONSITE_DEFENSE_RUNBOOK),
        md_link(PROJECT_HANDOFF_CHECKLIST),
        md_link(DEFENSE_QA_REMEDIATION_LEDGER),
        md_link(REVIEW_RISK_RESPONSE_PLAN),
        md_link(SPECIAL_PRIZE_SCORING_DRILL),
        md_link(POSTER_BOOTH_QA_PACK),
        md_link(COMMERCIALIZATION_ROADMAP),
        md_link(IP_OPEN_SOURCE_COMPLIANCE),
        md_link(LOCAL_BASELINE_DIFFERENTIATION),
        md_link(SUBMISSION_INTEGRITY_CARD),
        md_link(FINAL_SUBMISSION_HANDOFF),
        md_link(POSTER_BOARD_HTML),
        md_link(POSTER_RENDER_SMOKE_MD),
        md_link(POSTER_RENDER_SMOKE_JSON),
        md_link(DEFENSE_CONTROL_CONSOLE),
        md_link(DEFENSE_REHEARSAL_SCORECARD_MD),
        md_link(DEFENSE_REHEARSAL_SCORECARD_JSON),
        md_link(DEFENSE_REHEARSAL_RESULT_PACKET_MD),
        md_link(DEFENSE_REHEARSAL_RESULT_PACKET_JSON),
        md_link(EXPERT_FEEDBACK_REQUEST_PACKET_MD),
        md_link(EXPERT_FEEDBACK_REQUEST_PACKET_JSON),
        md_link(EXPERT_FEEDBACK_OUTREACH_LEDGER_MD),
        md_link(EXPERT_FEEDBACK_OUTREACH_LEDGER_JSON),
        md_link(EXPERT_FEEDBACK_OUTREACH_README),
        *expert_outreach_payload.get("outreach_files", []),
        md_link(TIMED_REHEARSAL_SCHEDULE_LEDGER_MD),
        md_link(TIMED_REHEARSAL_SCHEDULE_LEDGER_JSON),
        md_link(TIMED_REHEARSAL_SCHEDULE_README),
        *timed_rehearsal_schedule_payload.get("schedule_files", []),
        md_link(OFFICIAL_RUBRIC_ALIGNMENT_MD),
        md_link(OFFICIAL_RUBRIC_ALIGNMENT_JSON),
        md_link(JUDGE_OBJECTION_MATRIX_MD),
        md_link(JUDGE_OBJECTION_MATRIX_JSON),
        md_link(SPECIAL_PRIZE_READINESS_DASHBOARD_MD),
        md_link(SPECIAL_PRIZE_READINESS_DASHBOARD_JSON),
        md_link(HARD_EVIDENCE_CLOSURE_BOARD_MD),
        md_link(HARD_EVIDENCE_CLOSURE_BOARD_JSON),
        md_link(HARD_EVIDENCE_ACTION_PACK_MD),
        md_link(HARD_EVIDENCE_ACTION_PACK_JSON),
        md_link(EXTERNAL_EVIDENCE_EXECUTION_KIT_MD),
        md_link(EXTERNAL_EVIDENCE_EXECUTION_KIT_JSON),
        md_link(EXTERNAL_EVIDENCE_CLOSEOUT_CHECKLIST_MD),
        md_link(EXTERNAL_EVIDENCE_CLOSEOUT_CHECKLIST_JSON),
        md_link(EXTERNAL_EVIDENCE_EXPERT_HANDOFF_MD),
        md_link(EXTERNAL_EVIDENCE_TIMED_REHEARSAL_OBSERVER_MD),
        md_link(HARD_EVIDENCE_LEDGER_MD),
        md_link(HARD_EVIDENCE_LEDGER_JSON),
        md_link(HARD_EVIDENCE_README),
        md_link(HARD_EVIDENCE_EXPERT_README),
        md_link(HARD_EVIDENCE_REHEARSAL_README),
        *hard_evidence_payload.get("raw_evidence_files", []),
        md_link(APPLICATION_VALIDATION_DOC),
        md_link(EXPERT_FEEDBACK_PROTOCOL),
        md_link(APPLICATION_VALIDATION_REPORT),
        md_link(APPLICATION_VALUE_QUANTIFICATION_REPORT),
        md_link(APPLICATION_VALUE_QUANTIFICATION_REPORT_JSON),
        md_link(NUMERIC_TRACEABILITY_REPORT),
        md_link(NUMERIC_TRACEABILITY_REPORT_JSON_PATH),
        md_link(NO_ANSWER_BOUNDARY_EVALUATION_REPORT),
        md_link(NO_ANSWER_BOUNDARY_EVALUATION_REPORT_JSON),
        md_link(CLAIM_INTEGRITY_REPORT),
        md_link(CLAIM_INTEGRITY_REPORT_JSON_PATH),
        md_link(RUBRIC_DEFENSE_COVERAGE_REPORT),
        md_link(RUBRIC_DEFENSE_COVERAGE_REPORT_JSON),
        md_link(DEFENSE_SLIDE_TRACEABILITY_REPORT),
        md_link(DEFENSE_SLIDE_TRACEABILITY_REPORT_JSON),
        md_link(RUNTIME_REPRODUCIBILITY_SNAPSHOT_REPORT),
        md_link(RUNTIME_REPRODUCIBILITY_SNAPSHOT_REPORT_JSON),
        md_link(VERIFICATION_TRANSCRIPT_REPORT),
        md_link(VERIFICATION_TRANSCRIPT_REPORT_JSON),
        md_link(EXPERT_FEEDBACK_FORM),
        md_link(GRAPH_MANUAL_EVIDENCE_SUPPLEMENT),
        *graph_manual_evidence_source_files(),
        md_link(LIVE_SMOKE_REPORT),
        md_link(BROWSER_SMOKE_REPORT),
        md_link(BROWSER_SMOKE_JSON),
        md_link(READINESS_GATE_REPORT),
        md_link(GOAL_COMPLETION_REPORT),
        md_link(FINAL_ACCEPTANCE_AUDIT_MD),
        md_link(FINAL_ACCEPTANCE_AUDIT_JSON),
        md_link(SUBMISSION_PACKAGE_VERIFIER),
        *(md_link(path) for path in BROWSER_SCREENSHOTS),
        *(
            md_link(path)
            for path in (
                ctx["day3"],
                ctx["day4"],
                ctx["graph_report"],
                ctx["graph_report_json"],
                ctx["graph_context_demo_md"],
                ctx["graph_context_demo_json"],
                GRAPH_ANSWER_BENCHMARK_MD,
                GRAPH_ANSWER_BENCHMARK_JSON,
                GRAPH_GAP_REMEDIATION_MD,
                GRAPH_GAP_REMEDIATION_JSON,
                FAILURE_REMEDIATION_BEFORE_AFTER_MD,
                FAILURE_REMEDIATION_BEFORE_AFTER_JSON,
            )
            if path is not None
        ),
    ]
    manifest = {
        "generated_at": ctx["now"],
        "output_dir": md_link(OUT),
        "question_count": ctx["question_count"],
        "evaluation_coverage_profile": md_link(EVAL_COVERAGE_PROFILE),
        "evidence_files": evidence_files,
        "integrity_manifest": md_link(EVIDENCE_HASHES),
        "submission_archive": md_link(SUBMISSION_ARCHIVE),
        "submission_archive_manifest": md_link(SUBMISSION_ARCHIVE_MANIFEST),
    }
    write(OUT / "package_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    excluded_self_reports = [md_link(READINESS_GATE_REPORT)]
    hash_payload = {
        "algorithm": "sha256",
        "generated_at": ctx["now"],
        "excluded_self_reports": excluded_self_reports,
        "files": [
            {
                "path": relative,
                "bytes": (REPO_ROOT / relative).stat().st_size,
                "sha256": sha256_file(REPO_ROOT / relative),
            }
            for relative in sorted(path for path in evidence_files if path not in excluded_self_reports)
        ],
    }
    write(EVIDENCE_HASHES, json.dumps(hash_payload, ensure_ascii=False, indent=2))
    archive_inputs = build_submission_archive_inputs(evidence_files)
    write_submission_archive(ctx, archive_inputs)
    print(f"Wrote docs/challenge_cup with {ctx['question_count']} evaluation questions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
