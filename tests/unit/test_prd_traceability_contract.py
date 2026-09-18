from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTENT_MODULE = ROOT / "build" / "prd_official_authoring" / "prd_content_v2.py"
TRACEABILITY = ROOT / "docs" / "PRD_IMPLEMENTATION_TRACEABILITY.md"

REQUIREMENT_ID = re.compile(
    r"\b(?:PR-P0|PR-P1|TECH|NFR|AC-(?:M2|M3|M4|M5|E2E))-\d{2}\b"
)
TRACEABILITY_ROW = re.compile(
    r"^\|\s*((?:PR-P0|PR-P1|TECH|NFR|AC-(?:M2|M3|M4|M5|E2E))-\d{2})\s*\|",
    re.MULTILINE,
)


def _load_prd_content() -> list[tuple[str, str]]:
    spec = importlib.util.spec_from_file_location("powerrag_prd_content", CONTENT_MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CONTENT


def test_every_numbered_prd_requirement_has_exactly_one_traceability_row() -> None:
    content = "\n".join(text for _, text in _load_prd_content())
    requirement_ids = set(REQUIREMENT_ID.findall(content))
    assert requirement_ids, "No numbered PRD requirements were discovered"

    traceability = TRACEABILITY.read_text(encoding="utf-8")
    rows = TRACEABILITY_ROW.findall(traceability)
    duplicated_rows = {item for item in rows if rows.count(item) > 1}

    assert not duplicated_rows, f"Duplicated traceability rows: {sorted(duplicated_rows)}"
    assert requirement_ids == set(rows), (
        f"Missing rows: {sorted(requirement_ids - set(rows))}; "
        f"unexpected rows: {sorted(set(rows) - requirement_ids)}"
    )


def test_completed_prd_has_no_progress_report_or_placeholder_language() -> None:
    content = "\n".join(text for _, text in _load_prd_content())
    forbidden = (
        "32 项通过",
        "当前主控制台未检出",
        "当前代码缺少",
        "待补充",
        "TBD",
        "TODO",
    )
    assert all(token not in content for token in forbidden)
