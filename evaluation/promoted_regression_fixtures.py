"""Seed promoted regression fixtures that exercise non-empty GraphRAG gates."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .harness import RAGEvaluationCase
from .smoke import SMOKE_COLLECTION

REPO_ROOT = Path(__file__).resolve().parents[1]
CONSOLE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
DEFAULT_TRIAGE_REGRESSION_DATASET = (
    REPO_ROOT / "outputs" / "smoke_chroma" / "evaluation" / "graphrag_triage_regression.jsonl"
)

POWER_EQUIPMENT_TRIAGE_FIXTURE_SOURCE = "power_equipment_graphrag_quality_gold.md"
POWER_EQUIPMENT_TRIAGE_FIXTURE_TEXT = """# Power equipment GraphRAG quality gold fixture

This promoted regression fixture verifies that broad GraphRAG answers keep
traceable source evidence instead of passing through an empty graph summary.

## Inspection note GT-2-2026-06-18

Equipment: GT-2 gas turbine
Observation: vibration growth was recorded on bearing B2 during high-load operation.
Evidence id: gt2-vibration-001
Cause: borescope inspection found early bearing wear and lubricant contamination.
Recommended action: reduce load, replace the bearing at the next maintenance window,
and repeat vibration monitoring after the restart.

## Inspection note GT-3-2026-06-19

Equipment: GT-3 gas turbine
Observation: exhaust temperature spread stayed inside the normal control range.
Evidence id: gt3-normal-001
Cause: no bearing wear evidence was found.
Recommended action: continue routine monitoring.

Expected result:
- GT-2 is the relevant equipment.
- The answer must cite vibration growth, bearing B2, early bearing wear,
  lubricant contamination, and the recommended load reduction / bearing replacement.
- GT-3 must not be treated as a matching fault case.
"""

POWER_EQUIPMENT_TRIAGE_CASE = RAGEvaluationCase(
    id="power_equipment_graphrag_quality_gold_001",
    question=(
        "Which maintenance evidence links GT-2 vibration growth to bearing wear, "
        "and what action is recommended?"
    ),
    reference_answer=(
        "GT-2 vibration growth on bearing B2 is linked to early bearing wear and "
        "lubricant contamination; the recommended action is to reduce load, replace "
        "the bearing at the next maintenance window, and repeat vibration monitoring."
    ),
    expected_evidence_keywords=[
        "GT-2",
        "vibration growth",
        "bearing B2",
        "early bearing wear",
        "lubricant contamination",
        "reduce load",
        "replace the bearing",
    ],
    task_type="graphrag_triage",
    source_scope="power_equipment_graphrag_quality_gold",
    grading_notes=(
        "Promoted fixture for broad GraphRAG quality. The answer must include "
        "non-empty source evidence and avoid treating unrelated normal equipment as a fault case."
    ),
    expected_modes=["global", "comprehensive"],
)


def seed_promoted_graphrag_regression_fixture(
    *,
    persist_dir: str | Path,
    dataset_path: str | Path = DEFAULT_TRIAGE_REGRESSION_DATASET,
    collection_name: str = SMOKE_COLLECTION,
    backend: str = "hashing",
) -> dict[str, Any]:
    """Ingest the promoted fixture and upsert its regression case."""
    persist_path = Path(persist_dir)
    dataset = Path(dataset_path)
    _load_console_pipeline().ingest_source_payloads(
        payloads=[(POWER_EQUIPMENT_TRIAGE_FIXTURE_SOURCE, POWER_EQUIPMENT_TRIAGE_FIXTURE_TEXT.encode("utf-8"))],
        persist_dir=persist_path,
        collection_name=collection_name,
        chunk_size=2400,
        overlap=120,
        backend=backend,
    )
    cases = _load_existing_cases(dataset)
    case_record = POWER_EQUIPMENT_TRIAGE_CASE.to_dataset_record()
    cases = [case for case in cases if str(case.get("id")) != POWER_EQUIPMENT_TRIAGE_CASE.id]
    cases.append(case_record)
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(
        "".join(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n" for case in cases),
        encoding="utf-8",
    )
    return {
        "persist_dir": str(persist_path),
        "collection_name": collection_name,
        "dataset_path": str(dataset),
        "case_count": len(cases),
        "seeded_case_id": POWER_EQUIPMENT_TRIAGE_CASE.id,
        "source_file": POWER_EQUIPMENT_TRIAGE_FIXTURE_SOURCE,
    }


def _load_existing_cases(dataset_path: Path) -> list[dict[str, Any]]:
    if not dataset_path.exists():
        return []
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(dataset_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise ValueError(f"{dataset_path}:{line_number} must contain a JSON object")
        cases.append(payload)
    return cases


def _load_console_pipeline() -> Any:
    if str(CONSOLE_SRC) not in sys.path:
        sys.path.insert(0, str(CONSOLE_SRC))
    from chroma_rag_poc import pipeline

    return pipeline
