from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "docs" / "challenge_cup"
REPRO_DIR = PACKAGE_DIR / "reproducibility"
PACKAGE_MANIFEST = PACKAGE_DIR / "package_manifest.json"
BROWSER_SMOKE_JSON = REPRO_DIR / "browser_demo_smoke_report.json"
LIVE_SMOKE_JSON = REPRO_DIR / "live_demo_smoke_report.json"
CLAIM_MATRIX = PACKAGE_DIR / "07_评审主张证据矩阵.md"
ACCEPTANCE_CHECKLIST = PACKAGE_DIR / "06_结项验收清单.md"
AWARD_SELF_EVAL = PACKAGE_DIR / "08_特等奖评审自评表.md"
EXPERT_REVIEW_INDEX = PACKAGE_DIR / "09_专家快速审阅索引.md"
DEFENSE_REHEARSAL_CARD = PACKAGE_DIR / "10_答辩攻防与彩排卡.md"
APPLICATION_VALIDATION_DOC = PACKAGE_DIR / "11_应用场景与专家验证.md"
EXPERT_FEEDBACK_PROTOCOL = PACKAGE_DIR / "12_专家反馈采集与整改闭环.md"
DEMO_SCRIPT = PACKAGE_DIR / "04_系统演示脚本.md"
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
DATASET_RELATIVE = "evaluation/system_eval_questions.jsonl"
REPORT_MD = REPRO_DIR / "readiness_gate_report.md"
EVIDENCE_HASHES = REPRO_DIR / "evidence_hashes.json"
EVAL_COVERAGE_PROFILE = REPRO_DIR / "evaluation_coverage_profile.json"
APPLICATION_VALIDATION_REPORT = REPRO_DIR / "application_validation_report.md"
EXPERT_FEEDBACK_FORM = REPRO_DIR / "expert_feedback_form.md"
GRAPH_REPORT_JSON = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_same_question_report.json"
GRAPH_REPORT_MD = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_same_question_report.md"
GRAPH_EVIDENCE_BOUNDARY = (
    "Graph evidence coverage audits triples.csv keyword support; it is not a completed GraphRAG answer win-rate."
)
REQUIRED_GRAPH_CASE_FIELDS = {
    "id",
    "graph_evidence_coverage",
    "graph_evidence_status",
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
    "reproducibility/runbook.md",
    "reproducibility/dataset_manifest.md",
    "reproducibility/evaluation_coverage_profile.json",
    "reproducibility/evidence_hashes.json",
    "reproducibility/application_validation_report.md",
    "reproducibility/expert_feedback_form.md",
    "reproducibility/command_log.md",
]
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
    "missing frontend fallback",
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
    "特等奖不超过6件",
    "07_评审主张证据矩阵.md",
    "readiness_gate_report.md",
    "browser_demo_smoke_report.md",
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
}
REQUIRED_APPLICATION_VALIDATION_TERMS = {
    "固定应用场景",
    "人工原流程",
    "系统辅助后流程",
    "验证角色",
    "量化收益",
    "边界声明",
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
}
REQUIRED_SCENARIO_QUERY = "燃气轮机异常振动诊断流程"
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


@dataclass(slots=True)
class GateCheck:
    name: str
    passed: bool
    detail: str


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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

    triple_count = int(payload.get("graph_triple_count") or 0)
    if triple_count < 240:
        failures.append(f"graph_triple_count below 240: {triple_count}")
    supported = int(payload.get("graph_evidence_supported_case_count") or 0)
    partial = int(payload.get("graph_evidence_partial_case_count") or 0)
    missing = int(payload.get("graph_evidence_missing_case_count") or 0)
    if supported < 3:
        failures.append(f"graph_evidence_supported_case_count below 3: {supported}")
    if missing < 1:
        failures.append("graph_evidence_missing_case_count must preserve at least one known gap")
    if payload.get("graph_evidence_boundary") != GRAPH_EVIDENCE_BOUNDARY:
        failures.append("graph_evidence_boundary mismatch")

    cases = payload.get("cases", [])
    if not isinstance(cases, list) or len(cases) != int(payload.get("graphrag_question_count") or -1):
        failures.append("cases must match graphrag_question_count")
        cases = []
    supported_with_hits = 0
    missing_cases = 0
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
        if status == "missing":
            missing_cases += 1
    if supported_with_hits < 1:
        failures.append("no supported GraphRAG evidence case with matched_graph_evidence")
    if missing_cases < 1:
        failures.append("no missing GraphRAG evidence case retained")

    required_markdown_terms = {
        "Graph evidence coverage audit",
        "triples.csv",
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
        f"fixed GT-07 application case, evidence records, benefits, and boundaries verified; {len(evidence_paths)} evidence links verified"
        if not missing
        else f"missing application validation terms or evidence paths: {', '.join(missing)}",
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
        check_package_control_files(),
        check_eval_dataset(),
        check_evaluation_coverage_profile(),
        check_package_manifest(),
        check_evidence_hashes(),
        check_numeric_consistency(),
        check_graphrag_same_question_evidence(),
        check_claim_evidence_matrix(),
        check_acceptance_checklist(),
        check_award_self_eval(),
        check_expert_review_index(),
        check_defense_rehearsal_card(),
        check_application_validation_evidence(),
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
        "- Scope: challenge-cup package docs, control files, numeric consistency, GraphRAG evidence audit, claim-evidence matrix, acceptance checklist, special-prize rubric, expert review index, defense rehearsal pack, application validation, fixed scenario demo, scenario walkthrough script, expert feedback protocol, evaluation dataset, evaluation coverage profile, evidence manifest, evidence hashes, live smoke, browser smoke, screenshots, KG artifact links",
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
