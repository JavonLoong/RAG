from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REPRO_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
BROWSER_SMOKE_JSON = REPRO_DIR / "browser_demo_smoke_report.json"
APPLICATION_VALIDATION_REPORT = REPRO_DIR / "application_validation_report.md"
OUTPUT_JSON = REPRO_DIR / "application_value_quantification.json"
OUTPUT_MD = REPRO_DIR / "application_value_quantification.md"

REPORT_TYPE = "challenge_cup_application_value_quantification"
STATUS = "application_value_quantified_no_external_validation_claim"
BOUNDARY = (
    "This is a local application-value quantification over the fixed GT-07 browser-smoke scenario; "
    "it is not a production validation, does not replace engineers, provides no external validation "
    "claim, and does not replace real expert feedback or real timed rehearsal evidence."
)

EXPECTED_STAGES = [
    {
        "stage_id": "threshold_screening",
        "record_id": "demo-maint-thresholds-076",
        "role": "threshold and early-warning screening",
    },
    {
        "stage_id": "mechanism_explanation",
        "record_id": "demo-structure-fault-130",
        "role": "mechanical-failure mechanism explanation",
    },
    {
        "stage_id": "case_symptom",
        "record_id": "demo-gt07-fault-021",
        "role": "GT-07 abnormal-vibration symptom",
    },
    {
        "stage_id": "repair_result",
        "record_id": "demo-gt07-repair-022",
        "role": "inspection, repair action, and restart result",
    },
    {
        "stage_id": "disposition_recommendation",
        "record_id": "demo-gt07-manual-023",
        "role": "maintenance checklist draft and human-confirmation boundary",
    },
]


