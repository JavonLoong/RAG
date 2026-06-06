from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTPUT_JSON = OUTPUT_DIR / "hard_evidence_ledger.json"
OUTPUT_MD = OUTPUT_DIR / "hard_evidence_ledger.md"
INTAKE_ROOT = OUTPUT_DIR / "hard_evidence"
EXPERT_DIR = INTAKE_ROOT / "expert_feedback"
REHEARSAL_DIR = INTAKE_ROOT / "timed_rehearsal"
ROOT_README = INTAKE_ROOT / "README.md"
EXPERT_README = EXPERT_DIR / "README.md"
REHEARSAL_README = REHEARSAL_DIR / "README.md"

REPORT_TYPE = "challenge_cup_hard_evidence_ledger"
AWAITING_STATUS = "awaiting_real_external_feedback_and_timed_rehearsal"
READY_FOR_REVIEW_STATUS = "hard_evidence_collected_pending_review"
REQUIRED_BEFORE_GOAL_COMPLETION = ["expert_feedback", "timed_rehearsal"]
EXPERT_PREFLIGHT_COMMAND = (
    "python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback "
    "--id <real-feedback-id> --source <real-feedback-file> --evidence-type email_reply "
    "--reviewer-identity <real-reviewer-identity> --role-or-org <real-reviewer-role-or-org> "
    "--review-date <real-review-date-yyyy-mm-dd> --review-dimension practicality "
    "--review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> "
    "--remediation-action <action> --confirm-real-feedback"
)
EXPERT_RECORD_COMMAND = (
    "python scripts/record_challenge_cup_hard_evidence.py expert_feedback "
    "--id <real-feedback-id> --source <real-feedback-file> --evidence-type email_reply "
    "--reviewer-identity <real-reviewer-identity> --role-or-org <real-reviewer-role-or-org> "
    "--review-date <real-review-date-yyyy-mm-dd> --review-dimension practicality "
    "--review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> "
    "--remediation-action <action> --confirm-real-feedback"
)
REHEARSAL_RUN_COMMAND = (
    "python scripts/run_challenge_cup_timed_rehearsal.py --id <real-rehearsal-id> "
    "--rehearsal-date <real-rehearsal-date-yyyy-mm-dd> --observer <real-observer-alias> "
    "--opening-actual-seconds <actual-opening-seconds> --demo-actual-seconds <actual-demo-seconds> "
    "--offline-fallback-actual-seconds <actual-offline-fallback-seconds> "
    "--killer-question-seconds <q1-seconds> <q2-seconds> <q3-seconds> <q4-seconds> <q5-seconds> "
    "--confirm-real-rehearsal"
)
REHEARSAL_PREFLIGHT_COMMAND = (
    "python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal "
    "--id <real-rehearsal-id> --source <real-timer-or-observer-file> --evidence-type observer_note "
    "--rehearsal-date <real-rehearsal-date-yyyy-mm-dd> --observer <real-observer-alias> "
    "--opening-actual-seconds <actual-opening-seconds> --demo-actual-seconds <actual-demo-seconds> "
    "--offline-fallback-actual-seconds <actual-offline-fallback-seconds> "
    "--killer-question-seconds <q1-seconds> <q2-seconds> <q3-seconds> <q4-seconds> <q5-seconds> "
    "--confirm-real-rehearsal"
)
REHEARSAL_RECORD_COMMAND = (
    "python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal "
    "--id <real-rehearsal-id> --source <real-timer-or-observer-file> --evidence-type observer_note "
    "--rehearsal-date <real-rehearsal-date-yyyy-mm-dd> --observer <real-observer-alias> "
    "--opening-actual-seconds <actual-opening-seconds> --demo-actual-seconds <actual-demo-seconds> "
    "--offline-fallback-actual-seconds <actual-offline-fallback-seconds> "
    "--killer-question-seconds <q1-seconds> <q2-seconds> <q3-seconds> <q4-seconds> <q5-seconds> "
    "--confirm-real-rehearsal"
)

