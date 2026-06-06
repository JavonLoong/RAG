from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import record_challenge_cup_hard_evidence as intake


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"


class RehearsalInputError(ValueError):
    pass


def configure_paths(repo_root: Path) -> None:
    global REPO_ROOT, OUTPUT_DIR

    REPO_ROOT = repo_root
    OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
    intake.configure_paths(repo_root)


def positive_seconds(value: str) -> int:
    seconds = int(value)
    if seconds <= 0:
        raise argparse.ArgumentTypeError("seconds must be positive")
    return seconds


def validate_args(args: argparse.Namespace) -> None:
    if not args.confirm_real_rehearsal:
        raise RehearsalInputError(
            "refusing to record evidence without --confirm-real-rehearsal; do not archive rehearsal data "
            "unless these seconds came from an actual timed run"
        )
    intake.parse_iso_date(args.rehearsal_date)
    try:
        intake.validate_timed_rehearsal_limits(args)
    except intake.HardEvidenceInputError as exc:
        raise RehearsalInputError(str(exc)) from exc


def build_rehearsal_note(args: argparse.Namespace) -> str:
    killer_lines = [
        f"- q{index}_actual_seconds: {seconds}"
        for index, seconds in enumerate(args.killer_question_seconds, start=1)
    ]
    note_lines = [
        "# Challenge Cup Timed Rehearsal Observer Note",
        "",
        "This observer note is generated from supplied measured seconds after a real timed rehearsal.",
        "It is a rehearsal timing attachment, not expert feedback or award endorsement.",
        "",
        f"id: {args.id}",
        f"rehearsal_date: {args.rehearsal_date}",
        f"observer: {args.observer}",
        "--confirm-real-rehearsal supplied: true",
        "",
        "## Timing Results",
        "",
        f"- opening_actual_seconds: {args.opening_actual_seconds}",
        f"- demo_actual_seconds: {args.demo_actual_seconds}",
        f"- offline_fallback_actual_seconds: {args.offline_fallback_actual_seconds}",
        "- killer_question_results:",
        *killer_lines,
    ]
    if args.note:
        note_lines.extend(["", "## Observer Notes", ""])
        note_lines.extend(f"- {item}" for item in args.note)
    return "\n".join(note_lines).rstrip() + "\n"


def build_intake_args(source: Path, args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        id=args.id,
        source=str(source),
        evidence_type="observer_note",
        rehearsal_date=args.rehearsal_date,
        observer=args.observer,
        opening_actual_seconds=args.opening_actual_seconds,
        demo_actual_seconds=args.demo_actual_seconds,
        offline_fallback_actual_seconds=args.offline_fallback_actual_seconds,
        killer_question_seconds=args.killer_question_seconds,
        confirm_real_rehearsal=True,
        force=args.force,
    )


def record_timed_rehearsal(args: argparse.Namespace) -> tuple[Path, Path, dict[str, Any]]:
    validate_args(args)
    with tempfile.TemporaryDirectory(prefix=f"{args.id}-timed-rehearsal-") as temp_root:
        source = Path(temp_root) / f"{args.id}.txt"
        source.write_text(build_rehearsal_note(args), encoding="utf-8")
        metadata_path, source_path = intake.record_timed_rehearsal(build_intake_args(source, args))
    payload = intake.ledger.write_outputs()
    return metadata_path, source_path, payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a real timed-rehearsal observer note from supplied measured seconds, archive it as "
            "Challenge Cup hard evidence, and refresh the hard-evidence ledger."
        )
    )
    parser.add_argument("--id", required=True, type=intake.safe_evidence_id)
    parser.add_argument("--rehearsal-date", required=True)
    parser.add_argument("--observer", required=True)
    parser.add_argument("--opening-actual-seconds", required=True, type=positive_seconds)
    parser.add_argument("--demo-actual-seconds", required=True, type=positive_seconds)
    parser.add_argument("--offline-fallback-actual-seconds", required=True, type=positive_seconds)
    parser.add_argument("--killer-question-seconds", nargs="+", required=True, type=positive_seconds)
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--confirm-real-rehearsal", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        metadata_path, source_path, payload = record_timed_rehearsal(args)
    except RehearsalInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Recorded timed rehearsal metadata: {intake.repo_path(metadata_path)}")
    print(f"Recorded timed rehearsal note: {intake.repo_path(source_path)}")
    print(
        "Hard evidence counts: "
        f"expert_feedback={payload['categories']['expert_feedback']['collected_count']}, "
        f"timed_rehearsal={payload['categories']['timed_rehearsal']['collected_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
