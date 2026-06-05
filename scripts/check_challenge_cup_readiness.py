from __future__ import annotations

import json
import re
import subprocess
import sys
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
AWARD_SELF_EVAL = PACKAGE_DIR / "08_特等奖评审自评表.md"
EXPERT_REVIEW_INDEX = PACKAGE_DIR / "09_专家快速审阅索引.md"
DEFENSE_REHEARSAL_CARD = PACKAGE_DIR / "10_答辩攻防与彩排卡.md"
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
REPORT_MD = REPRO_DIR / "readiness_gate_report.md"

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
    "reproducibility/runbook.md",
    "reproducibility/dataset_manifest.md",
    "reproducibility/command_log.md",
]

REQUIRED_BROWSER_CHECKS = {
    "health endpoint",
    "libs route",
    "assets route",
    "deliverables route",
    "page identity",
    "desktop not blank",
    "desktop console health",
    "search interaction",
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
    "应用边界",
    "evaluation/system_eval_questions.jsonl",
    "browser_demo_smoke_report.md",
    "readiness_gate_report.md",
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
COMMAND_PREFIXES = ("python ", "node ", ".\\", "npm ", "uv ")


@dataclass(slots=True)
class GateCheck:
    name: str
    passed: bool
    detail: str


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def count_jsonl(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def git_tracked_paths() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return {item for item in result.stdout.decode("utf-8", errors="replace").split("\0") if item}


def check_package_docs() -> GateCheck:
    missing = [relative for relative in REQUIRED_PACKAGE_DOCS if not nonempty(PACKAGE_DIR / relative)]
    return GateCheck(
        "package documents",
        not missing,
        "all required challenge cup docs exist" if not missing else f"missing: {', '.join(missing)}",
    )


def check_eval_dataset() -> GateCheck:
    count = count_jsonl(DATASET) if DATASET.exists() else 0
    return GateCheck(
        "60 evaluation questions",
        count >= 60,
        f"{count} evaluation questions",
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
    question_count = int(manifest.get("question_count") or 0)
    passed = bool(evidence) and question_count >= 60 and not missing and not untracked
    if passed:
        detail = f"{len(evidence)} evidence files exist and are git-tracked; {question_count} questions"
    else:
        detail = f"evidence={len(evidence)}, questions={question_count}, missing={missing}, untracked={untracked}"
    return GateCheck("package evidence files", passed, detail)


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
    screenshots = payload.get("browser", {}).get("screenshots", {})
    missing = [path for path in screenshots.values() if not nonempty(REPO_ROOT / str(path))]
    kg_artifacts = payload.get("browser", {}).get("kg_artifacts", [])
    bad_artifacts = [str(item.get("href", "")) for item in kg_artifacts if not item.get("ok")]
    passed = len(screenshots) >= 4 and not missing and len(kg_artifacts) >= 4 and not bad_artifacts
    detail = (
        f"{len(screenshots)} screenshots and {len(kg_artifacts)} KG artifacts verified"
        if passed
        else f"missing_screenshots={missing}, bad_artifacts={bad_artifacts}"
    )
    return GateCheck("browser visual evidence", passed, detail)


def extract_markdown_code_span_paths(text: str) -> list[str]:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    paths: list[str] = []
    for value in re.findall(r"`([^`\n]+)`", text):
        item = value.strip()
        if not item or item.startswith(COMMAND_PREFIXES):
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


def run_gate() -> list[GateCheck]:
    return [
        check_package_docs(),
        check_eval_dataset(),
        check_package_manifest(),
        check_claim_evidence_matrix(),
        check_award_self_eval(),
        check_expert_review_index(),
        check_defense_rehearsal_card(),
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
        "- Scope: challenge-cup package docs, claim-evidence matrix, special-prize rubric, expert review index, defense rehearsal pack, evaluation dataset, evidence manifest, live smoke, browser smoke, screenshots, KG artifact links",
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
