from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
REPORT_DIR = REPO_ROOT / "evaluation" / "reports"
GRAPH_REPORT_JSON = REPORT_DIR / "challenge_cup_graphrag_same_question_report.json"
ANSWER_BENCHMARK_JSON = REPORT_DIR / "challenge_cup_graphrag_answer_benchmark.json"
OUTPUT_JSON = REPORT_DIR / "challenge_cup_graphrag_gap_remediation_plan.json"
OUTPUT_MD = REPORT_DIR / "challenge_cup_graphrag_gap_remediation_plan.md"
BOUNDARY = (
    "This plan turns partial/missing GraphRAG evidence into prioritized remediation work; it does not "
    "claim the gaps are already fixed."
)
NO_OVERCLAIM_RULES = [
    "不把 partial/missing 改写成成功案例",
    "不宣称 GraphRAG 已经全面优于 baseline",
    "补证完成前保留原始 supported/partial/missing 统计",
]
REQUIRED_EVIDENCE_TO_ARCHIVE = [
    "new_triples_or_summary_diff",
    "source_page_or_doc_anchor",
    "manual_review_note",
    "rerun_report_json",
]
RERUN_COMMANDS = [
    "python scripts/build_graphrag_challenge_report.py",
    "python scripts/build_graphrag_answer_benchmark.py",
    "python scripts/build_graphrag_gap_remediation_plan.py",
    "python scripts/check_challenge_cup_readiness.py",
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def missing_keywords(case: dict[str, Any]) -> list[str]:
    draft = str(case.get("graphrag_answer_draft", "")).lower()
    return [str(keyword) for keyword in case.get("expected_evidence_keywords", []) if str(keyword).lower() not in draft]


def action_type(answer_case: dict[str, Any], graph_case: dict[str, Any]) -> str:
    task_type = str(answer_case.get("task_type", ""))
    source_scope = str(graph_case.get("source_scope", ""))
    graph_mode = str(answer_case.get("graph_mode", ""))
    if "challenge_cup" in task_type or "project" in source_scope:
        return "add_project_claim_graph_evidence"
    if graph_mode == "graphrag_global":
        return "add_global_community_summary"
    if answer_case.get("graphrag_answer_status") == "missing":
        return "add_domain_relation_seed"
    return "expand_relation_synonyms"


def action_items(kind: str, case: dict[str, Any], missing: list[str]) -> list[str]:
    missing_text = "、".join(missing[:6]) if missing else "当前参考关键词"
    if kind == "add_project_claim_graph_evidence":
        return [
            f"为 {missing_text} 建立项目主张到证据文件的图谱边。",
            "把新增边绑定到 challenge_cup 文档、评测报告或命令记录，避免无来源项目自夸。",
            "重新运行同题 GraphRAG 报告，确认项目定位类问题不再仅依赖文本 baseline。",
        ]
    if kind == "add_global_community_summary":
        return [
            f"围绕 {missing_text} 增加跨文档社区摘要或全局关系说明。",
            "把摘要节点绑定到至少一个来源页、三元组或人工复核说明。",
            "重新比较 global GraphRAG 与 keyword/hybrid，但保留不全面优于 baseline 的边界。",
        ]
    if kind == "add_domain_relation_seed":
        return [
            f"把 {missing_text} 作为下一轮关系抽取或人工补图谱的 seed terms。",
            "为每个新增关系保存 subject、predicate、object、source_file、source_page 和 evidence_preview。",
            "如果找不到可靠证据，继续保留 missing，不用弱证据硬补。",
        ]
    return [
        f"为 {missing_text} 增补同义词、实体别名和关系谓词映射。",
        "检查现有 matched_graph_evidence 是否命中正确语义而非仅命中表面词。",
        "复跑 answer benchmark，确认 partial 题的关键词覆盖率是否提升。",
    ]


def build_item(answer_case: dict[str, Any], graph_case: dict[str, Any]) -> dict[str, Any]:
    status = str(answer_case["graphrag_answer_status"])
    missing = missing_keywords(answer_case)
    kind = action_type(answer_case, graph_case)
    return {
        "id": answer_case["id"],
        "question": answer_case["question"],
        "task_type": answer_case["task_type"],
        "source_scope": graph_case.get("source_scope"),
        "graph_mode": answer_case["graph_mode"],
        "current_status": status,
        "priority": "P0" if status == "missing" else "P1",
        "action_type": kind,
        "missing_expected_keywords": missing,
        "matched_graph_evidence_count": answer_case["matched_graph_evidence_count"],
        "baseline_coverage": answer_case["best_baseline_reference_keyword_coverage"],
        "graph_coverage": answer_case["graphrag_reference_keyword_coverage"],
        "action_items": action_items(kind, answer_case, missing),
        "acceptance_evidence": REQUIRED_EVIDENCE_TO_ARCHIVE,
        "claim_fixed": False,
    }


def build_payload() -> dict[str, Any]:
    graph_report = read_json(GRAPH_REPORT_JSON)
    benchmark = read_json(ANSWER_BENCHMARK_JSON)
    graph_cases = {str(case["id"]): case for case in graph_report["cases"]}
    answer_cases = list(benchmark["cases"])
    supported = sum(1 for case in answer_cases if case["graphrag_answer_status"] == "supported")
    partial = sum(1 for case in answer_cases if case["graphrag_answer_status"] == "partial")
    missing = sum(1 for case in answer_cases if case["graphrag_answer_status"] == "missing")
    remediation_items = [
        build_item(case, graph_cases[str(case["id"])])
        for case in answer_cases
        if case["graphrag_answer_status"] in {"partial", "missing"}
    ]
    priority_counts = {
        "P0": sum(1 for item in remediation_items if item["priority"] == "P0"),
        "P1": sum(1 for item in remediation_items if item["priority"] == "P1"),
    }
    return {
        "report_type": "challenge_cup_graphrag_gap_remediation_plan",
        "status": "ready_for_graph_iteration",
        "gaps_marked_fixed": False,
        "boundary": BOUNDARY,
        "source_dataset": rel(DATASET),
        "source_graph_report": rel(GRAPH_REPORT_JSON),
        "source_answer_benchmark": rel(ANSWER_BENCHMARK_JSON),
        "total_graph_cases": len(answer_cases),
        "supported_count": supported,
        "partial_count": partial,
        "missing_count": missing,
        "partial_or_missing_count": partial + missing,
        "priority_counts": priority_counts,
        "no_overclaim_rules": NO_OVERCLAIM_RULES,
        "required_evidence_to_archive": REQUIRED_EVIDENCE_TO_ARCHIVE,
        "rerun_commands": RERUN_COMMANDS,
        "remediation_items": remediation_items,
    }


def cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# GraphRAG 补证整改计划",
        "",
        "本计划把 GraphRAG 同题子集中的 partial/missing 结果转成下一轮可执行补证任务。它是整改入口，不是修复完成证明。",
        "",
        f"- Status: `{payload['status']}`",
        f"- Boundary: {payload['boundary']}",
        f"- Total cases: {payload['total_graph_cases']}",
        f"- Supported / partial / missing: {payload['supported_count']} / {payload['partial_count']} / {payload['missing_count']}",
        f"- Gaps marked fixed: `{payload['gaps_marked_fixed']}`",
        "",
        "## 不夸大规则",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["no_overclaim_rules"])
    lines.extend(
        [
            "",
            "## 整改任务",
            "",
            "| ID | Priority | Status | Action type | Missing keywords | Acceptance evidence |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in payload["remediation_items"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    cell(item["id"]),
                    cell(item["priority"]),
                    cell(item["current_status"]),
                    cell(item["action_type"]),
                    cell("、".join(item["missing_expected_keywords"])),
                    cell(", ".join(item["acceptance_evidence"])),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 执行动作", ""])
    for item in payload["remediation_items"]:
        lines.extend([f"### {item['id']} {item['question']}", ""])
        lines.extend(f"- {action}" for action in item["action_items"])
        lines.extend([f"- claim_fixed: `{item['claim_fixed']}`", ""])
    lines.extend(["## 复跑命令", ""])
    lines.extend(f"- `{command}`" for command in payload["rerun_commands"])
    lines.extend(["", "## Boundary", "", payload["boundary"]])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    payload = build_payload()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(OUTPUT_MD, payload)
    print(f"GraphRAG gap remediation plan: {OUTPUT_MD.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
