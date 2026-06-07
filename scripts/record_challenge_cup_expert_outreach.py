from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_challenge_cup_expert_outreach_ledger as ledger
from challenge_cup_hard_evidence_dates import parse_not_future_iso_date
from challenge_cup_hard_evidence_sources import sha256_file, source_attachment_failure


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTREACH_DIR = OUTPUT_DIR / "expert_feedback_outreach"

CHANNELS = {"email", "chat", "meeting", "phone", "in_person"}
STATUSES = {"sent", "followed_up", "no_response_yet", "declined"}
SAFE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{1,80}")


class OutreachInputError(ValueError):
    pass


def configure_paths(repo_root: Path) -> None:
    global REPO_ROOT, OUTPUT_DIR, OUTREACH_DIR

    REPO_ROOT = repo_root
    OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
    OUTREACH_DIR = OUTPUT_DIR / "expert_feedback_outreach"

    ledger.REPO_ROOT = REPO_ROOT
    ledger.OUTPUT_DIR = OUTPUT_DIR
    ledger.OUTPUT_JSON = OUTPUT_DIR / "expert_feedback_outreach_ledger.json"
    ledger.OUTPUT_MD = OUTPUT_DIR / "expert_feedback_outreach_ledger.md"
    ledger.OUTREACH_DIR = OUTREACH_DIR
    ledger.OUTREACH_README = OUTREACH_DIR / "README.md"


def repo_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def parse_iso_date(value: str) -> str:
    date.fromisoformat(value)
    return value


def parse_sent_date(value: str) -> str:
    try:
        parse_not_future_iso_date(value)
    except ValueError as exc:
        raise OutreachInputError("sent_date must be YYYY-MM-DD and not in the future") from exc
    return value


def safe_outreach_id(value: str) -> str:
    candidate = value.strip().lower()
    if not SAFE_ID_PATTERN.fullmatch(candidate):
        raise argparse.ArgumentTypeError("id must match [a-z0-9][a-z0-9_-]{1,80}")
    return candidate


def existing_source(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_file():
        raise FileNotFoundError(f"source outreach evidence file missing: {path}")
    return path


def valid_source_attachment(path_value: str) -> Path:
    source = existing_source(path_value)
    failure = source_attachment_failure(source)
    if failure:
        raise OutreachInputError(failure)
    return source


def valid_requested_attachment(path_value: str) -> str:
    posix = PurePosixPath(path_value)
    if posix.is_absolute() or ".." in posix.parts or "\\" in path_value:
        raise OutreachInputError(f"requested attachment path is unsafe: {path_value}")
    attachment = REPO_ROOT / path_value
    if not attachment.is_file() or attachment.stat().st_size <= 0:
        raise OutreachInputError(f"requested attachment path missing or empty: {path_value}")
    return path_value


def copy_source(source: Path, evidence_id: str, force: bool = False) -> Path:
    suffix = source.suffix or ".evidence"
    target = OUTREACH_DIR / f"{evidence_id}{suffix.lower()}"
    target.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = source.read_bytes()
    if target.exists() and target.read_bytes() != source_bytes and not force:
        raise FileExistsError(f"target source outreach already exists with different content: {repo_path(target)}")
    target.write_bytes(source_bytes)
    return target


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_metadata(path: Path, payload: dict[str, Any], *, force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"metadata already exists: {repo_path(path)}; use --force to overwrite")
    write_json(path, payload)


def validate_args(args: argparse.Namespace) -> None:
    if not args.confirm_real_outreach:
        raise OutreachInputError(
            "refusing to record outreach without --confirm-real-outreach; only archive real sent requests or follow-ups"
        )
    if args.channel not in CHANNELS:
        raise OutreachInputError(f"unsupported outreach channel: {args.channel}")
    if args.status not in STATUSES:
        raise OutreachInputError(f"unsupported outreach status: {args.status}")
    parse_sent_date(args.sent_date)
    if args.followup_due_date:
        parse_iso_date(args.followup_due_date)
    if len(args.requested_review_dimension) < 3:
        raise OutreachInputError("expert outreach needs at least three requested review dimensions")
    args.requested_attachment = [
        valid_requested_attachment(attachment)
        for attachment in args.requested_attachment
    ]


def record_outreach(args: argparse.Namespace) -> tuple[Path, Path, dict[str, Any]]:
    validate_args(args)
    source = valid_source_attachment(args.source)
    copied_source = copy_source(source, args.id, force=args.force)
    metadata = {
        "outreach_type": "expert_feedback_request",
        "recipient_alias": args.recipient_alias,
        "recipient_role": args.recipient_role,
        "channel": args.channel,
        "sent_date": args.sent_date,
        "status": args.status,
        "request_source_path": repo_path(copied_source),
        "source_sha256": sha256_file(copied_source),
        "requested_review_dimensions": args.requested_review_dimension,
        "requested_attachment_paths": args.requested_attachment,
        "followup_due_date": args.followup_due_date,
        "notes": args.note,
        "no_external_feedback_claimed": True,
        "does_not_satisfy_hard_evidence": True,
    }
    metadata_path = OUTREACH_DIR / f"{args.id}.json"
    write_metadata(metadata_path, metadata, force=args.force)
    payload = ledger.write_outputs()
    return metadata_path, copied_source, payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record real expert-feedback outreach without counting it as expert approval."
    )
    parser.add_argument("--id", required=True, type=safe_outreach_id)
    parser.add_argument("--source", required=True)
    parser.add_argument("--recipient-alias", required=True)
    parser.add_argument("--recipient-role", required=True)
    parser.add_argument("--channel", required=True, choices=sorted(CHANNELS))
    parser.add_argument("--sent-date", required=True)
    parser.add_argument("--status", required=True, choices=sorted(STATUSES))
    parser.add_argument("--requested-review-dimension", action="append", required=True)
    parser.add_argument("--requested-attachment", action="append", required=True)
    parser.add_argument("--followup-due-date")
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--confirm-real-outreach", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        metadata_path, source_path, payload = record_outreach(args)
    except (FileNotFoundError, FileExistsError, OutreachInputError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Recorded outreach metadata: {repo_path(metadata_path)}")
    print(f"Recorded outreach source: {repo_path(source_path)}")
    print(
        "Expert outreach counts: "
        f"metadata={payload['metadata_record_count']}, files={payload['outreach_record_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
