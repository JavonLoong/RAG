from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTPUT_JSON = OUTPUT_DIR / "hard_evidence_source_custody.json"
OUTPUT_MD = OUTPUT_DIR / "hard_evidence_source_custody.md"

REPORT_TYPE = "challenge_cup_hard_evidence_source_custody"
STATUS = "ready_for_real_source_custody_no_external_evidence_claim"
REQUIRED_BEFORE_GOAL_COMPLETION = ["expert_feedback", "timed_rehearsal"]
BOUNDARY = (
    "Source custody preflight only: this pack does not satisfy goal completion, does not claim expert "
    "approval, does not claim a timed rehearsal was completed, and provides no award guarantee."
)

EXPERT_PREFLIGHT_COMMAND = (
    "python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id "
    "--source path/to/original-real-feedback.eml --evidence-type email_reply "
    "--reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org "
    "--review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation "
    "--review-dimension boundary_rigor --remediation-issue issue --remediation-action action "
    "--confirm-real-feedback"
)
EXPERT_RECORD_COMMAND = (
    "python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id "
    "--source path/to/original-real-feedback.eml --evidence-type email_reply "
    "--reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org "
    "--review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation "
    "--review-dimension boundary_rigor --remediation-issue issue --remediation-action action "
    "--confirm-real-feedback"
)
REHEARSAL_PREFLIGHT_COMMAND = (
    "python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal --id real-rehearsal-id "
    "--source path/to/original-real-timer-or-observer-file.txt --evidence-type observer_note "
    "--rehearsal-date YYYY-MM-DD --observer real-observer-alias "
    "--opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 "
    "--killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal"
)
REHEARSAL_RUN_COMMAND = (
    "python scripts/run_challenge_cup_timed_rehearsal.py --id real-rehearsal-id "
    "--source path/to/original-real-timer-or-observer-file.txt --rehearsal-date YYYY-MM-DD "
    "--observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 "
    "--offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 "
    "--confirm-real-rehearsal"
)

SOURCE_RESTRICTIONS = [
    "the source must be the original evidence attachment received from the reviewer, observer, timer, or meeting record",
    "the source attachment must be non-empty before preflight and before record",
    "the source attachment must not be a JSON metadata file",
    "--source must not point inside docs/challenge_cup/reproducibility/hard_evidence/**; that tree is for archived intake outputs",
    "duplicate source_sha256 values within a hard evidence category must be rejected by the ledger",
    "--force is allowed only for a deliberate correction and must include a non-empty --force-reason",
    "every --force overwrite must append docs/challenge_cup/reproducibility/hard_evidence/override_log.jsonl with previous and new source_sha256 values",
]
INTEGRITY_GUARDRAILS = [
    "do not fabricate evidence or create placeholder hard evidence attachments",
    "do not claim expert approval before source archival and hard_evidence_ledger rebuild",
    "do not claim a timed rehearsal before source archival and hard_evidence_ledger rebuild",
    "no award guarantee is created by this source custody pack, readiness gate, or verifier",
    "source_sha256 must be calculated from the original source attachment before and after archival",
    "override_log.jsonl is mandatory for intentional replacement of archived metadata or source copies",
]


def configure_paths(repo_root: Path) -> None:
    global REPO_ROOT, OUTPUT_DIR, OUTPUT_JSON, OUTPUT_MD

    REPO_ROOT = repo_root
    OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
    OUTPUT_JSON = OUTPUT_DIR / "hard_evidence_source_custody.json"
    OUTPUT_MD = OUTPUT_DIR / "hard_evidence_source_custody.md"


def repo_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def checkpoint(
    checkpoint_id: str,
    owner: str,
    evidence_state: str,
    required_proof: str,
    command: str,
    acceptance_signal: str,
) -> dict[str, Any]:
    return {
        "checkpoint_id": checkpoint_id,
        "owner": owner,
        "evidence_state": evidence_state,
        "required_proof": required_proof,
        "command": command,
        "acceptance_signal": acceptance_signal,
        "does_not_claim_award_or_completion": True,
    }


