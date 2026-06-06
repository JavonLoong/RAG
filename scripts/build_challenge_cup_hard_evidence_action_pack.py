from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTPUT_JSON = OUTPUT_DIR / "hard_evidence_action_pack.json"
OUTPUT_MD = OUTPUT_DIR / "hard_evidence_action_pack.md"

REPORT_TYPE = "challenge_cup_hard_evidence_action_pack"
STATUS = "ready_for_real_external_evidence_collection"
REQUIRED_BEFORE_GOAL_COMPLETION = ["expert_feedback", "timed_rehearsal"]
BOUNDARY = (
    "This action pack is a human handoff for collecting real external hard evidence. "
    "It does not satisfy goal completion, does not claim expert approval, and does not claim "
    "a timed rehearsal has been completed."
)
SOURCE_INTEGRITY_GUARDRAILS = [
    "preflight and record commands calculate source_sha256 from the real source attachment",
    "metadata source_sha256 must match the archived source attachment content",
    "--source must be the original evidence attachment, not the generated .json metadata summary; the source attachment must be non-empty and must not be a JSON metadata file",
    "do not edit or replace the source attachment after recording; changed bytes will fail readiness and goal gates",
]
EXPERT_OUTREACH_COMMAND = (
    "python scripts/record_challenge_cup_expert_outreach.py --id real-outreach-id "
    "--source path/to/real-outreach-proof.eml --recipient-alias real-reviewer-alias "
    "--recipient-role real-reviewer-role --channel email --sent-date YYYY-MM-DD "
    "--status sent --requested-review-dimension practicality --requested-review-dimension innovation "
    "--requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/00_项目一页纸.md "
    "--requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md "
    "--followup-due-date YYYY-MM-DD --confirm-real-outreach"
)
EXPERT_PREFLIGHT_COMMAND = (
    "python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback "
    "--id real-feedback-id --source path/to/real-feedback.eml --evidence-type email_reply "
    "--reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org "
    "--review-date YYYY-MM-DD --review-dimension practicality "
    "--review-dimension innovation --review-dimension boundary_rigor --remediation-issue issue "
    "--remediation-action action --confirm-real-feedback"
)
EXPERT_RECORD_COMMAND = (
    "python scripts/record_challenge_cup_hard_evidence.py expert_feedback "
    "--id real-feedback-id --source path/to/real-feedback.eml --evidence-type email_reply "
    "--reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org "
    "--review-date YYYY-MM-DD --review-dimension practicality "
    "--review-dimension innovation --review-dimension boundary_rigor --remediation-issue issue "
    "--remediation-action action --confirm-real-feedback"
)
REHEARSAL_SCHEDULE_COMMAND = (
    "python scripts/record_challenge_cup_timed_rehearsal_schedule.py "
    "--id real-rehearsal-schedule-id --source path/to/real-calendar-or-observer-prep-file.txt "
    "--scheduled-date YYYY-MM-DD --observer real-observer-alias "
    "--venue-or-channel real-venue-or-channel --status scheduled --opening-planned-seconds 90 "
    "--demo-planned-seconds 180 --offline-fallback-planned-seconds 20 "
    "--killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible "
    "--checklist-item browser-smoke-opened --checklist-item offline-archive-ready "
    "--checklist-item five-killer-questions-assigned --confirm-real-schedule"
)
REHEARSAL_RUN_COMMAND = (
    "python scripts/run_challenge_cup_timed_rehearsal.py --id real-rehearsal-id "
    "--rehearsal-date YYYY-MM-DD --observer real-observer-alias "
    "--opening-actual-seconds actual-opening-seconds --demo-actual-seconds actual-demo-seconds "
    "--offline-fallback-actual-seconds actual-offline-fallback-seconds "
    "--killer-question-seconds q1-seconds q2-seconds q3-seconds q4-seconds q5-seconds "
    "--confirm-real-rehearsal"
)
REHEARSAL_PREFLIGHT_COMMAND = (
    "python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal "
    "--id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --evidence-type observer_note "
    "--rehearsal-date YYYY-MM-DD --observer real-observer-alias "
    "--opening-actual-seconds actual-opening-seconds --demo-actual-seconds actual-demo-seconds "
    "--offline-fallback-actual-seconds actual-offline-fallback-seconds "
    "--killer-question-seconds q1-seconds q2-seconds q3-seconds q4-seconds q5-seconds "
    "--confirm-real-rehearsal"
)
REHEARSAL_RECORD_COMMAND = (
    "python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal "
    "--id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --evidence-type observer_note "
    "--rehearsal-date YYYY-MM-DD --observer real-observer-alias "
    "--opening-actual-seconds actual-opening-seconds --demo-actual-seconds actual-demo-seconds "
    "--offline-fallback-actual-seconds actual-offline-fallback-seconds "
    "--killer-question-seconds q1-seconds q2-seconds q3-seconds q4-seconds q5-seconds "
    "--confirm-real-rehearsal"
)
FAILED_REHEARSAL_ARCHIVAL_RULE = (
    "If any measured rehearsal segment exceeds the limit or a required killer-question timing is missing, "
    "still archive the real rehearsal evidence with timing_acceptance_pass=false; the hard evidence ledger "
    "must place the metadata in rejected_metadata_records and collected_count must not satisfy the acceptance gate."
)
POWERSHELL_PYTHON = ".\\.venv\\Scripts\\python.exe"


