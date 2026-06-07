from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_challenge_cup_goal_completion.py"
REPORT = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "goal_completion_report.md"


def load_goal_module():
    spec = importlib.util.spec_from_file_location("check_challenge_cup_goal_completion", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_goal_completion_gate_fails_until_real_hard_evidence_is_archived() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_challenge_cup_goal_completion.py"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 1
    assert "Status: fail" in result.stdout
    report = REPORT.read_text(encoding="utf-8")
    assert "Status: `fail`" in report
    assert "expert_feedback" in report
    assert "timed_rehearsal" in report
    assert "completion_claim_allowed=False" in report
    assert "readiness gate passed 65/65" in report
    assert "61/61" not in report
    assert "60/60" not in report
    assert "59/59" not in report
    assert "56/56" not in report
    assert "55/55" not in report
    assert "不能标记目标完成" in report
    assert "## Next Actions" in report
    assert "docs/challenge_cup/reproducibility/external_evidence_closeout_checklist.md" in report
    assert "python scripts/record_challenge_cup_hard_evidence.py expert_feedback" in report
    assert "python scripts/run_challenge_cup_timed_rehearsal.py" in report
    assert "python scripts/build_challenge_cup_package.py" in report
    assert "python scripts/check_challenge_cup_goal_completion.py" in report
    for mojibake in ("鐪熚疄", "涓嶈兘", "鎶?readiness"):
        assert mojibake not in report


def test_goal_completion_gate_rejects_stale_readiness_gate_count(tmp_path: Path) -> None:
    module = load_goal_module()
    repro = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    repro.mkdir(parents=True)
    (repro / "readiness_gate_report.md").write_text(
        "# Challenge Cup Readiness Gate\n\n- Status: `pass`\n- Passed: 30/30\n",
        encoding="utf-8",
    )

    ok, detail = module.readiness_passed(tmp_path)

    assert ok is False
    assert "stale readiness gate count" in detail
    assert "65/65" in detail


def test_goal_completion_gate_passes_with_ready_package_and_complete_hard_evidence(tmp_path: Path) -> None:
    module = load_goal_module()
    repro = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    expert_source = repro / "hard_evidence" / "expert_feedback" / "advisor-a.txt"
    expert_meta = repro / "hard_evidence" / "expert_feedback" / "advisor-a.json"
    rehearsal_source = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.txt"
    rehearsal_meta = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.json"
    for path in (expert_source, expert_meta, rehearsal_source, rehearsal_meta):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("real evidence", encoding="utf-8")
    expert_meta.write_text(
        json.dumps(
            {
                "evidence_type": "email_reply",
                "reviewer_identity": "advisor-a",
                "role_or_org": "advisor",
                "review_date": "2026-06-06",
                "feedback_source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                "source_sha256": hashlib.sha256(expert_source.read_bytes()).hexdigest(),
                "source_origin": "external_attachment",
                "review_dimensions": ["practicality", "innovation", "boundary_rigor"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rehearsal_meta.write_text(
        json.dumps(
            {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-a",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [
                    {"question_index": index, "actual_seconds": 25} for index in range(1, 6)
                ],
                "recording_or_timer_source_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                "source_sha256": hashlib.sha256(rehearsal_source.read_bytes()).hexdigest(),
                "source_origin": "external_attachment",
                "real_rehearsal_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (repro / "readiness_gate_report.md").write_text(
        "# Challenge Cup Readiness Gate\n\n- Status: `pass`\n- Passed: 65/65\n",
        encoding="utf-8",
    )
    ledger = {
        "report_type": "challenge_cup_hard_evidence_ledger",
        "status": "hard_evidence_collected_pending_review",
        "completion_claim_allowed": True,
        "required_before_goal_completion": ["expert_feedback", "timed_rehearsal"],
        "categories": {
            "expert_feedback": {
                "required_min_count": 1,
                "raw_file_count": 2,
                "metadata_file_count": 1,
                "source_file_count": 1,
                "evidence_record_count": 1,
                "collected_count": 1,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                ],
                "metadata_files": ["docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json"],
                "source_files": ["docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt"],
                "evidence_records": [
                    {
                        "metadata_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
                        "source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                    }
                ],
            },
            "timed_rehearsal": {
                "required_min_count": 1,
                "raw_file_count": 2,
                "metadata_file_count": 1,
                "source_file_count": 1,
                "evidence_record_count": 1,
                "collected_count": 1,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                ],
                "metadata_files": ["docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json"],
                "source_files": ["docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt"],
                "evidence_records": [
                    {
                        "metadata_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
                        "source_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                    }
                ],
            },
        },
        "raw_evidence_files": [
            "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
            "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
            "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
            "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
        ],
    }
    (repro / "hard_evidence_ledger.json").write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    payload = module.write_report(tmp_path)

    assert payload["status"] == "pass"
    report = (repro / "goal_completion_report.md").read_text(encoding="utf-8")
    assert "Status: `pass`" in report
    assert "真实专家反馈" in report
    assert "真实计时彩排" in report


def test_goal_completion_gate_rejects_hard_evidence_without_real_confirmations(tmp_path: Path) -> None:
    module = load_goal_module()
    repro = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    expert_source = repro / "hard_evidence" / "expert_feedback" / "advisor-a.txt"
    expert_meta = repro / "hard_evidence" / "expert_feedback" / "advisor-a.json"
    rehearsal_source = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.txt"
    rehearsal_meta = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.json"
    for path in (expert_source, rehearsal_source):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("real evidence", encoding="utf-8")
    expert_meta.write_text(
        json.dumps(
            {
                "evidence_type": "email_reply",
                "reviewer_identity": "advisor-a",
                "role_or_org": "advisor",
                "review_date": "2026-06-06",
                "feedback_source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                "source_sha256": hashlib.sha256(expert_source.read_bytes()).hexdigest(),
                "review_dimensions": ["practicality", "innovation", "boundary_rigor"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rehearsal_meta.write_text(
        json.dumps(
            {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-a",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [
                    {"question_index": index, "actual_seconds": 25} for index in range(1, 6)
                ],
                "recording_or_timer_source_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                "source_sha256": hashlib.sha256(rehearsal_source.read_bytes()).hexdigest(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (repro / "readiness_gate_report.md").write_text(
        "# Challenge Cup Readiness Gate\n\n- Status: `pass`\n- Passed: 30/30\n",
        encoding="utf-8",
    )
    ledger = {
        "report_type": "challenge_cup_hard_evidence_ledger",
        "status": "hard_evidence_collected_pending_review",
        "completion_claim_allowed": True,
        "required_before_goal_completion": ["expert_feedback", "timed_rehearsal"],
        "categories": {
            "expert_feedback": {
                "required_min_count": 1,
                "raw_file_count": 2,
                "metadata_file_count": 1,
                "source_file_count": 1,
                "evidence_record_count": 1,
                "collected_count": 1,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                ],
                "metadata_files": ["docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json"],
                "source_files": ["docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt"],
                "evidence_records": [
                    {
                        "metadata_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
                        "source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                    }
                ],
            },
            "timed_rehearsal": {
                "required_min_count": 1,
                "raw_file_count": 2,
                "metadata_file_count": 1,
                "source_file_count": 1,
                "evidence_record_count": 1,
                "collected_count": 1,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                ],
                "metadata_files": ["docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json"],
                "source_files": ["docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt"],
                "evidence_records": [
                    {
                        "metadata_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
                        "source_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                    }
                ],
            },
        },
    }
    (repro / "hard_evidence_ledger.json").write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    payload = module.write_report(tmp_path)

    assert payload["status"] == "fail"
    assert any("real_feedback_confirmed" in item for item in payload["hard_evidence_failures"])
    assert any("real_rehearsal_confirmed" in item for item in payload["hard_evidence_failures"])


def test_goal_completion_gate_rejects_over_limit_timed_rehearsal_even_if_ledger_claims_complete(
    tmp_path: Path,
) -> None:
    module = load_goal_module()
    repro = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    expert_source = repro / "hard_evidence" / "expert_feedback" / "advisor-a.txt"
    expert_meta = repro / "hard_evidence" / "expert_feedback" / "advisor-a.json"
    rehearsal_source = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.txt"
    rehearsal_meta = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.json"
    for path in (expert_source, rehearsal_source):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("real evidence", encoding="utf-8")
    expert_meta.write_text(
        json.dumps(
            {
                "evidence_type": "email_reply",
                "reviewer_identity": "advisor-a",
                "role_or_org": "advisor",
                "review_date": "2026-06-06",
                "feedback_source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                "source_sha256": hashlib.sha256(expert_source.read_bytes()).hexdigest(),
                "review_dimensions": ["practicality", "innovation", "boundary_rigor"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rehearsal_meta.write_text(
        json.dumps(
            {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-a",
                "opening_actual_seconds": 91,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [
                    {"question_index": index, "actual_seconds": 25} for index in range(1, 6)
                ],
                "recording_or_timer_source_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                "source_sha256": hashlib.sha256(rehearsal_source.read_bytes()).hexdigest(),
                "real_rehearsal_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (repro / "readiness_gate_report.md").write_text(
        "# Challenge Cup Readiness Gate\n\n- Status: `pass`\n- Passed: 65/65\n",
        encoding="utf-8",
    )
    ledger = {
        "report_type": "challenge_cup_hard_evidence_ledger",
        "status": "hard_evidence_collected_pending_review",
        "completion_claim_allowed": True,
        "required_before_goal_completion": ["expert_feedback", "timed_rehearsal"],
        "categories": {
            "expert_feedback": {
                "required_min_count": 1,
                "collected_count": 1,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                ],
            },
            "timed_rehearsal": {
                "required_min_count": 1,
                "collected_count": 1,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                ],
            },
        },
    }
    (repro / "hard_evidence_ledger.json").write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    payload = module.write_report(tmp_path)

    assert payload["status"] == "fail"
    assert any("opening_actual_seconds=91 exceeds 90" in item for item in payload["hard_evidence_failures"])


def test_goal_completion_gate_rejects_incomplete_expert_feedback_even_if_ledger_claims_complete(
    tmp_path: Path,
) -> None:
    module = load_goal_module()
    repro = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    expert_source = repro / "hard_evidence" / "expert_feedback" / "advisor-a.txt"
    expert_meta = repro / "hard_evidence" / "expert_feedback" / "advisor-a.json"
    rehearsal_source = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.txt"
    rehearsal_meta = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.json"
    for path in (expert_source, rehearsal_source):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("real evidence", encoding="utf-8")
    expert_meta.write_text(
        json.dumps(
            {
                "evidence_type": "email_reply",
                "reviewer_identity": "advisor-a",
                "role_or_org": "advisor",
                "review_date": "2026-06-06",
                "feedback_source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                "source_sha256": hashlib.sha256(expert_source.read_bytes()).hexdigest(),
                "review_dimensions": ["practicality", "innovation"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rehearsal_meta.write_text(
        json.dumps(
            {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-a",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [
                    {"question_index": index, "actual_seconds": 25} for index in range(1, 6)
                ],
                "recording_or_timer_source_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                "source_sha256": hashlib.sha256(rehearsal_source.read_bytes()).hexdigest(),
                "real_rehearsal_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (repro / "readiness_gate_report.md").write_text(
        "# Challenge Cup Readiness Gate\n\n- Status: `pass`\n- Passed: 65/65\n",
        encoding="utf-8",
    )
    ledger = {
        "report_type": "challenge_cup_hard_evidence_ledger",
        "status": "hard_evidence_collected_pending_review",
        "completion_claim_allowed": True,
        "required_before_goal_completion": ["expert_feedback", "timed_rehearsal"],
        "categories": {
            "expert_feedback": {
                "required_min_count": 1,
                "collected_count": 1,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                ],
            },
            "timed_rehearsal": {
                "required_min_count": 1,
                "collected_count": 1,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                ],
            },
        },
    }
    (repro / "hard_evidence_ledger.json").write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    payload = module.write_report(tmp_path)

    assert payload["status"] == "fail"
    assert any("review_dimensions count=2 expected at least 3" in item for item in payload["hard_evidence_failures"])


def test_goal_completion_gate_rejects_generic_expert_feedback_dimensions_even_if_ledger_claims_complete(
    tmp_path: Path,
) -> None:
    module = load_goal_module()
    repro = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    expert_source = repro / "hard_evidence" / "expert_feedback" / "advisor-a.txt"
    expert_meta = repro / "hard_evidence" / "expert_feedback" / "advisor-a.json"
    rehearsal_source = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.txt"
    rehearsal_meta = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.json"
    for path in (expert_source, rehearsal_source):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("real evidence", encoding="utf-8")
    expert_meta.write_text(
        json.dumps(
            {
                "evidence_type": "email_reply",
                "reviewer_identity": "advisor-a",
                "role_or_org": "advisor",
                "review_date": "2026-06-06",
                "feedback_source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                "source_sha256": hashlib.sha256(expert_source.read_bytes()).hexdigest(),
                "review_dimensions": ["presentation", "readability", "pacing"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rehearsal_meta.write_text(
        json.dumps(
            {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-a",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [
                    {"question_index": index, "actual_seconds": 25} for index in range(1, 6)
                ],
                "recording_or_timer_source_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                "source_sha256": hashlib.sha256(rehearsal_source.read_bytes()).hexdigest(),
                "real_rehearsal_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (repro / "readiness_gate_report.md").write_text(
        "# Challenge Cup Readiness Gate\n\n- Status: `pass`\n- Passed: 65/65\n",
        encoding="utf-8",
    )
    ledger = {
        "report_type": "challenge_cup_hard_evidence_ledger",
        "status": "hard_evidence_collected_pending_review",
        "completion_claim_allowed": True,
        "required_before_goal_completion": ["expert_feedback", "timed_rehearsal"],
        "categories": {
            "expert_feedback": {
                "required_min_count": 1,
                "collected_count": 1,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                ],
            },
            "timed_rehearsal": {
                "required_min_count": 1,
                "collected_count": 1,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                ],
            },
        },
    }
    (repro / "hard_evidence_ledger.json").write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    payload = module.write_report(tmp_path)

    assert payload["status"] == "fail"
    assert any("missing required expert review dimension groups" in item for item in payload["hard_evidence_failures"])


def test_goal_completion_metadata_rejects_future_hard_evidence_dates() -> None:
    module = load_goal_module()

    expert_failures = module.expert_feedback_metadata_failures(
        {
            "evidence_type": "email_reply",
            "reviewer_identity": "advisor-a",
            "role_or_org": "advisor",
            "review_date": "2999-01-01",
            "review_dimensions": ["practicality", "innovation", "boundary_rigor"],
            "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
            "real_feedback_confirmed": True,
        },
        "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
    )
    rehearsal_failures = module.timed_rehearsal_timing_failures(
        {
            "evidence_type": "observer_note",
            "rehearsal_date": "2999-01-01",
            "observer": "observer-a",
            "opening_actual_seconds": 88,
            "demo_actual_seconds": 170,
            "offline_fallback_actual_seconds": 18,
            "killer_question_results": [{"question_index": index, "actual_seconds": 25} for index in range(1, 6)],
            "real_rehearsal_confirmed": True,
        },
        "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
    )

    assert any("review_date must be YYYY-MM-DD and not in the future" in item for item in expert_failures)
    assert any("rehearsal_date must be YYYY-MM-DD and not in the future" in item for item in rehearsal_failures)


def test_goal_completion_gate_rejects_json_source_attachment_even_if_ledger_claims_complete(
    tmp_path: Path,
) -> None:
    module = load_goal_module()
    repro = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    expert_meta = repro / "hard_evidence" / "expert_feedback" / "advisor-a.json"
    expert_source = repro / "hard_evidence" / "expert_feedback" / "advisor-source.json"
    rehearsal_meta = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.json"
    rehearsal_source = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-source.json"
    for path in (expert_meta, expert_source, rehearsal_meta, rehearsal_source):
        path.parent.mkdir(parents=True, exist_ok=True)
    expert_source.write_text('{"source": "not allowed"}', encoding="utf-8")
    rehearsal_source.write_text('{"source": "not allowed"}', encoding="utf-8")
    expert_meta.write_text(
        json.dumps(
            {
                "evidence_type": "email_reply",
                "reviewer_identity": "advisor-a",
                "role_or_org": "advisor",
                "review_date": "2026-06-06",
                "feedback_source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-source.json",
                "source_sha256": hashlib.sha256(expert_source.read_bytes()).hexdigest(),
                "review_dimensions": ["practicality", "innovation", "boundary_rigor"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rehearsal_meta.write_text(
        json.dumps(
            {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-a",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [
                    {"question_index": index, "actual_seconds": 25} for index in range(1, 6)
                ],
                "recording_or_timer_source_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-source.json",
                "source_sha256": hashlib.sha256(rehearsal_source.read_bytes()).hexdigest(),
                "real_rehearsal_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (repro / "readiness_gate_report.md").write_text(
        "# Challenge Cup Readiness Gate\n\n- Status: `pass`\n- Passed: 65/65\n",
        encoding="utf-8",
    )
    ledger = {
        "report_type": "challenge_cup_hard_evidence_ledger",
        "status": "hard_evidence_collected_pending_review",
        "completion_claim_allowed": True,
        "categories": {
            "expert_feedback": {
                "required_min_count": 1,
                "collected_count": 1,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
                ],
            },
            "timed_rehearsal": {
                "required_min_count": 1,
                "collected_count": 1,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
                ],
            },
        },
    }
    (repro / "hard_evidence_ledger.json").write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    payload = module.write_report(tmp_path)

    assert payload["status"] == "fail"
    assert any("must not be a json metadata file" in item for item in payload["hard_evidence_failures"])


def test_goal_completion_gate_rejects_source_sha256_mismatch_even_if_ledger_claims_complete(
    tmp_path: Path,
) -> None:
    module = load_goal_module()
    repro = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    expert_source = repro / "hard_evidence" / "expert_feedback" / "advisor-a.txt"
    expert_meta = repro / "hard_evidence" / "expert_feedback" / "advisor-a.json"
    rehearsal_source = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.txt"
    rehearsal_meta = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.json"
    for path in (expert_source, rehearsal_source):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("tampered evidence", encoding="utf-8")
    expert_meta.write_text(
        json.dumps(
            {
                "evidence_type": "email_reply",
                "reviewer_identity": "advisor-a",
                "role_or_org": "advisor",
                "review_date": "2026-06-06",
                "feedback_source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                "source_sha256": "0" * 64,
                "review_dimensions": ["practicality", "innovation", "boundary_rigor"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rehearsal_meta.write_text(
        json.dumps(
            {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-a",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [
                    {"question_index": index, "actual_seconds": 25} for index in range(1, 6)
                ],
                "recording_or_timer_source_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                "source_sha256": "0" * 64,
                "real_rehearsal_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (repro / "readiness_gate_report.md").write_text(
        "# Challenge Cup Readiness Gate\n\n- Status: `pass`\n- Passed: 65/65\n",
        encoding="utf-8",
    )
    ledger = {
        "report_type": "challenge_cup_hard_evidence_ledger",
        "status": "hard_evidence_collected_pending_review",
        "completion_claim_allowed": True,
        "categories": {
            "expert_feedback": {
                "required_min_count": 1,
                "collected_count": 1,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                ],
            },
            "timed_rehearsal": {
                "required_min_count": 1,
                "collected_count": 1,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                ],
            },
        },
    }
    (repro / "hard_evidence_ledger.json").write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    payload = module.write_report(tmp_path)

    assert payload["status"] == "fail"
    assert any("source_sha256 mismatch" in item for item in payload["hard_evidence_failures"])
