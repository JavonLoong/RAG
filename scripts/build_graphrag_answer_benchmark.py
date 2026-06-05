from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from build_graphrag_challenge_report import (
    OUTPUT_JSON as GRAPH_REPORT_JSON,
    OUTPUT_MD as GRAPH_REPORT_MD,
    build_payload as build_graph_report_payload,
    write_markdown as write_graph_report_markdown,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
REPORT_DIR = REPO_ROOT / "evaluation" / "reports"
OUTPUT_JSON = REPORT_DIR / "challenge_cup_graphrag_answer_benchmark.json"
OUTPUT_MD = REPORT_DIR / "challenge_cup_graphrag_answer_benchmark.md"
BOUNDARY = (
    "This is a deterministic offline answer benchmark over the fixed GraphRAG subset; it does not claim "
    "online LLM answer win-rate or that GraphRAG beats every baseline question."
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def refresh_graph_report() -> dict[str, Any]:
    payload = build_graph_report_payload()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_graph_report_markdown(GRAPH_REPORT_MD, payload)
    return payload


def answer_status(coverage: float) -> str:
    if coverage >= 0.5:
        return "supported"
    if coverage > 0:
        return "partial"
    return "missing"


def answer_level_verdict(status: str) -> str:
    return {
        "supported": "graph_supported",
        "partial": "graph_partial",
        "missing": "graph_missing",
    }[status]


def graph_answer_draft(case: dict[str, Any]) -> str:
    hits = case.get("matched_graph_evidence", [])
    if not hits:
        return "当前 triples.csv 未返回可支撑该题的图谱证据；该题必须保留为 missing，并依赖文本 baseline 或人工补证。"
    fragments = []
    for hit in hits[:3]:
        triple = f"{hit.get('subject', '')} --{hit.get('predicate', '')}--> {hit.get('object', '')}"
        preview = str(hit.get("evidence_preview", "")).strip()
        keyword = str(hit.get("keyword", "")).strip()
        fragments.append(f"{keyword}: {triple}。证据：{preview}")
    return "；".join(fragments)


def build_case(case: dict[str, Any], dataset_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    row = dataset_by_id[str(case["id"])]
    graph_coverage = float(case["graph_evidence_coverage"])
    status = answer_status(graph_coverage)
    return {
        "id": case["id"],
        "question": case["question"],
        "reference_answer": row["reference_answer"],
        "expected_evidence_keywords": list(row.get("expected_evidence_keywords", [])),
        "task_type": row["task_type"],
        "graph_mode": case["graph_mode"],
        "best_baseline_method": case["best_baseline_method"],
        "best_baseline_reference_keyword_coverage": float(case["best_baseline_coverage"]),
        "graphrag_reference_keyword_coverage": graph_coverage,
        "graphrag_answer_status": status,
        "answer_level_verdict": answer_level_verdict(status),
        "graphrag_answer_draft": graph_answer_draft(case),
        "matched_graph_evidence_count": len(case.get("matched_graph_evidence", [])),
        "recommendation": case["recommendation"],
        "boundary": "保留该题原始 GraphRAG 证据状态，不把 partial/missing 改写成成功案例。",
    }


def average(values: list[float]) -> float:
    return round(sum(values) / max(len(values), 1), 6)


def build_payload() -> dict[str, Any]:
    graph_report = refresh_graph_report()
    dataset_by_id = {str(row["id"]): row for row in read_jsonl(DATASET)}
    cases = [build_case(case, dataset_by_id) for case in graph_report["cases"]]
    supported = sum(1 for case in cases if case["graphrag_answer_status"] == "supported")
    partial = sum(1 for case in cases if case["graphrag_answer_status"] == "partial")
    missing = sum(1 for case in cases if case["graphrag_answer_status"] == "missing")
    if missing == 0 and partial == 0 and supported == len(cases):
        summary = (
            "manual graph evidence now closes all fixed GraphRAG evidence gaps; this remains a local "
            "deterministic evidence audit and does not claim online LLM answer win-rate."
        )
    elif missing == 0 and supported >= 7:
        summary = (
            "manual graph evidence now closes P0 missing cases; remaining partial cases still require relation "
            "synonym/schema work, and this does not claim online LLM answer win-rate."
        )
    else:
        summary = (
            "GraphRAG is not yet an answer-level win-rate improvement; current value is strongest for "
            "supported relation-evidence cases, while partial/missing cases expose the next data and graph gaps."
        )
    return {
        "report_type": "challenge_cup_graphrag_answer_benchmark",
        "benchmark_mode": "deterministic_offline_reference_keyword_coverage",
        "llm_answer_generated": False,
        "boundary": BOUNDARY,
        "dataset": rel(DATASET),
        "source_graph_report": rel(GRAPH_REPORT_JSON),
        "answer_benchmark_case_count": len(cases),
        "partial_or_missing_cases_retained": partial + missing > 0,
        "best_baseline_method_count": len(graph_report["baseline_methods"]),
        "graphrag_supported_answer_case_count": supported,
        "graphrag_partial_answer_case_count": partial,
        "graphrag_missing_answer_case_count": missing,
        "average_best_baseline_reference_keyword_coverage": average(
            [case["best_baseline_reference_keyword_coverage"] for case in cases]
        ),
        "average_graphrag_reference_keyword_coverage": average(
            [case["graphrag_reference_keyword_coverage"] for case in cases]
        ),
        "summary_verdict": summary,
        "cases": cases,
    }


def cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# GraphRAG answer benchmark",
        "",
        "本报告把 10 道 GraphRAG 同题从 context-only 推进到答案级覆盖对照：使用固定参考答案、expected evidence keywords、文本 baseline 覆盖率和 triples.csv 图谱证据覆盖率做确定性离线评测。",
        "",
        f"- Boundary: {payload['boundary']}",
        "- LLM answer generated: `False`",
        "- Benchmark mode: deterministic offline reference keyword coverage",
        f"- 10 道 GraphRAG 同题：{payload['answer_benchmark_case_count']}",
        f"- Graph supported / partial / missing: {payload['graphrag_supported_answer_case_count']} / {payload['graphrag_partial_answer_case_count']} / {payload['graphrag_missing_answer_case_count']}",
        f"- P0 missing 已补证: `{payload['graphrag_missing_answer_case_count'] == 0 and payload['graphrag_supported_answer_case_count'] >= 7}`",
        f"- Best baseline average coverage: {payload['average_best_baseline_reference_keyword_coverage']}",
        f"- GraphRAG evidence average coverage: {payload['average_graphrag_reference_keyword_coverage']}",
        (
            "- All fixed GraphRAG evidence gaps closed: "
            f"`{payload['graphrag_partial_answer_case_count'] == 0 and payload['graphrag_missing_answer_case_count'] == 0}`"
        ),
        "- 结论：不宣称 GraphRAG 全面优于 baseline；本报告只证明固定 GraphRAG 子集的本地证据覆盖，不证明在线 LLM answer win-rate。",
        "",
        "## 案例表",
        "",
        "| ID | Graph mode | Best baseline | Baseline coverage | GraphRAG coverage | Status | Verdict | Question |",
        "| --- | --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for case in payload["cases"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    cell(case["id"]),
                    cell(case["graph_mode"]),
                    cell(case["best_baseline_method"]),
                    cell(case["best_baseline_reference_keyword_coverage"]),
                    cell(case["graphrag_reference_keyword_coverage"]),
                    cell(case["graphrag_answer_status"]),
                    cell(case["answer_level_verdict"]),
                    cell(case["question"]),
                ]
            )
            + " |"
        )
    if payload["partial_or_missing_cases_retained"]:
        lines.extend(
            [
                "",
                "## 保留 partial/missing",
                "",
                "partial 和 missing 题没有被改写成成功案例；它们用于说明当前 GraphRAG evidence 仍需要补充关系、社区摘要或最终在线 answer benchmark。",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## All fixed GraphRAG evidence gaps closed",
                "",
                "固定 GraphRAG 同题子集当前没有 partial/missing 本地证据缺口；该结论仍限于离线关键词覆盖审计，不代表在线 LLM answer win-rate。",
            ]
        )
    lines.extend(["", "## Boundary", "", payload["boundary"]])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    payload = build_payload()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(OUTPUT_MD, payload)
    print(f"GraphRAG answer benchmark: {OUTPUT_MD.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
