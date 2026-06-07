from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
KIT_DIR = OUTPUT_DIR / "external_evidence_execution_kit"
OUTPUT_JSON = OUTPUT_DIR / "external_evidence_execution_kit.json"
OUTPUT_MD = OUTPUT_DIR / "external_evidence_execution_kit.md"
EXPERT_HANDOFF_MD = KIT_DIR / "expert_review_handoff.md"
TIMED_REHEARSAL_OBSERVER_MD = KIT_DIR / "timed_rehearsal_observer_sheet.md"

REPORT_TYPE = "challenge_cup_external_evidence_execution_kit"
STATUS = "ready_for_external_execution_handoff"
REQUIRED_BEFORE_GOAL_COMPLETION = ["expert_feedback", "timed_rehearsal"]
BOUNDARY = (
    "This kit packages the final human handoff materials for collecting real external hard evidence. "
    "It does not satisfy goal completion, does not claim expert approval, and does not claim a timed "
    "rehearsal has been completed."
)
SOURCE_INTEGRITY_GUARDRAILS = [
    "preflight and record commands calculate source_sha256 from the real source attachment",
    "metadata source_sha256 must match the archived source attachment content",
    "--source must be the original evidence attachment, not the generated .json metadata summary; the source attachment must be non-empty and must not be a JSON metadata file",
    "--source must not point inside docs/challenge_cup/reproducibility/hard_evidence/**; that directory is for archived intake outputs, not new source inputs",
    "hard_evidence_ledger rejects duplicate source_sha256 values within the same hard evidence category",
    "do not edit or replace the source attachment after recording; changed bytes will fail readiness and goal gates",
]
EXPERT_OUTREACH_COMMAND = (
    "python scripts/record_challenge_cup_expert_outreach.py --id real-outreach-id "
    "--source path/to/real-outreach-proof.eml --recipient-alias real-reviewer-alias "
    "--recipient-role real-reviewer-role --channel email --sent-date YYYY-MM-DD "
    "--status sent --requested-review-dimension practicality --requested-review-dimension innovation "
    "--requested-review-dimension boundary_rigor "
    "--requested-attachment docs/challenge_cup/00_项目一页纸.md "
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
    "--source path/to/real-timer-or-observer-file.txt "
    "--rehearsal-date YYYY-MM-DD --observer real-observer-alias "
    "--opening-actual-seconds 88 --demo-actual-seconds 170 "
    "--offline-fallback-actual-seconds 18 "
    "--killer-question-seconds 25 25 25 25 25 "
    "--confirm-real-rehearsal"
)
REHEARSAL_PREFLIGHT_COMMAND = (
    "python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal "
    "--id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --evidence-type observer_note "
    "--rehearsal-date YYYY-MM-DD --observer real-observer-alias "
    "--opening-actual-seconds 88 --demo-actual-seconds 170 "
    "--offline-fallback-actual-seconds 18 "
    "--killer-question-seconds 25 25 25 25 25 "
    "--confirm-real-rehearsal"
)
REHEARSAL_RECORD_COMMAND = (
    "python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal "
    "--id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --evidence-type observer_note "
    "--rehearsal-date YYYY-MM-DD --observer real-observer-alias "
    "--opening-actual-seconds 88 --demo-actual-seconds 170 "
    "--offline-fallback-actual-seconds 18 "
    "--killer-question-seconds 25 25 25 25 25 "
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


def expert_outreach_powershell_block() -> list[str]:
    return [
        f"Set-Location '{powershell_repo_root()}'",
        "$outreachId = 'outreach-YYYYMMDD-01'",
        "$outreachSource = 'D:\\path\\to\\real-outreach-proof.eml'",
        "$sentDate = 'YYYY-MM-DD'",
        "$followupDueDate = 'YYYY-MM-DD'",
        "$reviewer = 'real-reviewer-alias'",
        "$reviewerRole = 'real-reviewer-role'",
        *guarded_powershell_command(
            f"{POWERSHELL_PYTHON} .\\scripts\\record_challenge_cup_expert_outreach.py --id $outreachId --source $outreachSource --recipient-alias $reviewer --recipient-role $reviewerRole --channel email --sent-date $sentDate --status sent --requested-review-dimension practicality --requested-review-dimension innovation --requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/00_椤圭洰涓€椤电焊.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date $followupDueDate --confirm-real-outreach"
        ),
    ]


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
        "$rehearsalSource = 'D:\\path\\to\\real-timer-or-observer-file.txt'",
        "$rehearsalDate = 'YYYY-MM-DD'",
        "$observer = 'real-observer-alias'",
        "$opening = 88",
        "$demo = 170",
        "$offline = 18",
        "$killer = 25,25,25,25,25",
        *guarded_powershell_command(
            f"{POWERSHELL_PYTHON} .\\scripts\\run_challenge_cup_timed_rehearsal.py --id $rehearsalId --source $rehearsalSource --rehearsal-date $rehearsalDate --observer $observer --opening-actual-seconds $opening --demo-actual-seconds $demo --offline-fallback-actual-seconds $offline --killer-question-seconds $killer --confirm-real-rehearsal"
        ),
    ]


