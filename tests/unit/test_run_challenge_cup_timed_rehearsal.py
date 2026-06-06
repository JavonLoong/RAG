from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "run_challenge_cup_timed_rehearsal.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("run_challenge_cup_timed_rehearsal", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def timed_rehearsal_args(*extra: str) -> list[str]:
    return [
        "--id",
        "rehearsal-1",
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
        *extra,
    ]


def test_refuses_to_write_without_real_rehearsal_confirmation(tmp_path: Path) -> None:
    module = load_runner_module()
    module.configure_paths(tmp_path)

    exit_code = module.main(timed_rehearsal_args())

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_refuses_to_write_with_blank_observer(tmp_path: Path) -> None:
    module = load_runner_module()
    module.configure_paths(tmp_path)

    args = timed_rehearsal_args("--confirm-real-rehearsal")
    observer_index = args.index("--observer")
    args[observer_index + 1] = "   "
    exit_code = module.main(args)

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_records_confirmed_timed_rehearsal_note_and_refreshes_ledger(tmp_path: Path) -> None:
    module = load_runner_module()
    module.configure_paths(tmp_path)

    exit_code = module.main(timed_rehearsal_args("--confirm-real-rehearsal"))

    assert exit_code == 0
    evidence_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "timed_rehearsal"
    copied_note = evidence_dir / "rehearsal-1.txt"
    metadata_path = evidence_dir / "rehearsal-1.json"
    note = copied_note.read_text(encoding="utf-8")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert "observer-a" in note
    assert "opening_actual_seconds: 88" in note
    assert "--confirm-real-rehearsal supplied: true" in note
    assert metadata["evidence_type"] == "observer_note"
    assert metadata["source_origin"] == "generated_observer_note"
    assert metadata["recording_or_timer_source_path"] == (
        "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt"
    )
    assert metadata["killer_question_results"] == [
        {"question_index": 1, "actual_seconds": 25},
        {"question_index": 2, "actual_seconds": 26},
        {"question_index": 3, "actual_seconds": 27},
        {"question_index": 4, "actual_seconds": 28},
        {"question_index": 5, "actual_seconds": 29},
    ]
    ledger = json.loads(
        (tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["status"] == "awaiting_real_external_feedback_and_timed_rehearsal"
    assert ledger["completion_claim_allowed"] is False
    assert ledger["categories"]["expert_feedback"]["collected_count"] == 0
    rehearsal = ledger["categories"]["timed_rehearsal"]
    assert rehearsal["collected_count"] == 0
    assert rehearsal["evidence_records"] == []
    assert "source_origin must be external_attachment" in rehearsal["rejected_metadata_records"][0]["reasons"]


def test_records_external_timed_rehearsal_source_and_refreshes_ledger(tmp_path: Path) -> None:
    module = load_runner_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "timer-screenshot.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real independent timer screenshot or observer source", encoding="utf-8")

    exit_code = module.main(timed_rehearsal_args("--source", str(source), "--confirm-real-rehearsal"))

    assert exit_code == 0
    evidence_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "timed_rehearsal"
    copied_source = evidence_dir / "rehearsal-1.txt"
    metadata_path = evidence_dir / "rehearsal-1.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert copied_source.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert metadata["source_origin"] == "external_attachment"
    ledger = json.loads(
        (tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["categories"]["timed_rehearsal"]["collected_count"] == 1


def test_rejects_wrong_killer_question_count(tmp_path: Path) -> None:
    module = load_runner_module()
    module.configure_paths(tmp_path)

    args = timed_rehearsal_args("--confirm-real-rehearsal")
    killer_index = args.index("--killer-question-seconds")
    args = args[: killer_index + 1] + ["25", "26"] + ["--confirm-real-rehearsal"]
    exit_code = module.main(args)

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_archives_over_limit_timing_without_counting_it_complete(tmp_path: Path) -> None:
    module = load_runner_module()
    module.configure_paths(tmp_path)

    args = timed_rehearsal_args("--confirm-real-rehearsal")
    opening_index = args.index("--opening-actual-seconds")
    args[opening_index + 1] = "91"
    exit_code = module.main(args)

    assert exit_code == 0
    evidence_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence" / "timed_rehearsal"
    copied_note = evidence_dir / "rehearsal-1.txt"
    metadata_path = evidence_dir / "rehearsal-1.json"
    note = copied_note.read_text(encoding="utf-8")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert "opening_actual_seconds: 91" in note
    assert metadata["opening_actual_seconds"] == 91
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
    assert rehearsal["rejected_metadata_records"][0]["metadata_path"].endswith("rehearsal-1.json")
    assert "opening_actual_seconds=91 exceeds 90" in rehearsal["rejected_metadata_records"][0]["reasons"]
