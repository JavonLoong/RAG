from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_failure_remediation_before_after.py"


def load_remediation_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_failure_remediation_before_after", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_failure_remediation_before_after_builds_ablation_evidence(tmp_path: Path) -> None:
    module = load_remediation_module()
    module.REPO_ROOT = REPO_ROOT
    module.OUTPUT_JSON = tmp_path / "challenge_cup_failure_remediation_before_after.json"
    module.OUTPUT_MD = tmp_path / "challenge_cup_failure_remediation_before_after.md"

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_failure_remediation_before_after"
    assert payload["status"] == "remediation_card_ablation_ready_no_live_retriever_claim"
    assert payload["completion_claim_allowed"] is False
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["live_retriever_upgrade_claimed"] is False
    assert payload["source_day4_failure_analysis"].endswith("day4_failure_analysis_20260605_210642.json")
    assert payload["analyzed_question_count"] == 40
    assert set(payload["category_closure"]) == {
        "corpus_gap_or_query_gap",
        "evaluation_concept_gap",
        "exact_number_fact",
        "hybrid_dilution",
        "partial_ranking_gap",
        "structured_fact_routing",
        "terminology_alias_gap",
    }
    assert all(item["status"] in {"closed_by_remediation_card", "bounded_by_keyword_guardrail"} for item in payload["category_closure"].values())

    before = payload["before"]
    after = payload["after"]
    assert after["avg_effective_coverage"] > before["avg_hybrid_coverage"]
    assert after["zero_coverage_question_count"] < before["zero_coverage_question_count"]
    assert after["closed_or_bounded_case_count"] == payload["analyzed_question_count"]
    assert after["critical_case_status"] == {
        "se013": "closed_or_bounded",
        "se024": "closed_or_bounded",
        "se027": "closed_or_bounded",
        "se028": "closed_or_bounded",
    }
    assert payload["graph_fixed_subset"]["supported_count"] == 10
    assert payload["graph_fixed_subset"]["minimum_required_average_coverage"] == 0.866667
    assert payload["graph_fixed_subset"]["observed_average_coverage"] >= 0.866667
    assert payload["graph_fixed_subset"]["observed_min_coverage"] >= 0.5

    card_ids = {item["card_id"] for item in payload["remediation_cards"]}
    assert {
        "evaluation_metric_glossary",
        "kg_poc_fact_card",
        "goldwind_structured_fact_card",
        "reranker_alias_card",
        "keyword_guardrail_policy",
    } <= card_ids

    serialized = json.dumps(payload, ensure_ascii=False)
    assert "remediation-card ablation" in serialized
    assert "not a live retriever upgrade" in serialized
    assert "no award guarantee" in serialized
    assert "real expert feedback" in serialized
    assert "real timed rehearsal" in serialized

    assert json.loads(module.OUTPUT_JSON.read_text(encoding="utf-8")) == payload
    markdown = module.OUTPUT_MD.read_text(encoding="utf-8")
    for term in [
        "Failure Remediation Before/After",
        "remediation-card ablation",
        "se013",
        "se024",
        "se027",
        "se028",
        "not a live retriever upgrade",
        "real expert feedback",
        "real timed rehearsal",
    ]:
        assert term in markdown
