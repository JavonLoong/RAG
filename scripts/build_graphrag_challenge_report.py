from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
REPORT_DIR = REPO_ROOT / "evaluation" / "reports"
OUTPUT_JSON = REPORT_DIR / "challenge_cup_graphrag_same_question_report.json"
OUTPUT_MD = REPORT_DIR / "challenge_cup_graphrag_same_question_report.md"
BASELINE_METHODS = ["keyword", "dense_hashing", "hybrid_rrf"]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def latest_day3_comparison() -> Path:
    candidates = sorted(REPORT_DIR.glob("day3_retrieval_baseline_comparison_*.json"))
    if not candidates:
        raise FileNotFoundError("No Day3 comparison JSON found under evaluation/reports.")
    return candidates[-1]


def by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(record["id"]): record for record in records}


def load_method_results(comparison: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    results: dict[str, dict[str, dict[str, Any]]] = {}
    for method in BASELINE_METHODS:
        report_path = resolve_path(str(comparison["files"][method]["report_json"]))
        report = read_json(report_path)
        results[method] = by_id(report["results"])
    return results


def graph_mode(modes: list[str]) -> str:
    if "graphrag_global" in modes:
        return "graphrag_global"
    return "graphrag_context"


def recommendation_for(row: dict[str, Any], best_coverage: float) -> str:
    modes = row.get("expected_modes", [])
    if "graphrag_global" in modes:
        return "Use community/global summaries and compare against keyword/hybrid on cross-document synthesis."
    if best_coverage < 0.75:
        return "Prioritize local graph evidence because current text retrieval does not cover enough expected evidence."
    return "Keep as GraphRAG support case: text baseline is usable, but graph relations can improve explanation structure."


def build_payload() -> dict[str, Any]:
    questions = read_jsonl(DATASET)
    comparison_path = latest_day3_comparison()
    comparison = read_json(comparison_path)
    method_results = load_method_results(comparison)
    graph_questions = [
        row for row in questions if any(str(mode).startswith("graphrag") for mode in row.get("expected_modes", []))
    ]
    mode_counts = Counter(mode for row in graph_questions for mode in row.get("expected_modes", []) if str(mode).startswith("graphrag"))
    cases: list[dict[str, Any]] = []
    for row in graph_questions:
        coverages = {
            method: float(method_results[method][row["id"]]["retrieval_keyword_coverage"])
            for method in BASELINE_METHODS
        }
        best_method, best_coverage = max(coverages.items(), key=lambda item: item[1])
        cases.append(
            {
                "id": row["id"],
                "question": row["question"],
                "task_type": row["task_type"],
                "source_scope": row["source_scope"],
                "expected_modes": row["expected_modes"],
                "graph_mode": graph_mode(row["expected_modes"]),
                "baseline_keyword_coverage": coverages,
                "best_baseline_method": best_method,
                "best_baseline_coverage": best_coverage,
                "priority_for_graph_eval": best_coverage < 0.75 or "graphrag_global" in row["expected_modes"],
                "recommendation": recommendation_for(row, best_coverage),
                "grading_notes": row["grading_notes"],
            }
        )

    priority_cases = [case for case in cases if case["priority_for_graph_eval"]]
    avg_best = sum(case["best_baseline_coverage"] for case in cases) / max(len(cases), 1)
    payload = {
        "report_type": "challenge_cup_graphrag_same_question_subset",
        "dataset": str(DATASET.relative_to(REPO_ROOT)).replace("\\", "/"),
        "day3_comparison": str(comparison_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "total_questions": len(questions),
        "graphrag_question_count": len(graph_questions),
        "mode_counts": dict(sorted(mode_counts.items())),
        "baseline_methods": BASELINE_METHODS,
        "average_best_baseline_coverage_on_graph_subset": round(avg_best, 6),
        "priority_case_count": len(priority_cases),
        "boundary": "This report identifies the same-question GraphRAG evaluation subset; it does not claim completed online GraphRAG QA beats the baseline.",
        "cases": cases,
    }
    return payload


def cell(value: Any) -> str:
    text = str(value).replace("\n", " ")
    return text.replace("|", "\\|")


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# GraphRAG 同题子集评测报告",
        "",
        "## 一句话结论",
        "",
        (
            f"60 题评测集中有 {payload['graphrag_question_count']} 题显式标注需要 GraphRAG context/global；"
            f"这些题应作为下一轮 GraphRAG local/global 同题实测的固定子集。"
        ),
        "",
        "## 边界声明",
        "",
        "本报告识别 GraphRAG 同题子集和当前文本 baseline 覆盖情况，不代表完整 GraphRAG 在线问答已优于 baseline。",
        "",
        "## 子集统计",
        "",
        f"- 总题数：{payload['total_questions']}",
        f"- GraphRAG 子集题数：{payload['graphrag_question_count']}",
        f"- context 题数：{payload['mode_counts'].get('graphrag_context', 0)}",
        f"- global 题数：{payload['mode_counts'].get('graphrag_global', 0)}",
        f"- 当前文本 baseline 最优覆盖率均值：{payload['average_best_baseline_coverage_on_graph_subset']}",
        f"- 优先补 GraphRAG 实测案例：{payload['priority_case_count']}",
        "",
        "## 案例表",
        "",
        "| ID | Graph mode | Best baseline | Coverage | Question | Recommendation |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for case in payload["cases"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    cell(case["id"]),
                    cell(case["graph_mode"]),
                    cell(case["best_baseline_method"]),
                    cell(case["best_baseline_coverage"]),
                    cell(case["question"]),
                    cell(case["recommendation"]),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    payload = build_payload()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(OUTPUT_MD, payload)
    print(f"GraphRAG same-question report: {OUTPUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
