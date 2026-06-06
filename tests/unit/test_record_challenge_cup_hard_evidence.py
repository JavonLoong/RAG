from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "record_challenge_cup_hard_evidence.py"


def load_record_module():
    spec = importlib.util.spec_from_file_location("record_challenge_cup_hard_evidence", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_records_expert_feedback_attachment_and_metadata(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.txt"
    source.parent.mkdir(parents=True)
    source.write_text("真实专家邮件回复：建议压缩开场并保留边界声明。", encoding="utf-8")

    exit_code = module.main(
        [
            "expert_feedback",
            "--id",
            "advisor-a",
            "--source",
            str(source),
            "--evidence-type",
            "email_reply",
            "--reviewer-identity",
            "advisor-a",
            "--role-or-org",
            "advisor",
            "--review-date",
            "2026-06-06",
            "--review-dimension",
            "实用性",
            "--review-dimension",
            "创新性",
            "--review-dimension",
            "边界严谨性",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "tighten opening",
            "--confirm-real-feedback",
        ]
    )

    assert exit_code == 0
    evidence_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "expert_feedback"
    copied_source = evidence_dir / "advisor-a.txt"
    metadata_path = evidence_dir / "advisor-a.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert copied_source.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert metadata == {
        "evidence_type": "email_reply",
        "reviewer_identity": "advisor-a",
        "role_or_org": "advisor",
        "review_date": "2026-06-06",
        "feedback_source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "review_dimensions": ["实用性", "创新性", "边界严谨性"],
        "remediation_record": [{"issue": "demo pacing", "action": "tighten opening"}],
        "real_feedback_confirmed": True,
    }
    ledger = json.loads(
        (tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert metadata["feedback_source_path"] in ledger["categories"]["expert_feedback"]["evidence_files"]
    assert "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json" in ledger["raw_evidence_files"]
    expert = ledger["categories"]["expert_feedback"]
    assert expert["raw_file_count"] == 2
    assert expert["metadata_file_count"] == 1
    assert expert["source_file_count"] == 1
    assert expert["evidence_record_count"] == 1
    assert expert["collected_count"] == 1
    assert expert["evidence_records"] == [
        {
            "metadata_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
            "source_path": "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
        }
    ]


def test_records_timed_rehearsal_attachment_and_metadata(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "timer_note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("真实计时记录：开场 88 秒，演示 170 秒。", encoding="utf-8")

    exit_code = module.main(
        [
            "timed_rehearsal",
            "--id",
            "rehearsal-1",
            "--source",
            str(source),
            "--evidence-type",
            "observer_note",
            "--rehearsal-date",
            "2026-06-06",
            "--observer",
            "observer-a",
            "--opening-actual-seconds",
            "88",
            "--demo-actual-seconds",
            "170",
            "--offline-fallback-actual-seconds",
            "18",
            "--killer-question-seconds",
            "25",
            "26",
            "27",
            "28",
            "29",
            "--confirm-real-rehearsal",
        ]
    )

    assert exit_code == 0
    evidence_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "timed_rehearsal"
    copied_source = evidence_dir / "rehearsal-1.txt"
    metadata_path = evidence_dir / "rehearsal-1.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert copied_source.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert metadata["recording_or_timer_source_path"] == (
        "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt"
    )
    assert metadata["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert metadata["real_rehearsal_confirmed"] is True
    assert metadata["killer_question_results"] == [
        {"question_index": index, "actual_seconds": seconds}
        for index, seconds in enumerate([25, 26, 27, 28, 29], start=1)
    ]
    ledger = json.loads(
        (tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    rehearsal = ledger["categories"]["timed_rehearsal"]
    assert rehearsal["raw_file_count"] == 2
    assert rehearsal["metadata_file_count"] == 1
    assert rehearsal["source_file_count"] == 1
    assert rehearsal["evidence_record_count"] == 1
    assert rehearsal["collected_count"] == 1
    assert rehearsal["evidence_records"] == [
        {
            "metadata_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
            "source_path": "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
        }
    ]
    assert ledger["completion_claim_allowed"] is False


def test_rejects_missing_source_file(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)

    with pytest.raises(FileNotFoundError):
        module.main(
            [
                "expert_feedback",
                "--id",
                "advisor-a",
                "--source",
                str(tmp_path / "missing.txt"),
                "--evidence-type",
                "email_reply",
                "--reviewer-identity",
                "advisor-a",
                "--role-or-org",
                "advisor",
                "--review-date",
                "2026-06-06",
                "--review-dimension",
                "实用性",
                "--review-dimension",
                "创新性",
                "--review-dimension",
                "边界严谨性",
                "--remediation-issue",
                "demo pacing",
                "--remediation-action",
                "tighten opening",
                "--confirm-real-feedback",
            ]
        )


def test_refuses_empty_expert_feedback_source_file(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.txt"
    source.parent.mkdir(parents=True)
    source.write_text("", encoding="utf-8")

    exit_code = module.main(
        [
            "expert_feedback",
            "--id",
            "advisor-a",
            "--source",
            str(source),
            "--evidence-type",
            "email_reply",
            "--reviewer-identity",
            "advisor-a",
            "--role-or-org",
            "advisor",
            "--review-date",
            "2026-06-06",
            "--review-dimension",
            "实用性",
            "--review-dimension",
            "创新性",
            "--review-dimension",
            "边界严谨性",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "tighten opening",
            "--confirm-real-feedback",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_refuses_json_expert_feedback_source_file(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"real": "reply"}', encoding="utf-8")

    exit_code = module.main(
        [
            "expert_feedback",
            "--id",
            "advisor-a",
            "--source",
            str(source),
            "--evidence-type",
            "email_reply",
            "--reviewer-identity",
            "advisor-a",
            "--role-or-org",
            "advisor",
            "--review-date",
            "2026-06-06",
            "--review-dimension",
            "实用性",
            "--review-dimension",
            "创新性",
            "--review-dimension",
            "边界严谨性",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "tighten opening",
            "--confirm-real-feedback",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_refuses_expert_feedback_without_real_feedback_confirmation(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.txt"
    source.parent.mkdir(parents=True)
    source.write_text("真实专家邮件回复。", encoding="utf-8")

    exit_code = module.main(
        [
            "expert_feedback",
            "--id",
            "advisor-a",
            "--source",
            str(source),
            "--evidence-type",
            "email_reply",
            "--reviewer-identity",
            "advisor-a",
            "--role-or-org",
            "advisor",
            "--review-date",
            "2026-06-06",
            "--review-dimension",
            "实用性",
            "--review-dimension",
            "创新性",
            "--review-dimension",
            "边界严谨性",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "tighten opening",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_refuses_expert_feedback_with_generic_dimensions(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.txt"
    source.parent.mkdir(parents=True)
    source.write_text("真实专家邮件回复。", encoding="utf-8")

    exit_code = module.main(
        [
            "expert_feedback",
            "--id",
            "advisor-a",
            "--source",
            str(source),
            "--evidence-type",
            "email_reply",
            "--reviewer-identity",
            "advisor-a",
            "--role-or-org",
            "advisor",
            "--review-date",
            "2026-06-06",
            "--review-dimension",
            "presentation",
            "--review-dimension",
            "readability",
            "--review-dimension",
            "pacing",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "tighten opening",
            "--confirm-real-feedback",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_refuses_expert_feedback_with_blank_identity_fields(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.txt"
    source.parent.mkdir(parents=True)
    source.write_text("真实专家邮件回复。", encoding="utf-8")

    exit_code = module.main(
        [
            "expert_feedback",
            "--id",
            "advisor-a",
            "--source",
            str(source),
            "--evidence-type",
            "email_reply",
            "--reviewer-identity",
            "   ",
            "--role-or-org",
            "advisor",
            "--review-date",
            "2026-06-06",
            "--review-dimension",
            "实用性",
            "--review-dimension",
            "创新性",
            "--review-dimension",
            "边界严谨性",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "tighten opening",
            "--confirm-real-feedback",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_refuses_expert_feedback_with_blank_remediation_fields(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.txt"
    source.parent.mkdir(parents=True)
    source.write_text("真实专家邮件回复。", encoding="utf-8")

    exit_code = module.main(
        [
            "expert_feedback",
            "--id",
            "advisor-a",
            "--source",
            str(source),
            "--evidence-type",
            "email_reply",
            "--reviewer-identity",
            "advisor-a",
            "--role-or-org",
            "advisor",
            "--review-date",
            "2026-06-06",
            "--review-dimension",
            "实用性",
            "--review-dimension",
            "创新性",
            "--review-dimension",
            "边界严谨性",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "   ",
            "--confirm-real-feedback",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_refuses_expert_feedback_with_future_review_date(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.txt"
    source.parent.mkdir(parents=True)
    source.write_text("真实专家邮件回复。", encoding="utf-8")

    exit_code = module.main(
        [
            "expert_feedback",
            "--id",
            "advisor-a",
            "--source",
            str(source),
            "--evidence-type",
            "email_reply",
            "--reviewer-identity",
            "advisor-a",
            "--role-or-org",
            "advisor",
            "--review-date",
            "2999-01-01",
            "--review-dimension",
            "实用性",
            "--review-dimension",
            "创新性",
            "--review-dimension",
            "边界严谨性",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "tighten opening",
            "--confirm-real-feedback",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_refuses_timed_rehearsal_without_real_rehearsal_confirmation(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "timer_note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("真实计时记录。", encoding="utf-8")

    exit_code = module.main(
        [
            "timed_rehearsal",
            "--id",
            "rehearsal-1",
            "--source",
            str(source),
            "--evidence-type",
            "observer_note",
            "--rehearsal-date",
            "2026-06-06",
            "--observer",
            "observer-a",
            "--opening-actual-seconds",
            "88",
            "--demo-actual-seconds",
            "170",
            "--offline-fallback-actual-seconds",
            "18",
            "--killer-question-seconds",
            "25",
            "26",
            "27",
            "28",
            "29",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_refuses_timed_rehearsal_with_blank_observer(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "timer_note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("真实计时记录。", encoding="utf-8")

    exit_code = module.main(
        [
            "timed_rehearsal",
            "--id",
            "rehearsal-1",
            "--source",
            str(source),
            "--evidence-type",
            "observer_note",
            "--rehearsal-date",
            "2026-06-06",
            "--observer",
            "   ",
            "--opening-actual-seconds",
            "88",
            "--demo-actual-seconds",
            "170",
            "--offline-fallback-actual-seconds",
            "18",
            "--killer-question-seconds",
            "25",
            "26",
            "27",
            "28",
            "29",
            "--confirm-real-rehearsal",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_refuses_empty_timed_rehearsal_source_file(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "timer_note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("", encoding="utf-8")

    exit_code = module.main(
        [
            "timed_rehearsal",
            "--id",
            "rehearsal-1",
            "--source",
            str(source),
            "--evidence-type",
            "observer_note",
            "--rehearsal-date",
            "2026-06-06",
            "--observer",
            "observer-a",
            "--opening-actual-seconds",
            "88",
            "--demo-actual-seconds",
            "170",
            "--offline-fallback-actual-seconds",
            "18",
            "--killer-question-seconds",
            "25",
            "26",
            "27",
            "28",
            "29",
            "--confirm-real-rehearsal",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_refuses_json_timed_rehearsal_source_file(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "timer_note.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"seconds": 88}', encoding="utf-8")

    exit_code = module.main(
        [
            "timed_rehearsal",
            "--id",
            "rehearsal-1",
            "--source",
            str(source),
            "--evidence-type",
            "observer_note",
            "--rehearsal-date",
            "2026-06-06",
            "--observer",
            "observer-a",
            "--opening-actual-seconds",
            "88",
            "--demo-actual-seconds",
            "170",
            "--offline-fallback-actual-seconds",
            "18",
            "--killer-question-seconds",
            "25",
            "26",
            "27",
            "28",
            "29",
            "--confirm-real-rehearsal",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_refuses_timed_rehearsal_with_future_rehearsal_date(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "timer_note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("真实计时记录。", encoding="utf-8")

    exit_code = module.main(
        [
            "timed_rehearsal",
            "--id",
            "rehearsal-1",
            "--source",
            str(source),
            "--evidence-type",
            "observer_note",
            "--rehearsal-date",
            "2999-01-01",
            "--observer",
            "observer-a",
            "--opening-actual-seconds",
            "88",
            "--demo-actual-seconds",
            "170",
            "--offline-fallback-actual-seconds",
            "18",
            "--killer-question-seconds",
            "25",
            "26",
            "27",
            "28",
            "29",
            "--confirm-real-rehearsal",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_records_over_limit_timed_rehearsal_but_ledger_does_not_count_it_complete(tmp_path: Path) -> None:
    module = load_record_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "timer_note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("真实计时记录：开场 91 秒。", encoding="utf-8")

    exit_code = module.main(
        [
            "timed_rehearsal",
            "--id",
            "rehearsal-1",
            "--source",
            str(source),
            "--evidence-type",
            "observer_note",
            "--rehearsal-date",
            "2026-06-06",
            "--observer",
            "observer-a",
            "--opening-actual-seconds",
            "91",
            "--demo-actual-seconds",
            "170",
            "--offline-fallback-actual-seconds",
            "18",
            "--killer-question-seconds",
            "25",
            "26",
            "27",
            "28",
            "29",
            "--confirm-real-rehearsal",
        ]
    )

    assert exit_code == 0
    evidence_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "timed_rehearsal"
    metadata = json.loads((evidence_dir / "rehearsal-1.json").read_text(encoding="utf-8"))
    assert metadata["timing_acceptance_pass"] is False
    assert "opening_actual_seconds=91 exceeds 90" in metadata["timing_acceptance_failures"]
    ledger = json.loads(
        (tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    rehearsal = ledger["categories"]["timed_rehearsal"]
    assert rehearsal["collected_count"] == 0
    assert rehearsal["evidence_records"] == []
    assert "opening_actual_seconds=91 exceeds 90" in rehearsal["rejected_metadata_records"][0]["reasons"]
