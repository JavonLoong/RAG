from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTPUT_JSON = OUTPUT_DIR / "expert_feedback_outreach_ledger.json"
OUTPUT_MD = OUTPUT_DIR / "expert_feedback_outreach_ledger.md"
OUTREACH_DIR = OUTPUT_DIR / "expert_feedback_outreach"
OUTREACH_README = OUTREACH_DIR / "README.md"

REPORT_TYPE = "challenge_cup_expert_feedback_outreach_ledger"
EMPTY_STATUS = "ready_to_send_no_outreach_recorded"
AWAITING_RESPONSE_STATUS = "outreach_recorded_awaiting_response"
BOUNDARY = (
    "Outreach records prove that a real request was sent or followed up. They do not prove expert "
    "approval and do not satisfy the expert_feedback hard-evidence requirement."
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


def outreach_files() -> list[str]:
    if not OUTREACH_DIR.exists():
        return []
    return sorted(repo_path(path) for path in OUTREACH_DIR.rglob("*") if path.is_file() and is_candidate_file(path))


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
        if payload.get("outreach_type") == "expert_feedback_request":
            records.append(payload)
    return records


def build_payload() -> dict[str, Any]:
    files = outreach_files()
    records = load_metadata(files)
    status = AWAITING_RESPONSE_STATUS if records else EMPTY_STATUS
    return {
        "report_type": REPORT_TYPE,
        "status": status,
        "no_external_feedback_claimed": True,
        "does_not_satisfy_goal_completion": True,
        "boundary": BOUNDARY,
        "outreach_dir": repo_path(OUTREACH_DIR),
        "outreach_record_count": len(files),
        "metadata_record_count": len(records),
        "recipient_aliases": sorted({str(record.get("recipient_alias")) for record in records}),
        "channels": sorted({str(record.get("channel")) for record in records}),
        "statuses": sorted({str(record.get("status")) for record in records}),
        "outreach_files": files,
        "required_next_step": (
            "Archive a real signed form, email reply, meeting minute, or chat screenshot with "
            "record_challenge_cup_hard_evidence.py expert_feedback after a response arrives."
        ),
        "rerun_commands": [
            "python scripts/build_challenge_cup_expert_outreach_ledger.py",
            "python scripts/build_challenge_cup_package.py",
            "python scripts/check_challenge_cup_readiness.py",
        ],
    }


def write_readme() -> None:
    write_text(
        OUTREACH_README,
        "\n".join(
            [
                "# Expert Feedback Outreach Intake",
                "",
                "This directory records real outbound expert-feedback requests and follow-ups.",
                BOUNDARY,
                "",
                "- Use `python scripts/record_challenge_cup_expert_outreach.py ... --confirm-real-outreach` after a real send or follow-up.",
                "- Keep the sent email receipt, chat record, meeting invite, or follow-up note as the source attachment.",
                "- Do not count outreach as expert feedback. A real response must be archived with `python scripts/record_challenge_cup_hard_evidence.py expert_feedback ...`.",
            ]
        ),
    )


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Expert Feedback Outreach Ledger",
        "",
        f"- report_type: `{payload['report_type']}`",
        f"- status: `{payload['status']}`",
        f"- no_external_feedback_claimed: `{payload['no_external_feedback_claimed']}`",
        f"- does_not_satisfy_goal_completion: `{payload['does_not_satisfy_goal_completion']}`",
        f"- boundary: {payload['boundary']}",
        f"- outreach_record_count: `{payload['outreach_record_count']}`",
        f"- metadata_record_count: `{payload['metadata_record_count']}`",
        "",
        "## Outreach Files",
        "",
    ]
    if payload["outreach_files"]:
        lines.extend(f"- `{relative}`" for relative in payload["outreach_files"])
    else:
        lines.append("- No real outbound request has been recorded yet.")
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
    print(f"expert feedback outreach ledger: {repo_path(OUTPUT_MD)}")
    print(
        "expert outreach counts: "
        f"metadata={payload['metadata_record_count']}, files={payload['outreach_record_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
