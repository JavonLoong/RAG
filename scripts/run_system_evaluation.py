from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
DEFAULT_REPORT_DIR = REPO_ROOT / "evaluation" / "reports"
REQUIRED_DATASET_FIELDS = {
    "question",
    "expected_evidence_keywords",
    "task_type",
    "source_scope",
    "grading_notes",
}
RETRIEVAL_KEYS = (
    "retrieval_results",
    "retrieved_contexts",
    "contexts",
    "hits",
    "documents",
    "evidence",
)
CITATION_KEYS = ("citations", "citation", "sources", "references")
TEXT_KEYS = (
    "text",
    "content",
    "document",
    "chunk_text",
    "preview",
    "page_or_evidence",
    "evidence",
    "answer",
    "source",
    "source_file",
    "filename",
    "title",
)


def normalize_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text)
    return " ".join(text.lower().split())


def compact_text(value: Any, limit: int = 180) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "..."


def safe_rate(numerator: int | float, denominator: int | float) -> float | None:
    if denominator == 0:
        return None
    return round(float(numerator) / float(denominator), 6)


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def load_json_or_jsonl(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Input file does not exist: {path}")

    if path.suffix.lower() == ".jsonl":
        records: list[Any] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
        return records

    return json.loads(path.read_text(encoding="utf-8"))


def coerce_record_list(raw: Any, path: Path, preferred_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        for key in preferred_keys:
            value = raw.get(key)
            if isinstance(value, list):
                items = value
                break
        else:
            raise ValueError(f"JSON object in {path} must contain one of: {', '.join(preferred_keys)}")
    else:
        raise ValueError(f"{path} must be a JSON list or JSON object.")

    records: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Record #{index} in {path} must be an object.")
        records.append(item)
    return records


def load_dataset(path: Path) -> list[dict[str, Any]]:
    raw = load_json_or_jsonl(path)
    records = coerce_record_list(raw, path, ("questions", "items", "records"))

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(records, start=1):
        missing = sorted(field for field in REQUIRED_DATASET_FIELDS if field not in item)
        if missing:
            raise ValueError(f"Dataset record #{index} is missing required fields: {', '.join(missing)}")

        keywords = item["expected_evidence_keywords"]
        if not isinstance(keywords, list) or not all(str(keyword).strip() for keyword in keywords):
            raise ValueError(
                "Dataset field expected_evidence_keywords must be a non-empty list of strings "
                f"for record #{index}."
            )

        record = dict(item)
        record["id"] = str(record.get("id") or f"se{index:03d}")
        record["question"] = str(record["question"]).strip()
        record["expected_evidence_keywords"] = [str(keyword).strip() for keyword in keywords]
        if not record["question"]:
            raise ValueError(f"Dataset question is empty for record #{index}.")
        normalized.append(record)
    return normalized


def load_outputs(path: Path) -> list[dict[str, Any]]:
    raw = load_json_or_jsonl(path)
    if isinstance(raw, dict) and not any(isinstance(raw.get(key), list) for key in ("results", "outputs", "items", "records")):
        if raw.get("question"):
            return [raw]
    return coerce_record_list(raw, path, ("results", "outputs", "items", "records"))


def record_match_key(record: dict[str, Any]) -> str | None:
    record_id = record.get("id") or record.get("question_id") or record.get("qid")
    if record_id not in (None, ""):
        return f"id:{record_id}"
    question = str(record.get("question", "")).strip()
    if question:
        return f"question:{normalize_text(question)}"
    return None


def build_output_index(outputs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for output in outputs:
        key = record_match_key(output)
        if key:
            index[key] = output
        question = str(output.get("question", "")).strip()
        if question:
            index[f"question:{normalize_text(question)}"] = output
    return index


def find_output(dataset_record: dict[str, Any], output_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for key in (
        f"id:{dataset_record.get('id')}",
        f"question:{normalize_text(dataset_record.get('question', ''))}",
    ):
        if key in output_index:
            return output_index[key]
    return {}


def as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    return [value]


def stringify_record(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts: list[str] = []
        for key in TEXT_KEYS:
            if key in value and value[key] not in (None, ""):
                parts.append(str(value[key]))
        metadata = value.get("metadata")
        if isinstance(metadata, dict):
            for key in TEXT_KEYS:
                if key in metadata and metadata[key] not in (None, ""):
                    parts.append(str(metadata[key]))
        if parts:
            return " ".join(parts)
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def sort_retrieval_items(items: list[Any]) -> list[Any]:
    def sort_key(item: Any) -> tuple[int, int]:
        if isinstance(item, dict):
            rank = item.get("rank")
            try:
                return (0, int(rank))
            except (TypeError, ValueError):
                return (1, 0)
        return (1, 0)

    ranked = [item for item in items if isinstance(item, dict) and item.get("rank") not in (None, "")]
    if not ranked:
        return items
    return sorted(items, key=sort_key)


def extract_retrieval_items(record: dict[str, Any], top_k: int) -> list[Any]:
    candidates: list[Any] = []
    for key in RETRIEVAL_KEYS:
        if key in record:
            candidates.extend(as_list(record[key]))

    retrieval = record.get("retrieval")
    if isinstance(retrieval, dict):
        for key in ("results", "hits", "contexts", "documents"):
            if key in retrieval:
                candidates.extend(as_list(retrieval[key]))
    elif retrieval:
        candidates.extend(as_list(retrieval))

    sorted_items = sort_retrieval_items(candidates)
    if top_k <= 0:
        return sorted_items
    return sorted_items[:top_k]


def extract_citation_items(record: dict[str, Any], answer_text: str) -> list[Any]:
    citations: list[Any] = []
    for key in CITATION_KEYS:
        if key in record:
            citations.extend(as_list(record[key]))

    inline_citations = re.findall(r"(?:\[[0-9A-Za-z_.:-]{1,40}\]|【[^】]{1,80}】)", answer_text)
    citations.extend(inline_citations)
    return [citation for citation in citations if str(citation).strip()]


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    normalized_text = normalize_text(text)
    hits: list[str] = []
    for keyword in keywords:
        normalized_keyword = normalize_text(keyword)
        if normalized_keyword and normalized_keyword in normalized_text:
            hits.append(keyword)
    return hits


def keyword_coverage(hits: list[str], keywords: list[str]) -> float:
    if not keywords:
        return 0.0
    return round(len(set(hits)) / len(keywords), 6)


def expected_passage_id(record: dict[str, Any]) -> str:
    notes = str(record.get("grading_notes") or "")
    match = re.search(r"Relevant passage id:\s*([^\s,;]+)", notes, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def expected_source_ids(record: dict[str, Any]) -> list[str]:
    notes = str(record.get("grading_notes") or "")
    passage_id = expected_passage_id(record)
    if passage_id:
        return [passage_id]
    sentence_match = re.search(
        r"support sentence ids:\s*([^;]+)",
        notes,
        flags=re.IGNORECASE,
    )
    if sentence_match:
        return [
            item.strip()
            for item in sentence_match.group(1).split(",")
            if item.strip() and item.strip().lower() != "none"
        ]
    return []


def retrieval_contains_passage_id(retrieval_items: list[Any], passage_id: str) -> bool:
    if not passage_id:
        return False
    return bool(retrieval_source_id_hits(retrieval_items, [passage_id]))


def retrieval_source_id_hits(retrieval_items: list[Any], source_ids: list[str]) -> list[str]:
    hits: list[str] = []
    normalized_ids = [(source_id, normalize_text(source_id)) for source_id in source_ids if source_id]
    if not normalized_ids:
        return hits
    for source_id, normalized in normalized_ids:
        for item in retrieval_items:
            if normalized and normalized in normalize_text(stringify_record(item)):
                hits.append(source_id)
                break
            if isinstance(item, dict):
                metadata = item.get("metadata")
                if isinstance(metadata, dict):
                    for key in ("passage_id", "sentence_id", "document_id", "chunk_id"):
                        if normalize_text(metadata.get(key, "")) == normalized:
                            hits.append(source_id)
                            break
                    if hits and hits[-1] == source_id:
                        break
                for key in ("passage_id", "sentence_id", "document_id", "chunk_id"):
                    if normalize_text(item.get(key, "")) == normalized:
                        hits.append(source_id)
                        break
                if hits and hits[-1] == source_id:
                    break
    return hits


def classify_hallucination_risk(
    retrieval_coverage: float,
    answer_coverage: float,
    missing_citation: bool,
    has_answer: bool,
    retrieval_only: bool,
) -> str:
    if retrieval_only or not has_answer:
        return "not_applicable"
    if retrieval_coverage == 0 or answer_coverage == 0:
        return "high"
    if missing_citation or retrieval_coverage < 0.6 or answer_coverage < 0.6:
        return "medium"
    return "low"


def evaluate_records(
    dataset: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    *,
    top_k: int = 5,
    retrieval_only: bool = False,
) -> dict[str, Any]:
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0.")

    output_index = build_output_index(outputs)
    results: list[dict[str, Any]] = []
    task_type_counts: Counter[str] = Counter()

    total_expected_keywords = 0
    retrieval_keyword_hits_total = 0
    retrieval_question_hits = 0
    no_result_count = 0
    retrieval_coverages: list[float] = []
    answer_coverages: list[float] = []
    citation_coverages: list[float] = []
    answer_contains_evidence_count = 0
    complete_answer_count = 0
    answer_evaluated_count = 0
    citation_present_count = 0
    missing_citation_count = 0
    citation_keyword_hits_total = 0
    answer_expected_keywords_total = 0
    full_evidence_coverage_count = 0
    risk_counts: Counter[str] = Counter()
    retrieved_item_counts: list[float] = []
    passage_id_expected_count = 0
    passage_id_hit_count = 0
    gold_id_expected_count = 0
    gold_id_hit_count = 0

    for item in dataset:
        output = find_output(item, output_index)
        keywords = [str(keyword) for keyword in item.get("expected_evidence_keywords", [])]
        task_type = str(item.get("task_type", "unspecified"))
        task_type_counts[task_type] += 1
        total_expected_keywords += len(keywords)

        retrieval_items = extract_retrieval_items(output, top_k)
        retrieval_text = " ".join(stringify_record(retrieval_item) for retrieval_item in retrieval_items)
        answer_text = str(output.get("answer") or output.get("final_answer") or output.get("response") or "").strip()
        citation_items = extract_citation_items(output, answer_text)
        citation_text = " ".join(stringify_record(citation) for citation in citation_items)

        retrieval_hits = keyword_hits(retrieval_text, keywords)
        answer_hits = keyword_hits(answer_text, keywords)
        citation_hits = keyword_hits(citation_text, keywords)
        expected_pid = expected_passage_id(item)
        expected_ids = expected_source_ids(item)
        source_id_hits = retrieval_source_id_hits(retrieval_items, expected_ids)
        passage_id_hit = retrieval_contains_passage_id(retrieval_items, expected_pid) if expected_pid else None
        retrieval_coverage = keyword_coverage(retrieval_hits, keywords)
        answer_coverage = keyword_coverage(answer_hits, keywords)
        citation_coverage = keyword_coverage(citation_hits, keywords)
        has_retrieval_result = bool(retrieval_items)
        has_answer = bool(answer_text)
        missing_citation = has_answer and not citation_items and not retrieval_only
        answer_contains_evidence = has_answer and bool(answer_hits)
        hallucination_risk = classify_hallucination_risk(
            retrieval_coverage,
            answer_coverage,
            missing_citation,
            has_answer,
            retrieval_only,
        )

        retrieved_item_counts.append(float(len(retrieval_items)))
        retrieval_coverages.append(retrieval_coverage)
        retrieval_keyword_hits_total += len(set(retrieval_hits))
        if retrieval_hits:
            retrieval_question_hits += 1
        if retrieval_coverage == 1:
            full_evidence_coverage_count += 1
        if expected_pid:
            passage_id_expected_count += 1
            if passage_id_hit:
                passage_id_hit_count += 1
        if expected_ids:
            gold_id_expected_count += len(expected_ids)
            gold_id_hit_count += len(set(source_id_hits))
        if not has_retrieval_result:
            no_result_count += 1

        if has_answer and not retrieval_only:
            answer_evaluated_count += 1
            answer_expected_keywords_total += len(keywords)
            answer_coverages.append(answer_coverage)
            if answer_contains_evidence:
                answer_contains_evidence_count += 1
            if answer_coverage == 1:
                complete_answer_count += 1
            if citation_items:
                citation_present_count += 1
            if missing_citation:
                missing_citation_count += 1
            citation_coverages.append(citation_coverage)
            citation_keyword_hits_total += len(set(citation_hits))

        risk_counts[hallucination_risk] += 1
        results.append(
            {
                "id": item.get("id"),
                "question": item.get("question"),
                "task_type": task_type,
                "source_scope": item.get("source_scope"),
                "grading_notes": item.get("grading_notes"),
                "expected_evidence_keywords": keywords,
                "retrieval_evidence_keywords": retrieval_hits,
                "answer_evidence_keywords": answer_hits if not retrieval_only else [],
                "citation_evidence_keywords": citation_hits if not retrieval_only else [],
                "expected_passage_id": expected_pid or None,
                "retrieval_passage_id_hit": passage_id_hit,
                "expected_source_ids": expected_ids,
                "retrieval_source_id_hits": source_id_hits,
                "retrieval_keyword_coverage": retrieval_coverage,
                "answer_keyword_coverage": answer_coverage if has_answer and not retrieval_only else None,
                "citation_keyword_coverage": citation_coverage if has_answer and not retrieval_only else None,
                "retrieved_count_at_k": len(retrieval_items),
                "has_retrieval_result": has_retrieval_result,
                "answer_contains_evidence": answer_contains_evidence if not retrieval_only else None,
                "citation_count": len(citation_items) if not retrieval_only else None,
                "missing_citation": missing_citation if not retrieval_only else None,
                "hallucination_risk": hallucination_risk,
                "top_retrieval_previews": [compact_text(stringify_record(retrieval_item)) for retrieval_item in retrieval_items],
            }
        )

    total_questions = len(dataset)
    metrics = {
        "retrieval": {
            "evaluated_questions": total_questions,
            "question_recall_at_k": safe_rate(retrieval_question_hits, total_questions),
            "keyword_recall_at_k": safe_rate(retrieval_keyword_hits_total, total_expected_keywords),
            "average_keyword_coverage": average(retrieval_coverages),
            "passage_id_recall_at_k": safe_rate(passage_id_hit_count, passage_id_expected_count)
            if passage_id_expected_count
            else None,
            "passage_id_expected_count": passage_id_expected_count,
            "passage_id_hit_count": passage_id_hit_count,
            "gold_id_recall_at_k": safe_rate(gold_id_hit_count, gold_id_expected_count)
            if gold_id_expected_count
            else None,
            "gold_id_expected_count": gold_id_expected_count,
            "gold_id_hit_count": gold_id_hit_count,
            "full_evidence_coverage_rate": safe_rate(full_evidence_coverage_count, total_questions),
            "no_result_rate": safe_rate(no_result_count, total_questions),
            "average_retrieved_count_at_k": average(retrieved_item_counts),
        },
        "evidence": {
            "expected_keyword_total": total_expected_keywords,
            "retrieved_keyword_hit_total": retrieval_keyword_hits_total,
            "evidence_keyword_hit_rate": safe_rate(retrieval_keyword_hits_total, total_expected_keywords),
            "question_with_any_evidence_rate": safe_rate(retrieval_question_hits, total_questions),
            "question_with_full_evidence_rate": safe_rate(full_evidence_coverage_count, total_questions),
        },
        "citation": {
            "evaluated_questions": answer_evaluated_count,
            "citation_present_rate": safe_rate(citation_present_count, answer_evaluated_count),
            "missing_citation_rate": safe_rate(missing_citation_count, answer_evaluated_count),
            "citation_keyword_hit_rate": safe_rate(citation_keyword_hits_total, answer_expected_keywords_total)
            if answer_evaluated_count
            else None,
            "average_citation_keyword_coverage": average(citation_coverages),
        },
        "answer": {
            "evaluated_questions": answer_evaluated_count,
            "answer_contains_evidence_rate": safe_rate(answer_contains_evidence_count, answer_evaluated_count),
            "answer_completeness_avg": average(answer_coverages),
            "complete_answer_rate": safe_rate(complete_answer_count, answer_evaluated_count),
        },
        "hallucination_risk": {
            "low_count": risk_counts.get("low", 0),
            "medium_count": risk_counts.get("medium", 0),
            "high_count": risk_counts.get("high", 0),
            "not_applicable_count": risk_counts.get("not_applicable", 0),
            "high_risk_rate": safe_rate(risk_counts.get("high", 0), answer_evaluated_count),
            "medium_or_high_risk_rate": safe_rate(
                risk_counts.get("medium", 0) + risk_counts.get("high", 0),
                answer_evaluated_count,
            ),
        },
    }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "total_questions": total_questions,
            "top_k": top_k,
            "retrieval_only": retrieval_only,
            "task_type_counts": dict(sorted(task_type_counts.items())),
            "matched_outputs": sum(1 for item in dataset if find_output(item, output_index)),
            "missing_outputs": sum(1 for item in dataset if not find_output(item, output_index)),
        },
        "metrics": metrics,
        "results": results,
    }


def markdown_cell(value: Any) -> str:
    if isinstance(value, float):
        text = f"{value:.6f}"
    elif value is None:
        text = "-"
    else:
        text = compact_text(value, 160)
    return text.replace("|", "\\|").replace("\n", " ")


def metric_lines(payload: dict[str, Any]) -> list[str]:
    lines = ["| Group | Metric | Value |", "| --- | --- | --- |"]
    for group_name, group_metrics in payload["metrics"].items():
        for metric_name, value in group_metrics.items():
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(group_name),
                        markdown_cell(metric_name),
                        markdown_cell(value),
                    ]
                )
                + " |"
            )
    return lines


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    lines = [
        "# System Evaluation Report",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Questions: {summary['total_questions']}",
        f"- Top K: {summary['top_k']}",
        f"- Retrieval only: {summary['retrieval_only']}",
        f"- Matched outputs: {summary['matched_outputs']}",
        f"- Missing outputs: {summary['missing_outputs']}",
        "",
        "## Metrics",
        "",
        *metric_lines(payload),
        "",
        "## Task Types",
        "",
        "| Task type | Count |",
        "| --- | --- |",
    ]

    for task_type, count in summary["task_type_counts"].items():
        lines.append(f"| {markdown_cell(task_type)} | {markdown_cell(count)} |")

    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| ID | Type | Question | Retrieval coverage | Answer coverage | Missing citation | Risk | Notes |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for result in payload["results"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(result["id"]),
                    markdown_cell(result["task_type"]),
                    markdown_cell(result["question"]),
                    markdown_cell(result["retrieval_keyword_coverage"]),
                    markdown_cell(result["answer_keyword_coverage"]),
                    markdown_cell(result["missing_citation"]),
                    markdown_cell(result["hallucination_risk"]),
                    markdown_cell(result["grading_notes"]),
                ]
            )
            + " |"
        )

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def sanitize_run_name(run_name: str | None) -> str:
    if not run_name:
        return ""
    sanitized = re.sub(r"[^0-9A-Za-z_.-]+", "_", run_name.strip())
    return sanitized.strip("._-")


