from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_challenge_cup_hard_evidence_ledger as ledger
from challenge_cup_hard_evidence_dates import parse_not_future_iso_date
from challenge_cup_hard_evidence_sources import sha256_file, source_attachment_failure
from challenge_cup_expert_review_dimensions import missing_required_review_dimension_groups


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
INTAKE_ROOT = OUTPUT_DIR / "hard_evidence"
EXPERT_DIR = INTAKE_ROOT / "expert_feedback"
REHEARSAL_DIR = INTAKE_ROOT / "timed_rehearsal"

EXPERT_EVIDENCE_TYPES = {"signed_feedback_form", "email_reply", "meeting_minutes", "chat_screenshot"}
REHEARSAL_EVIDENCE_TYPES = {"timer_screenshot", "screen_recording", "observer_note", "missed_question_list"}
SAFE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{1,80}")
TIMING_LIMITS = {
    "opening_actual_seconds": 90,
    "demo_actual_seconds": 180,
    "offline_fallback_actual_seconds": 20,
    "killer_question_actual_seconds": 30,
    "killer_question_count": 5,
}
SOURCE_ORIGIN_EXTERNAL_ATTACHMENT = "external_attachment"
SOURCE_ORIGIN_GENERATED_OBSERVER_NOTE = "generated_observer_note"


class HardEvidenceInputError(ValueError):
    pass


def configure_paths(repo_root: Path) -> None:
    global REPO_ROOT, OUTPUT_DIR, INTAKE_ROOT, EXPERT_DIR, REHEARSAL_DIR

    REPO_ROOT = repo_root
    OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
    INTAKE_ROOT = OUTPUT_DIR / "hard_evidence"
    EXPERT_DIR = INTAKE_ROOT / "expert_feedback"
    REHEARSAL_DIR = INTAKE_ROOT / "timed_rehearsal"

    ledger.REPO_ROOT = REPO_ROOT
    ledger.OUTPUT_DIR = OUTPUT_DIR
    ledger.OUTPUT_JSON = OUTPUT_DIR / "hard_evidence_ledger.json"
    ledger.OUTPUT_MD = OUTPUT_DIR / "hard_evidence_ledger.md"
    ledger.INTAKE_ROOT = INTAKE_ROOT
    ledger.EXPERT_DIR = EXPERT_DIR
    ledger.REHEARSAL_DIR = REHEARSAL_DIR
    ledger.ROOT_README = INTAKE_ROOT / "README.md"
    ledger.EXPERT_README = EXPERT_DIR / "README.md"
    ledger.REHEARSAL_README = REHEARSAL_DIR / "README.md"


def repo_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def parse_iso_date(value: str) -> str:
    try:
        parse_not_future_iso_date(value)
    except ValueError as exc:
        raise HardEvidenceInputError("date must be YYYY-MM-DD and not in the future") from exc
    return value


def safe_evidence_id(value: str) -> str:
    candidate = value.strip().lower()
    if not SAFE_ID_PATTERN.fullmatch(candidate):
        raise argparse.ArgumentTypeError("id must match [a-z0-9][a-z0-9_-]{1,80}")
    return candidate