def timed_rehearsal_schedule_powershell_block() -> list[str]:
    return [
        f"Set-Location '{powershell_repo_root()}'",
        "$scheduleId = 'rehearsal-schedule-YYYYMMDD-01'",
        "$scheduleSource = 'D:\\path\\to\\real-calendar-or-observer-prep-file.txt'",
        "$scheduledDate = 'YYYY-MM-DD'",
        "$observer = 'real-observer-alias'",
        "$venue = 'real-venue-or-channel'",
        *guarded_powershell_command(
            f"{POWERSHELL_PYTHON} .\\scripts\\record_challenge_cup_timed_rehearsal_schedule.py --id $scheduleId --source $scheduleSource --scheduled-date $scheduledDate --observer $observer --venue-or-channel $venue --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible --checklist-item browser-smoke-opened --checklist-item offline-archive-ready --checklist-item five-killer-questions-assigned --confirm-real-schedule"
        ),
    ]


def configure_paths(repo_root: Path) -> None:
    global REPO_ROOT, OUTPUT_DIR, KIT_DIR, OUTPUT_JSON, OUTPUT_MD, EXPERT_HANDOFF_MD, TIMED_REHEARSAL_OBSERVER_MD

    REPO_ROOT = repo_root
    OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
    KIT_DIR = OUTPUT_DIR / "external_evidence_execution_kit"
    OUTPUT_JSON = OUTPUT_DIR / "external_evidence_execution_kit.json"
    OUTPUT_MD = OUTPUT_DIR / "external_evidence_execution_kit.md"
    EXPERT_HANDOFF_MD = KIT_DIR / "expert_review_handoff.md"
    TIMED_REHEARSAL_OBSERVER_MD = KIT_DIR / "timed_rehearsal_observer_sheet.md"


