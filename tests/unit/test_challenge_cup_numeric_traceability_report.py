from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_numeric_traceability_report.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_numeric_traceability_report", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_sources(root: Path, validation_latency: str = "41.80") -> None:
    repro = root / "docs" / "challenge_cup" / "reproducibility"
    repro.mkdir(parents=True)
    browser_payload = {
        "status": "pass",
        "browser": {
            "search_meta": "集合 gas_turbine_ocr_demo_snapshot · 延迟 41.80 ms · 结果 5 · 后端 public-demo",
            "overview_preview": "2,655 个向量片段 · 约 1,185,989 tokens",
            "visible_record_ids": [
                "demo-maint-thresholds-076",
                "demo-structure-fault-130",
                "demo-gt07-fault-021",
                "demo-gt07-repair-022",
                "demo-gt07-manual-023",
            ],
            "search_result_card_count": 5,
        },
    }
    value_payload = {
        "retrieval_latency_ms": 41.8,
        "returned_record_count": 5,
        "visible_record_count": 5,
        "indexed_chunks": 2655,
        "indexed_tokens": 1185989,
        "evidence_chain": [{"record_id": record_id} for record_id in browser_payload["browser"]["visible_record_ids"]],
    }
    (repro / "browser_demo_smoke_report.json").write_text(
        json.dumps(browser_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (repro / "application_value_quantification.json").write_text(
        json.dumps(value_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (repro / "application_validation_report.md").write_text(
        f"检索结果：集合 gas_turbine_ocr_demo_snapshot · 延迟 {validation_latency} ms · 结果 5 · 后端 public-demo。\n"
        f"系统在演示快照中从 2,655 个向量片段、约 1,185,989 tokens 中返回 5 条证据结果，"
        f"检索延迟为 {validation_latency} ms。\n",
        encoding="utf-8",
    )


def test_numeric_traceability_report_rejects_latency_drift(tmp_path, monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "OUTPUT_JSON", tmp_path / "numeric_traceability_report.json")
    monkeypatch.setattr(module, "OUTPUT_MD", tmp_path / "numeric_traceability_report.md")
    write_sources(tmp_path, validation_latency="42.10")

    payload = module.write_outputs()

    assert payload["status"] == "numeric_traceability_failed"
    assert payload["latency_ms"]["browser_smoke"] == 41.8
    assert payload["latency_ms"]["application_value"] == 41.8
    assert payload["latency_ms"]["application_validation_report"] == [42.1, 42.1]
    assert any("42.10 ms" in item for item in payload["failures"])


def test_numeric_traceability_report_accepts_consistent_gt07_numbers(tmp_path, monkeypatch) -> None:
    module = load_module()
    output_json = tmp_path / "numeric_traceability_report.json"
    output_md = tmp_path / "numeric_traceability_report.md"
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "OUTPUT_JSON", output_json)
    monkeypatch.setattr(module, "OUTPUT_MD", output_md)
    write_sources(tmp_path)

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_numeric_traceability_report"
    assert payload["status"] == "numeric_traceability_consistent_no_external_claim"
    assert payload["completion_claim_allowed"] is False
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["external_validation_claimed"] is False
    assert payload["latency_ms"] == {
        "browser_smoke": 41.8,
        "application_value": 41.8,
        "application_validation_report": [41.8, 41.8],
    }
    assert payload["result_counts"]["browser_smoke"] == 5
    assert payload["result_counts"]["application_value"] == 5
    assert payload["index_scale"]["chunks"] == 2655
    assert payload["index_scale"]["tokens"] == 1185989
    assert payload["record_ids"] == [
        "demo-maint-thresholds-076",
        "demo-structure-fault-130",
        "demo-gt07-fault-021",
        "demo-gt07-repair-022",
        "demo-gt07-manual-023",
    ]
    assert payload["failures"] == []
    assert "does not claim production validation" in payload["boundary"]
    assert payload["output_files"] == [
        "docs/challenge_cup/reproducibility/numeric_traceability_report.md",
        "docs/challenge_cup/reproducibility/numeric_traceability_report.json",
    ]

    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    markdown = output_md.read_text(encoding="utf-8")
    assert "Numeric Traceability Report" in markdown
    assert "41.80 ms" in markdown
    assert "2,655 chunks" in markdown
    assert "1,185,989 tokens" in markdown
    assert "numeric_traceability_consistent_no_external_claim" in markdown