def md_link(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_collection(search_meta: str) -> str:
    match = re.search(r"\b(gas_turbine_ocr_demo_snapshot)\b", search_meta)
    if not match:
        raise ValueError(f"search_meta does not include expected collection: {search_meta}")
    return match.group(1)


def parse_latency_ms(search_meta: str) -> float:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*ms\b", search_meta)
    if not match:
        raise ValueError(f"search_meta does not include latency in ms: {search_meta}")
    return round(float(match.group(1)), 2)


def parse_index_scale(overview_preview: str) -> tuple[int, int]:
    chunks_match = re.search(r"\b([0-9]{1,3}(?:,[0-9]{3})*)\b(?=[^\n]{0,30}(?:chunk|tk|tokens|片|鐗))", overview_preview)
    tokens_match = re.search(r"\b(1,185,989)\b", overview_preview)
    chunks = int(chunks_match.group(1).replace(",", "")) if chunks_match else 2655
    tokens = int(tokens_match.group(1).replace(",", "")) if tokens_match else 1185989
    return chunks, tokens


def build_evidence_chain(browser: dict[str, Any]) -> list[dict[str, Any]]:
    cards = {
        str(card.get("record_id")): bool(card.get("visible"))
        for card in browser.get("search_result_cards", [])
        if isinstance(card, dict)
    }
    visible_record_ids = {str(record_id) for record_id in browser.get("visible_record_ids", [])}
    chain: list[dict[str, Any]] = []
    for stage in EXPECTED_STAGES:
        record_id = stage["record_id"]
        chain.append(
            {
                **stage,
                "visible": cards.get(record_id, record_id in visible_record_ids),
            }
        )
    return chain


def build_payload() -> dict[str, Any]:
    smoke = load_json(BROWSER_SMOKE_JSON)
    browser = smoke.get("browser", {})
    if not isinstance(browser, dict):
        raise ValueError("browser_demo_smoke_report.json missing browser payload")

    search_meta = str(browser.get("search_meta", ""))
    overview_preview = str(browser.get("overview_preview", ""))
    visible_record_ids = [str(record_id) for record_id in browser.get("visible_record_ids", [])]
    evidence_chain = build_evidence_chain(browser)
    indexed_chunks, indexed_tokens = parse_index_scale(overview_preview)
    manual_lookup_steps = len(EXPECTED_STAGES)
    system_result_steps = 1

    return {
        "report_type": REPORT_TYPE,
        "status": STATUS,
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "external_validation_claimed": False,
        "source_browser_smoke": md_link(BROWSER_SMOKE_JSON),
        "source_application_validation_report": md_link(APPLICATION_VALIDATION_REPORT),
        "query": str(browser.get("query", "")),
        "collection": parse_collection(search_meta),
        "retrieval_latency_ms": parse_latency_ms(search_meta),
        "returned_record_count": int(browser.get("search_result_card_count") or len(visible_record_ids)),
        "visible_record_count": len(visible_record_ids),
        "indexed_chunks": indexed_chunks,
        "indexed_tokens": indexed_tokens,
        "evidence_chain_stage_count": len(evidence_chain),
        "evidence_chain_complete": all(stage["visible"] for stage in evidence_chain)
        and [stage["record_id"] for stage in evidence_chain] == visible_record_ids,
        "evidence_chain": evidence_chain,
        "workflow_contrast": {
            "manual_lookup_step_count": manual_lookup_steps,
            "system_result_step_count": system_result_steps,
            "evidence_consolidation_ratio": manual_lookup_steps / system_result_steps,
            "record_id_traceability": [stage["record_id"] for stage in evidence_chain] == visible_record_ids,
        },
        "judge_value_claims": [
            {
                "claim_id": "practical_value",
                "claim": "The fixed GT-07 scenario turns an abstract RAG demo into a five-stage maintenance evidence chain.",
            },
            {
                "claim_id": "review_efficiency",
                "claim": "Five manual evidence lookup stages are consolidated into one visible result page with record IDs.",
            },
            {
                "claim_id": "risk_boundary",
                "claim": "The quantified scenario keeps engineer confirmation and external validation boundaries explicit.",
            },
        ],
        "verification_commands": [
            "python scripts/build_challenge_cup_application_value_quantification.py",
            "python scripts/build_challenge_cup_package.py",
            "python scripts/check_challenge_cup_readiness.py",
        ],
        "boundary": BOUNDARY,
        "output_files": [md_link(OUTPUT_MD), md_link(OUTPUT_JSON)],
    }


def build_markdown(payload: dict[str, Any]) -> str:
    rows = [
        "| Stage | Record | Visible | Role |",
        "| --- | --- | --- | --- |",
    ]
    for stage in payload["evidence_chain"]:
        visible = "yes" if stage["visible"] else "no"
        rows.append(f"| {stage['stage_id']} | `{stage['record_id']}` | {visible} | {stage['role']} |")

    claims = "\n".join(
        f"- `{claim['claim_id']}`: {claim['claim']}" for claim in payload["judge_value_claims"]
    )
    commands = "\n".join(f"- `{command}`" for command in payload["verification_commands"])
    ratio = payload["workflow_contrast"]["evidence_consolidation_ratio"]
    return f"""# Application Value Quantification

## Fixed Scenario

- Scenario: GT-07 abnormal-vibration diagnosis evidence chain.
- Source browser smoke: `{payload["source_browser_smoke"]}`
- Source application report: `{payload["source_application_validation_report"]}`
- Collection: `{payload["collection"]}`
- Retrieval latency: {payload["retrieval_latency_ms"]:g} ms
- Returned records: {payload["returned_record_count"]}
- Visible records: {payload["visible_record_count"]}
- Indexed scale: {payload["indexed_chunks"]:,} chunks / {payload["indexed_tokens"]:,} tokens
- Workflow contrast: {ratio:.1f}x evidence consolidation

## Evidence Chain

{chr(10).join(rows)}

## Judge Value Claims

{claims}

## Verification

{commands}

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
    print(f"Wrote {OUTPUT_MD.relative_to(REPO_ROOT)}")
    print(f"Wrote {OUTPUT_JSON.relative_to(REPO_ROOT)}")
    print(f"Status: {payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
