from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = REPO_ROOT / "evaluation" / "reports"
DEFAULT_DOCS_SUMMARY = (
    REPO_ROOT
    / "docs"
    / "project_deliverables"
    / "06_汇报材料_发群和组会"
    / "第四天失败案例分析.md"
)


def compact_text(value: Any, limit: int = 220) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def markdown_cell(value: Any) -> str:
    if isinstance(value, float):
        text = f"{value:.6f}"
    else:
        text = compact_text(value, 180)
    return text.replace("|", "\\|").replace("\n", " ")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def latest_comparison(report_dir: Path) -> Path:
    candidates = sorted(report_dir.glob("day3_retrieval_baseline_comparison_*.json"))
    if not candidates:
        raise FileNotFoundError(f"No day3 comparison JSON found in {report_dir}")
    return candidates[-1]


def normalize_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def index_by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(record.get("id")): record for record in records}


def read_method_data(comparison: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, dict[str, Any]]]]:
    reports: dict[str, dict[str, Any]] = {}
    outputs: dict[str, dict[str, dict[str, Any]]] = {}
    for method, paths in comparison["files"].items():
        report = load_json(Path(paths["report_json"]))
        output_records = load_jsonl(Path(paths["outputs"]))
        reports[method] = report
        outputs[method] = index_by_id(output_records)
    return reports, outputs