def repo_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def execution_packets() -> list[dict[str, Any]]:
    return [
        {
            "packet_id": "expert_feedback_review",
            "hard_evidence_category": "expert_feedback",
            "owner": "project lead + real external reviewer",
            "handoff_file": repo_path(EXPERT_HANDOFF_MD),
            "attachment_files": [
                "docs/challenge_cup/00_项目一页纸.md",
                "docs/challenge_cup/11_应用场景与专家验证.md",
                "docs/challenge_cup/22_同类方案对比与创新性证据卡.md",
                "docs/challenge_cup/reproducibility/application_validation_report.md",
                "docs/challenge_cup/reproducibility/expert_feedback_form.md",
                "docs/challenge_cup/reproducibility/expert_feedback_request_packet.md",
                "docs/challenge_cup/reproducibility/readiness_gate_report.md",
            ],
            "execution_steps": [
                "Send the handoff file and attachments to a real advisor, domain expert, or engineering reviewer.",
                "Ask the reviewer to comment on practicality, innovation, evidence quality, defense clarity, and boundaries.",
                "Archive the original signed form, email reply, meeting minutes, or chat screenshot before claiming feedback.",
                "Record at least one remediation issue and action after receiving the real feedback.",
            ],
            "done_when": [
                "a real reviewer identity and role are recorded",
                "a real feedback source file is archived",
                "record_challenge_cup_hard_evidence.py expert_feedback records metadata, source path, and --confirm-real-feedback",
                "hard_evidence_ledger.categories.expert_feedback.collected_count >= 1",
            ],
            "recording_commands": [
                EXPERT_OUTREACH_COMMAND,
                EXPERT_PREFLIGHT_COMMAND,
                EXPERT_RECORD_COMMAND,
            ],
            "pre_hard_evidence_powershell_block": expert_outreach_powershell_block(),
            "powershell_execution_block": expert_feedback_powershell_block(),
            "source_integrity_guardrails": SOURCE_INTEGRITY_GUARDRAILS,
            "acceptance_gate": "hard_evidence_ledger.categories.expert_feedback.collected_count >= 1",
            "does_not_satisfy_goal_completion": True,
        },
        {
            "packet_id": "timed_rehearsal_observer",
            "hard_evidence_category": "timed_rehearsal",
            "owner": "presenter + real observer",
            "handoff_file": repo_path(TIMED_REHEARSAL_OBSERVER_MD),
            "attachment_files": [
                "docs/challenge_cup/04_系统演示脚本.md",
                "docs/challenge_cup/05_答辩问答手册.md",
                "docs/challenge_cup/10_答辩攻防与彩排卡.md",
                "docs/challenge_cup/14_现场答辩操作Runbook.md",
                "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md",
                "docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md",
                "docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md",
                "docs/challenge_cup/reproducibility/final_acceptance_audit.md",
            ],
            "execution_steps": [
                "Assign a real observer and make the timer visible before the rehearsal starts.",
                "Run the 90-second opening, three-minute demo, offline fallback switch, and five killer questions.",
                "Record actual seconds for every segment and mark missed evidence anchors immediately.",
                "Archive the timer screenshot, screen recording, observer note, or missed-question list before claiming completion.",
            ],
            "done_when": [
                "a real observer is recorded",
                "opening/demo/offline fallback/killer-question seconds are measured",
                "run_challenge_cup_timed_rehearsal.py records actual timing metadata only with an independent --source attachment",
                "hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1 only when timing_acceptance_pass=true",
            ],
            "recording_commands": [
                REHEARSAL_SCHEDULE_COMMAND,
                REHEARSAL_RUN_COMMAND,
                REHEARSAL_PREFLIGHT_COMMAND,
                REHEARSAL_RECORD_COMMAND,
            ],
            "pre_hard_evidence_powershell_block": timed_rehearsal_schedule_powershell_block(),
            "powershell_execution_block": timed_rehearsal_powershell_block(),
            "source_integrity_guardrails": SOURCE_INTEGRITY_GUARDRAILS,
            "failed_rehearsal_archival_rule": FAILED_REHEARSAL_ARCHIVAL_RULE,
            "acceptance_gate": "hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1",
            "does_not_satisfy_goal_completion": True,
        },
    ]


