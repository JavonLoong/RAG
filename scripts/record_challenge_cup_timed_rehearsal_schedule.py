from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_challenge_cup_timed_rehearsal_schedule_ledger as ledger
from challenge_cup_hard_evidence_sources import sha256_file, source_attachment_failure


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
SCHEDULE_DIR = OUTPUT_DIR / "timed_rehearsal_schedule"

STATUSES = {"scheduled", "rescheduled", "cancelled", "observer_ready"}
SAFE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{1,80}")
TIMING_LIMITS = {
    "opening_planned_seconds": 90,
    "demo_planned_seconds": 180,
    "offline_fallback_planned_seconds": 20,
    "killer_question_planned_seconds": 30,
    "killer_question_count": 5,
}
REQUIRED_HARD_EVIDENCE_AFTER_RUN = [
    "timer_screenshot",
    "screen_recording",
    "observer_note",
    "missed_question_list",
]


class ScheduleInputError(ValueError):
    pass


def configure_paths(repo_root: Path) -> None:
    global REPO_ROOT, OUTPUT_DIR, SCHEDULE_DIR

    REPO_ROOT = repo_root
    OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
    SCHEDULE_DIR = OUTPUT_DIR / "timed_rehearsal_schedule"

    ledger.REPO_ROOT = REPO_ROOT
    ledger.OUTPUT_DIR = OUTPUT_DIR
    ledger.OUTPUT_JSON = OUTPUT_DIR / "timed_rehearsal_schedule_ledger.json"
    ledger.OUTPUT_MD = OUTPUT_DIR / "timed_rehearsal_schedule_ledger.md"
    ledger.SCHEDULE_DIR = SCHEDULE_DIR
    ledger.SCHEDULE_README = SCHEDULE_DIR / "README.md"


def repo_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def parse_iso_date(value: str) -> str:
    date.fromisoformat(value)
    return value


def safe_schedule_id(value: str) -> str:
    candidate = value.strip().lower()
    if not SAFE_ID_PATTERN.fullmatch(candidate):
        raise argparse.ArgumentTypeError("id must match [a-z0-9][a-z0-9_-]{1,80}")
    return candidate


def existing_source(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_file():
        raise FileNotFoundError(f"source schedule evidence file missing: {path}")
    return path


def valid_source_attachment(path_value: str) -> Path:
    source = existing_source(path_value)
    failure = source_attachment_failure(source)
    if failure:
        raise ScheduleInputError(failure)
    return source


def copy_source(source: Path, evidence_id: str, force: bool = False) -> Path:
    suffix = source.suffix or ".evidence"
    target = SCHEDULE_DIR / f"{evidence_id}{suffix.lower()}"
    target.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = source.read_bytes()
    if target.exists() and target.read_bytes() != source_bytes and not force:
        raise FileExistsError(f"target source schedule already exists with different content: {repo_path(target)}")
    target.write_bytes(source_bytes)
    return target


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def positive_int(value: int, field: str) -> None:
    if value <= 0:
        raise ScheduleInputError(f"{field} must be positive")


def validate_args(args: argparse.Namespace) -> None:
    if not args.confirm_real_schedule:
        raise ScheduleInputError(
            "refusing to record schedule without --confirm-real-schedule; only archive real schedule records"
        )
    if args.status not in STATUSES:
        raise ScheduleInputError(f"unsupported schedule status: {args.status}")
    parse_iso_date(args.scheduled_date)
    planned = {
        "opening_planned_seconds": args.opening_planned_seconds,
        "demo_planned_seconds": args.demo_planned_seconds,
        "offline_fallback_planned_seconds": args.offline_fallback_planned_seconds,
        "killer_question_planned_seconds": args.killer_question_planned_seconds,
        "killer_question_count": args.killer_question_count,
    }
    for field, value in planned.items():
        positive_int(value, field)
        limit = TIMING_LIMITS[field]
        if field == "killer_question_count" and value != limit:
            raise ScheduleInputError(f"{field} must be exactly {limit}")
        if field != "killer_question_count" and value > limit:
            raise ScheduleInputError(f"{field}={value} exceeds {limit}")
    if len(args.checklist_item) < 4:
        raise ScheduleInputError("timed rehearsal schedule needs at least four checklist items")


def record_schedule(args: argparse.Namespace) -> tuple[Path, Path, dict[str, Any]]:
    validate_args(args)
    source = valid_source_attachment(args.source)
    copied_source = copy_source(source, args.id, force=args.force)
    metadata = {
        "schedule_type": "timed_rehearsal_schedule",
        "scheduled_date": args.scheduled_date,
        "observer": args.observer,
        "venue_or_channel": args.venue_or_channel,
        "status": args.status,
        "schedule_source_path": repo_path(copied_source),
        "source_sha256": sha256_file(copied_source),
        "planned_timing_targets": {
            "opening_planned_seconds": args.opening_planned_seconds,
            "demo_planned_seconds": args.demo_planned_seconds,
            "offline_fallback_planned_seconds": args.offline_fallback_planned_seconds,
            "killer_question_planned_seconds": args.killer_question_planned_seconds,
            "killer_question_count": args.killer_question_count,
        },
        "checklist_items": args.checklist_item,
        "notes": args.note,
        "required_hard_evidence_after_run": REQUIRED_HARD_EVIDENCE_AFTER_RUN,
        "no_timed_rehearsal_claimed": True,
        "does_not_satisfy_hard_evidence": True,
    }
    metadata_path = SCHEDULE_DIR / f"{args.id}.json"
    write_json(metadata_path, metadata)
    payload = ledger.write_outputs()
    return metadata_path, copied_source, payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record real timed-rehearsal scheduling without counting it as completed rehearsal evidence."
    )
    parser.add_argument("--id", required=True, type=safe_schedule_id)
    parser.add_argument("--source", required=True)
    parser.add_argument("--scheduled-date", required=True)
    parser.add_argument("--observer", required=True)
    parser.add_argument("--venue-or-channel", required=True)
    parser.add_argument("--status", required=True, choices=sorted(STATUSES))
    parser.add_argument("--opening-planned-seconds", required=True, type=int)
    parser.add_argument("--demo-planned-seconds", required=True, type=int)
    parser.add_argument("--offline-fallback-planned-seconds", required=True, type=int)
    parser.add_argument("--killer-question-planned-seconds", required=True, type=int)
    parser.add_argument("--killer-question-count", required=True, type=int)
    parser.add_argument("--checklist-item", action="append", required=True)
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--confirm-real-schedule", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        metadata_path, source_path, payload = record_schedule(args)
    except (FileNotFoundError, ScheduleInputError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Recorded timed rehearsal schedule metadata: {repo_path(metadata_path)}")
    print(f"Recorded timed rehearsal schedule source: {repo_path(source_path)}")
    print(
        "Timed rehearsal schedule counts: "
        f"metadata={payload['metadata_record_count']}, files={payload['schedule_record_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
