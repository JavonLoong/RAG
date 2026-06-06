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
                "python scripts/record_challenge_cup_expert_outreach.py --id advisor-a-20260606 --source <real-outreach-proof> --recipient-alias advisor-a --recipient-role advisor --channel email --sent-date 2026-06-06 --status sent --requested-review-dimension practicality --requested-review-dimension innovation --requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/00_项目一页纸.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date 2026-06-09 --confirm-real-outreach",
                "python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id advisor-a --source <real-feedback-file> --evidence-type email_reply --reviewer-identity advisor-a --role-or-org advisor --review-date 2026-06-06 --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback",
                "python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id advisor-a --source <real-feedback-file> --evidence-type email_reply --reviewer-identity advisor-a --role-or-org advisor --review-date 2026-06-06 --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback",
            ],
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
                "run_challenge_cup_timed_rehearsal.py records actual timing metadata",
                "hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1",
            ],
            "recording_commands": [
                "python scripts/record_challenge_cup_timed_rehearsal_schedule.py --id rehearsal-schedule-20260606 --source <real-calendar-or-observer-prep-file> --scheduled-date 2026-06-06 --observer observer-a --venue-or-channel meeting-room-a --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible --checklist-item browser-smoke-opened --checklist-item offline-archive-ready --checklist-item five-killer-questions-assigned --confirm-real-schedule",
                "python scripts/run_challenge_cup_timed_rehearsal.py --id rehearsal-1 --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal",
                "python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal --id rehearsal-1 --source <real-timer-or-observer-file> --evidence-type observer_note --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal",
                "python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal --id rehearsal-1 --source <real-timer-or-observer-file> --evidence-type observer_note --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal",
            ],
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
        "boundary": BOUNDARY,
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
    lines.extend(["", "## Recording Commands", ""])
    lines.extend(f"- `{item}`" for item in packet["recording_commands"])
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
        lines.extend(["", "Recording commands:"])
        lines.extend(f"- `{item}`" for item in packet["recording_commands"])
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
