from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "record_challenge_cup_timed_rehearsal_schedule.py"


def load_schedule_module():
    spec = importlib.util.spec_from_file_location("record_challenge_cup_timed_rehearsal_schedule", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def schedule_args(source: Path, *extra: str) -> list[str]:
    return [
        "--id",
        "rehearsal-schedule-20260606",
        "--source",
        str(source),
        "--scheduled-date",
        "2026-06-06",
        "--observer",
        "observer-a",
        "--venue-or-channel",
        "meeting-room-a",
        "--status",
        "scheduled",
        "--opening-planned-seconds",
        "90",
        "--demo-planned-seconds",
        "180",
        "--offline-fallback-planned-seconds",
        "20",
        "--killer-question-planned-seconds",
        "30",
        "--killer-question-count",
        "5",
        "--checklist-item",
        "timer visible to observer",
        "--checklist-item",
        "browser smoke report opened",
        "--checklist-item",
        "offline fallback archive ready",
        "--checklist-item",
        "five killer questions assigned",
        *extra,
    ]


def test_refuses_to_write_without_real_schedule_confirmation(tmp_path: Path) -> None:
    module = load_schedule_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "calendar_invite.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real rehearsal calendar invite", encoding="utf-8")

    exit_code = module.main(schedule_args(source))

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_records_confirmed_timed_rehearsal_schedule_and_refreshes_ledger(tmp_path: Path) -> None:
    module = load_schedule_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "calendar_invite.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real rehearsal calendar invite", encoding="utf-8")

    exit_code = module.main(schedule_args(source, "--confirm-real-schedule"))

    assert exit_code == 0
    schedule_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "timed_rehearsal_schedule"
    copied_source = schedule_dir / "rehearsal-schedule-20260606.txt"
    metadata_path = schedule_dir / "rehearsal-schedule-20260606.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert copied_source.read_text(encoding="utf-8") == "real rehearsal calendar invite"
    assert metadata == {
        "schedule_type": "timed_rehearsal_schedule",
        "scheduled_date": "2026-06-06",
        "observer": "observer-a",
        "venue_or_channel": "meeting-room-a",
        "status": "scheduled",
        "schedule_source_path": (
            "docs/challenge_cup/reproducibility/timed_rehearsal_schedule/rehearsal-schedule-20260606.txt"
        ),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "planned_timing_targets": {
            "opening_planned_seconds": 90,
            "demo_planned_seconds": 180,
            "offline_fallback_planned_seconds": 20,
            "killer_question_planned_seconds": 30,
            "killer_question_count": 5,
        },
        "checklist_items": [
            "timer visible to observer",
            "browser smoke report opened",
            "offline fallback archive ready",
            "five killer questions assigned",
        ],
        "notes": [],
        "required_hard_evidence_after_run": [
            "timer_screenshot",
            "screen_recording",
            "observer_note",
            "missed_question_list",
        ],
        "no_timed_rehearsal_claimed": True,
        "does_not_satisfy_hard_evidence": True,
    }
    ledger = json.loads(
        (
            tmp_path
            / "docs"
            / "challenge_cup"
            / "reproducibility"
            / "timed_rehearsal_schedule_ledger.json"
        ).read_text(encoding="utf-8")
    )
    assert ledger["report_type"] == "challenge_cup_timed_rehearsal_schedule_ledger"
    assert ledger["status"] == "rehearsal_scheduled_awaiting_run"
    assert ledger["no_timed_rehearsal_claimed"] is True
    assert ledger["does_not_satisfy_goal_completion"] is True
    assert ledger["schedule_record_count"] == 2
    assert metadata["schedule_source_path"] in ledger["schedule_files"]


def test_refuses_duplicate_schedule_id_without_traceback(tmp_path: Path, capsys) -> None:
    module = load_schedule_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "calendar_invite.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real rehearsal calendar invite", encoding="utf-8")

    assert module.main(schedule_args(source, "--confirm-real-schedule")) == 0
    capsys.readouterr()

    exit_code = module.main(schedule_args(source, "--confirm-real-schedule"))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "metadata already exists" in captured.err
    assert "Traceback" not in captured.err


def test_rejects_empty_schedule_source_file(tmp_path: Path) -> None:
    module = load_schedule_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "calendar_invite.txt"
    source.parent.mkdir(parents=True)
    source.write_text("", encoding="utf-8")

    exit_code = module.main(schedule_args(source, "--confirm-real-schedule"))

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_rejects_json_schedule_source_file(tmp_path: Path) -> None:
    module = load_schedule_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "calendar_invite.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"scheduled": true}', encoding="utf-8")

    exit_code = module.main(schedule_args(source, "--confirm-real-schedule"))

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()


def test_rejects_under_scoped_or_not_timed_schedule(tmp_path: Path) -> None:
    module = load_schedule_module()
    module.configure_paths(tmp_path)
    source = tmp_path / "incoming" / "calendar_invite.txt"
    source.parent.mkdir(parents=True)
    source.write_text("real rehearsal calendar invite", encoding="utf-8")
    args = schedule_args(source, "--confirm-real-schedule")
    count_index = args.index("--killer-question-count")
    args[count_index + 1] = "4"
    first_checklist = args.index("--checklist-item")
    truncated_args = args[: first_checklist + 2] + ["--confirm-real-schedule"]

    exit_code = module.main(truncated_args)

    assert exit_code == 2
    assert not (tmp_path / "docs").exists()
