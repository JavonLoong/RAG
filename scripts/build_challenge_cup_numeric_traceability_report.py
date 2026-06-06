from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_MD_RELATIVE = "docs/challenge_cup/reproducibility/numeric_traceability_report.md"
OUTPUT_JSON_RELATIVE = "docs/challenge_cup/reproducibility/numeric_traceability_report.json"
OUTPUT_MD = REPO_ROOT / OUTPUT_MD_RELATIVE
OUTPUT_JSON = REPO_ROOT / OUTPUT_JSON_RELATIVE

REPORT_TYPE = "challenge_cup_numeric_traceability_report"
OK_STATUS = "numeric_traceability_consistent_no_external_claim"
FAIL_STATUS = "numeric_traceability_failed"
BOUNDARY = (
    "This is a local numeric traceability report for the fixed GT-07 browser-smoke scenario; it does not "
    "claim production validation, does not claim external validation, does not replace engineers, and does "
    "not replace real expert feedback or real timed rehearsal evidence."
)


def repro_dir() -> Path:
    return REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"


def browser_smoke_json() -> Path:
    return repro_dir() / "browser_demo_smoke_report.json"


def application_value_json() -> Path:
    return repro_dir() / "application_value_quantification.json"


def application_validation_report() -> Path:
    return repro_dir() / "application_validation_report.md"


