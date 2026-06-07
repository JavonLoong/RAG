from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_hard_evidence_ledger.py"


def load_ledger_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_hard_evidence_ledger", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def configure_module_paths(module, repo_root: Path) -> None:
    module.REPO_ROOT = repo_root
    module.OUTPUT_DIR = repo_root / "docs" / "challenge_cup" / "reproducibility"
    module.OUTPUT_JSON = module.OUTPUT_DIR / "hard_evidence_ledger.json"
    module.OUTPUT_MD = module.OUTPUT_DIR / "hard_evidence_ledger.md"
    module.INTAKE_ROOT = module.OUTPUT_DIR / "hard_evidence"
    module.EXPERT_DIR = module.INTAKE_ROOT / "expert_feedback"
    module.REHEARSAL_DIR = module.INTAKE_ROOT / "timed_rehearsal"
    module.ROOT_README = module.INTAKE_ROOT / "README.md"
    module.EXPERT_README = module.EXPERT_DIR / "README.md"
    module.REHEARSAL_README = module.REHEARSAL_DIR / "README.md"


def test_hard_evidence_ledger_readme_commands_require_real_dates(tmp_path: Path) -> None:
    module = load_ledger_module()
    configure_module_paths(module, tmp_path)

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_hard_evidence_ledger"
    assert payload["status"] == "awaiting_real_external_feedback_and_timed_rehearsal"
    assert payload["completion_claim_allowed"] is False
    assert payload["required_before_goal_completion"] == ["expert_feedback", "timed_rehearsal"]

    output_json = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_ledger.json"
    output_md = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_ledger.md"
    root_readme = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "README.md"
    expert_readme = root_readme.parent / "expert_feedback" / "README.md"
    rehearsal_readme = root_readme.parent / "timed_rehearsal" / "README.md"

    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    assert output_md.exists()
    assert root_readme.exists()
    command_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [expert_readme, rehearsal_readme]
    )
    assert "2026-06-06" not in command_text
    assert "20260606" not in command_text
    for placeholder in [
        "<real-feedback-id>",
        "<real-feedback-file>",
        "<real-reviewer-identity>",
        "<real-reviewer-role-or-org>",
        "<real-review-date-yyyy-mm-dd>",
        "<real-rehearsal-id>",
        "<real-timer-or-observer-file>",
        "<real-rehearsal-date-yyyy-mm-dd>",
        "<actual-opening-seconds>",
        "<q5-seconds>",
    ]:
        assert placeholder in command_text
    assert "must not be in the future" in command_text
    assert "source attachment must be non-empty and must not be a JSON metadata file" in command_text
    assert "source_origin" in command_text
    assert "reviewer_identity, role_or_org, and remediation issue/action must be non-empty text" in command_text
    assert "observer must be non-empty text" in command_text