def shared_checkpoints(category_id: str, preflight_command: str, archive_command: str) -> list[dict[str, Any]]:
    return [
        checkpoint(
            "source_received",
            "project lead",
            "external source exists outside archived hard_evidence intake",
            "original evidence attachment is present, non-empty, and traceable to a real human source",
            "manual source receipt check before running preflight",
            "source file path, source owner, source date, and source type are known",
        ),
        checkpoint(
            "source_sha256_preflighted",
            "evidence administrator",
            "source hash calculated without writing intake files",
            "preflight output contains source_sha256 and does not create archived metadata",
            preflight_command,
            "preflight status=pass and source_sha256 is recorded for the original source attachment",
        ),
        checkpoint(
            "record_command_archives_source",
            "evidence administrator",
            "source copied into the hard_evidence intake tree by the record command",
            "metadata source_path and source_sha256 match the archived source copy",
            archive_command,
            f"hard_evidence metadata for {category_id} records source_origin=external_attachment and matching source_sha256",
        ),
        checkpoint(
            "ledger_rebuilt",
            "evidence administrator",
            "hard evidence ledger rebuilt from archived intake files",
            "ledger category reflects accepted or rejected metadata without manual edits",
            "python scripts/build_challenge_cup_hard_evidence_ledger.py",
            f"hard_evidence_ledger.categories.{category_id} reflects the recorded source status",
        ),
        checkpoint(
            "package_rebuilt",
            "evidence administrator",
            "package manifests and archive regenerated after source archival",
            "package manifest, evidence hashes, command log, and archive include the new source and metadata",
            "python scripts/build_challenge_cup_package.py",
            "package_manifest.json, evidence_hashes.json, and challenge_cup_submission_archive_manifest.json are refreshed",
        ),
        checkpoint(
            "submission_verifier_rerun",
            "evidence administrator",
            "submission archive verified after package rebuild",
            "verifier checks the refreshed archive, manifest, and hash inventory",
            "python docs/challenge_cup/reproducibility/verify_submission_package.py --root .",
            "submission package verifier reports Status: pass",
        ),
        checkpoint(
            "readiness_gate_rerun",
            "evidence administrator",
            "readiness gate rerun after package rebuild",
            "readiness report reflects the current package state after hard evidence changes",
            "python scripts/check_challenge_cup_readiness.py",
            "readiness gate reports Status: pass for the current gate count",
        ),
        checkpoint(
            "goal_gate_rerun",
            "project lead",
            "goal completion decision made only by the goal gate",
            "goal completion gate reads current readiness report and hard evidence ledger",
            "python scripts/check_challenge_cup_goal_completion.py",
            "goal_completion_report.md explicitly states whether completion_claim_allowed is True or False",
        ),
    ]


def category_payload(category_id: str, source_role: str, preflight_command: str, archive_command: str) -> dict[str, Any]:
    return {
        "category_id": category_id,
        "source_role": source_role,
        "counts_as_hard_evidence_after_record_only": True,
        "does_not_satisfy_goal_completion_before_record": True,
        "source_restrictions": SOURCE_RESTRICTIONS,
        "custody_checkpoints": shared_checkpoints(category_id, preflight_command, archive_command),
        "operator_commands": [
            preflight_command,
            archive_command,
            "python scripts/build_challenge_cup_hard_evidence_ledger.py",
            "python scripts/build_challenge_cup_package.py",
            "python docs/challenge_cup/reproducibility/verify_submission_package.py --root .",
            "python scripts/check_challenge_cup_readiness.py",
            "python scripts/check_challenge_cup_goal_completion.py",
        ],
    }


def source_custody_categories() -> list[dict[str, Any]]:
    return [
        category_payload(
            "expert_feedback",
            "real reviewer signed form, email reply, meeting minutes, or chat screenshot",
            EXPERT_PREFLIGHT_COMMAND,
            EXPERT_RECORD_COMMAND,
        ),
        category_payload(
            "timed_rehearsal",
            "real timer screenshot, screen recording, observer note, or missed-question list",
            REHEARSAL_PREFLIGHT_COMMAND,
            REHEARSAL_RUN_COMMAND,
        ),
    ]


def build_payload() -> dict[str, Any]:
    return {
        "report_type": REPORT_TYPE,
        "status": STATUS,
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "required_before_goal_completion": REQUIRED_BEFORE_GOAL_COMPLETION,
        "boundary": BOUNDARY,
        "source_custody_categories": source_custody_categories(),
        "integrity_guardrails": INTEGRITY_GUARDRAILS,
        "output_files": [repo_path(OUTPUT_MD), repo_path(OUTPUT_JSON)],
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Hard Evidence Source Custody",
        "",
        f"- report_type: `{payload['report_type']}`",
        f"- status: `{payload['status']}`",
        f"- completion_claim_allowed: `{payload['completion_claim_allowed']}`",
        "- does_not_satisfy_goal_completion=True",
        f"- boundary: {payload['boundary']}",
        "",
        "## Integrity Guardrails",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["integrity_guardrails"])
    for category in payload["source_custody_categories"]:
        lines.extend(
            [
                "",
                f"## {category['category_id']}",
                "",
                f"- source_role: {category['source_role']}",
                f"- counts_as_hard_evidence_after_record_only: `{category['counts_as_hard_evidence_after_record_only']}`",
                f"- does_not_satisfy_goal_completion_before_record: `{category['does_not_satisfy_goal_completion_before_record']}`",
                "",
                "### Source Restrictions",
                "",
            ]
        )
        lines.extend(f"- {item}" for item in category["source_restrictions"])
        lines.extend(
            [
                "",
                "### Custody Checkpoints",
                "",
                "| ID | State | Command | Acceptance Signal |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in category["custody_checkpoints"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{item['checkpoint_id']}`",
                        item["evidence_state"],
                        f"`{item['command']}`",
                        item["acceptance_signal"],
                    ]
                )
                + " |"
            )
        lines.extend(["", "### Operator Commands", ""])
        lines.extend(f"- `{item}`" for item in category["operator_commands"])
    write_text(path, "\n".join(lines))


def write_outputs(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or build_payload()
    write_text(OUTPUT_JSON, json.dumps(payload, ensure_ascii=False, indent=2))
    write_markdown(OUTPUT_MD, payload)
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"hard evidence source custody: {repo_path(OUTPUT_MD)}")
    print(f"Status: {payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
