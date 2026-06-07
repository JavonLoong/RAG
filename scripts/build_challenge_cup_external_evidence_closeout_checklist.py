from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTPUT_JSON = OUTPUT_DIR / "external_evidence_closeout_checklist.json"
OUTPUT_MD = OUTPUT_DIR / "external_evidence_closeout_checklist.md"

REPORT_TYPE = "challenge_cup_external_evidence_closeout_checklist"
STATUS = "ready_for_real_external_evidence_closeout"
REQUIRED_BEFORE_GOAL_COMPLETION = ["expert_feedback", "timed_rehearsal"]
DAY_OF_EXECUTION_OWNER = "project lead"
HARD_EVIDENCE_READY_STATUS = "hard_evidence_collected_pending_review"
BOUNDARY = (
    "Day-of closeout support only: this checklist does not satisfy goal completion, does not claim "
    "expert approval, does not claim a timed rehearsal was completed, and provides no award guarantee."
)

EXPERT_PREFLIGHT_COMMAND = (
    "python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id "
    "--source path/to/real-feedback.eml --evidence-type email_reply "
    "--reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org "
    "--review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation "
    "--review-dimension boundary_rigor --remediation-issue issue --remediation-action action "
    "--confirm-real-feedback"
)
EXPERT_RECORD_COMMAND = (
    "python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id "
    "--source path/to/real-feedback.eml --evidence-type email_reply "
    "--reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org "
    "--review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation "
    "--review-dimension boundary_rigor --remediation-issue issue --remediation-action action "
    "--confirm-real-feedback"
)
REHEARSAL_PREFLIGHT_COMMAND = (
    "python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal --id real-rehearsal-id "
    "--source path/to/real-timer-or-observer-file.txt --evidence-type observer_note "
    "--rehearsal-date YYYY-MM-DD --observer real-observer-alias "
    "--opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 "
    "--killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal"
)
REHEARSAL_RUN_COMMAND = (
    "python scripts/run_challenge_cup_timed_rehearsal.py --id real-rehearsal-id "
    "--source path/to/real-timer-or-observer-file.txt --rehearsal-date YYYY-MM-DD "
    "--observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 "
    "--offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 "
    "--confirm-real-rehearsal"
)


def configure_paths(repo_root: Path) -> None:
    global REPO_ROOT, OUTPUT_DIR, OUTPUT_JSON, OUTPUT_MD

    REPO_ROOT = repo_root
    OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
    OUTPUT_JSON = OUTPUT_DIR / "external_evidence_closeout_checklist.json"
    OUTPUT_MD = OUTPUT_DIR / "external_evidence_closeout_checklist.md"


def repo_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def item(
    *,
    check_id: str,
    phase: str,
    owner: str,
    evidence_category: str,
    proof_required: str,
    command: str,
    expected_after_step: str,
    acceptance_signal: str,
    cannot_substitute: str,
    counts_as_hard_evidence: bool = False,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "phase": phase,
        "owner": owner,
        "evidence_category": evidence_category,
        "proof_required": proof_required,
        "command": command,
        "expected_after_step": expected_after_step,
        "acceptance_signal": acceptance_signal,
        "cannot_substitute": cannot_substitute,
        "counts_as_hard_evidence": counts_as_hard_evidence,
        "does_not_claim_award_or_completion": True,
    }


