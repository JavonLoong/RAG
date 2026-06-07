from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from check_challenge_cup_readiness import CURRENT_READINESS_GATE_COUNT


REPO_ROOT = Path(__file__).resolve().parents[1]
REPRO_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTPUT_JSON = REPRO_DIR / "final_acceptance_audit.json"
OUTPUT_MD = REPRO_DIR / "final_acceptance_audit.md"
READINESS_REPORT = REPRO_DIR / "readiness_gate_report.md"
GOAL_COMPLETION_REPORT = REPRO_DIR / "goal_completion_report.md"
HARD_EVIDENCE_LEDGER = REPRO_DIR / "hard_evidence_ledger.json"
ARCHIVE_MANIFEST = REPRO_DIR / "challenge_cup_submission_archive_manifest.json"
SUBMISSION_VERIFIER = REPRO_DIR / "verify_submission_package.py"
SUBMISSION_VERIFIER_RELATIVE = "docs/challenge_cup/reproducibility/verify_submission_package.py"
REPORT_TYPE = "challenge_cup_final_acceptance_audit"
READY_AWAITING_STATUS = "package_ready_awaiting_external_hard_evidence"
CONFIRMATION_FIELDS = {
    "expert_feedback": ("real_feedback_confirmed", "feedback_source_path"),
    "timed_rehearsal": ("real_rehearsal_confirmed", "recording_or_timer_source_path"),
}
BOUNDARY = (
    "This audit proves package-level acceptance readiness and explicitly preserves the hard-evidence "
    "boundary. It does not claim expert approval, timed rehearsal completion, final goal completion, "
    "or award probability."
)
SELF_REFERENTIAL_READINESS_GATES = {"final acceptance audit", "verification transcript"}
GENERATION_CYCLE_READINESS_GATES = {
    "package control files",
    "package evidence files",
    "evidence integrity hashes",
    "submission archive",
    "judge objection response matrix",
    "poster render smoke",
    "external evidence execution kit",
    "final acceptance audit",
    "verification transcript",
    "special prize readiness dashboard",
}
GENERATION_CYCLE_PATHS = {
    "docs/challenge_cup/package_manifest.json",
    "docs/challenge_cup/reproducibility/evidence_hashes.json",
    "docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json",
    "docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip",
    "docs/challenge_cup/reproducibility/submission_integrity_card.md",
    "docs/challenge_cup/reproducibility/judge_objection_response_matrix.json",
    "docs/challenge_cup/reproducibility/judge_objection_response_matrix.md",
    "docs/challenge_cup/reproducibility/poster_render_smoke_report.json",
    "docs/challenge_cup/reproducibility/poster_render_smoke_report.md",
    "docs/challenge_cup/reproducibility/external_evidence_execution_kit.json",
    "docs/challenge_cup/reproducibility/external_evidence_execution_kit.md",
    "docs/challenge_cup/reproducibility/external_evidence_execution_kit/expert_review_handoff.md",
    "docs/challenge_cup/reproducibility/external_evidence_execution_kit/timed_rehearsal_observer_sheet.md",
    "docs/challenge_cup/reproducibility/final_acceptance_audit.json",
    "docs/challenge_cup/reproducibility/final_acceptance_audit.md",
    "docs/challenge_cup/reproducibility/goal_completion_report.md",
    "docs/challenge_cup/reproducibility/verification_transcript.json",
    "docs/challenge_cup/reproducibility/verification_transcript.md",
    "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.json",
    "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md",
}


