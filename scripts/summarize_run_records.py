"""Summarize structured run records and JSONL operation logs.

The script is intentionally dependency-free so it can run in a fresh checkout:

    python scripts/summarize_run_records.py

Outputs:
    observability/reports/run_records_summary.json
    observability/reports/run_records_summary.md
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OBSERVABILITY_DIR = REPO_ROOT / "observability"
LOGS_DIR = OBSERVABILITY_DIR / "logs"
REPORTS_DIR = OBSERVABILITY_DIR / "reports"
SUMMARY_JSON = REPORTS_DIR / "run_records_summary.json"
SUMMARY_MD = REPORTS_DIR / "run_records_summary.md"

REQUIRED_RUN_RECORD_FIELDS = [
    "run_id",
    "task_type",
    "started_at",
    "finished_at",
    "duration_seconds",
    "status",
    "input_paths",
    "output_paths",
    "metrics",
    "errors",
    "log_path",
    "notes",
]

VALID_STATUSES = {"success", "failure", "partial", "running", "unknown"}
DONE_EVENTS = {"build_done", "done", "completed", "complete", "success", "finished"}
ERROR_MARKERS = ("error", "failed", "failure", "exception", "traceback")


def rel_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def compact_payload(payload: dict[str, Any], max_length: int = 500) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def find_run_record_files() -> list[Path]:
    candidates: set[Path] = set()
    if LOGS_DIR.exists():
        candidates.update(LOGS_DIR.rglob("run_record*.json"))
    if OBSERVABILITY_DIR.exists():
        candidates.update(OBSERVABILITY_DIR.glob("run_record*.json"))

    excluded_names = {"run_record_schema.json"}
    return sorted(
        path
        for path in candidates
        if path.name not in excluded_names
        and REPORTS_DIR not in path.parents
        and path.is_file()
    )


def find_log_files() -> list[Path]:
    if not LOGS_DIR.exists():
        return []
    return sorted(
        path
        for pattern in ("*.log", "*.jsonl")
        for path in LOGS_DIR.rglob(pattern)
        if path.is_file()
    )


def infer_task_type(events: list[dict[str, Any]], path: Path) -> str:
    event_names = {str(event.get("event", "")).lower() for event in events}
    path_text = str(path).lower()
    if {"upsert_batch", "library_done"} & event_names or "chroma" in path_text:
        return "chroma_build"
    if "pdf_probe" in event_names or "pdf" in path_text:
        return "pdf_extraction"
    if any("retriev" in name or "query" in name or "search" in name for name in event_names):
        return "retrieval"
    if any("triple" in name or "kg" in name or "graph" in name for name in event_names):
        return "kg_extraction"
    return "unknown"


def infer_status(
    events: list[dict[str, Any]], malformed_errors: list[dict[str, Any]]
) -> str:
    if malformed_errors:
        return "partial"
    event_names = [str(event.get("event", "")).lower() for event in events]
    payload_texts = [compact_payload(event).lower() for event in events]
    has_error = any(
        any(marker in name for marker in ERROR_MARKERS) for name in event_names
    ) or any(any(marker in text for marker in ERROR_MARKERS) for text in payload_texts)
    if has_error:
        return "failure"
    if any(name in DONE_EVENTS or name.endswith("_done") for name in event_names):
        return "success"
    if any(name.endswith("_start") or name == "start" for name in event_names):
        return "running"
    return "unknown"


def extract_error_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        event_name = str(event.get("event", "")).lower()
        level = str(event.get("level", "")).lower()
        payload_text = compact_payload(event).lower()
        if (
            level in {"error", "critical"}
            or any(marker in event_name for marker in ERROR_MARKERS)
            or any(marker in payload_text for marker in ERROR_MARKERS)
        ):
            errors.append(
                {
                    "stage": event.get("event"),
                    "message": str(event.get("message") or event.get("error") or event_name),
                    "details": {"line": index, "event": event},
                }
            )
    return errors


def metrics_from_events(events: list[dict[str, Any]], log_path: Path) -> dict[str, Any]:
    event_counts = Counter(str(event.get("event", "unknown")) for event in events)
    metrics: dict[str, Any] = {
        "log_line_count": len(events),
        "log_bytes": log_path.stat().st_size,
        "event_counts": dict(sorted(event_counts.items())),
    }

    pdf_events = [
        event
        for event in events
        if event.get("event") in {"pdf_probe", "pdf_result"}
    ]
    for event in events:
        nested_pdf = event.get("pdf_extraction")
        if isinstance(nested_pdf, dict):
            pdf_events.append(nested_pdf)
    if pdf_events:
        classification_counts = Counter(
            str(event.get("classification"))
            for event in pdf_events
            if event.get("classification")
        )
        metrics.update(
            {
                "pdf_file_count": len(pdf_events),
                "pdf_probe_count": event_counts.get("pdf_probe", 0),
                "pdf_result_count": event_counts.get("pdf_result", 0),
                "pages_total": sum_int(pdf_events, "total_pages"),
                "pages_scanned": sum_int(pdf_events, "pages_scanned")
                + sum_int(pdf_events, "sampled_pages"),
                "pages_with_text": sum_int(pdf_events, "pages_with_text"),
                "extractable_chars": sum_int(pdf_events, "extractable_chars")
                + sum_int(pdf_events, "extracted_chars"),
                "ocr_queue_count": sum(
                    1
                    for event in pdf_events
                    if int_or_none(event.get("extractable_chars")) == 0
                    or int_or_none(event.get("extracted_chars")) == 0
                    or int_or_none(event.get("pages_with_text")) == 0
                    or event.get("classification") == "needs_ocr"
                ),
                "pdf_classification_counts": dict(sorted(classification_counts.items())),
            }
        )
        audit_summaries = [
            event.get("summary")
            for event in events
            if event.get("event") == "audit_done" and isinstance(event.get("summary"), dict)
        ]
        if audit_summaries:
            metrics["audit_summary"] = audit_summaries[-1]

    upsert_events = [
        event
        for event in events
        if event.get("event") in {"upsert_batch", "chroma_add_batch"}
    ]
    collection_events = [
        event
        for event in events
        if event.get("event") == "library_done" or event.get("collection_count") is not None
    ]
    if upsert_events or collection_events:
        docs_by_collection = {
            str(event.get("collection", "unknown")): event.get("document_count")
            if event.get("document_count") is not None
            else event.get("collection_count")
            for event in collection_events
        }
        storage_by_collection = {
            str(event.get("collection", "unknown")): event.get("storage_bytes")
            for event in collection_events
            if event.get("storage_bytes") is not None
        }
        metrics.update(
            {
                "chroma_upsert_batches": len(upsert_events),
                "chroma_upserted_count": sum_int(upsert_events, "count"),
                "chroma_collection_count": len(collection_events),
                "chroma_total_document_count": sum_int(collection_events, "document_count")
                + sum_int(collection_events, "collection_count"),
                "chroma_storage_bytes": sum_int(collection_events, "storage_bytes"),
                "chroma_documents_by_collection": docs_by_collection,
                "chroma_storage_bytes_by_collection": storage_by_collection,
            }
        )
        build_done_events = [event for event in events if event.get("event") == "build_done"]
        if build_done_events:
            last_build = build_done_events[-1]
            for key in (
                "qa_chunks",
                "pdf_chunks",
                "embedding_backend",
                "embedding_dimension",
                "chunk_size",
                "overlap",
            ):
                if key in last_build:
                    metrics[key] = last_build[key]

    query_events = [
        event
        for event in events
        if any(token in str(event.get("event", "")).lower() for token in ("query", "search", "retriev"))
    ]
    if query_events:
        metrics.update(
            {
                "query_count": len(query_events),
                "top_k_values": unique_strings([event.get("top_k") for event in query_events]),
                "retrieved_count": sum_int(query_events, "retrieved_count"),
                "hit_count": sum_int(query_events, "hit_count"),
            }
        )

    triple_events = [
        event
        for event in events
        if any(token in str(event.get("event", "")).lower() for token in ("triple", "kg", "graph"))
    ]
    if triple_events:
        metrics.update(
            {
                "kg_event_count": len(triple_events),
                "candidate_triple_count": sum_int(triple_events, "candidate_triple_count"),
                "validated_triple_count": sum_int(triple_events, "validated_triple_count"),
                "triple_count": sum_int(triple_events, "triple_count"),
            }
        )

    done_events = [
        event
        for event in events
        if str(event.get("event", "")).lower() in DONE_EVENTS
        or str(event.get("event", "")).lower().endswith("_done")
    ]
    elapsed_values = [float_or_none(event.get("elapsed_s")) for event in done_events]
    elapsed_values = [value for value in elapsed_values if value is not None]
    if elapsed_values:
        metrics["duration_from_log_seconds"] = elapsed_values[-1]

    return metrics


def sum_int(events: list[dict[str, Any]], key: str) -> int:
    total = 0
    for event in events:
        value = int_or_none(event.get(key))
        if value is not None:
            total += value
    return total


def int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def derive_duration_seconds(
    started_at: str | None, finished_at: str | None, metrics: dict[str, Any]
) -> float | None:
    from_log = float_or_none(metrics.get("duration_from_log_seconds"))
    if from_log is not None:
        return round(from_log, 3)

    start_dt = parse_iso_datetime(started_at)
    finish_dt = parse_iso_datetime(finished_at)
    if start_dt and finish_dt:
        try:
            return round((finish_dt - start_dt).total_seconds(), 3)
        except TypeError:
            return None
    return None


def paths_from_events(events: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    input_keys = (
        "input_path",
        "input_paths",
        "raw_dir",
        "source_file",
        "source_path",
        "file_name",
        "qa_source",
        "pdf_source",
    )
    output_keys = (
        "output_path",
        "output_paths",
        "output_dir",
        "report_dir",
        "json_path",
        "csv_path",
        "md_path",
        "library",
        "library_dir",
        "report_path",
    )
    input_values: list[Any] = []
    output_values: list[Any] = []
    for event in events:
        for key in input_keys:
            append_path_value(input_values, event.get(key))
        for key in output_keys:
            append_path_value(output_values, event.get(key))
    return unique_strings(input_values), unique_strings(output_values)


def append_path_value(target: list[Any], value: Any) -> None:
    if isinstance(value, list):
        target.extend(item for item in value if isinstance(item, (str, Path)))
    elif isinstance(value, (str, Path)) and value:
        target.append(value)


def parse_jsonl_log(path: Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return failure_record_from_file(path, f"Could not read log file: {exc}")
    except UnicodeDecodeError as exc:
        return failure_record_from_file(path, f"Could not decode log file as UTF-8: {exc}")

    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw_text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            errors.append(
                {
                    "stage": "jsonl_parse",
                    "message": f"Malformed JSON line {line_number}: {exc.msg}",
                    "details": {"line": line_number, "text": stripped[:300]},
                }
            )
            continue
        if not isinstance(payload, dict):
            errors.append(
                {
                    "stage": "jsonl_parse",
                    "message": f"JSON line {line_number} is not an object.",
                    "details": {"line": line_number, "value": payload},
                }
            )
            continue
        events.append(payload)

    if not events:
        return {
            "run_id": path.stem,
            "task_type": "unknown",
            "started_at": None,
            "finished_at": None,
            "duration_seconds": None,
            "status": "failure" if errors else "unknown",
            "input_paths": [],
            "output_paths": [],
            "metrics": {"log_line_count": 0, "log_bytes": path.stat().st_size},
            "errors": errors
            or [
                {
                    "stage": "jsonl_parse",
                    "message": "Log file contained no structured JSON events.",
                    "details": None,
                }
            ],
            "log_path": rel_path(path),
            "notes": "No structured events could be summarized.",
            "source_kind": "jsonl_log",
            "gaps": [
                "Missing structured run record fields: run_id, task_type, started_at, finished_at, duration_seconds, status, input_paths, output_paths, metrics, errors, notes."
            ],
        }

    event_errors = extract_error_events(events)
    errors.extend(event_errors)
    started_at = first_timestamp(events)
    finished_at = last_timestamp(events)
    metrics = metrics_from_events(events, path)
    input_paths, output_paths = paths_from_events(events)
    status = infer_status(events, errors)
    task_type = infer_task_type(events, path)
    run_id = infer_run_id(path, task_type, started_at)
    duration_seconds = derive_duration_seconds(started_at, finished_at, metrics)
    gaps = gaps_for_derived_log(events, run_id, task_type, duration_seconds)

    if gaps and status == "success":
        status = "partial"

    return {
        "run_id": run_id,
        "task_type": task_type,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "status": status,
        "input_paths": input_paths,
        "output_paths": output_paths,
        "metrics": metrics,
        "errors": errors,
        "log_path": rel_path(path),
        "notes": "Derived from JSONL log events; see gaps for fields not present in a standard run_record JSON.",
        "source_kind": "jsonl_log",
        "gaps": gaps,
    }


def first_timestamp(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        if event.get("ts"):
            return str(event["ts"])
        if event.get("timestamp"):
            return str(event["timestamp"])
    return None


def last_timestamp(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        if event.get("ts"):
            return str(event["ts"])
        if event.get("timestamp"):
            return str(event["timestamp"])
    return None


def infer_run_id(path: Path, task_type: str, started_at: str | None) -> str:
    timestamp = ""
    parsed = parse_iso_datetime(started_at)
    if parsed:
        timestamp = parsed.strftime("%Y%m%d-%H%M%S")
    elif path.stem:
        timestamp = path.stem.split("-", 2)[0]
    if timestamp:
        return f"{task_type}-{timestamp}"
    return path.stem


def gaps_for_derived_log(
    events: list[dict[str, Any]], run_id: str, task_type: str, duration_seconds: float | None
) -> list[str]:
    event_keys = set().union(*(event.keys() for event in events)) if events else set()
    missing = [
        field
        for field in REQUIRED_RUN_RECORD_FIELDS
        if field not in event_keys and field not in {"log_path", "metrics", "errors", "notes"}
    ]
    gaps: list[str] = []
    if missing:
        gaps.append(
            "Log is not a full run_record JSON; missing explicit fields: "
            + ", ".join(missing)
            + "."
        )
    if task_type == "unknown":
        gaps.append("Could not infer task_type from event names or log path.")
    if duration_seconds is None:
        gaps.append("Could not derive duration_seconds from elapsed_s or timestamps.")
    if run_id.startswith("unknown-"):
        gaps.append("run_id was generated from file name and should be written explicitly.")
    return gaps


def failure_record_from_file(path: Path, message: str) -> dict[str, Any]:
    return {
        "run_id": path.stem,
        "task_type": "unknown",
        "started_at": None,
        "finished_at": None,
        "duration_seconds": None,
        "status": "failure",
        "input_paths": [],
        "output_paths": [],
        "metrics": {},
        "errors": [{"stage": "file_read", "message": message, "details": None}],
        "log_path": rel_path(path),
        "notes": "File could not be read; no fallback parsing was attempted.",
        "source_kind": "jsonl_log",
        "gaps": ["Could not read source file, so no run metrics were available."],
    }


def parse_run_record(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return failure_record_from_file(path, f"Could not read run_record JSON: {exc}")
    except UnicodeDecodeError as exc:
        return failure_record_from_file(path, f"Could not decode run_record JSON as UTF-8: {exc}")
    except json.JSONDecodeError as exc:
        return failure_record_from_file(path, f"Malformed run_record JSON: {exc.msg}")

    if not isinstance(payload, dict):
        return failure_record_from_file(path, "run_record JSON root must be an object.")

    errors = list(payload.get("errors") if isinstance(payload.get("errors"), list) else [])
    gaps = validate_run_record_payload(payload)
    status = str(payload.get("status", "unknown"))
    if status not in VALID_STATUSES:
        errors.append(
            {
                "stage": "schema_validation",
                "message": f"Invalid status value: {status}",
                "details": None,
            }
        )
        status = "partial"
    elif gaps and status == "success":
        status = "partial"

    return {
        "run_id": str(payload.get("run_id") or path.stem),
        "task_type": str(payload.get("task_type") or "unknown"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "duration_seconds": payload.get("duration_seconds"),
        "status": status,
        "input_paths": payload.get("input_paths") if isinstance(payload.get("input_paths"), list) else [],
        "output_paths": payload.get("output_paths") if isinstance(payload.get("output_paths"), list) else [],
        "metrics": payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {},
        "errors": errors,
        "log_path": payload.get("log_path") or rel_path(path),
        "notes": str(payload.get("notes") or ""),
        "source_kind": "run_record_json",
        "gaps": gaps,
    }


def validate_run_record_payload(payload: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    missing = [field for field in REQUIRED_RUN_RECORD_FIELDS if field not in payload]
    if missing:
        gaps.append("Missing required fields: " + ", ".join(missing) + ".")
    for field in ("input_paths", "output_paths", "errors"):
        if field in payload and not isinstance(payload[field], list):
            gaps.append(f"Field {field} should be a list.")
    if "metrics" in payload and not isinstance(payload["metrics"], dict):
        gaps.append("Field metrics should be an object.")
    if payload.get("duration_seconds") is None:
        gaps.append("duration_seconds is null or missing.")
    return gaps


def aggregate(records: list[dict[str, Any]], scanned_sources: dict[str, list[str]]) -> dict[str, Any]:
    status_counts = Counter(record["status"] for record in records)
    task_counts = Counter(record["task_type"] for record in records)
    source_counts = Counter(record["source_kind"] for record in records)
    total_duration = sum(
        value
        for value in (float_or_none(record.get("duration_seconds")) for record in records)
        if value is not None
    )
    total_errors = sum(len(record.get("errors", [])) for record in records)
    total_gaps = sum(len(record.get("gaps", [])) for record in records)

    metric_totals = {
        "extractable_chars": sum_metric(records, "extractable_chars"),
        "ocr_queue_count": sum_metric(records, "ocr_queue_count"),
        "chroma_upserted_count": sum_metric(records, "chroma_upserted_count"),
        "chroma_total_document_count": sum_metric(records, "chroma_total_document_count"),
        "chroma_storage_bytes": sum_metric(records, "chroma_storage_bytes"),
        "query_count": sum_metric(records, "query_count"),
        "hit_count": sum_metric(records, "hit_count"),
        "candidate_triple_count": sum_metric(records, "candidate_triple_count"),
        "validated_triple_count": sum_metric(records, "validated_triple_count"),
        "triple_count": sum_metric(records, "triple_count"),
    }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(REPO_ROOT),
        "scanned_sources": scanned_sources,
        "record_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "task_type_counts": dict(sorted(task_counts.items())),
        "source_kind_counts": dict(sorted(source_counts.items())),
        "total_duration_seconds": round(total_duration, 3),
        "total_errors": total_errors,
        "total_gaps": total_gaps,
        "metric_totals": metric_totals,
        "records": records,
    }


def sum_metric(records: list[dict[str, Any]], key: str) -> int | float:
    total: int | float = 0
    for record in records:
        metrics = record.get("metrics")
        if not isinstance(metrics, dict):
            continue
        value = metrics.get(key)
        parsed_int = int_or_none(value)
        if parsed_int is not None:
            total += parsed_int
            continue
        parsed_float = float_or_none(value)
        if parsed_float is not None:
            total += parsed_float
    return total


def write_summary_json(summary: dict[str, Any]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_summary_markdown(summary: dict[str, Any]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Run Records Summary",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Repository: `{summary['repo_root']}`",
        f"- Records summarized: `{summary['record_count']}`",
        f"- Total duration seconds: `{summary['total_duration_seconds']}`",
        f"- Total errors: `{summary['total_errors']}`",
        f"- Total gaps: `{summary['total_gaps']}`",
        "",
        "## Counts",
        "",
        "| Group | Counts |",
        "| --- | --- |",
        f"| Status | `{json.dumps(summary['status_counts'], ensure_ascii=False)}` |",
        f"| Task type | `{json.dumps(summary['task_type_counts'], ensure_ascii=False)}` |",
        f"| Source kind | `{json.dumps(summary['source_kind_counts'], ensure_ascii=False)}` |",
        "",
        "## Metric Totals",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in summary["metric_totals"].items():
        lines.append(f"| `{key}` | {value} |")

    lines.extend(
        [
            "",
            "## Records",
            "",
            "| Run ID | Task | Status | Duration | Inputs | Outputs | Errors | Gaps |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for record in summary["records"]:
        lines.append(
            "| `{run_id}` | `{task}` | `{status}` | {duration} | {inputs} | {outputs} | {errors} | {gaps} |".format(
                run_id=record["run_id"],
                task=record["task_type"],
                status=record["status"],
                duration=record["duration_seconds"],
                inputs=len(record.get("input_paths", [])),
                outputs=len(record.get("output_paths", [])),
                errors=len(record.get("errors", [])),
                gaps=len(record.get("gaps", [])),
            )
        )

    lines.extend(["", "## Gaps And Errors", ""])
    any_detail = False
    for record in summary["records"]:
        if record.get("gaps") or record.get("errors"):
            any_detail = True
            lines.append(f"### `{record['run_id']}`")
            for gap in record.get("gaps", []):
                lines.append(f"- Gap: {gap}")
            for error in record.get("errors", []):
                lines.append(f"- Error: {error.get('message', error)}")
            lines.append("")
    if not any_detail:
        lines.append("No gaps or errors were detected in the scanned records.")

    SUMMARY_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    log_files = find_log_files()
    run_record_files = find_run_record_files()
    records = [parse_run_record(path) for path in run_record_files]
    records.extend(parse_jsonl_log(path) for path in log_files)

    scanned_sources = {
        "log_files": [rel_path(path) for path in log_files],
        "run_record_files": [rel_path(path) for path in run_record_files],
    }
    summary = aggregate(records, scanned_sources)
    write_summary_json(summary)
    write_summary_markdown(summary)

    print(
        json.dumps(
            {
                "records": summary["record_count"],
                "status_counts": summary["status_counts"],
                "total_errors": summary["total_errors"],
                "total_gaps": summary["total_gaps"],
                "summary_json": rel_path(SUMMARY_JSON),
                "summary_md": rel_path(SUMMARY_MD),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
