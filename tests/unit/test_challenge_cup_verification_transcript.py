from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_verification_transcript.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_verification_transcript", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verification_transcript_summarizes_current_gates_without_goal_overclaim(tmp_path, monkeypatch) -> None:
    module = load_module()
    output_json = tmp_path / "verification_transcript.json"
    output_md = tmp_path / "verification_transcript.md"
    repro = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    repro.mkdir(parents=True)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "OUTPUT_JSON", output_json)
    monkeypatch.setattr(module, "OUTPUT_MD", output_md)
    monkeypatch.setattr(module, "CURRENT_READINESS_GATE_COUNT", 62)

    (repro / "readiness_gate_report.md").write_text(
        "# Challenge Cup Readiness Gate\n\n- Status: `pass`\n- Passed: 56/56\n",
        encoding="utf-8",
    )
    (repro / "final_acceptance_audit.json").write_text(
        json.dumps(
            {
                "report_type": "challenge_cup_final_acceptance_audit",
                "status": "package_ready_awaiting_external_hard_evidence",
                "package_readiness": {"status": "pass", "passed": 56, "total": 56},
                "submission_package_verifier": {"available": True, "archived": True},
                "goal_completion": {"status": "fail", "completion_claim_allowed": False},
                "can_submit_for_package_review": True,
                "can_mark_goal_complete": False,
                "blocking_items": [{"category": "expert_feedback"}, {"category": "timed_rehearsal"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (repro / "goal_completion_report.md").write_text(
        "# Challenge Cup Goal Completion Gate\n\n"
        "- Status: `fail`\n"
        "- completion_claim_allowed=False\n"
        "- Package readiness: `True` (readiness gate passed 56/56)\n",
        encoding="utf-8",
    )

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_verification_transcript"
    assert payload["status"] == "package_verification_transcript_ready_goal_still_blocked"
    assert payload["completion_claim_allowed"] is False
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["external_validation_claimed"] is False
    assert payload["readiness_gate"]["status"] == "pass"
    assert payload["readiness_gate"]["passed"] == 62
    assert payload["readiness_gate"]["total"] == 62
    assert payload["readiness_gate"]["source_report_passed"] == 56
    assert payload["final_acceptance"]["status"] == "package_ready_awaiting_external_hard_evidence"
    assert payload["goal_completion"]["status"] == "fail"
    assert payload["goal_completion"]["expected_failure"] is True
    assert {item["category"] for item in payload["blocking_items"]} == {
        "expert_feedback",
        "timed_rehearsal",
    }
    commands = {item["command"]: item for item in payload["verification_commands"]}
    assert commands[".\\.venv\\Scripts\\python.exe scripts/check_challenge_cup_readiness.py"]["expected_exit_code"] == 0
    assert commands[
        ".\\.venv\\Scripts\\python.exe docs/challenge_cup/reproducibility/verify_submission_package.py --root ."
    ]["observed_status"] == "pass"
    assert commands[".\\.venv\\Scripts\\python.exe scripts/check_challenge_cup_goal_completion.py"][
        "expected_exit_code"
    ] == 1
    assert "does not claim goal completion" in payload["boundary"]
    assert "does not replace real expert feedback or real timed rehearsal evidence" in payload["boundary"]
    assert payload["output_files"] == [
        "docs/challenge_cup/reproducibility/verification_transcript.md",
        "docs/challenge_cup/reproducibility/verification_transcript.json",
    ]

    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    markdown = output_md.read_text(encoding="utf-8")
    assert "Verification Transcript" in markdown
    assert "readiness gate pass 62/62" in markdown
    assert "Expected Failure" in markdown
    assert "does not claim goal completion" in markdown


def test_verification_transcript_bootstraps_self_referential_readiness_failure(tmp_path, monkeypatch) -> None:
    module = load_module()
    output_json = tmp_path / "verification_transcript.json"
    output_md = tmp_path / "verification_transcript.md"
    repro = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    repro.mkdir(parents=True)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "OUTPUT_JSON", output_json)
    monkeypatch.setattr(module, "OUTPUT_MD", output_md)
    monkeypatch.setattr(module, "CURRENT_READINESS_GATE_COUNT", 62)

    (repro / "readiness_gate_report.md").write_text(
        "# Challenge Cup Readiness Gate\n\n"
        "- Status: `fail`\n"
        "- Passed: 60/62\n\n"
        "| Gate | Result | Evidence |\n"
        "| --- | --- | --- |\n"
        "| package documents | pass | ok |\n"
        "| final acceptance audit | fail | status=not_ready; package_readiness.status=fail; package_readiness count=52/62 |\n"
        "| verification transcript | fail | readiness.status=fail; final_acceptance.status=not_ready; .\\.venv\\Scripts\\python.exe scripts/check_challenge_cup_readiness.py observed_status=fail |\n",
        encoding="utf-8",
    )
    (repro / "final_acceptance_audit.json").write_text(
        json.dumps(
            {
                "report_type": "challenge_cup_final_acceptance_audit",
                "status": "package_ready_awaiting_external_hard_evidence",
                "package_readiness": {
                    "status": "pass",
                    "passed": 62,
                    "total": 62,
                    "source_report_status": "fail",
                    "source_report_passed": 60,
                    "source_report_total": 62,
                    "self_referential_readiness_bootstrap": True,
                },
                "submission_package_verifier": {"available": True, "archived": True},
                "goal_completion": {"status": "fail", "completion_claim_allowed": False},
                "can_submit_for_package_review": True,
                "can_mark_goal_complete": False,
                "blocking_items": [{"category": "expert_feedback"}, {"category": "timed_rehearsal"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (repro / "goal_completion_report.md").write_text(
        "# Challenge Cup Goal Completion Gate\n\n"
        "- Status: `fail`\n"
        "- completion_claim_allowed=False\n",
        encoding="utf-8",
    )

    payload = module.write_outputs()

    assert payload["readiness_gate"]["status"] == "pass"
    assert payload["readiness_gate"]["passed"] == 62
    assert payload["readiness_gate"]["total"] == 62
    assert payload["readiness_gate"]["source_report_status"] == "fail"
    assert payload["readiness_gate"]["source_report_passed"] == 60
    assert payload["readiness_gate"]["source_report_total"] == 62
    assert payload["readiness_gate"]["self_referential_readiness_bootstrap"] is True
    commands = {item["command"]: item for item in payload["verification_commands"]}
    assert commands[".\\.venv\\Scripts\\python.exe scripts/check_challenge_cup_readiness.py"]["observed_status"] == "pass"
    assert commands[".\\.venv\\Scripts\\python.exe scripts/build_challenge_cup_final_acceptance_audit.py"][
        "observed_status"
    ] == "package_ready_awaiting_external_hard_evidence"
    markdown = output_md.read_text(encoding="utf-8")
    assert "readiness gate pass 62/62" in markdown


def test_verification_transcript_parse_readiness_bootstraps_generation_cycle_failures(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "CURRENT_READINESS_GATE_COUNT", 62)
    report = (
        "# Challenge Cup Readiness Gate\n\n"
        "- Status: `fail`\n"
        "- Passed: 58/62\n\n"
        "| Gate | Result | Evidence |\n"
        "| --- | --- | --- |\n"
        "| package evidence files | fail | evidence=97, questions=60, missing=[], untracked=[], dirty=['docs/challenge_cup/reproducibility/final_acceptance_audit.json', 'docs/challenge_cup/reproducibility/verification_transcript.md'] |\n"
        "| evidence integrity hashes | fail | bytes mismatch: docs/challenge_cup/reproducibility/final_acceptance_audit.json; sha256 mismatch: docs/challenge_cup/reproducibility/verification_transcript.md |\n"
        "| submission archive | fail | stale archive entry: docs/challenge_cup/reproducibility/final_acceptance_audit.json; stale archive entry: docs/challenge_cup/reproducibility/verification_transcript.md |\n"
        "| verification transcript | fail | dirty verification transcript files: ['docs/challenge_cup/reproducibility/verification_transcript.json', 'docs/challenge_cup/reproducibility/verification_transcript.md'] |\n"
    )

    readiness = module.parse_readiness_count(report)

    assert readiness["status"] == "pass"
    assert readiness["passed"] == 62
    assert readiness["total"] == 62
    assert readiness["source_report_status"] == "fail"
    assert readiness["self_referential_readiness_bootstrap"] is False
    assert readiness["generation_cycle_readiness_bootstrap"] is True
    assert readiness["readiness_bootstrap_reason"] == "generation_cycle"