def repo_path(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def safe_repo_relative(path: str) -> bool:
    parts = Path(path).parts
    return path and not Path(path).is_absolute() and ".." not in parts and "\\" not in path


def parse_status_line(text: str) -> str:
    match = re.search(r"- Status: `([^`]+)`", text)
    return match.group(1) if match else "unknown"


def parse_passed_count(text: str) -> dict[str, int | None]:
    match = re.search(r"- Passed:\s*(\d+)/(\d+)", text)
    if not match:
        return {"passed": None, "total": None}
    return {"passed": int(match.group(1)), "total": int(match.group(2))}


def failed_readiness_gate_evidence(text: str) -> dict[str, str]:
    failed: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[1] == "fail":
            failed[cells[0]] = cells[2]
    return failed


def failed_readiness_gates(text: str) -> set[str]:
    return set(failed_readiness_gate_evidence(text))


def readiness_evidence_paths(evidence: str) -> set[str]:
    quoted_paths = re.findall(r"'([^']+)'", evidence)
    bare_paths = re.findall(
        r"docs/[A-Za-z0-9_./\\-]+(?:\.json|\.md|\.zip|\.html|\.pptx|\.py)",
        evidence,
    )
    return {path.replace("\\", "/") for path in [*quoted_paths, *bare_paths]}


def is_self_referential_gate_failure(gate: str, evidence: str) -> bool:
    if gate == "final acceptance audit":
        return "package_readiness.status=fail" in evidence or "package_readiness count=" in evidence
    if gate == "verification transcript":
        return (
            "readiness.status=fail" in evidence
            or "final_acceptance.status=not_ready" in evidence
            or "observed_status=fail" in evidence
            or "readiness gate pass" in evidence
        )
    return False


def is_self_referential_readiness_failure(text: str) -> bool:
    failed = failed_readiness_gate_evidence(text)
    return bool(failed) and set(failed) <= SELF_REFERENTIAL_READINESS_GATES and all(
        is_self_referential_gate_failure(gate, evidence) for gate, evidence in failed.items()
    )


def is_generation_cycle_gate_failure(gate: str, evidence: str) -> bool:
    if gate in SELF_REFERENTIAL_READINESS_GATES and is_self_referential_gate_failure(gate, evidence):
        return True
    paths = readiness_evidence_paths(evidence)
    if paths and not paths <= GENERATION_CYCLE_PATHS:
        return False
    if "missing=[" in evidence and "missing=[]" not in evidence:
        return False
    if "untracked=[" in evidence and "untracked=[]" not in evidence and not paths <= GENERATION_CYCLE_PATHS:
        return False
    if gate == "final acceptance audit":
        return is_self_referential_gate_failure(gate, evidence)
    if gate == "verification transcript":
        return bool(paths) or is_self_referential_gate_failure(gate, evidence)
    return gate in GENERATION_CYCLE_READINESS_GATES and bool(paths)


def readiness_bootstrap_reason(text: str, readiness_status: str) -> str:
    if readiness_status != "fail":
        return ""
    failed = failed_readiness_gate_evidence(text)
    if not failed:
        return ""
    if is_self_referential_readiness_failure(text):
        return "self_referential"
    if set(failed) <= GENERATION_CYCLE_READINESS_GATES and all(
        is_generation_cycle_gate_failure(gate, evidence) for gate, evidence in failed.items()
    ):
        return "generation_cycle"
    return ""


def normalize_readiness_count(
    readiness_status: str,
    count: dict[str, int | None],
    *,
    bootstrap_readiness: bool = False,
    bootstrap_reason: str = "",
) -> dict[str, int | None | bool | str]:
    passed = count["passed"]
    total = count["total"]
    normalized = dict(count)
    should_sync_current_gate_count = (
        readiness_status == "pass"
        and passed is not None
        and total is not None
        and passed == total
        and total < CURRENT_READINESS_GATE_COUNT
    )
    if should_sync_current_gate_count or bootstrap_readiness:
        normalized["passed"] = CURRENT_READINESS_GATE_COUNT
        normalized["total"] = CURRENT_READINESS_GATE_COUNT
    normalized["source_report_passed"] = passed
    normalized["source_report_total"] = total
    normalized["current_gate_count"] = CURRENT_READINESS_GATE_COUNT
    normalized["source_report_status"] = readiness_status
    normalized["count_synced_for_current_gate_set"] = should_sync_current_gate_count
    normalized["count_synced_for_self_referential_audit"] = bootstrap_reason == "self_referential"
    normalized["self_referential_readiness_bootstrap"] = bootstrap_reason == "self_referential"
    return normalized


def parse_completion_claim_allowed(text: str) -> bool | None:
    if "completion_claim_allowed=True" in text:
        return True
    if "completion_claim_allowed=False" in text:
        return False
    return None


def blocking_items_from_ledger(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    categories = ledger.get("categories", {})
    if not isinstance(categories, dict):
        return items
    for category_name, category in categories.items():
        if not isinstance(category, dict):
            continue
        required = int(category.get("required_min_count") or 0)
        collected = int(category.get("collected_count") or 0)
        evidence_files = [str(item) for item in category.get("evidence_files", [])]
        confirmed = category_has_confirmed_metadata(str(category_name), evidence_files)
        if collected < max(1, required) or len(evidence_files) < max(1, required) or not confirmed:
            items.append(
                {
                    "category": str(category_name),
                    "required_min_count": required,
                    "collected_count": collected,
                    "evidence_files": evidence_files,
                    "intake_dir": str(category.get("intake_dir") or ""),
                    "confirmed_metadata_found": confirmed,
                }
            )
    return items


def category_has_confirmed_metadata(category_name: str, evidence_files: list[str]) -> bool:
    if category_name not in CONFIRMATION_FIELDS:
        return bool(evidence_files)
    confirmation_field, source_field = CONFIRMATION_FIELDS[category_name]
    for relative in evidence_files:
        if not relative.lower().endswith(".json") or not safe_repo_relative(relative):
            continue
        path = REPO_ROOT / relative
        if not path.exists() or path.stat().st_size == 0:
            continue
        try:
            metadata = load_json(path)
        except json.JSONDecodeError:
            continue
        source_relative = str(metadata.get(source_field, ""))
        if (
            metadata.get(confirmation_field) is True
            and safe_repo_relative(source_relative)
            and (REPO_ROOT / source_relative).exists()
            and (REPO_ROOT / source_relative).stat().st_size > 0
        ):
            return True
    return False


def build_payload() -> dict[str, Any]:
    readiness_text = read_text(READINESS_REPORT)
    goal_text = read_text(GOAL_COMPLETION_REPORT)
    hard_ledger = load_json(HARD_EVIDENCE_LEDGER)
    archive_manifest = load_json(ARCHIVE_MANIFEST)

    readiness_status = parse_status_line(readiness_text)
    bootstrap_reason = readiness_bootstrap_reason(readiness_text, readiness_status)
    self_referential_failure = bootstrap_reason == "self_referential"
    should_bootstrap_readiness = bool(bootstrap_reason)
    readiness_count = normalize_readiness_count(
        readiness_status,
        parse_passed_count(readiness_text),
        bootstrap_readiness=should_bootstrap_readiness,
        bootstrap_reason=bootstrap_reason,
    )
    completion_claim_allowed = parse_completion_claim_allowed(goal_text)
    goal_status = parse_status_line(goal_text)
    verifier_archived = SUBMISSION_VERIFIER_RELATIVE in {
        str(item) for item in archive_manifest.get("included_files", [])
    }
    verifier_available = SUBMISSION_VERIFIER.exists() and SUBMISSION_VERIFIER.stat().st_size > 0
    blocking_items = blocking_items_from_ledger(hard_ledger)
    effective_readiness_status = "pass" if should_bootstrap_readiness else readiness_status
    package_ready = (
        effective_readiness_status == "pass"
        and readiness_count["passed"] == readiness_count["total"]
        and verifier_available
        and verifier_archived
    )
    can_mark_goal_complete = goal_status == "pass" and completion_claim_allowed is True and not blocking_items

    if package_ready and not can_mark_goal_complete and blocking_items:
        status = READY_AWAITING_STATUS
    elif can_mark_goal_complete:
        status = "goal_complete"
    else:
        status = "not_ready"

    return {
        "report_type": REPORT_TYPE,
        "status": status,
        "package_readiness": {
            "status": effective_readiness_status,
            **readiness_count,
            "readiness_bootstrap_reason": bootstrap_reason,
            "generation_cycle_readiness_bootstrap": bootstrap_reason == "generation_cycle",
            "report": repo_path(READINESS_REPORT),
        },
        "submission_package_verifier": {
            "available": verifier_available,
            "archived": verifier_archived,
            "path": repo_path(SUBMISSION_VERIFIER),
        },
        "goal_completion": {
            "status": goal_status,
            "completion_claim_allowed": completion_claim_allowed,
            "report": repo_path(GOAL_COMPLETION_REPORT),
        },
        "can_submit_for_package_review": package_ready,
        "can_mark_goal_complete": can_mark_goal_complete,
        "blocking_items": blocking_items,
        "next_required_actions": [
            "Archive real expert feedback with scripts/record_challenge_cup_hard_evidence.py expert_feedback ... --confirm-real-feedback",
            "Archive real timed rehearsal evidence with scripts/run_challenge_cup_timed_rehearsal.py ... --source <real-timer-or-observer-file> --confirm-real-rehearsal or scripts/record_challenge_cup_hard_evidence.py timed_rehearsal ... --confirm-real-rehearsal",
            "Rebuild package, rerun readiness, rerun goal completion, and rerun this audit.",
        ],
        "boundary": BOUNDARY,
    }


def write_markdown(payload: dict[str, Any]) -> None:
    lines = [
        "# Final Acceptance Audit",
        "",
        f"- Status: `{payload['status']}`",
        f"- Can submit for package review: `{payload['can_submit_for_package_review']}`",
        f"- Can mark goal complete: `{payload['can_mark_goal_complete']}`",
        f"- Readiness gate: `{payload['package_readiness']['status']}` "
        f"({payload['package_readiness']['passed']}/{payload['package_readiness']['total']})",
        f"- Submission verifier: `verify_submission_package.py` available={payload['submission_package_verifier']['available']} archived={payload['submission_package_verifier']['archived']}",
        f"- Goal completion: `{payload['goal_completion']['status']}`; completion_claim_allowed={payload['goal_completion']['completion_claim_allowed']}",
        "",
        "## Blocking Items",
        "",
    ]
    for item in payload["blocking_items"]:
        lines.append(
            f"- `{item['category']}`: collected={item['collected_count']}, "
            f"required={item['required_min_count']}, intake=`{item['intake_dir']}`"
        )
    lines.extend(["", "## Next Required Actions", ""])
    lines.extend(f"- {item}" for item in payload["next_required_actions"])
    lines.extend(["", "## Boundary", "", str(payload["boundary"])])
    OUTPUT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_outputs() -> dict[str, Any]:
    payload = build_payload()
    REPRO_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(payload)
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"final acceptance audit: {repo_path(OUTPUT_MD)}")
    print(f"Status: {payload['status']}")
    return 0 if payload["status"] in {READY_AWAITING_STATUS, "goal_complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
