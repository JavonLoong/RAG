from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_final_acceptance_audit.py"
REPORT_JSON = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "final_acceptance_audit.json"
REPORT_MD = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "final_acceptance_audit.md"


def load_module():
    scripts_path = str(REPO_ROOT / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    spec = importlib.util.spec_from_file_location("build_challenge_cup_final_acceptance_audit", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_final_acceptance_audit_summarizes_package_ready_but_goal_incomplete() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_challenge_cup_final_acceptance_audit.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert "final_acceptance_audit.md" in result.stdout
    payload = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    assert payload["report_type"] == "challenge_cup_final_acceptance_audit"
    assert payload["status"] == "package_ready_awaiting_external_hard_evidence"
    assert payload["package_readiness"]["status"] == "pass"
    assert payload["package_readiness"]["passed"] == 62
    assert payload["package_readiness"]["total"] == 62
    assert payload["package_readiness"]["current_gate_count"] == 62
    assert payload["package_readiness"]["source_report_passed"] in {57, 58, 60, 61, 62}
    assert payload["package_readiness"]["source_report_total"] in {61, 62}
    assert payload["submission_package_verifier"]["available"] is True
    assert payload["submission_package_verifier"]["archived"] is True
    assert payload["goal_completion"]["status"] == "fail"
    assert payload["goal_completion"]["completion_claim_allowed"] is False
    assert payload["can_submit_for_package_review"] is True
    assert payload["can_mark_goal_complete"] is False
    assert {item["category"] for item in payload["blocking_items"]} == {"expert_feedback", "timed_rehearsal"}
    assert "--confirm-real-feedback" in "\n".join(payload["next_required_actions"])
    assert "--confirm-real-rehearsal" in "\n".join(payload["next_required_actions"])

    markdown = REPORT_MD.read_text(encoding="utf-8")
    assert "Final Acceptance Audit" in markdown
    assert "package_ready_awaiting_external_hard_evidence" in markdown
    assert "verify_submission_package.py" in markdown
    assert "completion_claim_allowed=False" in markdown
    assert "--confirm-real-feedback" in markdown
    assert "--confirm-real-rehearsal" in markdown


def test_final_acceptance_bootstraps_self_referential_readiness_failure(tmp_path, monkeypatch) -> None:
    module = load_module()
    repro = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    repro.mkdir(parents=True)
    verifier = repro / "verify_submission_package.py"
    verifier.write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "REPRO_DIR", repro)
    monkeypatch.setattr(module, "READINESS_REPORT", repro / "readiness_gate_report.md")
    monkeypatch.setattr(module, "GOAL_COMPLETION_REPORT", repro / "goal_completion_report.md")
    monkeypatch.setattr(module, "HARD_EVIDENCE_LEDGER", repro / "hard_evidence_ledger.json")
    monkeypatch.setattr(module, "ARCHIVE_MANIFEST", repro / "challenge_cup_submission_archive_manifest.json")
    monkeypatch.setattr(module, "SUBMISSION_VERIFIER", verifier)
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
    (repro / "goal_completion_report.md").write_text(
        "# Challenge Cup Goal Completion Gate\n\n- Status: `fail`\n- completion_claim_allowed=False\n",
        encoding="utf-8",
    )
    (repro / "hard_evidence_ledger.json").write_text(
        json.dumps(
            {
                "categories": {
                    "expert_feedback": {
                        "required_min_count": 1,
                        "collected_count": 0,
                        "evidence_files": [],
                        "intake_dir": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback",
                    },
                    "timed_rehearsal": {
                        "required_min_count": 1,
                        "collected_count": 0,
                        "evidence_files": [],
                        "intake_dir": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    (repro / "challenge_cup_submission_archive_manifest.json").write_text(
        json.dumps({"included_files": [module.SUBMISSION_VERIFIER_RELATIVE]}),
        encoding="utf-8",
    )

    payload = module.build_payload()

    assert payload["status"] == "package_ready_awaiting_external_hard_evidence"
    assert payload["can_submit_for_package_review"] is True
    assert payload["can_mark_goal_complete"] is False
    assert payload["package_readiness"]["status"] == "pass"
    assert payload["package_readiness"]["passed"] == 62
    assert payload["package_readiness"]["total"] == 62
    assert payload["package_readiness"]["source_report_status"] == "fail"
    assert payload["package_readiness"]["source_report_passed"] == 60
    assert payload["package_readiness"]["source_report_total"] == 62
    assert payload["package_readiness"]["self_referential_readiness_bootstrap"] is True
    assert payload["package_readiness"]["count_synced_for_self_referential_audit"] is True


def test_final_acceptance_bootstrap_reason_accepts_only_generation_cycle_failures(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "CURRENT_READINESS_GATE_COUNT", 62)
    generation_cycle_report = (
        "# Challenge Cup Readiness Gate\n\n"
        "- Status: `fail`\n"
        "- Passed: 58/62\n\n"
        "| Gate | Result | Evidence |\n"
        "| --- | --- | --- |\n"
        "| package evidence files | fail | evidence=97, questions=60, missing=[], untracked=[], dirty=['docs/challenge_cup/reproducibility/final_acceptance_audit.json', 'docs/challenge_cup/reproducibility/verification_transcript.md'] |\n"
        "| evidence integrity hashes | fail | bytes mismatch: docs/challenge_cup/reproducibility/final_acceptance_audit.json; sha256 mismatch: docs/challenge_cup/reproducibility/verification_transcript.md |\n"
        "| submission archive | fail | stale archive entry: docs/challenge_cup/reproducibility/final_acceptance_audit.json; stale archive entry: docs/challenge_cup/reproducibility/verification_transcript.md |\n"
        "| external evidence execution kit | fail | dirty external evidence execution kit files: ['docs/challenge_cup/reproducibility/external_evidence_execution_kit.json', 'docs/challenge_cup/reproducibility/external_evidence_execution_kit.md'] |\n"
        "| verification transcript | fail | dirty verification transcript files: ['docs/challenge_cup/reproducibility/verification_transcript.json', 'docs/challenge_cup/reproducibility/verification_transcript.md'] |\n"
    )
    reason = module.readiness_bootstrap_reason(generation_cycle_report, "fail")
    normalized = module.normalize_readiness_count(
        "fail",
        module.parse_passed_count(generation_cycle_report),
        bootstrap_readiness=bool(reason),
        bootstrap_reason=reason,
    )

    assert reason == "generation_cycle"
    assert normalized["passed"] == 62
    assert normalized["total"] == 62
    assert normalized["self_referential_readiness_bootstrap"] is False

    real_failure_report = generation_cycle_report + "| no-answer boundary evaluation | fail | unsupported claim accepted |\n"
    assert module.readiness_bootstrap_reason(real_failure_report, "fail") == ""