def question_rows(reports: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for method, report in reports.items():
        for result in report["results"]:
            qid = str(result["id"])
            if qid not in rows:
                rows[qid] = {
                    "id": qid,
                    "question": result["question"],
                    "task_type": result["task_type"],
                    "source_scope": result["source_scope"],
                    "grading_notes": result["grading_notes"],
                    "expected_evidence_keywords": result["expected_evidence_keywords"],
                    "methods": {},
                }
            rows[qid]["methods"][method] = {
                "coverage": result["retrieval_keyword_coverage"],
                "evidence_keywords": result["retrieval_evidence_keywords"],
                "retrieved_count_at_k": result["retrieved_count_at_k"],
                "top_previews": result["top_retrieval_previews"],
            }
    return rows


def top_hit_for(method: str, qid: str, outputs: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    record = outputs.get(method, {}).get(qid, {})
    hits = record.get("hits") or []
    return hits[0] if hits else {}


def classify_failure(row: dict[str, Any]) -> tuple[str, str, str]:
    question = str(row["question"])
    task_type = str(row["task_type"])
    expected = [str(item) for item in row["expected_evidence_keywords"]]
    methods = row["methods"]
    keyword_cov = methods.get("keyword", {}).get("coverage", 0) or 0
    dense_cov = methods.get("dense_hashing", {}).get("coverage", 0) or 0
    hybrid_cov = methods.get("hybrid_rrf", {}).get("coverage", 0) or 0
    all_zero = keyword_cov == 0 and dense_cov == 0 and hybrid_cov == 0

    if task_type == "structured_data_fact":
        return (
            "structured_fact_routing",
            "结构化事实没有被专门路由到数据质量报告或字段清单，普通文本 chunk 对精确字段名/数值召回不足。",
            "给 Goldwind/SCADA 类问题建立结构化摘要索引，保留 key-value、字段名、行列规模和报告路径。",
        )
    if row["id"] == "se024" or any(re.search(r"\d", item) for item in expected):
        return (
            "exact_number_fact",
            "问题要求精确数字事实，但当前 chunk 和排序没有把 POC 数量结论排进 Top-K。",
            "为项目成果总览、POC 运行报告建立短 chunk 或事实卡片，专门承载 27/26/1/0 这类汇报数字。",
        )
    if "reranker" in question.lower() or "Reranker" in expected:
        return (
            "terminology_alias_gap",
            "题目使用 Reranker 英文术语，但材料中更常出现“重排、二次排序、Cross-Encoder”等中文或别名。",
            "增加查询改写/同义词扩展：Reranker -> 重排、二次排序、Cross-Encoder、精排。",
        )
    if task_type in {"answer_quality", "evaluation_method"}:
        return (
            "evaluation_concept_gap",
            "这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。",
            "把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。",
        )
    if keyword_cov > dense_cov and keyword_cov >= hybrid_cov:
        return (
            "hybrid_dilution",
            "关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。",
            "在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。",
        )
    if all_zero:
        return (
            "corpus_gap_or_query_gap",
            "三种方法都没有命中预期关键词，可能是语料范围、题目问法或评测关键词与材料表达不一致。",
            "回看原文证据，补同义词、补短摘要，或把该题标为需要 GraphRAG/结构化索引的问题。",
        )
    return (
        "partial_ranking_gap",
        "有方法能部分命中，但 Top-K 内证据不完整，主要是排序和 chunk 粒度问题。",
        "调小关键报告 chunk、增加 reranker，并做按 source_scope 的候选过滤或加权。",
    )


def build_analysis(comparison_path: Path) -> dict[str, Any]:
    comparison = load_json(comparison_path)
    reports, outputs = read_method_data(comparison)
    rows = question_rows(reports)

    analyzed: list[dict[str, Any]] = []
    for qid in sorted(rows):
        row = rows[qid]
        method_coverages = {
            method: row["methods"].get(method, {}).get("coverage")
            for method in ("keyword", "dense_hashing", "hybrid_rrf")
        }
        min_coverage = min(value for value in method_coverages.values() if value is not None)
        max_coverage = max(value for value in method_coverages.values() if value is not None)
        include = min_coverage == 0 or max_coverage < 0.75
        if not include:
            continue
        category, reason, action = classify_failure(row)
        analyzed.append(
            {
                "id": row["id"],
                "question": row["question"],
                "task_type": row["task_type"],
                "expected_evidence_keywords": row["expected_evidence_keywords"],
                "coverages": method_coverages,
                "category": category,
                "reason": reason,
                "action": action,
                "top_hits": {
                    method: {
                        "source_file": top_hit_for(method, qid, outputs).get("source_file", ""),
                        "source_scope": top_hit_for(method, qid, outputs).get("source_scope", ""),
                        "preview": compact_text(top_hit_for(method, qid, outputs).get("preview", ""), 260),
                    }
                    for method in ("keyword", "dense_hashing", "hybrid_rrf")
                },
            }
        )

    category_counts: dict[str, int] = {}
    for item in analyzed:
        category_counts[item["category"]] = category_counts.get(item["category"], 0) + 1

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "comparison": str(comparison_path),
        "day3_summaries": comparison["summaries"],
        "analyzed_question_count": len(analyzed),
        "category_counts": dict(sorted(category_counts.items())),
        "cases": analyzed,
    }


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Day 4 Failure Case Analysis",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Day 3 comparison: `{payload['comparison']}`",
        f"- Analyzed cases: {payload['analyzed_question_count']}",
        "",
        "## Category Counts",
        "",
        "| Category | Count |",
        "| --- | ---: |",
    ]
    for category, count in payload["category_counts"].items():
        lines.append(f"| {markdown_cell(category)} | {count} |")

    lines.extend(
        [
            "",
            "## Method Snapshot",
            "",
            "| Method | Question recall@K | Avg keyword coverage | Strong | Weak | Missed |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in payload["day3_summaries"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(item["method"]),
                    markdown_cell(item["question_recall_at_k"]),
                    markdown_cell(item["avg_retrieval_keyword_coverage"]),
                    markdown_cell(item["strong_questions"]),
                    markdown_cell(item["weak_questions"]),
                    markdown_cell(item["missed_questions"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| ID | Type | Coverage keyword/dense/hybrid | Category | Reason | Action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in payload["cases"]:
        coverage_text = (
            f"{item['coverages'].get('keyword')}/"
            f"{item['coverages'].get('dense_hashing')}/"
            f"{item['coverages'].get('hybrid_rrf')}"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(item["id"]),
                    markdown_cell(item["task_type"]),
                    markdown_cell(coverage_text),
                    markdown_cell(item["category"]),
                    markdown_cell(item["reason"]),
                    markdown_cell(item["action"]),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Top Hit Diagnostics", ""])
    for item in payload["cases"]:
        lines.extend(
            [
                f"### {item['id']} {item['question']}",
                "",
                f"- Category: `{item['category']}`",
                f"- Action: {item['action']}",
                "",
                "| Method | Source | Scope | Top preview |",
                "| --- | --- | --- | --- |",
            ]
        )
        for method, hit in item["top_hits"].items():
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(method),
                        markdown_cell(hit["source_file"]),
                        markdown_cell(hit["source_scope"]),
                        markdown_cell(hit["preview"]),
                    ]
                )
                + " |"
            )
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_presentation_summary(path: Path, payload: dict[str, Any], report_md: Path) -> None:
    lines = [
        "# 第四天失败案例分析",
        "",
        "## 一句话结论",
        "",
        (
            "第三天 baseline 的主要问题不是系统完全检索不到，而是专业术语别名、结构化数字事实、"
            "评测概念题和弱 embedding 排序共同造成 Top-K 证据覆盖不足。"
        ),
        "",
        "## 失败原因归类",
        "",
        "| 原因类别 | 数量 | 优化方向 |",
        "| --- | ---: | --- |",
    ]
    action_by_category: dict[str, str] = {}
    for item in payload["cases"]:
        action_by_category.setdefault(item["category"], item["action"])
    for category, count in payload["category_counts"].items():
        lines.append(f"| {markdown_cell(category)} | {count} | {markdown_cell(action_by_category.get(category, ''))} |")

    lines.extend(
        [
            "",
            "## 汇报口径",
            "",
            "可以这样讲：",
            "",
            "> 第四天我重点分析了 baseline 未命中的题目。结果说明，当前系统链路能跑通，但还没有把术语别名、结构化事实、评测指标定义和弱向量模型的问题完全处理好。下一步优化不是继续堆页面，而是补同义词扩展、结构化事实卡片、source_scope 路由和更好的 embedding/reranker。",
            "",
            "## 重点失败样例",
            "",
            "| ID | 问题 | 归类 | 下一步 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in payload["cases"][:8]:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(item["id"]),
                    markdown_cell(item["question"]),
                    markdown_cell(item["category"]),
                    markdown_cell(item["action"]),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 详细报告", "", f"详见 `{report_md}`。"])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze Day 3 retrieval baseline weak and failed cases.")
    parser.add_argument("--comparison", default="", help="Day 3 comparison JSON. Defaults to latest in reports.")
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--docs-summary", default=str(DEFAULT_DOCS_SUMMARY))
    args = parser.parse_args(argv)

    output_dir = normalize_path(args.output_dir)
    comparison_path = normalize_path(args.comparison) if args.comparison else latest_comparison(output_dir)
    docs_summary = normalize_path(args.docs_summary)
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = build_analysis(comparison_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_json = output_dir / f"day4_failure_analysis_{stamp}.json"
    report_md = output_dir / f"day4_failure_analysis_{stamp}.md"
    write_json_report(report_json, payload)
    write_markdown_report(report_md, payload)
    docs_summary.parent.mkdir(parents=True, exist_ok=True)
    write_presentation_summary(docs_summary, payload, report_md)

    print(f"Wrote JSON report: {report_json}")
    print(f"Wrote Markdown report: {report_md}")
    print(f"Wrote presentation summary: {docs_summary}")
    print(f"Analyzed cases: {payload['analyzed_question_count']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
