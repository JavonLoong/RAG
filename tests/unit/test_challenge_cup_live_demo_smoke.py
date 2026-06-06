from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
REPORT_JSON = REPORT_DIR / "live_demo_smoke_report.json"
REPORT_MD = REPORT_DIR / "live_demo_smoke_report.md"


def test_live_demo_smoke_writes_report_and_checks_core_routes(tmp_path) -> None:
    committed_json_before = REPORT_JSON.read_text(encoding="utf-8")
    committed_md_before = REPORT_MD.read_text(encoding="utf-8")
    report_dir = tmp_path / "live-smoke"

    result = subprocess.run(
        [sys.executable, "scripts/run_challenge_cup_live_demo_smoke.py", "--report-dir", str(report_dir)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert "live_demo_smoke_report.md" in result.stdout
    payload = json.loads((report_dir / "live_demo_smoke_report.json").read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["passed"] == len(payload["checks"])
    check_names = {check["name"] for check in payload["checks"]}
    assert {
        "health endpoint",
        "frontend root page",
        "trusted cors origin",
        "search top_k guard",
        "graphrag path guard",
        "live retrieval ingest",
        "live retrieval stats",
        "live retrieval search",
    } <= check_names
    retrieval = payload["retrieval"]
    assert retrieval["collection"] == "challenge_cup_live_retrieval_smoke"
    assert retrieval["backend"] == "hashing"
    assert retrieval["not_public_demo"] is True
    assert retrieval["stats"]["chunk_count"] == 3
    assert retrieval["stats"]["record_count"] == 3
    assert retrieval["stats"]["source_file_count"] == 1
    assert retrieval["result_count"] == 3
    assert len(retrieval["raw_record_ids"]) == 3
    assert {
        "live-gt07-threshold",
        "live-gt07-fault",
        "live-gt07-repair",
    } <= set(retrieval["record_ids"])
    assert all("gt07-live-smoke.json" in item for item in retrieval["raw_record_ids"])
    assert "missing frontend fallback" not in check_names

    markdown = (report_dir / "live_demo_smoke_report.md").read_text(encoding="utf-8")
    assert "Live Demo Smoke Report" in markdown
    assert "Live Retrieval Evidence" in markdown
    assert "not public-demo" in markdown
    assert "frontend root page" in markdown
    assert "GraphRAG" in markdown
    assert REPORT_JSON.read_text(encoding="utf-8") == committed_json_before
    assert REPORT_MD.read_text(encoding="utf-8") == committed_md_before
