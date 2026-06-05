from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "evaluation" / "reports"
GRAPH_REPORT_JSON = REPORT_DIR / "challenge_cup_graphrag_same_question_report.json"
OUTPUT_JSON = REPORT_DIR / "challenge_cup_graphrag_context_demo.json"
OUTPUT_MD = REPORT_DIR / "challenge_cup_graphrag_context_demo.md"
TEXT_BASELINE_METHOD = "keyword"
DEMO_CASE_LIMIT = 3
BOUNDARY = (
    "This report is a context-only GraphRAG retrieval demo; it does not generate LLM answers "
    "or prove online answer win-rate."
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def latest_day3_comparison() -> Path:
    candidates = sorted(REPORT_DIR.glob("day3_retrieval_baseline_comparison_*.json"))
    if not candidates:
        raise FileNotFoundError("No Day3 comparison JSON found under evaluation/reports.")
    return candidates[-1]


def load_text_outputs(comparison: dict[str, Any]) -> tuple[Path, dict[str, dict[str, Any]]]:
    output_path = resolve_path(str(comparison["files"][TEXT_BASELINE_METHOD]["outputs"]))
    outputs = {str(row["id"]): row for row in read_jsonl(output_path)}
    return output_path, outputs


def text_evidence_for(row: dict[str, Any], limit: int = 2) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, hit in enumerate(row.get("hits", [])[:limit], start=1):
        preview = str(hit.get("preview") or hit.get("text") or "")[:360]
        items.append(
            {
                "id": f"T{index}",
                "source_type": "text",
                "rank": int(hit.get("rank") or index),
                "raw_id": str(hit.get("id", "")),
                "source": str(hit.get("source_file", "")),
                "source_scope": str(hit.get("source_scope", "")),
                "score": hit.get("score"),
                "preview": preview,
            }
        )
    return items


def graph_evidence_for(case: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, hit in enumerate(case.get("matched_graph_evidence", [])[:limit], start=1):
        items.append(
            {
                "id": f"G{index}",
                "source_type": "graph",
                "rank": index,
                "keyword": str(hit.get("keyword", "")),
                "triple_id": str(hit.get("triple_id", "")),
                "subject": str(hit.get("subject", "")),
                "predicate": str(hit.get("predicate", "")),
                "object": str(hit.get("object", "")),
                "source": str(hit.get("source_file", "")),
                "source_page": str(hit.get("source_page", "")),
                "confidence": str(hit.get("confidence", "")),
                "evidence_preview": str(hit.get("evidence_preview", "")),
            }
        )
    return items


def build_prompt_context(question: str, text_items: list[dict[str, Any]], graph_items: list[dict[str, Any]]) -> str:
    lines = [
        "# GraphRAG context-only QA demo",
        "",
        f"Question: {question}",
        "",
        "Context-only debug mode: no LLM answer was generated.",
        "",
        "## Text retrieval evidence",
    ]
    if text_items:
        for item in text_items:
            score = f" score={float(item['score']):.4g}" if isinstance(item.get("score"), int | float) else ""
            lines.extend(
                [
                    f"[{item['id']}] {item['source']}{score}",
                    str(item["preview"]),
                    "",
                ]
            )
    else:
        lines.extend(["No text retrieval evidence returned.", ""])

    lines.append("## Graph retrieval evidence")
    if graph_items:
        for item in graph_items:
            triple = f"{item['subject']} --{item['predicate']}--> {item['object']}"
            source = f" source={item['source']}" if item["source"] else ""
            confidence = f" confidence={item['confidence']}" if item["confidence"] else ""
            lines.extend(
                [
                    f"[{item['id']}] {triple}{source}{confidence}",
                    f"Evidence: {item['evidence_preview']}",
                    "",
                ]
            )
    else:
        lines.extend(["No graph retrieval evidence returned.", ""])

    return "\n".join(lines).rstrip()


def build_case(case: dict[str, Any], text_output: dict[str, Any]) -> dict[str, Any]:
    text_items = text_evidence_for(text_output)
    graph_items = graph_evidence_for(case)
    return {
        "id": case["id"],
        "question": case["question"],
        "graph_mode": case["graph_mode"],
        "graph_evidence_coverage": case["graph_evidence_coverage"],
        "graph_evidence_status": case["graph_evidence_status"],
        "best_baseline_method": case["best_baseline_method"],
        "best_baseline_coverage": case["best_baseline_coverage"],
        "text_evidence": text_items,
        "graph_evidence": graph_items,
        "citations": [*text_items, *graph_items],
        "prompt_context": build_prompt_context(case["question"], text_items, graph_items),
        "answer": None,
    }


def build_payload() -> dict[str, Any]:
    graph_report = read_json(GRAPH_REPORT_JSON)
    comparison_path = latest_day3_comparison()
    comparison = read_json(comparison_path)
    text_output_path, text_outputs = load_text_outputs(comparison)
    supported_cases = [
        case for case in graph_report["cases"] if case.get("graph_evidence_status") == "supported"
    ][:DEMO_CASE_LIMIT]
    cases = [build_case(case, text_outputs[str(case["id"])]) for case in supported_cases]
    return {
        "report_type": "challenge_cup_graphrag_context_demo",
        "context_only": True,
        "answer_generated": False,
        "boundary": BOUNDARY,
        "source_graph": str(graph_report["graph_evidence_source"]),
        "source_graph_report": rel(GRAPH_REPORT_JSON),
        "day3_comparison": rel(comparison_path),
        "text_baseline_method": TEXT_BASELINE_METHOD,
        "text_baseline_outputs": rel(text_output_path),
        "demo_case_count": len(cases),
        "case_ids": [case["id"] for case in cases],
        "cases": cases,
    }


def cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# GraphRAG context-only QA demo",
        "",
        "本报告把 GraphRAG 同题 supported 案例转成固定 context-only QA 快照：同时展示文本检索证据和 triples.csv 图谱关系证据，但不生成 LLM 答案。",
        "",
        f"- Boundary: {payload['boundary']}",
        f"- Graph source: `{payload['source_graph']}`",
        f"- Text baseline: `{payload['text_baseline_method']}` / `{payload['text_baseline_outputs']}`",
        f"- Demo cases: {payload['demo_case_count']} ({', '.join(payload['case_ids'])})",
        "",
        "## Cases",
        "",
        "| ID | Graph mode | Text evidence | Graph evidence | Context-only boundary |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for case in payload["cases"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    cell(case["id"]),
                    cell(case["graph_mode"]),
                    cell(len(case["text_evidence"])),
                    cell(len(case["graph_evidence"])),
                    "不生成 LLM 答案",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Retrieved Context Snapshots", ""])
    for case in payload["cases"]:
        lines.extend(
            [
                f"### {case['id']} {case['question']}",
                "",
                "```text",
                case["prompt_context"],
                "```",
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    payload = build_payload()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(OUTPUT_MD, payload)
    print(f"GraphRAG context demo: {OUTPUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
