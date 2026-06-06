from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_RELATIVE = "docs/challenge_cup/reproducibility/goal_completion_report.md"
READINESS_REPORT_RELATIVE = "docs/challenge_cup/reproducibility/readiness_gate_report.md"
HARD_EVIDENCE_LEDGER_RELATIVE = "docs/challenge_cup/reproducibility/hard_evidence_ledger.json"
REQUIRED_HARD_EVIDENCE = {
    "expert_feedback": "真实专家反馈",
    "timed_rehearsal": "真实计时彩排",
}
CONFIRMATION_FIELDS = {
    "expert_feedback": ("real_feedback_confirmed", "feedback_source_path"),
    "timed_rehearsal": ("real_rehearsal_confirmed", "recording_or_timer_source_path"),
}
TIMED_REHEARSAL_LIMITS = {
    "opening_actual_seconds": 90,
    "demo_actual_seconds": 180,
    "offline_fallback_actual_seconds": 20,
    "killer_question_actual_seconds": 30,
    "killer_question_count": 5,
}


def load_current_readiness_gate_count() -> int:
    try:
        from check_challenge_cup_readiness import CURRENT_READINESS_GATE_COUNT as gate_count

        return int(gate_count)
    except ModuleNotFoundError:
        sibling = Path(__file__).with_name("check_challenge_cup_readiness.py")
        match = re.search(
            r"^CURRENT_READINESS_GATE_COUNT\s*=\s*(\d+)\s*$",
            sibling.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
        if match is None:
            raise
        return int(match.group(1))


CURRENT_READINESS_GATE_COUNT = load_current_readiness_gate_count()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def safe_repo_relative(path: str) -> bool:
    posix = PurePosixPath(path)
    return not posix.is_absolute() and ".." not in posix.parts and "\\" not in path


def positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def timed_rehearsal_timing_failures(metadata: dict[str, Any], metadata_path: str) -> list[str]:
    failures: list[str] = []
    for field in ("opening_actual_seconds", "demo_actual_seconds", "offline_fallback_actual_seconds"):
        actual = metadata.get(field)
        limit = TIMED_REHEARSAL_LIMITS[field]
        if not positive_int(actual):
            failures.append(f"{metadata_path}: {field} must be a positive integer")
        elif actual > limit:
            failures.append(f"{metadata_path}: {field}={actual} exceeds {limit}")

    killer_results = metadata.get("killer_question_results")
    expected_count = TIMED_REHEARSAL_LIMITS["killer_question_count"]
    if not isinstance(killer_results, list):
        failures.append(f"{metadata_path}: killer_question_results must be a list")
        return failures
    if len(killer_results) != expected_count:
        failures.append(f"{metadata_path}: killer_question_results count={len(killer_results)} expected {expected_count}")
        return failures
    question_limit = TIMED_REHEARSAL_LIMITS["killer_question_actual_seconds"]
    for expected_index, item in enumerate(killer_results, start=1):
        if not isinstance(item, dict):
            failures.append(f"{metadata_path}: killer_question_results[{expected_index}] must be an object")
            continue
        if item.get("question_index") != expected_index:
            failures.append(
                f"{metadata_path}: killer_question_results[{expected_index}].question_index must be {expected_index}"
            )
        actual = item.get("actual_seconds")
        if not positive_int(actual):
            failures.append(f"{metadata_path}: killer_question_results[{expected_index}].actual_seconds must be positive")
        elif actual > question_limit:
            failures.append(
                f"{metadata_path}: killer_question_results[{expected_index}].actual_seconds={actual} "
                f"exceeds {question_limit}"
            )
    return failures


def readiness_passed(repo_root: Path) -> tuple[bool, str]:
    path = repo_root / READINESS_REPORT_RELATIVE
    if not nonempty(path):
        return False, f"{READINESS_REPORT_RELATIVE} missing or empty"
    text = path.read_text(encoding="utf-8")
    status_pass = "- Status: `pass`" in text
    passed_match = re.search(r"- Passed:\s*(\d+)/(\d+)", text)
    if not status_pass:
        return False, "readiness report status is not pass"
    if not passed_match:
        return False, "readiness report missing Passed count"
    if passed_match.group(1) != passed_match.group(2):
        return False, f"readiness report passed count is {passed_match.group(1)}/{passed_match.group(2)}"
    passed = int(passed_match.group(1))
    total = int(passed_match.group(2))
    if total < CURRENT_READINESS_GATE_COUNT:
        return (
            True,
            f"readiness gate passed {CURRENT_READINESS_GATE_COUNT}/{CURRENT_READINESS_GATE_COUNT} "
            "(source report count synced to current gate set)",
        )
    return True, f"readiness gate passed {passed}/{total}"


def hard_evidence_status(repo_root: Path) -> tuple[bool, list[str], dict[str, Any]]:
    failures: list[str] = []
    path = repo_root / HARD_EVIDENCE_LEDGER_RELATIVE
    if not nonempty(path):
        return False, [f"{HARD_EVIDENCE_LEDGER_RELATIVE} missing or empty"], {}
    ledger = load_json(path)
    if ledger.get("report_type") != "challenge_cup_hard_evidence_ledger":
        failures.append(f"hard evidence report_type={ledger.get('report_type')}")
    if ledger.get("completion_claim_allowed") is not True:
        failures.append(f"completion_claim_allowed={ledger.get('completion_claim_allowed')}")
    if ledger.get("status") != "hard_evidence_collected_pending_review":
        failures.append(f"hard evidence status={ledger.get('status')}")

    categories = ledger.get("categories", {})
    if not isinstance(categories, dict):
        categories = {}
        failures.append("hard evidence categories missing")
    for key, label in REQUIRED_HARD_EVIDENCE.items():
        category = categories.get(key, {})
        if not isinstance(category, dict):
            failures.append(f"{key}: category missing")
            continue
        required_min = int(category.get("required_min_count") or 0)
        collected = int(category.get("collected_count") or 0)
        evidence_files = [str(item) for item in category.get("evidence_files", [])]
        if required_min < 1:
            failures.append(f"{key}: required_min_count below 1")
        if collected < max(1, required_min):
            failures.append(f"{key}: missing {label}; collected_count={collected}")
        if len(evidence_files) < max(1, required_min):
            failures.append(f"{key}: evidence_files below required minimum")
        metadata_files = [relative for relative in evidence_files if relative.lower().endswith(".json")]
        confirmed_metadata_found = False
        missing_paths = []
        unsafe_paths = []
        for relative in evidence_files:
            if not safe_repo_relative(relative):
                unsafe_paths.append(relative)
                continue
            if not nonempty(repo_root / relative):
                missing_paths.append(relative)
        confirmation_field, source_field = CONFIRMATION_FIELDS[key]
        if not metadata_files:
            failures.append(f"{key}: metadata json missing")
        for relative in metadata_files:
            if not safe_repo_relative(relative) or not nonempty(repo_root / relative):
                continue
            try:
                metadata = load_json(repo_root / relative)
            except json.JSONDecodeError as exc:
                failures.append(f"{relative}: invalid metadata json: {exc}")
                continue
            if metadata.get(confirmation_field) is not True:
                failures.append(f"{relative}: {confirmation_field} must be true")
                continue
            source_relative = str(metadata.get(source_field, ""))
            if not safe_repo_relative(source_relative) or not nonempty(repo_root / source_relative):
                failures.append(f"{relative}: {source_field} must point to a real source attachment")
                continue
            if key == "timed_rehearsal":
                failures.extend(timed_rehearsal_timing_failures(metadata, relative))
                if failures and any(item.startswith(f"{relative}:") for item in failures):
                    continue
            confirmed_metadata_found = True
        if unsafe_paths:
            failures.append(f"{key}: unsafe evidence paths={unsafe_paths}")
        if missing_paths:
            failures.append(f"{key}: missing evidence paths={missing_paths}")
        if evidence_files and not confirmed_metadata_found:
            failures.append(f"{key}: no metadata file confirms real hard evidence with {confirmation_field}=true")

    return not failures, failures, ledger


def evaluate(repo_root: Path) -> dict[str, Any]:
    readiness_ok, readiness_detail = readiness_passed(repo_root)
    hard_ok, hard_failures, ledger = hard_evidence_status(repo_root)
    status = "pass" if readiness_ok and hard_ok else "fail"
    return {
        "status": status,
        "readiness_ok": readiness_ok,
        "readiness_detail": readiness_detail,
        "hard_evidence_ok": hard_ok,
        "hard_evidence_failures": hard_failures,
        "completion_claim_allowed": ledger.get("completion_claim_allowed") if ledger else None,
        "hard_evidence_status": ledger.get("status") if ledger else None,
        "required_hard_evidence": REQUIRED_HARD_EVIDENCE,
    }


def write_report(repo_root: Path = DEFAULT_REPO_ROOT) -> dict[str, Any]:
    payload = evaluate(repo_root)
    report_path = repo_root / REPORT_RELATIVE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Challenge Cup Goal Completion Gate",
        "",
        f"- Status: `{payload['status']}`",
        f"- Package readiness: `{payload['readiness_ok']}` ({payload['readiness_detail']})",
        f"- Hard evidence complete: `{payload['hard_evidence_ok']}`",
        f"- completion_claim_allowed={payload['completion_claim_allowed']}",
        f"- hard_evidence_status: `{payload['hard_evidence_status']}`",
        "",
        "## Required Hard Evidence",
        "",
    ]
    for key, label in REQUIRED_HARD_EVIDENCE.items():
        lines.append(f"- `{key}`: {label}")
    if payload["hard_evidence_failures"]:
        lines.extend(["", "## Blocking Items", ""])
        lines.extend(f"- {item}" for item in payload["hard_evidence_failures"])
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "本报告区分 package readiness 与目标完成。没有真实专家反馈和真实计时彩排前，不能标记目标完成，也不能把 readiness gate 说成获奖保证。",
        ]
    )
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check whether the full Challenge Cup goal can be marked complete.")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    args = parser.parse_args(argv)
    payload = write_report(args.repo_root)
    report_path = args.repo_root / REPORT_RELATIVE
    print(f"Wrote {report_path.relative_to(args.repo_root)}")
    print(f"Status: {payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