def test_hard_evidence_ledger_counts_valid_metadata_source_pair_as_one_record(tmp_path: Path) -> None:
    module = load_ledger_module()
    configure_module_paths(module, tmp_path)
    expert_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "expert_feedback"
    rehearsal_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "timed_rehearsal"
    expert_dir.mkdir(parents=True)
    rehearsal_dir.mkdir(parents=True)

    expert_source = expert_dir / "advisor-a.txt"
    expert_source.write_text("real expert reply", encoding="utf-8")
    (expert_dir / "advisor-a.json").write_text(
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
    (expert_dir / "orphan-source.txt").write_text("source without metadata", encoding="utf-8")

    rehearsal_source = rehearsal_dir / "rehearsal-1.txt"
    rehearsal_source.write_text("real timer record", encoding="utf-8")
    (rehearsal_dir / "rehearsal-1.json").write_text(
        json.dumps(
            {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-a",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [
                    {"question_index": index, "actual_seconds": seconds}
                    for index, seconds in enumerate([25, 26, 27, 28, 29], start=1)
                ],
                "recording_or_timer_source_path": (
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt"
                ),
                "source_sha256": hashlib.sha256(rehearsal_source.read_bytes()).hexdigest(),
                "source_origin": "external_attachment",
                "real_rehearsal_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (rehearsal_dir / "orphan-metadata.json").write_text(
        json.dumps(
            {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-b",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [
                    {"question_index": index, "actual_seconds": seconds}
                    for index, seconds in enumerate([25, 26, 27, 28, 29], start=1)
                ],
                "recording_or_timer_source_path": (
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/missing.txt"
                ),
                "real_rehearsal_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = module.write_outputs()

    expert = payload["categories"]["expert_feedback"]
    assert expert["raw_file_count"] == 3
    assert expert["metadata_file_count"] == 1
    assert expert["source_file_count"] == 2
    assert expert["evidence_record_count"] == 1
    assert expert["collected_count"] == 1
    assert expert["evidence_records"] == [
        {
            "metadata_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
            "source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
        }
    ]

    rehearsal = payload["categories"]["timed_rehearsal"]
    assert rehearsal["raw_file_count"] == 3
    assert rehearsal["metadata_file_count"] == 2
    assert rehearsal["source_file_count"] == 1
    assert rehearsal["evidence_record_count"] == 1
    assert rehearsal["collected_count"] == 1
    assert rehearsal["evidence_records"] == [
        {
            "metadata_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
            "source_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
        }
    ]
    assert payload["completion_claim_allowed"] is True


def test_hard_evidence_ledger_rejects_source_sha256_mismatch(tmp_path: Path) -> None:
    module = load_ledger_module()
    configure_module_paths(module, tmp_path)
    expert_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "expert_feedback"
    expert_dir.mkdir(parents=True)
    expert_source = expert_dir / "advisor-a.txt"
    expert_source.write_text("tampered expert reply", encoding="utf-8")
    (expert_dir / "advisor-a.json").write_text(
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

    payload = module.write_outputs()

    expert = payload["categories"]["expert_feedback"]
    assert expert["collected_count"] == 0
    assert expert["evidence_records"] == []
    assert expert["rejected_metadata_records"][0]["metadata_path"].endswith("advisor-a.json")
    assert any("source_sha256 mismatch" in reason for reason in expert["rejected_metadata_records"][0]["reasons"])


def test_hard_evidence_ledger_rejects_over_limit_rehearsal_metadata(tmp_path: Path) -> None:
    module = load_ledger_module()
    configure_module_paths(module, tmp_path)
    rehearsal_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "timed_rehearsal"
    rehearsal_dir.mkdir(parents=True)
    rehearsal_source = rehearsal_dir / "rehearsal-over-limit.txt"
    rehearsal_source.write_text("real timer record with opening over limit", encoding="utf-8")
    (rehearsal_dir / "rehearsal-over-limit.json").write_text(
        json.dumps(
            {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-a",
                "opening_actual_seconds": 91,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [
                    {"question_index": index, "actual_seconds": seconds}
                    for index, seconds in enumerate([25, 26, 27, 28, 29], start=1)
                ],
                "recording_or_timer_source_path": (
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-over-limit.txt"
                ),
                "source_sha256": hashlib.sha256(rehearsal_source.read_bytes()).hexdigest(),
                "real_rehearsal_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = module.write_outputs()

    rehearsal = payload["categories"]["timed_rehearsal"]
    assert rehearsal["raw_file_count"] == 2
    assert rehearsal["metadata_file_count"] == 1
    assert rehearsal["source_file_count"] == 1
    assert rehearsal["evidence_record_count"] == 0
    assert rehearsal["collected_count"] == 0
    assert rehearsal["evidence_records"] == []
    assert rehearsal["rejected_metadata_records"][0]["metadata_path"].endswith("rehearsal-over-limit.json")
    assert "opening_actual_seconds=91 exceeds 90" in rehearsal["rejected_metadata_records"][0]["reasons"]
    assert payload["completion_claim_allowed"] is False


def test_hard_evidence_ledger_rejects_generic_expert_feedback_dimensions(tmp_path: Path) -> None:
    module = load_ledger_module()
    configure_module_paths(module, tmp_path)
    expert_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "expert_feedback"
    expert_dir.mkdir(parents=True)
    expert_source = expert_dir / "advisor-a.txt"
    expert_source.write_text("real expert reply", encoding="utf-8")
    (expert_dir / "advisor-a.json").write_text(
        json.dumps(
            {
                "evidence_type": "email_reply",
                "reviewer_identity": "advisor-a",
                "role_or_org": "advisor",
                "review_date": "2026-06-06",
                "feedback_source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                "review_dimensions": ["presentation", "readability", "pacing"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = module.write_outputs()

    expert = payload["categories"]["expert_feedback"]
    assert expert["raw_file_count"] == 2
    assert expert["metadata_file_count"] == 1
    assert expert["source_file_count"] == 1
    assert expert["evidence_record_count"] == 0
    assert expert["collected_count"] == 0
    assert expert["evidence_records"] == []
    assert payload["completion_claim_allowed"] is False


def test_hard_evidence_ledger_rejects_blank_identity_and_remediation_fields(tmp_path: Path) -> None:
    module = load_ledger_module()
    configure_module_paths(module, tmp_path)
    expert_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "expert_feedback"
    rehearsal_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "timed_rehearsal"
    expert_dir.mkdir(parents=True)
    rehearsal_dir.mkdir(parents=True)

    expert_source = expert_dir / "advisor-a.txt"
    expert_source.write_text("real expert reply", encoding="utf-8")
    (expert_dir / "advisor-a.json").write_text(
        json.dumps(
            {
                "evidence_type": "email_reply",
                "reviewer_identity": "   ",
                "role_or_org": "advisor",
                "review_date": "2026-06-06",
                "feedback_source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                "source_sha256": hashlib.sha256(expert_source.read_bytes()).hexdigest(),
                "review_dimensions": ["practicality", "innovation", "boundary_rigor"],
                "remediation_record": [{"issue": "demo pacing", "action": "   "}],
                "real_feedback_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rehearsal_source = rehearsal_dir / "rehearsal-1.txt"
    rehearsal_source.write_text("real timer record", encoding="utf-8")
    (rehearsal_dir / "rehearsal-1.json").write_text(
        json.dumps(
            {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "   ",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [
                    {"question_index": index, "actual_seconds": seconds}
                    for index, seconds in enumerate([25, 26, 27, 28, 29], start=1)
                ],
                "recording_or_timer_source_path": (
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt"
                ),
                "source_sha256": hashlib.sha256(rehearsal_source.read_bytes()).hexdigest(),
                "real_rehearsal_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = module.write_outputs()

    expert = payload["categories"]["expert_feedback"]
    assert expert["collected_count"] == 0
    expert_reasons = expert["rejected_metadata_records"][0]["reasons"]
    assert "reviewer_identity must be non-empty text" in expert_reasons
    assert "remediation_record[0].action must be non-empty text" in expert_reasons

    rehearsal = payload["categories"]["timed_rehearsal"]
    assert rehearsal["collected_count"] == 0
    assert "observer must be non-empty text" in rehearsal["rejected_metadata_records"][0]["reasons"]
    assert payload["completion_claim_allowed"] is False


def test_hard_evidence_ledger_rejects_future_dated_metadata(tmp_path: Path) -> None:
    module = load_ledger_module()
    configure_module_paths(module, tmp_path)
    expert_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "expert_feedback"
    rehearsal_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "timed_rehearsal"
    expert_dir.mkdir(parents=True)
    rehearsal_dir.mkdir(parents=True)
    expert_source = expert_dir / "advisor-a.txt"
    expert_source.write_text("real expert reply", encoding="utf-8")
    (expert_dir / "advisor-a.json").write_text(
        json.dumps(
            {
                "evidence_type": "email_reply",
                "reviewer_identity": "advisor-a",
                "role_or_org": "advisor",
                "review_date": "2999-01-01",
                "feedback_source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                "review_dimensions": ["practicality", "innovation", "boundary_rigor"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rehearsal_source = rehearsal_dir / "rehearsal-1.txt"
    rehearsal_source.write_text("real timer record", encoding="utf-8")
    (rehearsal_dir / "rehearsal-1.json").write_text(
        json.dumps(
            {
                "evidence_type": "observer_note",
                "rehearsal_date": "2999-01-01",
                "observer": "observer-a",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [
                    {"question_index": index, "actual_seconds": seconds}
                    for index, seconds in enumerate([25, 26, 27, 28, 29], start=1)
                ],
                "recording_or_timer_source_path": (
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt"
                ),
                "real_rehearsal_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = module.write_outputs()

    assert payload["categories"]["expert_feedback"]["collected_count"] == 0
    assert payload["categories"]["timed_rehearsal"]["collected_count"] == 0
    assert payload["completion_claim_allowed"] is False


def test_hard_evidence_ledger_rejects_empty_source_attachment(tmp_path: Path) -> None:
    module = load_ledger_module()
    configure_module_paths(module, tmp_path)
    expert_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "expert_feedback"
    rehearsal_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "timed_rehearsal"
    expert_dir.mkdir(parents=True)
    rehearsal_dir.mkdir(parents=True)
    (expert_dir / "advisor-a.txt").write_text("", encoding="utf-8")
    (expert_dir / "advisor-a.json").write_text(
        json.dumps(
            {
                "evidence_type": "email_reply",
                "reviewer_identity": "advisor-a",
                "role_or_org": "advisor",
                "review_date": "2026-06-06",
                "feedback_source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                "review_dimensions": ["practicality", "innovation", "boundary_rigor"],
                "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
                "real_feedback_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (rehearsal_dir / "rehearsal-1.txt").write_text("", encoding="utf-8")
    (rehearsal_dir / "rehearsal-1.json").write_text(
        json.dumps(
            {
                "evidence_type": "observer_note",
                "rehearsal_date": "2026-06-06",
                "observer": "observer-a",
                "opening_actual_seconds": 88,
                "demo_actual_seconds": 170,
                "offline_fallback_actual_seconds": 18,
                "killer_question_results": [
                    {"question_index": index, "actual_seconds": seconds}
                    for index, seconds in enumerate([25, 26, 27, 28, 29], start=1)
                ],
                "recording_or_timer_source_path": (
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt"
                ),
                "real_rehearsal_confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = module.write_outputs()

    assert payload["categories"]["expert_feedback"]["collected_count"] == 0
    assert payload["categories"]["timed_rehearsal"]["collected_count"] == 0
    assert payload["completion_claim_allowed"] is False