def write_reports(
    payload: dict[str, Any],
    output_dir: Path,
    *,
    run_name: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    now = generated_at or datetime.now()
    report_payload = copy.deepcopy(payload)
    report_payload["generated_at"] = now.isoformat(timespec="seconds")

    stamp = now.strftime("%Y%m%d_%H%M%S")
    sanitized_run = sanitize_run_name(run_name)
    stem = f"system_eval_{sanitized_run}_{stamp}" if sanitized_run else f"system_eval_{stamp}"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    write_json_report(json_path, report_payload)
    write_markdown_report(md_path, report_payload)
    return {"json": json_path, "md": md_path}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate RAG system outputs against a system evaluation set. "
            "Inputs may be JSONL or JSON with records/results/outputs."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="System output JSONL/JSON. Records can contain answer, citations, and retrieval_results/hits.",
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET),
        help="Evaluation set JSONL/JSON with question, expected_evidence_keywords, task_type, source_scope, grading_notes.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Number of retrieval items to evaluate per question.")
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Evaluate only retrieval results; answer and citation metrics are marked not applicable.",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORT_DIR), help="Directory for system_eval_*.json/.md.")
    parser.add_argument("--run-name", default="", help="Optional name inserted into report filenames.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    dataset_path = normalize_path(args.dataset)
    input_path = normalize_path(args.input)
    output_dir = normalize_path(args.output_dir)

    dataset = load_dataset(dataset_path)
    outputs = load_outputs(input_path)
    payload = evaluate_records(dataset, outputs, top_k=args.top_k, retrieval_only=args.retrieval_only)
    payload["dataset"] = str(dataset_path)
    payload["input"] = str(input_path)

    paths = write_reports(payload, output_dir, run_name=args.run_name)
    print(f"Wrote JSON report: {paths['json']}")
    print(f"Wrote Markdown report: {paths['md']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
