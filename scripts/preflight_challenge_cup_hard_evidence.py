from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import record_challenge_cup_hard_evidence as intake


REPO_ROOT = Path(__file__).resolve().parents[1]
TIMING_LIMITS = intake.TIMING_LIMITS


class PreflightInputError(ValueError):
    pass


def configure_paths(repo_root: Path) -> None:
    global REPO_ROOT

    REPO_ROOT = repo_root
    intake.configure_paths(repo_root)


def repo_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def positive_seconds(value: str) -> int:
    seconds = int(value)
    if seconds <= 0:
        raise argparse.ArgumentTypeError("seconds must be positive")
    return seconds


def nonempty_source(path_value: str) -> Path:
    try:
        return intake.valid_source_attachment(path_value)
    except intake.HardEvidenceInputError as exc:
        raise PreflightInputError(str(exc)) from exc


def target_source_path(source: Path, target_dir: Path, evidence_id: str) -> Path:
    suffix = source.suffix or ".evidence"
    return target_dir / f"{evidence_id}{suffix.lower()}"


def base_payload(category: str, args: argparse.Namespace, source: Path, target_dir: Path) -> dict[str, Any]:
    return {
        "report_type": "challenge_cup_hard_evidence_preflight",
        "status": "pass",
        "category": category,
        "dry_run": True,
        "does_not_write_hard_evidence": True,
        "source_path": repo_path(source),
        "would_copy_source_to": repo_path(target_source_path(source, target_dir, args.id)),
        "would_write_metadata_to": repo_path(target_dir / f"{args.id}.json"),
        "boundary": "Preflight validates inputs only; it does not archive evidence or satisfy goal completion.",
    }


def preflight_expert_feedback(args: argparse.Namespace) -> dict[str, Any]:
    if not args.confirm_real_feedback:
        raise PreflightInputError(
            "refusing expert feedback preflight without --confirm-real-feedback; use only with a real feedback source"
        )
    if args.evidence_type not in intake.EXPERT_EVIDENCE_TYPES:
        raise PreflightInputError(f"unsupported expert feedback evidence_type: {args.evidence_type}")
    if len(args.review_dimension) < 3:
        raise PreflightInputError("expert feedback preflight needs at least three review dimensions")
    missing_dimension_groups = intake.missing_required_review_dimension_groups(args.review_dimension)
    if missing_dimension_groups:
        raise PreflightInputError(
            "expert feedback preflight missing required review dimension groups: "
            + ", ".join(missing_dimension_groups)
        )
    intake.parse_iso_date(args.review_date)
    source = nonempty_source(args.source)
    payload = base_payload("expert_feedback", args, source, intake.EXPERT_DIR)
    payload["validated_metadata"] = {
        "evidence_type": args.evidence_type,
        "reviewer_identity": args.reviewer_identity,
        "role_or_org": args.role_or_org,
        "review_date": args.review_date,
        "review_dimension_count": len(args.review_dimension),
        "has_remediation_record": bool(args.remediation_issue and args.remediation_action),
        "real_feedback_confirmed": True,
    }
    return payload


def preflight_timed_rehearsal(args: argparse.Namespace) -> dict[str, Any]:
    if not args.confirm_real_rehearsal:
        raise PreflightInputError(
            "refusing timed rehearsal preflight without --confirm-real-rehearsal; use only after an actual observed run"
        )
    if args.evidence_type not in intake.REHEARSAL_EVIDENCE_TYPES:
        raise PreflightInputError(f"unsupported timed rehearsal evidence_type: {args.evidence_type}")
    intake.parse_iso_date(args.rehearsal_date)
    source = nonempty_source(args.source)
    try:
        intake.validate_timed_rehearsal_limits(args)
    except intake.HardEvidenceInputError as exc:
        raise PreflightInputError(str(exc)) from exc
    timing_fields = {
        "opening_actual_seconds": args.opening_actual_seconds,
        "demo_actual_seconds": args.demo_actual_seconds,
        "offline_fallback_actual_seconds": args.offline_fallback_actual_seconds,
    }

    payload = base_payload("timed_rehearsal", args, source, intake.REHEARSAL_DIR)
    payload["validated_metadata"] = {
        "evidence_type": args.evidence_type,
        "rehearsal_date": args.rehearsal_date,
        "observer": args.observer,
        **timing_fields,
        "killer_question_count": len(args.killer_question_seconds),
        "max_killer_question_seconds": max(args.killer_question_seconds),
        "real_rehearsal_confirmed": True,
    }
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preflight real Challenge Cup hard-evidence inputs without copying files or refreshing ledgers."
    )
    subparsers = parser.add_subparsers(dest="category", required=True)

    expert = subparsers.add_parser("expert_feedback", help="Dry-run real expert feedback intake.")
    expert.add_argument("--id", required=True, type=intake.safe_evidence_id)
    expert.add_argument("--source", required=True)
    expert.add_argument("--evidence-type", required=True, choices=sorted(intake.EXPERT_EVIDENCE_TYPES))
    expert.add_argument("--reviewer-identity", required=True)
    expert.add_argument("--role-or-org", required=True)
    expert.add_argument("--review-date", required=True)
    expert.add_argument("--review-dimension", action="append", required=True)
    expert.add_argument("--remediation-issue", required=True)
    expert.add_argument("--remediation-action", required=True)
    expert.add_argument("--confirm-real-feedback", action="store_true")

    rehearsal = subparsers.add_parser("timed_rehearsal", help="Dry-run real timed rehearsal intake.")
    rehearsal.add_argument("--id", required=True, type=intake.safe_evidence_id)
    rehearsal.add_argument("--source", required=True)
    rehearsal.add_argument("--evidence-type", required=True, choices=sorted(intake.REHEARSAL_EVIDENCE_TYPES))
    rehearsal.add_argument("--rehearsal-date", required=True)
    rehearsal.add_argument("--observer", required=True)
    rehearsal.add_argument("--opening-actual-seconds", required=True, type=positive_seconds)
    rehearsal.add_argument("--demo-actual-seconds", required=True, type=positive_seconds)
    rehearsal.add_argument("--offline-fallback-actual-seconds", required=True, type=positive_seconds)
    rehearsal.add_argument("--killer-question-seconds", nargs="+", required=True, type=positive_seconds)
    rehearsal.add_argument("--confirm-real-rehearsal", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.category == "expert_feedback":
            payload = preflight_expert_feedback(args)
        elif args.category == "timed_rehearsal":
            payload = preflight_timed_rehearsal(args)
        else:
            raise PreflightInputError(f"unsupported hard evidence category: {args.category}")
    except (FileNotFoundError, PreflightInputError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