def closeout_items() -> list[dict[str, Any]]:
    return [
        item(
            check_id="package_preflight_clean",
            phase="before_external_execution",
            owner="project lead",
            evidence_category="package_readiness",
            proof_required="current package tree and readiness report",
            command="python scripts/check_challenge_cup_readiness.py",
            expected_after_step="readiness gate reports pass 65/65 before external execution starts",
            acceptance_signal="docs/challenge_cup/reproducibility/readiness_gate_report.md contains Status: `pass` and Passed: 65/65",
            cannot_substitute="a clean package preflight does not substitute for real expert feedback or real timed rehearsal evidence",
        ),
        item(
            check_id="expert_feedback_source_ready",
            phase="expert_feedback_preflight",
            owner="project lead + real external reviewer",
            evidence_category="expert_feedback",
            proof_required="real expert feedback source attachment before archival",
            command=EXPERT_PREFLIGHT_COMMAND,
            expected_after_step="preflight validates reviewer identity, role, date, dimensions, remediation, and source attachment without writing intake files",
            acceptance_signal="preflight returns status=pass and reports source_sha256 for the real feedback attachment",
            cannot_substitute="expert outreach, generated summaries, and metadata JSON do not substitute for the real feedback attachment",
        ),
        item(
            check_id="expert_feedback_archived",
            phase="expert_feedback_archival",
            owner="project lead",
            evidence_category="expert_feedback",
            proof_required="real expert feedback source attachment",
            command=EXPERT_RECORD_COMMAND,
            expected_after_step="hard_evidence_ledger expert_feedback collected_count reaches at least 1 after ledger rebuild",
            acceptance_signal="metadata has real_feedback_confirmed=true, source_origin=external_attachment, source_sha256, reviewer identity, dimensions, and remediation record",
            cannot_substitute="outreach proof alone does not substitute for received expert feedback",
            counts_as_hard_evidence=True,
        ),
        item(
            check_id="timed_rehearsal_source_ready",
            phase="timed_rehearsal_preflight",
            owner="presenter + observer",
            evidence_category="timed_rehearsal",
            proof_required="real timed rehearsal timer or observer attachment before archival",
            command=REHEARSAL_PREFLIGHT_COMMAND,
            expected_after_step="preflight validates observer, date, five killer-question timings, and source attachment without writing intake files",
            acceptance_signal="preflight returns status=pass and reports source_sha256 for the real timed rehearsal attachment",
            cannot_substitute="schedule proof or a generated note without independent source does not substitute for a real observed run",
        ),
        item(
            check_id="timed_rehearsal_archived",
            phase="timed_rehearsal_archival",
            owner="presenter + observer",
            evidence_category="timed_rehearsal",
            proof_required="real timed rehearsal timer or observer attachment",
            command=REHEARSAL_RUN_COMMAND,
            expected_after_step="hard_evidence_ledger timed_rehearsal collected_count reaches at least 1 only if timing acceptance passes",
            acceptance_signal="metadata has real_rehearsal_confirmed=true, source_origin=external_attachment, source_sha256, and timing_acceptance_pass=true",
            cannot_substitute="a scheduled rehearsal or over-limit rehearsal does not substitute for a passing timed rehearsal",
            counts_as_hard_evidence=True,
        ),
        item(
            check_id="hard_evidence_ledger_rebuilt",
            phase="post_evidence_refresh",
            owner="evidence administrator",
            evidence_category="hard_evidence",
            proof_required="archived expert_feedback and timed_rehearsal intake files",
            command="python scripts/build_challenge_cup_hard_evidence_ledger.py",
            expected_after_step="ledger shows both hard evidence categories collected and no rejected metadata blocks goal completion",
            acceptance_signal=(
                "hard_evidence_ledger.json has status="
                f"{HARD_EVIDENCE_READY_STATUS} and completion_claim_allowed=true"
            ),
            cannot_substitute="manual edits to the ledger do not substitute for recorded source attachments and metadata",
        ),
        item(
            check_id="package_rebuilt_after_evidence",
            phase="post_evidence_refresh",
            owner="evidence administrator",
            evidence_category="package_readiness",
            proof_required="updated hard evidence ledger and intake files",
            command="python scripts/build_challenge_cup_package.py",
            expected_after_step="package manifest, evidence hashes, command log, and archive include the new hard evidence files",
            acceptance_signal="package_manifest.json, evidence_hashes.json, and challenge_cup_submission_archive_manifest.json reference the new evidence",
            cannot_substitute="source files copied outside the package do not substitute for regenerated manifests and archive",
        ),
        item(
            check_id="readiness_gate_rerun",
            phase="post_evidence_refresh",
            owner="evidence administrator",
            evidence_category="package_readiness",
            proof_required="rebuilt package files",
            command="python scripts/check_challenge_cup_readiness.py",
            expected_after_step="readiness gate passes after evidence refresh",
            acceptance_signal="readiness_gate_report.md contains Status: `pass` and Passed: 65/65",
            cannot_substitute="a stale readiness report does not substitute for a rerun after evidence changes",
        ),
        item(
            check_id="submission_archive_verified",
            phase="post_evidence_refresh",
            owner="evidence administrator",
            evidence_category="package_integrity",
            proof_required="rebuilt submission archive",
            command="python docs/challenge_cup/reproducibility/verify_submission_package.py --root .",
            expected_after_step="submission package verifier passes against the refreshed archive and hashes",
            acceptance_signal="verifier prints Status: pass and verifies hashed files",
            cannot_substitute="readiness pass alone does not substitute for archive/hash verification",
        ),
        item(
            check_id="goal_completion_gate_rerun",
            phase="goal_completion_decision",
            owner="project lead",
            evidence_category="goal_completion",
            proof_required="passing readiness report and completed hard_evidence_ledger",
            command="python scripts/check_challenge_cup_goal_completion.py",
            expected_after_step="goal completion gate is the only local authority for marking the objective complete",
            acceptance_signal="goal_completion_report.md contains Status: `pass` and completion_claim_allowed=True",
            cannot_substitute="final audit, archive verification, or reviewer enthusiasm do not substitute for the goal completion gate",
        ),
        item(
            check_id="final_acceptance_audit_refreshed",
            phase="final_review",
            owner="project lead",
            evidence_category="final_audit",
            proof_required="latest goal completion report and refreshed package",
            command="python scripts/build_challenge_cup_final_acceptance_audit.py",
            expected_after_step="final audit reflects whether package review and goal completion are allowed",
            acceptance_signal="final_acceptance_audit.json preserves no award guarantee while reflecting the latest goal status",
            cannot_substitute="final audit cannot override a failing goal completion gate",
        ),
    ]


