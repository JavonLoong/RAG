from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_judge_objection_matrix.py"


def load_objection_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_judge_objection_matrix", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_judge_objection_matrix_builds_evidence_bound_responses(tmp_path: Path) -> None:
    module = load_objection_module()
    module.REPO_ROOT = tmp_path
    module.OUTPUT_DIR = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    module.OUTPUT_JSON = module.OUTPUT_DIR / "judge_objection_response_matrix.json"
    module.OUTPUT_MD = module.OUTPUT_DIR / "judge_objection_response_matrix.md"

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_judge_objection_response_matrix"
    assert payload["status"] == "ready_for_judge_objection_drill_no_external_claims"
    assert payload["completion_claim_allowed"] is False
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["response_rules"]["max_answer_seconds"] == 30
    assert payload["response_rules"]["must_cite_evidence"] is True
    assert payload["response_rules"]["must_state_boundary_when_external_validation_is_missing"] is True

    objections = payload["objections"]
    assert len(objections) >= 10
    expected_ids = {
        "OJ-01-normal-rag",
        "OJ-02-graphrag-baseline",
        "OJ-03-engineer-replacement",
        "OJ-04-production-data",
        "OJ-05-live-demo-failure",
        "OJ-06-cherry-picked-evaluation",
        "OJ-07-expert-validation",
        "OJ-08-special-prize-claim",
        "OJ-09-ip-and-compliance",
        "OJ-10-project-closure",
    }
    assert expected_ids <= {item["objection_id"] for item in objections}

    for item in objections:
        assert item["severity"] in {"P0", "P1"}
        assert item["answer_time_limit_seconds"] <= 30
        assert item["one_sentence_answer"]
        assert item["evidence_files"]
        assert item["fallback_if_challenged"]
        assert item["forbidden_overclaim"]
        assert item["rubric_dimensions"]
        assert all(str(path).startswith(("docs/", "evaluation/")) for path in item["evidence_files"])

    serialized = json.dumps(payload, ensure_ascii=False)
    assert "no award guarantee" in serialized
    assert "real expert feedback" in serialized
    assert "real timed rehearsal" in serialized
    assert "readiness gate is not an award guarantee" in serialized

    output = json.loads(module.OUTPUT_JSON.read_text(encoding="utf-8"))
    assert output == payload
    markdown = module.OUTPUT_MD.read_text(encoding="utf-8")
    for term in [
        "Judge Objection Response Matrix",
        "OJ-01-normal-rag",
        "OJ-08-special-prize-claim",
        "30 seconds",
        "no award guarantee",
        "real expert feedback",
        "real timed rehearsal",
    ]:
        assert term in markdown