def repo_link(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{repo_link(path)} must contain a JSON object")
    return payload


def parse_latency_label(text: str) -> tuple[float, str]:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*ms\b", text)
    if match is None:
        raise ValueError(f"could not parse latency in ms from: {text}")
    raw = match.group(1)
    return round(float(raw), 2), f"{raw} ms"


def parse_all_latency_labels(text: str) -> list[tuple[float, str]]:
    values: list[tuple[float, str]] = []
    for match in re.finditer(r"([0-9]+(?:\.[0-9]+)?)\s*ms\b", text):
        raw = match.group(1)
        values.append((round(float(raw), 2), f"{raw} ms"))
    return values


def parse_result_count(search_meta: str, fallback: int) -> int:
    match = re.search(r"(?:结果|result[s]?)\s*[:：]?\s*(\d+)", search_meta, flags=re.IGNORECASE)
    if match is not None:
        return int(match.group(1))
    return fallback


def parse_index_scale(overview_preview: str) -> tuple[int | None, int | None]:
    numbers = re.findall(r"\b[0-9]{1,3}(?:,[0-9]{3})+\b", overview_preview)
    chunks = int(numbers[0].replace(",", "")) if numbers else None
    tokens = int(numbers[1].replace(",", "")) if len(numbers) > 1 else None
    return chunks, tokens


def normalize_float(value: Any) -> float:
    return round(float(value), 2)


def collect_record_ids(value_payload: dict[str, Any]) -> list[str]:
    evidence_chain = value_payload.get("evidence_chain", [])
    if not isinstance(evidence_chain, list):
        return []
    record_ids: list[str] = []
    for item in evidence_chain:
        if isinstance(item, dict) and item.get("record_id") is not None:
            record_ids.append(str(item["record_id"]))
    return record_ids


def build_payload() -> dict[str, Any]:
    smoke = load_json(browser_smoke_json())
    value = load_json(application_value_json())
    validation_text = application_validation_report().read_text(encoding="utf-8", errors="replace")

    browser = smoke.get("browser", {})
    if not isinstance(browser, dict):
        raise ValueError("browser_demo_smoke_report.json missing browser object")

    search_meta = str(browser.get("search_meta", ""))
    overview_preview = str(browser.get("overview_preview", ""))
    browser_latency, browser_latency_label = parse_latency_label(search_meta)
    browser_record_ids = [str(record_id) for record_id in browser.get("visible_record_ids", [])]
    browser_result_count = parse_result_count(
        search_meta,
        int(browser.get("search_result_card_count") or len(browser_record_ids)),
    )
    overview_chunks, overview_tokens = parse_index_scale(overview_preview)

    app_value_latency = normalize_float(value.get("retrieval_latency_ms"))
    app_value_count = int(value.get("returned_record_count") or value.get("visible_record_count") or 0)
    app_value_record_ids = collect_record_ids(value)
    chunks = int(value.get("indexed_chunks") or overview_chunks or 0)
    tokens = int(value.get("indexed_tokens") or overview_tokens or 0)
    validation_latency_pairs = parse_all_latency_labels(validation_text)
    validation_latencies = [latency for latency, _label in validation_latency_pairs]

    failures: list[str] = []
    if app_value_latency != browser_latency:
        failures.append(
            "application_value latency "
            f"{app_value_latency:.2f} ms does not match browser_smoke {browser_latency_label}"
        )
    for latency, label in validation_latency_pairs:
        if latency != browser_latency:
            failures.append(
                "application_validation_report latency "
                f"{label} does not match browser_smoke {browser_latency_label}"
            )
    if not validation_latency_pairs:
        failures.append("application_validation_report does not contain a latency in ms")
    if app_value_count != browser_result_count:
        failures.append(
            "application_value returned_record_count "
            f"{app_value_count} does not match browser_smoke result count {browser_result_count}"
        )
    if int(value.get("visible_record_count") or 0) != len(browser_record_ids):
        failures.append(
            "application_value visible_record_count "
            f"{value.get('visible_record_count')} does not match browser visible record count {len(browser_record_ids)}"
        )
    if app_value_record_ids != browser_record_ids:
        failures.append("application_value evidence_chain record_ids do not match browser visible_record_ids")
    if overview_chunks is not None and overview_chunks != chunks:
        failures.append(f"browser overview chunks {overview_chunks} do not match application_value {chunks}")
    if overview_tokens is not None and overview_tokens != tokens:
        failures.append(f"browser overview tokens {overview_tokens} do not match application_value {tokens}")

    return {
        "report_type": REPORT_TYPE,
        "status": OK_STATUS if not failures else FAIL_STATUS,
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "external_validation_claimed": False,
        "sources": {
            "browser_smoke": repo_link(browser_smoke_json()),
            "application_value": repo_link(application_value_json()),
            "application_validation_report": repo_link(application_validation_report()),
        },
        "latency_ms": {
            "browser_smoke": browser_latency,
            "application_value": app_value_latency,
            "application_validation_report": validation_latencies,
        },
        "result_counts": {
            "browser_smoke": browser_result_count,
            "application_value": app_value_count,
            "browser_visible_record_ids": len(browser_record_ids),
            "application_value_visible_record_count": int(value.get("visible_record_count") or 0),
        },
        "index_scale": {
            "chunks": chunks,
            "tokens": tokens,
        },
        "record_ids": browser_record_ids,
        "application_value_record_ids": app_value_record_ids,
        "failures": failures,
        "boundary": BOUNDARY,
        "output_files": [OUTPUT_MD_RELATIVE, OUTPUT_JSON_RELATIVE],
    }


def build_markdown(payload: dict[str, Any]) -> str:
    validation_labels = ", ".join(f"{item:.2f} ms" for item in payload["latency_ms"]["application_validation_report"])
    failure_lines = "\n".join(f"- {failure}" for failure in payload["failures"]) or "- none"
    record_lines = "\n".join(f"- `{record_id}`" for record_id in payload["record_ids"])
    return f"""# Numeric Traceability Report

- report_type: `{payload["report_type"]}`
- status: `{payload["status"]}`
- completion_claim_allowed: `{payload["completion_claim_allowed"]}`
- does_not_satisfy_goal_completion: `{payload["does_not_satisfy_goal_completion"]}`
- external_validation_claimed: `{payload["external_validation_claimed"]}`

## Sources

- browser smoke: `{payload["sources"]["browser_smoke"]}`
- application value: `{payload["sources"]["application_value"]}`
- application validation report: `{payload["sources"]["application_validation_report"]}`

## GT-07 Numeric Trace

- Browser smoke latency: {payload["latency_ms"]["browser_smoke"]:.2f} ms
- Application value latency: {payload["latency_ms"]["application_value"]:.2f} ms
- Application validation latency values: {validation_labels}
- Returned result count: {payload["result_counts"]["browser_smoke"]}
- Application value result count: {payload["result_counts"]["application_value"]}
- Indexed scale: {payload["index_scale"]["chunks"]:,} chunks / {payload["index_scale"]["tokens"]:,} tokens

## Record IDs

{record_lines}

## Failures

{failure_lines}

## Boundary

{payload["boundary"]}
"""


def write_outputs(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or build_payload()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(build_markdown(payload).rstrip() + "\n", encoding="utf-8")
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"Wrote {repo_link(OUTPUT_MD)}")
    print(f"Wrote {repo_link(OUTPUT_JSON)}")
    print(f"Status: {payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