def existing_source(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_file():
        raise FileNotFoundError(f"source evidence file missing: {path}")
    return path


def valid_source_attachment(path_value: str) -> Path:
    source = existing_source(path_value)
    failure = source_attachment_failure(source)
    if failure:
        raise HardEvidenceInputError(failure)
    return source


def required_nonempty_text(field: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HardEvidenceInputError(f"{field} must be non-empty text")
    return normalized


def required_nonempty_text_list(field: str, values: list[str]) -> list[str]:
    return [required_nonempty_text(f"{field}[{index}]", value) for index, value in enumerate(values, start=1)]


def validate_positive_timing(field: str, actual: int) -> None:
    if actual <= 0:
        raise HardEvidenceInputError(f"{field}={actual} must be positive")


def validate_timed_rehearsal_limits(args: argparse.Namespace) -> None:
    if len(args.killer_question_seconds) != TIMING_LIMITS["killer_question_count"]:
        raise HardEvidenceInputError("timed rehearsal needs exactly five killer-question timings")

    timing_fields = {
        "opening_actual_seconds": args.opening_actual_seconds,
        "demo_actual_seconds": args.demo_actual_seconds,
        "offline_fallback_actual_seconds": args.offline_fallback_actual_seconds,
    }
    for field, actual in timing_fields.items():
        validate_positive_timing(field, actual)

    for index, actual in enumerate(args.killer_question_seconds, start=1):
        validate_positive_timing(f"killer_question_seconds[{index}]", actual)


def timed_rehearsal_acceptance_failures(args: argparse.Namespace) -> list[str]:
    failures: list[str] = []
    timing_fields = {
        "opening_actual_seconds": args.opening_actual_seconds,
        "demo_actual_seconds": args.demo_actual_seconds,
        "offline_fallback_actual_seconds": args.offline_fallback_actual_seconds,
    }
    for field, actual in timing_fields.items():
        limit = TIMING_LIMITS[field]
        if actual > limit:
            failures.append(f"{field}={actual} exceeds {limit}")

    question_limit = TIMING_LIMITS["killer_question_actual_seconds"]
    for index, actual in enumerate(args.killer_question_seconds, start=1):
        if actual > question_limit:
            failures.append(f"killer_question_seconds[{index}]={actual} exceeds {question_limit}")
    return failures


def copy_source(source: Path, target_dir: Path, evidence_id: str, force: bool = False) -> Path:
    suffix = source.suffix or ".evidence"
    target = target_dir / f"{evidence_id}{suffix.lower()}"
    target.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = source.read_bytes()
    if target.exists() and target.read_bytes() != source_bytes and not force:
        raise FileExistsError(f"target source evidence already exists with different content: {repo_path(target)}")
    target.write_bytes(source_bytes)
    return target


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record_expert_feedback(args: argparse.Namespace) -> tuple[Path, Path]:
    if not args.confirm_real_feedback:
        raise HardEvidenceInputError(
            "refusing to record expert feedback without --confirm-real-feedback; do not archive feedback "
            "unless the source is a real signed form, email reply, meeting minute, or chat screenshot"
        )
    if args.evidence_type not in EXPERT_EVIDENCE_TYPES:
        raise ValueError(f"unsupported expert feedback evidence_type: {args.evidence_type}")
    reviewer_identity = required_nonempty_text("reviewer_identity", args.reviewer_identity)
    role_or_org = required_nonempty_text("role_or_org", args.role_or_org)
    review_dimensions = required_nonempty_text_list("review_dimension", args.review_dimension)
    remediation_issue = required_nonempty_text("remediation_issue", args.remediation_issue)
    remediation_action = required_nonempty_text("remediation_action", args.remediation_action)
    if len(review_dimensions) < 3:
        raise ValueError("expert feedback needs at least three review dimensions")
    missing_dimension_groups = missing_required_review_dimension_groups(review_dimensions)
    if missing_dimension_groups:
        raise HardEvidenceInputError(
            "expert feedback missing required review dimension groups: "
            + ", ".join(missing_dimension_groups)
        )
    review_date = parse_iso_date(args.review_date)
    source = valid_source_attachment(args.source)
    copied_source = copy_source(source, EXPERT_DIR, args.id, force=args.force)
    metadata = {
        "evidence_type": args.evidence_type,
        "reviewer_identity": reviewer_identity,
        "role_or_org": role_or_org,
        "review_date": review_date,
        "feedback_source_path": repo_path(copied_source),
        "source_sha256": sha256_file(copied_source),
        "source_origin": SOURCE_ORIGIN_EXTERNAL_ATTACHMENT,
        "review_dimensions": review_dimensions,
        "remediation_record": [{"issue": remediation_issue, "action": remediation_action}],
        "real_feedback_confirmed": True,
    }
    metadata_path = EXPERT_DIR / f"{args.id}.json"
    write_json(metadata_path, metadata)
    return metadata_path, copied_source


def record_timed_rehearsal(args: argparse.Namespace) -> tuple[Path, Path]:
    if not args.confirm_real_rehearsal:
        raise HardEvidenceInputError(
            "refusing to record timed rehearsal without --confirm-real-rehearsal; do not archive rehearsal data "
            "unless these timings came from an actual observed run"
        )
    if args.evidence_type not in REHEARSAL_EVIDENCE_TYPES:
        raise ValueError(f"unsupported timed rehearsal evidence_type: {args.evidence_type}")
    observer = required_nonempty_text("observer", args.observer)
    rehearsal_date = parse_iso_date(args.rehearsal_date)
    validate_timed_rehearsal_limits(args)
    source = valid_source_attachment(args.source)
    copied_source = copy_source(source, REHEARSAL_DIR, args.id, force=args.force)
    timing_failures = timed_rehearsal_acceptance_failures(args)
    source_origin = getattr(args, "source_origin", SOURCE_ORIGIN_EXTERNAL_ATTACHMENT)
    metadata = {
        "evidence_type": args.evidence_type,
        "rehearsal_date": rehearsal_date,
        "observer": observer,
        "opening_actual_seconds": args.opening_actual_seconds,
        "demo_actual_seconds": args.demo_actual_seconds,
        "offline_fallback_actual_seconds": args.offline_fallback_actual_seconds,
        "killer_question_results": [
            {"question_index": index, "actual_seconds": seconds}
            for index, seconds in enumerate(args.killer_question_seconds, start=1)
        ],
        "recording_or_timer_source_path": repo_path(copied_source),
        "source_sha256": sha256_file(copied_source),
        "source_origin": source_origin,
        "timing_acceptance_pass": not timing_failures,
        "timing_acceptance_failures": timing_failures,
        "real_rehearsal_confirmed": True,
    }
    metadata_path = REHEARSAL_DIR / f"{args.id}.json"
    write_json(metadata_path, metadata)
    return metadata_path, copied_source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record real Challenge Cup hard evidence and refresh the hard-evidence ledger."
    )
    subparsers = parser.add_subparsers(dest="category", required=True)

    expert = subparsers.add_parser("expert_feedback", help="Record real expert feedback evidence.")
    expert.add_argument("--id", required=True, type=safe_evidence_id)
    expert.add_argument("--source", required=True)
    expert.add_argument("--evidence-type", required=True, choices=sorted(EXPERT_EVIDENCE_TYPES))
    expert.add_argument("--reviewer-identity", required=True)
    expert.add_argument("--role-or-org", required=True)
    expert.add_argument("--review-date", required=True)
    expert.add_argument("--review-dimension", action="append", required=True)
    expert.add_argument("--remediation-issue", required=True)
    expert.add_argument("--remediation-action", required=True)
    expert.add_argument("--confirm-real-feedback", action="store_true")
    expert.add_argument("--force", action="store_true")

    rehearsal = subparsers.add_parser("timed_rehearsal", help="Record real timed rehearsal evidence.")
    rehearsal.add_argument("--id", required=True, type=safe_evidence_id)
    rehearsal.add_argument("--source", required=True)
    rehearsal.add_argument("--evidence-type", required=True, choices=sorted(REHEARSAL_EVIDENCE_TYPES))
    rehearsal.add_argument("--rehearsal-date", required=True)
    rehearsal.add_argument("--observer", required=True)
    rehearsal.add_argument("--opening-actual-seconds", required=True, type=int)
    rehearsal.add_argument("--demo-actual-seconds", required=True, type=int)
    rehearsal.add_argument("--offline-fallback-actual-seconds", required=True, type=int)
    rehearsal.add_argument("--killer-question-seconds", nargs="+", required=True, type=int)
    rehearsal.add_argument("--confirm-real-rehearsal", action="store_true")
    rehearsal.add_argument("--force", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.category == "expert_feedback":
            metadata_path, source_path = record_expert_feedback(args)
        elif args.category == "timed_rehearsal":
            metadata_path, source_path = record_timed_rehearsal(args)
        else:
            raise ValueError(f"unsupported hard evidence category: {args.category}")
    except HardEvidenceInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    payload = ledger.write_outputs()
    print(f"Recorded metadata: {repo_path(metadata_path)}")
    print(f"Recorded source: {repo_path(source_path)}")
    print(
        "Hard evidence counts: "
        f"expert_feedback={payload['categories']['expert_feedback']['collected_count']}, "
        f"timed_rehearsal={payload['categories']['timed_rehearsal']['collected_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
