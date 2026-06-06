from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "preflight_challenge_cup_hard_evidence.py"


def load_preflight_module():
    spec = importlib.util.spec_from_file_location("preflight_challenge_cup_hard_evidence", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def hard_evidence_dir(root: Path) -> Path:
    return root / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence"


def test_preflights_confirmed_expert_feedback_without_writing_hard_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    module = load_preflight_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real advisor feedback", encoding="utf-8")

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
            "practicality",
            "--review-dimension",
            "innovation",
            "--review-dimension",
            "boundary_rigor",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "tighten opening",
            "--confirm-real-feedback",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ledger_acceptance"] == {
        "category": "expert_feedback",
        "will_count_as_hard_evidence": True,
        "will_enter_rejected_metadata_records": False,
        "completion_gate_effect": "recorded metadata can satisfy expert_feedback after ledger rebuild",
        "reasons": [],
    }
    assert not hard_evidence_dir(tmp_path).exists()


def test_refuses_expert_feedback_preflight_without_real_confirmation(tmp_path: Path) -> None:
    module = load_preflight_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real advisor feedback", encoding="utf-8")

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
            "practicality",
            "--review-dimension",
            "innovation",
            "--review-dimension",
            "boundary_rigor",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "tighten opening",
        ]
    )

    assert exit_code == 2
    assert not hard_evidence_dir(tmp_path).exists()


def test_refuses_expert_feedback_preflight_with_json_source(tmp_path: Path) -> None:
    module = load_preflight_module()
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
            "practicality",
            "--review-dimension",
            "innovation",
            "--review-dimension",
            "boundary_rigor",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "tighten opening",
            "--confirm-real-feedback",
        ]
    )

    assert exit_code == 2
    assert not hard_evidence_dir(tmp_path).exists()


def test_refuses_expert_feedback_preflight_with_too_few_dimensions(tmp_path: Path) -> None:
    module = load_preflight_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real advisor feedback", encoding="utf-8")

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
            "practicality",
            "--review-dimension",
            "innovation",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "tighten opening",
            "--confirm-real-feedback",
        ]
    )

    assert exit_code == 2
    assert not hard_evidence_dir(tmp_path).exists()


def test_refuses_expert_feedback_preflight_with_generic_dimensions(tmp_path: Path) -> None:
    module = load_preflight_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real advisor feedback", encoding="utf-8")

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
    assert not hard_evidence_dir(tmp_path).exists()


def test_refuses_expert_feedback_preflight_with_blank_identity_fields(tmp_path: Path) -> None:
    module = load_preflight_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real advisor feedback", encoding="utf-8")

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
            "practicality",
            "--review-dimension",
            "innovation",
            "--review-dimension",
            "boundary_rigor",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "tighten opening",
            "--confirm-real-feedback",
        ]
    )

    assert exit_code == 2
    assert not hard_evidence_dir(tmp_path).exists()


def test_refuses_expert_feedback_preflight_with_blank_remediation_fields(tmp_path: Path) -> None:
    module = load_preflight_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real advisor feedback", encoding="utf-8")

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
            "practicality",
            "--review-dimension",
            "innovation",
            "--review-dimension",
            "boundary_rigor",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "   ",
            "--confirm-real-feedback",
        ]
    )

    assert exit_code == 2
    assert not hard_evidence_dir(tmp_path).exists()


def test_refuses_expert_feedback_preflight_with_future_review_date(tmp_path: Path) -> None:
    module = load_preflight_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "advisor_reply.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real advisor feedback", encoding="utf-8")

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
            "practicality",
            "--review-dimension",
            "innovation",
            "--review-dimension",
            "boundary_rigor",
            "--remediation-issue",
            "demo pacing",
            "--remediation-action",
            "tighten opening",
            "--confirm-real-feedback",
        ]
    )

    assert exit_code == 2
    assert not hard_evidence_dir(tmp_path).exists()


def test_preflights_confirmed_timed_rehearsal_without_writing_hard_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    module = load_preflight_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "timer_note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real timed rehearsal observer note", encoding="utf-8")

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
    payload = json.loads(capsys.readouterr().out)
    assert payload["ledger_acceptance"] == {
        "category": "timed_rehearsal",
        "will_count_as_hard_evidence": True,
        "will_enter_rejected_metadata_records": False,
        "completion_gate_effect": "recorded metadata can satisfy timed_rehearsal after ledger rebuild",
        "reasons": [],
    }
    assert not hard_evidence_dir(tmp_path).exists()


def test_refuses_timed_rehearsal_preflight_with_blank_observer(tmp_path: Path) -> None:
    module = load_preflight_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "timer_note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real timed rehearsal observer note", encoding="utf-8")

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
    assert not hard_evidence_dir(tmp_path).exists()


def test_refuses_timed_rehearsal_preflight_without_real_confirmation(tmp_path: Path) -> None:
    module = load_preflight_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "timer_note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real timed rehearsal observer note", encoding="utf-8")

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
    assert not hard_evidence_dir(tmp_path).exists()


def test_refuses_timed_rehearsal_preflight_with_json_source(tmp_path: Path) -> None:
    module = load_preflight_module()
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
    assert not hard_evidence_dir(tmp_path).exists()


def test_preflights_over_limit_timed_rehearsal_as_archivable_but_not_accepted(tmp_path: Path, capsys) -> None:
    module = load_preflight_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "timer_note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real timed rehearsal observer note", encoding="utf-8")

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
    payload = json.loads(capsys.readouterr().out)
    assert payload["validated_metadata"]["timing_acceptance_pass"] is False
    assert "opening_actual_seconds=91 exceeds 90" in payload["validated_metadata"]["timing_acceptance_failures"]
    assert payload["ledger_acceptance"]["category"] == "timed_rehearsal"
    assert payload["ledger_acceptance"]["will_count_as_hard_evidence"] is False
    assert payload["ledger_acceptance"]["will_enter_rejected_metadata_records"] is True
    assert payload["ledger_acceptance"]["completion_gate_effect"] == (
        "recorded metadata will be archived but will not satisfy timed_rehearsal until a passing rehearsal is recorded"
    )
    assert "opening_actual_seconds=91 exceeds 90" in payload["ledger_acceptance"]["reasons"]
    assert not hard_evidence_dir(tmp_path).exists()


def test_refuses_timed_rehearsal_preflight_with_future_rehearsal_date(tmp_path: Path) -> None:
    module = load_preflight_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "timer_note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real timed rehearsal observer note", encoding="utf-8")

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
    assert not hard_evidence_dir(tmp_path).exists()


def test_refuses_timed_rehearsal_preflight_with_wrong_killer_question_count(tmp_path: Path) -> None:
    module = load_preflight_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "timer_note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real timed rehearsal observer note", encoding="utf-8")

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
            "--confirm-real-rehearsal",
        ]
    )

    assert exit_code == 2
    assert not hard_evidence_dir(tmp_path).exists()