def powershell_repo_root() -> str:
    return str(REPO_ROOT).replace("'", "''")


def guarded_powershell_command(command: str) -> list[str]:
    return [command, "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }"]


def expert_feedback_powershell_block() -> list[str]:
    return [
        f"Set-Location '{powershell_repo_root()}'",
        "$feedbackId = 'advisor-a-YYYYMMDD-01'",
        "$feedbackSource = 'D:\\path\\to\\real-feedback.eml'",
        "$reviewDate = 'YYYY-MM-DD'",
        "$reviewer = 'real-reviewer-identity'",
        "$reviewerRole = 'real-reviewer-role-or-org'",
        "$remediationIssue = 'demo-pacing'",
        "$remediationAction = 'tighten-opening'",
        *guarded_powershell_command(
            f"{POWERSHELL_PYTHON} .\\scripts\\preflight_challenge_cup_hard_evidence.py expert_feedback --id $feedbackId --source $feedbackSource --evidence-type email_reply --reviewer-identity $reviewer --role-or-org $reviewerRole --review-date $reviewDate --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue $remediationIssue --remediation-action $remediationAction --confirm-real-feedback"
        ),
        *guarded_powershell_command(
            f"{POWERSHELL_PYTHON} .\\scripts\\record_challenge_cup_hard_evidence.py expert_feedback --id $feedbackId --source $feedbackSource --evidence-type email_reply --reviewer-identity $reviewer --role-or-org $reviewerRole --review-date $reviewDate --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue $remediationIssue --remediation-action $remediationAction --confirm-real-feedback"
        ),
    ]


def timed_rehearsal_powershell_block() -> list[str]:
    return [
        f"Set-Location '{powershell_repo_root()}'",
        "$rehearsalId = 'rehearsal-YYYYMMDD-01'",
        "$rehearsalDate = 'YYYY-MM-DD'",
        "$observer = 'real-observer-alias'",
        "$opening = 88",
        "$demo = 170",
        "$offline = 18",
        "$killer = 25,25,25,25,25",
        *guarded_powershell_command(
            f"{POWERSHELL_PYTHON} .\\scripts\\run_challenge_cup_timed_rehearsal.py --id $rehearsalId --rehearsal-date $rehearsalDate --observer $observer --opening-actual-seconds $opening --demo-actual-seconds $demo --offline-fallback-actual-seconds $offline --killer-question-seconds $killer --confirm-real-rehearsal"
        ),
    ]


def configure_paths(repo_root: Path) -> None:
    global REPO_ROOT, OUTPUT_DIR, OUTPUT_JSON, OUTPUT_MD

    REPO_ROOT = repo_root
    OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
    OUTPUT_JSON = OUTPUT_DIR / "hard_evidence_action_pack.json"
    OUTPUT_MD = OUTPUT_DIR / "hard_evidence_action_pack.md"


