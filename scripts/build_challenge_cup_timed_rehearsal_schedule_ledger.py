from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTPUT_JSON = OUTPUT_DIR / "timed_rehearsal_schedule_ledger.json"
OUTPUT_MD = OUTPUT_DIR / "timed_rehearsal_schedule_ledger.md"
SCHEDULE_DIR = OUTPUT_DIR / "timed_rehearsal_schedule"
SCHEDULE_README = SCHEDULE_DIR / "README.md"

REPORT_TYPE = "challenge_cup_timed_rehearsal_schedule_ledger"
EMPTY_STATUS = "ready_to_schedule_no_rehearsal_recorded"
SCHEDULED_STATUS = "rehearsal_scheduled_awaiting_run"
BOUNDARY = (
    "Schedule records prove that a real timed rehearsal was scheduled or observer preparation was "
    "recorded. They do not prove a timed rehearsal was completed and do not satisfy the "
    "timed_rehearsal hard-evidence requirement."
)
PLACEHOLDER_NAME_FRAGMENTS = {"example", "placeholder", "sample", "template", "todo"}


def repo_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def is_candidate_file(path: Path) -> bool:
    name = path.name.lower()
    if path.name == "README.md" or name.startswith("."):
        return False
    return not any(fragment in name for fragment in PLACEHOLDER_NAME_FRAGMENTS)


def schedule_files() -> list[str]:
    if not SCHEDULE_DIR.exists():
        return []
    return sorted(repo_path(path) for path in SCHEDULE_DIR.rglob("*") if path.is_file() and is_candidate_file(path))


def load_metadata(files: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative in files:
        path = REPO_ROOT / relative
        if path.suffix.lower() != ".json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("schedule_type") == "timed_rehearsal_schedule":
            records.append(payload)
    return records


def build_payload() -> dict[str, Any]:
    files = schedule_files()
    records = load_metadata(files)
    status = SCHEDULED_STATUS if records else EMPTY_STATUS
    return {
        "report_type": REPORT_TYPE,
        "status": status,
        "no_timed_rehearsal_claimed": True,
        "does_not_satisfy_goal_completion": True,
        "boundary": BOUNDARY,
        "schedule_dir": repo_path(SCHEDULE_DIR),
        "schedule_record_count": len(files),
        "metadata_record_count": len(records),
        "observers": sorted({str(record.get("observer")) for record in records}),
        "statuses": sorted({str(record.get("status")) for record in records}),
        "schedule_files": files,
        "required_next_step": (
            "After the timed rehearsal is actually run, archive measured seconds and observer evidence "
            "with run_challenge_cup_timed_rehearsal.py --source <real-timer-or-observer-file> --confirm-real-rehearsal or "
            "record_challenge_cup_hard_evidence.py timed_rehearsal ... --confirm-real-rehearsal."
        ),
        "rerun_commands": [
            "python scripts/build_challenge_cup_timed_rehearsal_schedule_ledger.py",
            "python scripts/build_challenge_cup_package.py",
            "python scripts/check_challenge_cup_readiness.py",
        ],
    }


def write_readme() -> None:
    write_text(
        SCHEDULE_README,
        "\n".join(
            [
                "# Timed Rehearsal Schedule Intake",
                "",
                "This directory records real timed-rehearsal scheduling and observer-preparation records.",
                BOUNDARY,
                "",
                "- Use `python scripts/record_challenge_cup_timed_rehearsal_schedule.py ... --confirm-real-schedule` after a real calendar invite, meeting notice, or observer preparation note exists.",
                "- Keep the calendar invite, meeting notice, chat confirmation, or observer checklist as the source attachment.",
                "- The source attachment must be non-empty, must not be a JSON metadata file, and will be stored with source_sha256.",
                "- Do not count schedule records as timed rehearsal completion. A real run must be archived with `python scripts/run_challenge_cup_timed_rehearsal.py ... --source <real-timer-or-observer-file> --confirm-real-rehearsal` or `python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal ... --confirm-real-rehearsal`.",
            ]
        ),
    )


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Timed Rehearsal Schedule Ledger",
        "",
        f"- report_type: `{payload['report_type']}`",
        f"- status: `{payload['status']}`",
        f"- no_timed_rehearsal_claimed: `{payload['no_timed_rehearsal_claimed']}`",
        f"- does_not_satisfy_goal_completion: `{payload['does_not_satisfy_goal_completion']}`",
        f"- boundary: {payload['boundary']}",
        f"- schedule_record_count: `{payload['schedule_record_count']}`",
        f"- metadata_record_count: `{payload['metadata_record_count']}`",
        "",
        "## Schedule Files",
        "",
    ]
    if payload["schedule_files"]:
        lines.extend(f"- `{relative}`" for relative in payload["schedule_files"])
    else:
        lines.append("- No real timed rehearsal schedule has been recorded yet.")
    lines.extend(["", "## Required Next Step", "", payload["required_next_step"], "", "## Rerun Commands", ""])
    lines.extend(f"- `{command}`" for command in payload["rerun_commands"])
    write_text(path, "\n".join(lines))


def write_outputs(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    write_readme()
    payload = payload or build_payload()
    write_text(OUTPUT_JSON, json.dumps(payload, ensure_ascii=False, indent=2))
    write_markdown(OUTPUT_MD, payload)
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"timed rehearsal schedule ledger: {repo_path(OUTPUT_MD)}")
    print(
        "timed rehearsal schedule counts: "
        f"metadata={payload['metadata_record_count']}, files={payload['schedule_record_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