PLACEHOLDER_NAME_FRAGMENTS = {
    "example",
    "placeholder",
    "sample",
    "template",
    "todo",
}


def configure_paths(repo_root: Path) -> None:
    global REPO_ROOT, OUTPUT_DIR, OUTPUT_JSON, OUTPUT_MD
    global INTAKE_ROOT, EXPERT_DIR, REHEARSAL_DIR, ROOT_README, EXPERT_README, REHEARSAL_README

    REPO_ROOT = repo_root
    OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
    OUTPUT_JSON = OUTPUT_DIR / "hard_evidence_ledger.json"
    OUTPUT_MD = OUTPUT_DIR / "hard_evidence_ledger.md"
    INTAKE_ROOT = OUTPUT_DIR / "hard_evidence"
    EXPERT_DIR = INTAKE_ROOT / "expert_feedback"
    REHEARSAL_DIR = INTAKE_ROOT / "timed_rehearsal"
    ROOT_README = INTAKE_ROOT / "README.md"
    EXPERT_README = EXPERT_DIR / "README.md"
    REHEARSAL_README = REHEARSAL_DIR / "README.md"


def text(value: str) -> str:
    return value.encode("utf-8").decode("unicode_escape")


def repo_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def is_candidate_evidence(path: Path) -> bool:
    name = path.name.lower()
    if path.name == "README.md" or name == ".gitkeep" or name.startswith("."):
        return False
    return not any(fragment in name for fragment in PLACEHOLDER_NAME_FRAGMENTS)


