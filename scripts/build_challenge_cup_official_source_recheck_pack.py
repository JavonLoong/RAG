from __future__ import annotations

import json
import re
import hashlib
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OFFICIAL_RUBRIC_JSON = OUTPUT_DIR / "official_rubric_alignment.json"
OUTPUT_JSON = OUTPUT_DIR / "official_source_recheck_pack.json"
OUTPUT_MD = OUTPUT_DIR / "official_source_recheck_pack.md"

REPORT_TYPE = "challenge_cup_official_source_recheck_pack"
STATUS = "ready_for_final_submission_source_recheck"


FINAL_SUBMISSION_CHECKS = [
    {
        "check_id": "official_url_access",
        "required_action": "open_each_official_tsinghua_url",
        "acceptance_signal": "Every official URL opens from the final review machine or has an archived official attachment.",
    },
    {
        "check_id": "latest_public_result_not_superseded",
        "required_action": "search_for_new_tsinghua_challenge_cup_notice_or_result_page",
        "acceptance_signal": "No new Tsinghua Challenge Cup official notice or result page supersedes the locked latest_public_result.",
    },
    {
        "check_id": "rubric_dimension_recheck",
        "required_action": "compare_locked_rubric_dimensions_against_public_sources",
        "acceptance_signal": "Academic/practical value, innovation, completion, and defense-performance dimensions remain supportable.",
    },
    {
        "check_id": "department_benchmark_recheck",
        "required_action": "reopen_44th_department_benchmark_sources",
        "acceptance_signal": "Department benchmark signals remain official Tsinghua-domain sources and are not used as award guarantees.",
    },
    {
        "check_id": "boundary_recheck",
        "required_action": "confirm_no_award_or_external_validation_overclaim",
        "acceptance_signal": "The package still says no award guarantee and does not satisfy goal completion without real hard evidence.",
    },
]


def repo_relative(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_filename(raw: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw.strip())
    return safe or "official_source"


def snapshot_dir() -> Path:
    return OUTPUT_DIR / "official_source_snapshots"


def load_official_rubric() -> dict[str, Any]:
    return json.loads(OFFICIAL_RUBRIC_JSON.read_text(encoding="utf-8"))


def source_recheck_item(source: dict[str, Any], source_lock: dict[str, Any]) -> dict[str, Any]:
    latest = source_lock.get("latest_public_result", {})
    anchor_terms = list(source.get("claims", []))
    if source.get("source_id") == latest.get("source_id"):
        anchor_terms = list(latest.get("anchor_terms") or anchor_terms)
    snapshot_path = write_source_snapshot(source, anchor_terms)
    return {
        "source_id": source.get("source_id"),
        "title": source.get("title"),
        "url": source.get("url"),
        "source_type": source.get("source_type"),
        "locked_checked_at": source.get("checked_at"),
        "snapshot_path": repo_relative(snapshot_path),
        "snapshot_sha256": sha256_file(snapshot_path),
        "required_action": "open_official_url_and_compare_anchor_terms",
        "manual_recheck_required": True,
        "anchor_terms": anchor_terms,
        "outcome_if_changed": (
            "Update official_rubric_alignment, rebuild the package, rerun readiness, "
            "and keep no-award/no-external-validation boundaries."
        ),
    }


def write_source_snapshot(source: dict[str, Any], anchor_terms: list[Any]) -> Path:
    source_id = str(source.get("source_id", "official_source"))
    path = snapshot_dir() / f"{safe_filename(source_id)}.md"
    lines = [
        "# Official Source Anchor Snapshot",
        "",
        f"- source_id: `{source_id}`",
        f"- title: {source.get('title')}",
        f"- url: {source.get('url')}",
        f"- source_type: `{source.get('source_type')}`",
        f"- locked_checked_at: `{source.get('checked_at')}`",
        "",
        "## Anchor Terms",
        "",
    ]
    lines.extend(f"- {term}" for term in anchor_terms)
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This is a local anchor snapshot derived from the locked official-source alignment. "
            "Before final submission, reopen the official URL and compare these anchor terms; "
            "do not use this snapshot as an award guarantee or external expert validation.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def build_payload() -> dict[str, Any]:
    rubric = load_official_rubric()
    source_lock = rubric.get("official_source_lock", {})
    latest = source_lock.get("latest_public_result", {})
    sources = [source_recheck_item(source, source_lock) for source in rubric.get("official_sources", [])]
    return {
        "report_type": REPORT_TYPE,
        "status": STATUS,
        "generated_from": repo_relative(OFFICIAL_RUBRIC_JSON),
        "source_lock_current_as_of": source_lock.get("current_as_of"),
        "latest_public_result_source_id": latest.get("source_id"),
        "requires_manual_recheck_before_final_submission": True,
        "completion_claim_allowed": False,
        "no_award_guarantee": True,
        "does_not_satisfy_goal_completion": True,
        "source_recheck_items": sources,
        "final_submission_checks": FINAL_SUBMISSION_CHECKS,
        "rerun_commands": [
            "python scripts/build_challenge_cup_official_source_recheck_pack.py",
            "python scripts/build_challenge_cup_package.py",
            "python scripts/check_challenge_cup_readiness.py",
        ],
        "integrity_rules": {
            "manual_web_recheck_required": True,
            "no_award_guarantee": True,
            "no_fake_external_validation": True,
            "does_not_satisfy_goal_completion": True,
        },
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Official Source Recheck Pack",
        "",
        f"- report_type: `{payload['report_type']}`",
        f"- status: `{payload['status']}`",
        f"- generated_from: `{payload['generated_from']}`",
        f"- source_lock_current_as_of: `{payload['source_lock_current_as_of']}`",
        f"- latest_public_result_source_id: `{payload['latest_public_result_source_id']}`",
        f"- manual_web_recheck_required: `{payload['requires_manual_recheck_before_final_submission']}`",
        f"- completion_claim_allowed: `{payload['completion_claim_allowed']}`",
        f"- no_award_guarantee: `{payload['no_award_guarantee']}`",
        f"- does_not_satisfy_goal_completion: `{payload['does_not_satisfy_goal_completion']}`",
        "",
        "## Source Recheck Items",
        "",
        "| Source | Action | URL | Snapshot | Anchor Terms |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in payload["source_recheck_items"]:
        anchors = "<br>".join(str(term) for term in item.get("anchor_terms", [])[:4])
        lines.append(
            f"| `{item['source_id']}` | `{item['required_action']}` | {item['url']} | "
            f"`{item['snapshot_path']}`<br>`snapshot_sha256={item['snapshot_sha256']}` | {anchors} |"
        )
    lines.extend(
        [
            "",
            "## Final Submission Checks",
            "",
            "| Check | Required Action | Acceptance Signal |",
            "| --- | --- | --- |",
        ]
    )
    for item in payload["final_submission_checks"]:
        lines.append(
            f"| `{item['check_id']}` | {item['required_action']} | {item['acceptance_signal']} |"
        )
    lines.extend(
        [
            "",
            "## Rerun Commands",
            "",
        ]
    )
    lines.extend(f"- `{command}`" for command in payload["rerun_commands"])
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This pack is a final-submission work order for manual official-source freshness checks. "
            "It makes no award guarantee, does not claim expert approval, does not replace real "
            "external feedback or a real timed rehearsal, and does not satisfy goal completion.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_outputs(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or build_payload()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(OUTPUT_MD, payload)
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"official source recheck pack: {repo_relative(OUTPUT_MD)}")
    print(f"official source recheck items: {len(payload['source_recheck_items'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