def operator_sequence() -> list[dict[str, Any]]:
    return [
        {
            "step_id": "verify_package_ready",
            "phase": "machine_package_preflight",
            "category": "package_readiness",
            "command": "python scripts/check_challenge_cup_readiness.py",
            "human_proof_required": "none; this is a machine gate before contacting reviewers or observers",
            "counts_as_hard_evidence": False,
            "expected_after_step": "readiness gate reports pass 64/64",
            "guardrail": "A passing package gate is not expert approval, timed rehearsal completion, or award proof.",
            "does_not_claim_award_or_completion": True,
        },
        {
            "step_id": "record_expert_outreach",
            "phase": "expert_feedback_outreach",
            "category": "expert_feedback",
            "command": EXPERT_OUTREACH_COMMAND,
            "human_proof_required": "real sent email, chat message, meeting notice, or follow-up screenshot",
            "counts_as_hard_evidence": False,
            "expected_after_step": "expert_feedback_outreach_ledger records the outreach but hard_evidence_ledger remains open",
            "guardrail": "Outreach proves a request was sent; it does not prove expert feedback was received.",
            "does_not_claim_award_or_completion": True,
        },
        {
            "step_id": "record_rehearsal_schedule",
            "phase": "timed_rehearsal_scheduling",
            "category": "timed_rehearsal",
            "command": REHEARSAL_SCHEDULE_COMMAND,
            "human_proof_required": "real calendar invite, meeting notice, or observer preparation record",
            "counts_as_hard_evidence": False,
            "expected_after_step": "timed_rehearsal_schedule_ledger records the schedule but timed_rehearsal evidence remains open",
            "guardrail": "A schedule proves intent to rehearse; it does not prove a timed rehearsal happened.",
            "does_not_claim_award_or_completion": True,
        },
        {
            "step_id": "preflight_expert_feedback",
            "phase": "expert_feedback_validation",
            "category": "expert_feedback",
            "command": EXPERT_PREFLIGHT_COMMAND,
            "human_proof_required": "real signed form, email reply, meeting minutes, or chat screenshot from reviewer",
            "counts_as_hard_evidence": False,
            "expected_after_step": "preflight returns pass and does not write hard evidence",
            "guardrail": "Preflight is a dry run; only record_challenge_cup_hard_evidence.py archives evidence.",
            "does_not_claim_award_or_completion": True,
        },
        {
            "step_id": "record_expert_feedback",
            "phase": "expert_feedback_archival",
            "category": "expert_feedback",
            "command": EXPERT_RECORD_COMMAND,
            "human_proof_required": "same real reviewer feedback source that passed preflight",
            "counts_as_hard_evidence": True,
            "expected_after_step": "hard_evidence_ledger.categories.expert_feedback.collected_count >= 1",
            "guardrail": "Records feedback evidence only; it still does not guarantee an award.",
            "does_not_claim_award_or_completion": True,
        },
        {
            "step_id": "run_timed_rehearsal",
            "phase": "timed_rehearsal_archival",
            "category": "timed_rehearsal",
            "command": REHEARSAL_RUN_COMMAND,
            "human_proof_required": "actual observed rehearsal timings from a visible timer or observer note",
            "counts_as_hard_evidence": True,
            "expected_after_step": (
                "if timing_acceptance_pass=true, hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1; "
                "if timing_acceptance_pass=false, metadata is preserved in rejected_metadata_records and collected_count does not satisfy the gate"
            ),
            "guardrail": "Measured rehearsal timing supports defense readiness; it is not expert approval or award proof.",
            "does_not_claim_award_or_completion": True,
        },
        {
            "step_id": "rebuild_package",
            "phase": "post_evidence_package_refresh",
            "category": "package_readiness",
            "command": "python scripts/build_challenge_cup_package.py",
            "human_proof_required": "archived expert feedback and archived timed rehearsal evidence are already present",
            "counts_as_hard_evidence": False,
            "expected_after_step": "package manifest, evidence hashes, and submission archive are refreshed",
            "guardrail": "Package rebuild is only a refresh; it does not prove readiness or goal completion.",
            "does_not_claim_award_or_completion": True,
        },
        {
            "step_id": "check_readiness_gate",
            "phase": "post_evidence_package_refresh",
            "category": "package_readiness",
            "command": "python scripts/check_challenge_cup_readiness.py",
            "human_proof_required": "refreshed package files from the previous step",
            "counts_as_hard_evidence": False,
            "expected_after_step": "readiness gate reports the current package state",
            "guardrail": "A passing readiness gate is still package readiness, not award proof.",
            "does_not_claim_award_or_completion": True,
        },
        {
            "step_id": "verify_submission_package",
            "phase": "post_evidence_package_refresh",
            "category": "package_readiness",
            "command": "python docs/challenge_cup/reproducibility/verify_submission_package.py --root .",
            "human_proof_required": "refreshed submission archive from the package rebuild step",
            "counts_as_hard_evidence": False,
            "expected_after_step": "submission package verifier passes against the refreshed archive",
            "guardrail": "Archive verification proves package integrity only; it does not close external evidence.",
            "does_not_claim_award_or_completion": True,
        },
        {
            "step_id": "check_goal_completion_gate",
            "phase": "post_evidence_package_refresh",
            "category": "goal_completion",
            "command": "python scripts/check_challenge_cup_goal_completion.py",
            "human_proof_required": "archived hard evidence ledger and refreshed readiness report",
            "counts_as_hard_evidence": False,
            "expected_after_step": "goal-completion gate explicitly states whether completion is allowed",
            "guardrail": "Do not treat any previous step as proof unless goal completion explicitly passes.",
            "does_not_claim_award_or_completion": True,
        },
        {
            "step_id": "refresh_final_audit",
            "phase": "final_acceptance_refresh",
            "category": "final_audit",
            "command": "python scripts/build_challenge_cup_final_acceptance_audit.py",
            "human_proof_required": "goal completion report and hard-evidence ledger from the refreshed package",
            "counts_as_hard_evidence": False,
            "expected_after_step": "final_acceptance_audit states whether package review or goal completion is allowed",
            "guardrail": "Final audit must preserve no-award-guarantee language even after hard evidence is collected.",
            "does_not_claim_award_or_completion": True,
        },
    ]