def candidate_evidence_paths(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    files = [path for path in directory.rglob("*") if path.is_file() and is_candidate_evidence(path)]
    return sorted(files, key=repo_path)


def evidence_files(directory: Path) -> list[str]:
    return [repo_path(path) for path in candidate_evidence_paths(directory)]


def read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def source_path_field(category_key: str) -> str:
    if category_key == "expert_feedback":
        return "feedback_source_path"
    if category_key == "timed_rehearsal":
        return "recording_or_timer_source_path"
    raise ValueError(f"unknown hard evidence category: {category_key}")


def confirmation_field(category_key: str) -> str:
    if category_key == "expert_feedback":
        return "real_feedback_confirmed"
    if category_key == "timed_rehearsal":
        return "real_rehearsal_confirmed"
    raise ValueError(f"unknown hard evidence category: {category_key}")


def build_evidence_records(
    category_key: str,
    paths: list[Path],
    accepted_types: list[str],
    required_fields: list[str],
) -> list[dict[str, str]]:
    metadata_paths = [path for path in paths if path.suffix.lower() == ".json"]
    source_files = {repo_path(path) for path in paths if path.suffix.lower() != ".json"}
    required = set(required_fields)
    source_field = source_path_field(category_key)
    confirmed_field = confirmation_field(category_key)
    records: list[dict[str, str]] = []
    for metadata_path in metadata_paths:
        payload = read_json_object(metadata_path)
        if payload is None:
            continue
        if not required.issubset(payload):
            continue
        if payload.get(confirmed_field) is not True:
            continue
        if payload.get("evidence_type") not in accepted_types:
            continue
        source_path = payload.get(source_field)
        if not isinstance(source_path, str) or not source_path:
            continue
        if source_path not in source_files:
            continue
        records.append(
            {
                "metadata_path": repo_path(metadata_path),
                "source_path": source_path,
            }
        )
    return sorted(records, key=lambda item: (item["metadata_path"], item["source_path"]))


def build_category(
    key: str,
    directory: Path,
    accepted_types: list[str],
    required_fields: list[str],
) -> dict[str, Any]:
    paths = candidate_evidence_paths(directory)
    files = [repo_path(path) for path in paths]
    metadata_files = [repo_path(path) for path in paths if path.suffix.lower() == ".json"]
    source_files = [repo_path(path) for path in paths if path.suffix.lower() != ".json"]
    records = build_evidence_records(key, paths, accepted_types, required_fields)
    return {
        "category": key,
        "intake_dir": repo_path(directory),
        "required_min_count": 1,
        "raw_file_count": len(files),
        "metadata_file_count": len(metadata_files),
        "source_file_count": len(source_files),
        "evidence_record_count": len(records),
        "collected_count": len(records),
        "accepted_evidence_types": accepted_types,
        "required_metadata_fields": required_fields,
        "evidence_files": files,
        "metadata_files": metadata_files,
        "source_files": source_files,
        "evidence_records": records,
    }


def build_payload() -> dict[str, Any]:
    expert = build_category(
        "expert_feedback",
        EXPERT_DIR,
        [
            "signed_feedback_form",
            "email_reply",
            "meeting_minutes",
            "chat_screenshot",
        ],
        [
            "reviewer_identity",
            "role_or_org",
            "review_date",
            "feedback_source_path",
            "review_dimensions",
            "remediation_record",
            "real_feedback_confirmed",
        ],
    )
    rehearsal = build_category(
        "timed_rehearsal",
        REHEARSAL_DIR,
        [
            "timer_screenshot",
            "screen_recording",
            "observer_note",
            "missed_question_list",
        ],
        [
            "rehearsal_date",
            "observer",
            "opening_actual_seconds",
            "demo_actual_seconds",
            "offline_fallback_actual_seconds",
            "killer_question_results",
            "recording_or_timer_source_path",
            "real_rehearsal_confirmed",
        ],
    )
    categories = {
        "expert_feedback": expert,
        "timed_rehearsal": rehearsal,
    }
    completion_allowed = all(
        categories[key]["collected_count"] >= categories[key]["required_min_count"]
        for key in REQUIRED_BEFORE_GOAL_COMPLETION
    )
    status = READY_FOR_REVIEW_STATUS if completion_allowed else AWAITING_STATUS
    return {
        "report_type": REPORT_TYPE,
        "status": status,
        "completion_claim_allowed": completion_allowed,
        "required_before_goal_completion": REQUIRED_BEFORE_GOAL_COMPLETION,
        "categories": categories,
        "no_fake_evidence_rules": [
            text("\\u4e0d\\u4f2a\\u9020\\u5916\\u90e8\\u610f\\u89c1"),
            text("\\u4e0d\\u628a\\u5185\\u90e8\\u81ea\\u8bc4\\u5199\\u6210\\u4e13\\u5bb6\\u80cc\\u4e66"),
            text(
                "\\u6ca1\\u6709\\u771f\\u5b9e\\u4e13\\u5bb6\\u53cd\\u9988"
                "\\u548c\\u771f\\u5b9e\\u8ba1\\u65f6\\u5f69\\u6392\\u524d\\uff0c"
                "\\u4e0d\\u80fd\\u6807\\u8bb0\\u76ee\\u6807\\u5b8c\\u6210"
            ),
        ],
        "ledger_files": [
            repo_path(OUTPUT_MD),
            repo_path(OUTPUT_JSON),
            repo_path(ROOT_README),
            repo_path(EXPERT_README),
            repo_path(REHEARSAL_README),
        ],
        "raw_evidence_files": sorted(expert["evidence_files"] + rehearsal["evidence_files"]),
        "rerun_commands": [
            "python scripts/build_challenge_cup_hard_evidence_ledger.py",
            "python scripts/build_challenge_cup_package.py",
            "python scripts/check_challenge_cup_readiness.py",
        ],
    }


def write_readmes() -> None:
    write_text(
        ROOT_README,
        "\n".join(
            [
                "# Hard Evidence Intake",
                "",
                text(
                    "\\u8fd9\\u4e2a\\u76ee\\u5f55\\u53ea\\u6536\\u7eb3\\u771f\\u5b9e"
                    "\\u4e13\\u5bb6\\u53cd\\u9988\\u548c\\u771f\\u5b9e\\u8ba1\\u65f6"
                    "\\u5f69\\u6392\\u7684\\u539f\\u59cb\\u6216\\u6458\\u8981\\u8bc1\\u636e\\u3002"
                ),
                "",
                "- `expert_feedback/`: signed feedback, email replies, meeting minutes, or chat screenshots.",
                "- `timed_rehearsal/`: timer screenshots, recordings, observer notes, or missed-question lists.",
                "- Each category must include at least one JSON summary with the required metadata fields; screenshots or recordings alone do not satisfy the readiness gate.",
                "- Preflight expert feedback with `python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback ... --confirm-real-feedback` before recording.",
                "- Record expert feedback with `python scripts/record_challenge_cup_hard_evidence.py expert_feedback ... --confirm-real-feedback`.",
                "- Preferred timed rehearsal flow: `python scripts/run_challenge_cup_timed_rehearsal.py ... --confirm-real-rehearsal` generates an observer note from measured seconds and archives it.",
                "- Preflight source-based timed rehearsal evidence with `python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal ... --confirm-real-rehearsal` before source-based recording.",
                "- Record timed rehearsal evidence with `python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal ... --confirm-real-rehearsal`.",
                text("- \\u4e0d\\u4f2a\\u9020\\u8bc1\\u636e\\uff1b\\u6ca1\\u6709\\u8fd9\\u4e24\\u7c7b\\u771f\\u5b9e\\u8bc1\\u636e\\u524d\\uff0c\\u4e0d\\u80fd\\u6807\\u8bb0\\u76ee\\u6807\\u5b8c\\u6210\\u3002"),
            ]
        ),
    )
    write_text(
        EXPERT_README,
        "\n".join(
            [
                "# Expert Feedback Evidence",
                "",
                text(
                    "\\u653e\\u5165\\u771f\\u5b9e\\u4e13\\u5bb6\\u53cd\\u9988\\u8bc1\\u636e\\uff1a"
                    "\\u7b7e\\u5b57\\u9875\\u3001\\u90ae\\u4ef6\\u56de\\u590d\\u3001"
                    "\\u4f1a\\u8bae\\u7eaa\\u8981\\u6216\\u804a\\u5929\\u622a\\u56fe\\u3002"
                ),
                text(
                    "\\u6bcf\\u4efd\\u8bc1\\u636e\\u5e94\\u80fd\\u770b\\u5230 reviewer identity\\u3001"
                    "role/org\\u3001date\\u3001review dimensions \\u548c remediation record\\u3002"
                ),
                "Required JSON fields: evidence_type, reviewer_identity, role_or_org, review_date, feedback_source_path, review_dimensions, remediation_record, real_feedback_confirmed.",
                "Use YYYY-MM-DD for review_date. feedback_source_path must point to the real source attachment, not the JSON summary itself.",
                f"Preflight CLI: `{EXPERT_PREFLIGHT_COMMAND}`.",
                f"Recommended CLI: `{EXPERT_RECORD_COMMAND}`.",
            ]
        ),
    )
    write_text(
        REHEARSAL_README,
        "\n".join(
            [
                "# Timed Rehearsal Evidence",
                "",
                text(
                    "\\u653e\\u5165\\u771f\\u5b9e\\u8ba1\\u65f6\\u5f69\\u6392\\u8bc1\\u636e\\uff1a"
                    "\\u8ba1\\u65f6\\u622a\\u56fe\\u3001\\u5f55\\u5c4f\\u3001"
                    "\\u89c2\\u5bdf\\u5458\\u5907\\u6ce8\\u6216\\u95ee\\u9898\\u9057\\u6f0f\\u6e05\\u5355\\u3002"
                ),
                "Required timing fields: opening_actual_seconds, demo_actual_seconds, offline_fallback_actual_seconds, killer_question_results.",
                "Required JSON fields: evidence_type, rehearsal_date, observer, opening_actual_seconds, demo_actual_seconds, offline_fallback_actual_seconds, killer_question_results, recording_or_timer_source_path, real_rehearsal_confirmed.",
                "Use YYYY-MM-DD for rehearsal_date. recording_or_timer_source_path must point to the real timer screenshot, recording, or observer note, not the JSON summary itself.",
                f"Preferred CLI: `{REHEARSAL_RUN_COMMAND}`.",
                f"Preflight CLI: `{REHEARSAL_PREFLIGHT_COMMAND}`.",
                f"Recommended CLI: `{REHEARSAL_RECORD_COMMAND}`.",
                text("\\u8d85\\u65f6\\u548c\\u7b54\\u8fa9\\u9057\\u6f0f\\u70b9\\u5fc5\\u987b\\u4fdd\\u7559\\uff0c\\u4e0d\\u80fd\\u7c89\\u9970\\u4e3a\\u901a\\u8fc7\\u3002"),
            ]
        ),
    )


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    categories = payload["categories"]
    lines = [
        text("# \\u786c\\u8bc1\\u636e\\u53f0\\u8d26"),
        "",
        f"- report_type: `{payload['report_type']}`",
        f"- status: `{payload['status']}`",
        f"- completion_claim_allowed: `{payload['completion_claim_allowed']}`",
        text(
            "- \\u8fb9\\u754c\\uff1a\\u771f\\u5b9e\\u4e13\\u5bb6\\u53cd\\u9988\\u548c"
            "\\u771f\\u5b9e\\u8ba1\\u65f6\\u5f69\\u6392\\u5c1a\\u672a\\u540c\\u65f6"
            "\\u5f52\\u6863\\u524d\\uff0c\\u4e0d\\u4f2a\\u9020\\uff0c\\u4e0d\\u80fd"
            "\\u6807\\u8bb0\\u76ee\\u6807\\u5b8c\\u6210\\u3002"
        ),
        "",
        text("## \\u5fc5\\u987b\\u5f52\\u6863\\u7684\\u771f\\u5b9e\\u8bc1\\u636e"),
        "",
        "| Category | Required Records | Evidence Records | Raw Files | Intake Dir |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for key in REQUIRED_BEFORE_GOAL_COMPLETION:
        category = categories[key]
        lines.append(
            f"| {key} | {category['required_min_count']} | {category['collected_count']} | "
            f"{category['raw_file_count']} | `{category['intake_dir']}` |"
        )
    lines.extend(["", text("## \\u539f\\u5219"), ""])
    lines.extend(f"- {item}" for item in payload["no_fake_evidence_rules"])
    lines.extend(["", text("## \\u8bc1\\u636e\\u6587\\u4ef6"), ""])
    if payload["raw_evidence_files"]:
        lines.extend(f"- `{item}`" for item in payload["raw_evidence_files"])
    else:
        lines.append(text("- \\u5c1a\\u672a\\u5f52\\u6863\\u771f\\u5b9e\\u9644\\u4ef6\\u3002"))
    lines.extend(["", "## Rerun Commands", ""])
    lines.extend(f"- `{command}`" for command in payload["rerun_commands"])
    write_text(path, "\n".join(lines))


def write_outputs(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    write_readmes()
    payload = payload or build_payload()
    write_text(OUTPUT_JSON, json.dumps(payload, ensure_ascii=False, indent=2))
    write_markdown(OUTPUT_MD, payload)
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"hard evidence ledger: {repo_path(OUTPUT_MD)}")
    print(
        "hard evidence counts: "
        f"expert_feedback={payload['categories']['expert_feedback']['collected_count']}, "
        f"timed_rehearsal={payload['categories']['timed_rehearsal']['collected_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