def build_payload() -> dict[str, Any]:
    return {
        "report_type": REPORT_TYPE,
        "status": STATUS,
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "required_before_goal_completion": REQUIRED_BEFORE_GOAL_COMPLETION,
        "day_of_execution_owner": DAY_OF_EXECUTION_OWNER,
        "boundary": BOUNDARY,
        "closeout_items": closeout_items(),
        "integrity_rules": [
            "real expert feedback must come from a real reviewer source attachment",
            "real timed rehearsal must come from a real timer or observer attachment",
            "source_sha256 and source_origin=external_attachment are required for hard evidence closure",
            "goal completion can pass only after both categories are archived and the goal gate passes",
            "no award guarantee is made by this checklist or by any local gate",
        ],
        "output_files": [repo_path(OUTPUT_MD), repo_path(OUTPUT_JSON)],
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# External Evidence Closeout Checklist",
        "",
        f"- report_type: `{payload['report_type']}`",
        f"- status: `{payload['status']}`",
        f"- completion_claim_allowed: `{payload['completion_claim_allowed']}`",
        "- does_not_satisfy_goal_completion=True",
        f"- day-of closeout owner: {payload['day_of_execution_owner']}",
        f"- boundary: {payload['boundary']}",
        "",
        "## Integrity Rules",
        "",
    ]
    lines.extend(f"- {rule}" for rule in payload["integrity_rules"])
    lines.extend(
        [
            "",
            "## Day-Of Closeout Items",
            "",
            "| ID | Phase | Evidence | Counts As Hard Evidence | Command | Acceptance Signal |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item_payload in payload["closeout_items"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{item_payload['check_id']}`",
                    item_payload["phase"],
                    item_payload["evidence_category"],
                    f"`{item_payload['counts_as_hard_evidence']}`",
                    f"`{item_payload['command']}`",
                    item_payload["acceptance_signal"],
                ]
            )
            + " |"
        )
    lines.extend(["", "## Cannot Substitute", ""])
    lines.extend(
        f"- `{item_payload['check_id']}`: {item_payload['cannot_substitute']}"
        for item_payload in payload["closeout_items"]
    )
    write_text(path, "\n".join(lines))


def write_outputs(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or build_payload()
    write_text(OUTPUT_JSON, json.dumps(payload, ensure_ascii=False, indent=2))
    write_markdown(OUTPUT_MD, payload)
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"external evidence closeout checklist: {repo_path(OUTPUT_MD)}")
    print(f"Status: {payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