def build_payload() -> dict[str, Any]:
    return {
        "report_type": REPORT_TYPE,
        "status": STATUS,
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "required_before_goal_completion": REQUIRED_BEFORE_GOAL_COMPLETION,
        "boundary": BOUNDARY,
        "operator_sequence": operator_sequence(),
        "integrity_rules": [
            "不伪造真实专家反馈",
            "不伪造真实计时彩排",
            "外发材料、排期记录和执行包本身不满足 goal completion",
        ],
        "execution_packets": execution_packets(),
        "verification_commands": [
            "python scripts/build_challenge_cup_external_evidence_execution_kit.py",
            "python scripts/build_challenge_cup_hard_evidence_ledger.py",
            "python scripts/build_challenge_cup_package.py",
            "python scripts/check_challenge_cup_readiness.py",
            "python scripts/check_challenge_cup_goal_completion.py",
            "python scripts/build_challenge_cup_final_acceptance_audit.py",
        ],
        "output_files": [
            repo_path(OUTPUT_MD),
            repo_path(OUTPUT_JSON),
            repo_path(EXPERT_HANDOFF_MD),
            repo_path(TIMED_REHEARSAL_OBSERVER_MD),
        ],
    }


def write_packet_handoff(packet: dict[str, Any]) -> None:
    lines = [
        f"# {packet['packet_id']} Handoff",
        "",
        f"- hard_evidence_category: `{packet['hard_evidence_category']}`",
        f"- owner: {packet['owner']}",
        f"- acceptance_gate: `{packet['acceptance_gate']}`",
        f"- does_not_satisfy_goal_completion: `{packet['does_not_satisfy_goal_completion']}`",
        "",
        "## Integrity Boundary",
        "",
        "不伪造真实专家反馈；不伪造真实计时彩排；未归档真实硬证据前不能标记目标完成。",
        "",
        "## Attachment Files",
        "",
    ]
    lines.extend(f"- `{item}`" for item in packet["attachment_files"])
    lines.extend(["", "## Execution Steps", ""])
    lines.extend(f"- {item}" for item in packet["execution_steps"])
    lines.extend(["", "## Done When", ""])
    lines.extend(f"- {item}" for item in packet["done_when"])
    lines.extend(["", "## Source Integrity Guardrails", ""])
    lines.extend(f"- {item}" for item in packet["source_integrity_guardrails"])
    lines.extend(["", "## Recording Commands", ""])
    lines.extend(f"- `{item}`" for item in packet["recording_commands"])
    lines.extend(["", "## Pre-hard-evidence PowerShell block", ""])
    lines.append("```powershell")
    lines.extend(packet["pre_hard_evidence_powershell_block"])
    lines.append("```")
    lines.extend(["", "## PowerShell execution block", ""])
    lines.append("```powershell")
    lines.extend(packet["powershell_execution_block"])
    lines.append("```")
    if packet.get("failed_rehearsal_archival_rule"):
        lines.extend(["", "## Failed Rehearsal Archival Rule", ""])
        lines.append(packet["failed_rehearsal_archival_rule"])
    write_text(REPO_ROOT / packet["handoff_file"], "\n".join(lines))


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# External Evidence Execution Kit",
        "",
        f"- report_type: `{payload['report_type']}`",
        f"- status: `{payload['status']}`",
        f"- completion_claim_allowed: `{payload['completion_claim_allowed']}`",
        "- does_not_satisfy_goal_completion=True",
        f"- boundary: {payload['boundary']}",
        "",
        "## Integrity Rules",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["integrity_rules"])
    lines.extend(["", "## Operator Sequence", ""])
    for item in payload["operator_sequence"]:
        lines.extend(
            [
                f"### {item['step_id']}",
                "",
                f"- Phase: `{item['phase']}`",
                f"- Category: `{item['category']}`",
                f"- Command: `{item['command']}`",
                f"- Human proof required: {item['human_proof_required']}",
                f"- counts_as_hard_evidence: `{item['counts_as_hard_evidence']}`",
                f"- Expected after step: {item['expected_after_step']}",
                f"- Guardrail: {item['guardrail']}",
                f"- does_not_claim_award_or_completion: `{item['does_not_claim_award_or_completion']}`",
                "",
            ]
        )
    lines.extend(["", "## Execution Packets", ""])
    for packet in payload["execution_packets"]:
        lines.extend(
            [
                f"### {packet['packet_id']}",
                "",
                f"- Category: `{packet['hard_evidence_category']}`",
                f"- Owner: {packet['owner']}",
                f"- Handoff file: `{packet['handoff_file']}`",
                f"- Acceptance gate: `{packet['acceptance_gate']}`",
                f"- Does not satisfy goal completion yet: `{packet['does_not_satisfy_goal_completion']}`",
                "",
                "Attachment files:",
            ]
        )
        lines.extend(f"- `{item}`" for item in packet["attachment_files"])
        lines.extend(["", "Source integrity guardrails:"])
        lines.extend(f"- {item}" for item in packet["source_integrity_guardrails"])
        lines.extend(["", "Recording commands:"])
        lines.extend(f"- `{item}`" for item in packet["recording_commands"])
        lines.extend(["", "Pre-hard-evidence PowerShell block:", ""])
        lines.append("```powershell")
        lines.extend(packet["pre_hard_evidence_powershell_block"])
        lines.append("```")
        lines.extend(["", "PowerShell execution block:", ""])
        lines.append("```powershell")
        lines.extend(packet["powershell_execution_block"])
        lines.append("```")
        if packet.get("failed_rehearsal_archival_rule"):
            lines.extend(["", "Failed rehearsal archival rule:"])
            lines.append(f"- {packet['failed_rehearsal_archival_rule']}")
        lines.append("")
    lines.extend(["## Verification Commands", ""])
    lines.extend(f"- `{item}`" for item in payload["verification_commands"])
    write_text(path, "\n".join(lines))


def write_outputs(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or build_payload()
    write_text(OUTPUT_JSON, json.dumps(payload, ensure_ascii=False, indent=2))
    write_markdown(OUTPUT_MD, payload)
    for packet in payload["execution_packets"]:
        write_packet_handoff(packet)
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"external evidence execution kit: {repo_path(OUTPUT_MD)}")
    print(f"Status: {payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