def repo_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def action_streams() -> list[dict[str, Any]]:
    return [
        {
            "category": "expert_feedback",
            "human_owner": "project lead + external reviewer",
            "human_action": (
                "Send the prepared review packet to a real advisor, domain expert, or engineering reviewer; "
                "request signed comments, email reply, meeting minutes, or chat feedback against the listed dimensions."
            ),
            "proof_to_collect": [
                "real outbound proof",
                "reviewer identity and role",
                "signed feedback form, email reply, meeting minutes, or chat screenshot",
                "remediation issue and action after feedback",
            ],
            "ready_packet_files": [
                "docs/challenge_cup/00_项目一页纸.md",
                "docs/challenge_cup/11_应用场景与专家验证.md",
                "docs/challenge_cup/reproducibility/expert_feedback_form.md",
                "docs/challenge_cup/reproducibility/expert_feedback_request_packet.md",
                "docs/challenge_cup/reproducibility/final_acceptance_audit.md",
            ],
            "recording_commands": [
                EXPERT_OUTREACH_COMMAND,
                EXPERT_PREFLIGHT_COMMAND,
                EXPERT_RECORD_COMMAND,
            ],
            "powershell_execution_block": expert_feedback_powershell_block(),
            "source_integrity_guardrails": SOURCE_INTEGRITY_GUARDRAILS,
            "acceptance_gate": "hard_evidence_ledger.categories.expert_feedback.collected_count >= 1",
            "does_not_satisfy_goal_completion": True,
        },
        {
            "category": "timed_rehearsal",
            "human_owner": "presenter + observer",
            "human_action": (
                "Schedule and run a real timed defense rehearsal with an observer, visible timer, offline backup check, "
                "and five killer questions; archive measured timings and missed evidence anchors."
            ),
            "proof_to_collect": [
                "real schedule or observer preparation proof",
                "timer screenshot or screen recording",
                "observer note",
                "five killer-question timings and missed-question list",
            ],
            "ready_packet_files": [
                "docs/challenge_cup/04_系统演示脚本.md",
                "docs/challenge_cup/05_答辩问答手册.md",
                "docs/challenge_cup/10_答辩攻防与彩排卡.md",
                "docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md",
                "docs/challenge_cup/reproducibility/final_acceptance_audit.md",
            ],
            "recording_commands": [
                REHEARSAL_SCHEDULE_COMMAND,
                REHEARSAL_RUN_COMMAND,
                REHEARSAL_PREFLIGHT_COMMAND,
                REHEARSAL_RECORD_COMMAND,
            ],
            "powershell_execution_block": timed_rehearsal_powershell_block(),
            "source_integrity_guardrails": SOURCE_INTEGRITY_GUARDRAILS,
            "failed_rehearsal_archival_rule": FAILED_REHEARSAL_ARCHIVAL_RULE,
            "acceptance_gate": "hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1",
            "does_not_satisfy_goal_completion": True,
        },
    ]


def build_payload() -> dict[str, Any]:
    return {
        "report_type": REPORT_TYPE,
        "status": STATUS,
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "required_before_goal_completion": REQUIRED_BEFORE_GOAL_COMPLETION,
        "operator_outcome": "package can be reviewed; goal cannot be closed",
        "action_streams": action_streams(),
        "verification_commands": [
            "python scripts/build_challenge_cup_hard_evidence_ledger.py",
            "python scripts/build_challenge_cup_package.py",
            "python scripts/check_challenge_cup_readiness.py",
            "python scripts/check_challenge_cup_goal_completion.py",
            "python scripts/build_challenge_cup_final_acceptance_audit.py",
        ],
        "integrity_rules": [
            "不伪造专家意见",
            "不伪造计时彩排",
            "schedule or outreach records do not satisfy hard evidence until real feedback/rehearsal proof is archived",
        ],
        "boundary": BOUNDARY,
        "output_files": [repo_path(OUTPUT_MD), repo_path(OUTPUT_JSON)],
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# External Hard Evidence Action Pack",
        "",
        f"- report_type: `{payload['report_type']}`",
        f"- status: `{payload['status']}`",
        f"- completion_claim_allowed: `{payload['completion_claim_allowed']}`",
        f"- does_not_satisfy_goal_completion=True",
        f"- operator_outcome: {payload['operator_outcome']}",
        f"- boundary: {payload['boundary']}",
        "",
        "## Integrity Rules",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["integrity_rules"])
    lines.extend(["", "## Human Handoff Streams", ""])
    for stream in payload["action_streams"]:
        lines.extend(
            [
                f"### {stream['category']}",
                "",
                f"- Human owner: {stream['human_owner']}",
                f"- Human action: {stream['human_action']}",
                f"- Acceptance gate: `{stream['acceptance_gate']}`",
                f"- Does not satisfy goal completion yet: `{stream['does_not_satisfy_goal_completion']}`",
                "",
                "Proof to collect:",
            ]
        )
        lines.extend(f"- {item}" for item in stream["proof_to_collect"])
        lines.extend(["", "Source integrity guardrails:"])
        lines.extend(f"- {item}" for item in stream["source_integrity_guardrails"])
        lines.extend(["", "Ready packet files:"])
        lines.extend(f"- `{item}`" for item in stream["ready_packet_files"])
        lines.extend(["", "Recording commands:"])
        lines.extend(f"- `{item}`" for item in stream["recording_commands"])
        lines.extend(["", "PowerShell execution block:", ""])
        lines.append("```powershell")
        lines.extend(stream["powershell_execution_block"])
        lines.append("```")
        if stream.get("failed_rehearsal_archival_rule"):
            lines.extend(["", "Failed rehearsal archival rule:"])
            lines.append(f"- {stream['failed_rehearsal_archival_rule']}")
        lines.append("")
    lines.extend(["## Verification Commands", ""])
    lines.extend(f"- `{item}`" for item in payload["verification_commands"])
    write_text(path, "\n".join(lines))


def write_outputs(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or build_payload()
    write_text(OUTPUT_JSON, json.dumps(payload, ensure_ascii=False, indent=2))
    write_markdown(OUTPUT_MD, payload)
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"hard evidence action pack: {repo_path(OUTPUT_MD)}")
    print(f"Status: {payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
