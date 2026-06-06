from __future__ import annotations

import importlib.util
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


def test_preflights_confirmed_expert_feedback_without_writing_hard_evidence(tmp_path: Path) -> None:
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


def test_preflights_confirmed_timed_rehearsal_without_writing_hard_evidence(tmp_path: Path) -> None:
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


def test_refuses_timed_rehearsal_preflight_with_over_limit_timing(tmp_path: Path) -> None:
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
