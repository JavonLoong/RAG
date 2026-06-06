from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTPUT_JSON = OUTPUT_DIR / "hard_evidence_closure_board.json"
OUTPUT_MD = OUTPUT_DIR / "hard_evidence_closure_board.md"

REPORT_TYPE = "challenge_cup_hard_evidence_closure_board"
STATUS = "awaiting_real_external_evidence_closure"
REQUIRED_BEFORE_GOAL_COMPLETION = ["expert_feedback", "timed_rehearsal"]
BOUNDARY = (
    "This closure board is an execution control artifact. It does not satisfy goal completion, "
    "does not prove expert feedback, and does not prove a timed rehearsal was completed."
)


def configure_paths(repo_root: Path) -> None:
    global REPO_ROOT, OUTPUT_DIR, OUTPUT_JSON, OUTPUT_MD

    REPO_ROOT = repo_root
    OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
    OUTPUT_JSON = OUTPUT_DIR / "hard_evidence_closure_board.json"
    OUTPUT_MD = OUTPUT_DIR / "hard_evidence_closure_board.md"


def repo_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def closure_streams() -> list[dict[str, Any]]:
    return [
        {
            "category": "expert_feedback",
            "closure_phase": "collect_real_external_feedback",
            "target_min_count": 1,
            "current_collected_count": 0,
            "required_source_examples": [
                "signed_feedback_form",
                "email_reply",
                "meeting_minutes",
                "chat_screenshot",
            ],
            "ready_to_execute_commands": [
                "python scripts/record_challenge_cup_expert_outreach.py --id advisor-a-20260606 --source <real-outreach-proof> --recipient-alias advisor-a --recipient-role advisor --channel email --sent-date 2026-06-06 --status sent --requested-review-dimension practicality --requested-review-dimension innovation --requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/00_项目一页纸.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date 2026-06-09 --confirm-real-outreach",
                "python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id advisor-a --source <real-feedback-file> --evidence-type email_reply --reviewer-identity advisor-a --role-or-org advisor --review-date 2026-06-06 --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback",
            ],
            "post_collection_commands": [
                "python scripts/build_challenge_cup_hard_evidence_ledger.py",
                "python scripts/build_challenge_cup_package.py",
                "python scripts/check_challenge_cup_readiness.py",
                "python scripts/check_challenge_cup_goal_completion.py",
            ],
            "acceptance_gate": "hard_evidence_ledger.categories.expert_feedback.collected_count >= 1",
        },
        {
            "category": "timed_rehearsal",
            "closure_phase": "run_real_timed_rehearsal",
            "target_min_count": 1,
            "current_collected_count": 0,
            "required_source_examples": [
                "timer_screenshot",
                "screen_recording",
                "observer_note",
                "missed_question_list",
            ],
            "ready_to_execute_commands": [
                "python scripts/record_challenge_cup_timed_rehearsal_schedule.py --id rehearsal-schedule-20260606 --source <real-calendar-or-observer-prep-file> --scheduled-date 2026-06-06 --observer observer-a --venue-or-channel meeting-room-a --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible --checklist-item browser-smoke-opened --checklist-item offline-archive-ready --checklist-item five-killer-questions-assigned --confirm-real-schedule",
                "python scripts/run_challenge_cup_timed_rehearsal.py --id rehearsal-1 --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal",
                "python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal --id rehearsal-1 --source <real-timer-or-observer-file> --evidence-type observer_note --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal",
            ],
            "post_collection_commands": [
                "python scripts/build_challenge_cup_hard_evidence_ledger.py",
                "python scripts/build_challenge_cup_package.py",
                "python scripts/check_challenge_cup_readiness.py",
                "python scripts/check_challenge_cup_goal_completion.py",
            ],
            "acceptance_gate": "hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1",
        },
    ]


def build_payload() -> dict[str, Any]:
    streams = closure_streams()
    return {
        "report_type": REPORT_TYPE,
        "status": STATUS,
        "no_completion_claimed": True,
        "does_not_satisfy_goal_completion": True,
        "boundary": BOUNDARY,
        "required_before_goal_completion": REQUIRED_BEFORE_GOAL_COMPLETION,
        "blocker_count": len(REQUIRED_BEFORE_GOAL_COMPLETION),
        "closure_streams": streams,
        "post_closure_verification_commands": [
            "python scripts/build_challenge_cup_hard_evidence_ledger.py",
            "python scripts/build_challenge_cup_package.py",
            "python scripts/check_challenge_cup_readiness.py",
            "python scripts/check_challenge_cup_goal_completion.py",
        ],
        "ledger_files": [
            repo_path(OUTPUT_MD),
            repo_path(OUTPUT_JSON),
        ],
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Hard Evidence Closure Board",
        "",
        f"- report_type: `{payload['report_type']}`",
        f"- status: `{payload['status']}`",
        f"- no_completion_claimed: `{payload['no_completion_claimed']}`",
        f"- does_not_satisfy_goal_completion: `{payload['does_not_satisfy_goal_completion']}`",
        f"- boundary: {payload['boundary']}",
        "",
        "## Closure Streams",
        "",
        "| Category | Phase | Target | Current | Acceptance Gate |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for stream in payload["closure_streams"]:
        lines.append(
            "| {category} | {closure_phase} | {target_min_count} | {current_collected_count} | `{acceptance_gate}` |".format(
                **stream
            )
        )
    lines.extend(["", "## Ready Commands", ""])
    for stream in payload["closure_streams"]:
        lines.extend([f"### {stream['category']}", ""])
        lines.extend(f"- `{command}`" for command in stream["ready_to_execute_commands"])
    lines.extend(["", "## Post-Closure Verification", ""])
    lines.extend(f"- `{command}`" for command in payload["post_closure_verification_commands"])
    write_text(path, "\n".join(lines))


def write_outputs(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or build_payload()
    write_text(OUTPUT_JSON, json.dumps(payload, ensure_ascii=False, indent=2))
    write_markdown(OUTPUT_MD, payload)
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"hard evidence closure board: {repo_path(OUTPUT_MD)}")
    print(f"hard evidence closure blockers: {payload['blocker_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
