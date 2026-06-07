from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_hard_evidence_source_custody.py"


def load_source_custody_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_hard_evidence_source_custody", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_builds_hard_evidence_source_custody_without_claiming_completion(tmp_path: Path) -> None:
    module = load_source_custody_module()
    module.configure_paths(tmp_path)

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_hard_evidence_source_custody"
    assert payload["status"] == "ready_for_real_source_custody_no_external_evidence_claim"
    assert payload["completion_claim_allowed"] is False
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["required_before_goal_completion"] == ["expert_feedback", "timed_rehearsal"]
    assert "no award guarantee" in payload["boundary"]
    assert "does not claim expert approval" in payload["boundary"]
    assert "does not claim a timed rehearsal was completed" in payload["boundary"]

    categories = {item["category_id"]: item for item in payload["source_custody_categories"]}
    assert set(categories) == {"expert_feedback", "timed_rehearsal"}
    expected_checkpoints = [
        "source_received",
        "source_sha256_preflighted",
        "record_command_archives_source",
        "ledger_rebuilt",
        "package_rebuilt",
        "submission_verifier_rerun",
        "readiness_gate_rerun",
        "goal_gate_rerun",
    ]
    for category_id, category in categories.items():
        assert [item["checkpoint_id"] for item in category["custody_checkpoints"]] == expected_checkpoints
        assert category["counts_as_hard_evidence_after_record_only"] is True
        assert category["does_not_satisfy_goal_completion_before_record"] is True
        restrictions = "\n".join(category["source_restrictions"])
        assert "original evidence attachment" in restrictions
        assert "non-empty" in restrictions
        assert "must not be a JSON metadata file" in restrictions
        assert "hard_evidence/**" in restrictions
        assert "duplicate source_sha256" in restrictions
        assert "--force" in restrictions
        assert "--force-reason" in restrictions
        assert "override_log.jsonl" in restrictions
        commands = "\n".join(category["operator_commands"])
        assert "preflight_challenge_cup_hard_evidence.py" in commands
        assert "build_challenge_cup_hard_evidence_ledger.py" in commands
        assert "build_challenge_cup_package.py" in commands
        assert "check_challenge_cup_readiness.py" in commands
        assert "verify_submission_package.py --root ." in commands
        assert "check_challenge_cup_goal_completion.py" in commands
        if category_id == "expert_feedback":
            assert "preflight_challenge_cup_hard_evidence.py expert_feedback" in commands
            assert "record_challenge_cup_hard_evidence.py expert_feedback" in commands
            assert "--confirm-real-feedback" in commands
        if category_id == "timed_rehearsal":
            assert "run_challenge_cup_timed_rehearsal.py" in commands
            assert "preflight_challenge_cup_hard_evidence.py timed_rehearsal" in commands
            assert "--confirm-real-rehearsal" in commands

    guardrails = "\n".join(payload["integrity_guardrails"])
    for term in (
        "do not fabricate evidence",
        "do not claim expert approval before source archival",
        "do not claim a timed rehearsal before source archival",
        "no award guarantee",
        "source_sha256",
        "override_log.jsonl",
    ):
        assert term in guardrails

    output_json = (
        tmp_path
        / "docs"
        / "challenge_cup"
        / "reproducibility"
        / "hard_evidence_source_custody.json"
    )
    output_md = (
        tmp_path
        / "docs"
        / "challenge_cup"
        / "reproducibility"
        / "hard_evidence_source_custody.md"
    )
    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    markdown = output_md.read_text(encoding="utf-8")
    for phrase in (
        "Hard Evidence Source Custody",
        "does_not_satisfy_goal_completion=True",
        "ready_for_real_source_custody_no_external_evidence_claim",
        "source_sha256",
        "original evidence attachment",
        "must not be a JSON metadata file",
        "hard_evidence/**",
        "duplicate source_sha256",
        "--force-reason",
        "override_log.jsonl",
        "no award guarantee",
        "expert_feedback",
        "timed_rehearsal",
    ):
        assert phrase in markdown
