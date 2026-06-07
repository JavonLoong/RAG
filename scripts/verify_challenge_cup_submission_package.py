from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


PACKAGE_RELATIVE = PurePosixPath("docs/challenge_cup")
PACKAGE_MANIFEST_RELATIVE = PACKAGE_RELATIVE / "package_manifest.json"
EVIDENCE_HASHES_RELATIVE = PACKAGE_RELATIVE / "reproducibility/evidence_hashes.json"
LIVE_SMOKE_RELATIVE = PACKAGE_RELATIVE / "reproducibility/live_demo_smoke_report.json"
BROWSER_SMOKE_RELATIVE = PACKAGE_RELATIVE / "reproducibility/browser_demo_smoke_report.json"
GOAL_COMPLETION_RELATIVE = PACKAGE_RELATIVE / "reproducibility/goal_completion_report.md"
REPORT_TYPE = "challenge_cup_submission_package_verification"
COMPLETION_CLAIM_ALLOWED_RE = re.compile(r"^- completion_claim_allowed=(True|False)\s*$", re.MULTILINE)
REQUIRED_GOAL_COMPLETION_NEXT_ACTION_TERMS = (
    "## Next Actions",
    "docs/challenge_cup/reproducibility/external_evidence_closeout_checklist.md",
    "python scripts/record_challenge_cup_hard_evidence.py expert_feedback",
    "python scripts/run_challenge_cup_timed_rehearsal.py",
    "python scripts/build_challenge_cup_package.py",
    "python scripts/check_challenge_cup_goal_completion.py",
)
REQUIRED_GOAL_COMPLETION_READABLE_BOUNDARY_TERMS = (
    "真实专家反馈",
    "真实计时彩排",
    "不能标记目标完成",
    "不能把 readiness gate 说成获奖保证",
)
FORBIDDEN_GOAL_COMPLETION_MOJIBAKE_TERMS = (
    "鐪熚疄",
    "鍙嶉",
    "褰╂帓",
    "涓嶈兘",
    "鏈姤",
    "鎶?readiness",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(raw: str) -> bool:
    posix = PurePosixPath(raw)
    return not posix.is_absolute() and ".." not in posix.parts and "\\" not in raw


def path_for(root: Path, relative: str | PurePosixPath) -> Path:
    raw = str(relative)
    if not safe_relative_path(raw):
        raise ValueError(f"unsafe path: {raw}")
    return root / Path(*PurePosixPath(raw).parts)


def load_json(root: Path, relative: str | PurePosixPath, failures: list[str]) -> dict[str, Any]:
    path = path_for(root, relative)
    if not path.exists() or path.stat().st_size == 0:
        failures.append(f"{relative} missing or empty")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        failures.append(f"{relative} invalid json: {exc}")
        return {}


def read_text(root: Path, relative: str | PurePosixPath, failures: list[str]) -> str:
    path = path_for(root, relative)
    if not path.exists() or path.stat().st_size == 0:
        failures.append(f"{relative} missing or empty")
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def parse_completion_claim_allowed(text: str, failures: list[str]) -> bool | None:
    match = COMPLETION_CLAIM_ALLOWED_RE.search(text)
    if match:
        return match.group(1) == "True"
    failures.append("goal completion report missing completion_claim_allowed")
    return None


def goal_completion_next_actions_ready(text: str, failures: list[str]) -> bool:
    missing = [term for term in REQUIRED_GOAL_COMPLETION_NEXT_ACTION_TERMS if term not in text]
    if missing:
        failures.append(f"goal completion report missing next actions: {missing}")
        return False
    return True


def goal_completion_boundary_readable(text: str, failures: list[str]) -> bool:
    missing = [term for term in REQUIRED_GOAL_COMPLETION_READABLE_BOUNDARY_TERMS if term not in text]
    forbidden = [term for term in FORBIDDEN_GOAL_COMPLETION_MOJIBAKE_TERMS if term in text]
    if missing:
        failures.append(f"goal completion report missing readable boundary terms: {missing}")
    if forbidden:
        failures.append(f"goal completion report contains mojibake boundary terms: {forbidden}")
    return not missing and not forbidden


def verify_package(root: Path) -> dict[str, Any]:
    root = root.resolve()
    failures: list[str] = []

    manifest = load_json(root, PACKAGE_MANIFEST_RELATIVE, failures)
    hashes = load_json(root, EVIDENCE_HASHES_RELATIVE, failures)
    live_smoke = load_json(root, LIVE_SMOKE_RELATIVE, failures)
    browser_smoke = load_json(root, BROWSER_SMOKE_RELATIVE, failures)
    goal_completion = read_text(root, GOAL_COMPLETION_RELATIVE, failures)

    evidence_files = [str(item) for item in manifest.get("evidence_files", []) if isinstance(item, str)]
    excluded = {str(item) for item in hashes.get("excluded_self_reports", []) if isinstance(item, str)}
    expected_hashed = sorted(path for path in evidence_files if path not in excluded)
    hash_entries = hashes.get("files", [])
    entry_by_path = {
        str(item.get("path", "")): item
        for item in hash_entries
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }

    if manifest.get("integrity_manifest") != str(EVIDENCE_HASHES_RELATIVE):
        failures.append(f"integrity_manifest={manifest.get('integrity_manifest')}")
    if hashes.get("algorithm") != "sha256":
        failures.append(f"hash algorithm={hashes.get('algorithm')}")
    if sorted(entry_by_path) != expected_hashed:
        missing = sorted(path for path in expected_hashed if path not in entry_by_path)
        extra = sorted(path for path in entry_by_path if path not in expected_hashed)
        failures.append(f"hash manifest path mismatch: missing={missing}, extra={extra}")

    evidence_verified = 0
    hashed_verified = 0
    for relative in evidence_files:
        if not safe_relative_path(relative):
            failures.append(f"unsafe evidence path: {relative}")
            continue
        if relative in excluded:
            continue
        path = path_for(root, relative)
        if not path.exists() or path.stat().st_size == 0:
            failures.append(f"evidence file missing or empty: {relative}")
            continue
        evidence_verified += 1
        entry = entry_by_path.get(relative)
        if entry is None:
            continue
        if int(entry.get("bytes") or -1) != path.stat().st_size:
            failures.append(f"bytes mismatch: {relative}")
        if str(entry.get("sha256", "")) != sha256_file(path):
            failures.append(f"sha256 mismatch: {relative}")
        else:
            hashed_verified += 1

    live_status = str(live_smoke.get("status", "missing"))
    browser_status = str(browser_smoke.get("status", "missing"))
    if live_status != "pass":
        failures.append(f"live smoke status={live_status}")
    if browser_status != "pass":
        failures.append(f"browser smoke status={browser_status}")

    goal_status = "pass" if "Status: `pass`" in goal_completion else "fail" if "Status: `fail`" in goal_completion else "unknown"
    completion_claim_allowed = parse_completion_claim_allowed(goal_completion, failures)
    if goal_status == "pass" and completion_claim_allowed is not True:
        failures.append("goal completion passed without completion_claim_allowed=True")
    if goal_status == "fail" and completion_claim_allowed is True:
        failures.append("goal completion failed while completion_claim_allowed=True")
    if goal_status == "unknown":
        failures.append("goal completion status missing")
    next_actions_ready = True
    readable_boundary_ready = goal_completion_boundary_readable(goal_completion, failures)
    if goal_status == "fail":
        next_actions_ready = goal_completion_next_actions_ready(goal_completion, failures)

    return {
        "report_type": REPORT_TYPE,
        "root": str(root),
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "evidence_files_verified": evidence_verified,
        "hashed_files_verified": hashed_verified,
        "excluded_self_reports": sorted(excluded),
        "live_smoke_status": live_status,
        "browser_smoke_status": browser_status,
        "goal_completion_status": goal_status,
        "completion_claim_allowed": completion_claim_allowed,
        "goal_completion_next_actions_ready": next_actions_ready,
        "goal_completion_readable_boundary_ready": readable_boundary_ready,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify an extracted Challenge Cup submission package.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Extraction root containing docs/challenge_cup.")
    parser.add_argument("--json-output", type=Path, help="Optional JSON report path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = verify_package(args.root)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Status: {payload['status']}")
    print(f"Evidence files verified: {payload['evidence_files_verified']}")
    print(f"Hashed files verified: {payload['hashed_files_verified']}")
    if payload["failures"]:
        print("Failures:")
        for failure in payload["failures"]:
            print(f"- {failure}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
