from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_no_answer_boundary_evaluation.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_no_answer_boundary_evaluation", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_no_answer_boundary_evaluation_rejects_empty_context_specific_claims(tmp_path, monkeypatch) -> None:
    module = load_module()
    output_json = tmp_path / "no_answer_boundary_evaluation.json"
    output_md = tmp_path / "no_answer_boundary_evaluation.md"
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "OUTPUT_JSON", output_json)
    monkeypatch.setattr(module, "OUTPUT_MD", output_md)

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_no_answer_boundary_evaluation"
    assert payload["status"] == "no_answer_boundary_guard_verified_no_live_llm_claim"
    assert payload["completion_claim_allowed"] is False
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["external_validation_claimed"] is False
    assert payload["live_retriever_claimed"] is False
    assert payload["online_llm_behavior_claimed"] is False
    assert payload["deterministic_guard_only"] is True
    assert payload["case_count"] == 4
    assert payload["all_cases_passed"] is True
    assert payload["failures"] == []

    results = {case["case_id"]: case for case in payload["cases"]}
    unsupported = results["empty_context_specific_maintenance_claim"]
    assert unsupported["expected_safe"] is False
    assert unsupported["actual_safe"] is False
    assert unsupported["score"] == 0.0
    assert any("No retrieved evidence" in claim for claim in unsupported["hallucinated_claims"])

    chinese_refusal = results["empty_context_chinese_no_answer"]
    assert chinese_refusal["expected_safe"] is True
    assert chinese_refusal["actual_safe"] is True
    assert "证据不足" in chinese_refusal["answer"]

    assert "does not claim live retriever coverage" in payload["boundary"]
    assert "does not claim online LLM behavior" in payload["boundary"]
    assert payload["output_files"] == [
        "docs/challenge_cup/reproducibility/no_answer_boundary_evaluation.md",
        "docs/challenge_cup/reproducibility/no_answer_boundary_evaluation.json",
    ]

    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    markdown = output_md.read_text(encoding="utf-8")
    assert "No-Answer Boundary Evaluation" in markdown
    assert "no_answer_boundary_guard_verified_no_live_llm_claim" in markdown
    assert "No retrieved evidence" in markdown
    assert "证据不足" in markdown
