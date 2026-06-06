from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REPRO_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTPUT_JSON = REPRO_DIR / "special_prize_readiness_dashboard.json"
OUTPUT_MD = REPRO_DIR / "special_prize_readiness_dashboard.md"
OFFICIAL_RUBRIC = REPRO_DIR / "official_rubric_alignment.json"
FINAL_ACCEPTANCE_AUDIT = REPRO_DIR / "final_acceptance_audit.json"
HARD_EVIDENCE_ACTION_PACK = REPRO_DIR / "hard_evidence_action_pack.json"

REPORT_TYPE = "challenge_cup_special_prize_readiness_dashboard"
STATUS = "special_prize_review_ready_with_external_evidence_gaps"
BOUNDARY = (
    "This dashboard translates public Tsinghua Challenge Cup rubric signals into defense actions. "
    "It does not guarantee an award and does not close the goal while real expert feedback and real "
    "timed rehearsal evidence remain unarchived."
)


DIMENSION_ACTIONS = {
    "academic_or_practical_value": "Lead with the fixed GT-07 maintenance scenario and show why evidence-bound retrieval matters.",
    "innovation": "Contrast keyword/RAG/GraphRAG on the same-question subset and explain evidence-bound graph construction.",
    "completion": "Open the package manifest, readiness gate, archive verifier, and browser smoke evidence.",
    "defense_performance": "Run the three-minute script against the scorecard and archive a real timed rehearsal.",
    "academic_norms_and_rigor": "State boundaries before judges ask: no production claim, no expert approval claim, no award guarantee.",
}

DIMENSION_MESSAGES = {
    "academic_or_practical_value": "The project has a concrete power-equipment knowledge scenario and auditable evidence chain.",
    "innovation": "The differentiator is evidence-bound GraphRAG plus failure analysis, not a generic RAG wrapper.",
    "completion": "The submission package, verifier, demo smoke reports, and reproducibility gates are already packaged.",
    "defense_performance": "The defense materials are ready, but a real timed rehearsal must still be archived.",
    "academic_norms_and_rigor": "The package explicitly preserves unfinished external-evidence boundaries.",
}


def repo_path(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def build_rubric_readiness(official: dict[str, Any]) -> list[dict[str, Any]]:
    dimensions = official.get("dimensions", {})
    if not isinstance(dimensions, dict):
        return []

    readiness: list[dict[str, Any]] = []
    for key, dimension in dimensions.items():
        if not isinstance(dimension, dict):
            continue
        evidence_files = [str(item) for item in dimension.get("evidence_files", [])]
        external_gap = key == "defense_performance"
        readiness.append(
            {
                "dimension_key": str(key),
                "label": str(dimension.get("label", key)),
                "official_source_ids": [str(item) for item in dimension.get("official_source_ids", [])],
                "project_argument": str(dimension.get("project_argument", "")),
                "evidence_files": evidence_files,
                "readiness_level": "ready_with_external_gap" if external_gap else "strong_evidence_linked",
                "judge_message": DIMENSION_MESSAGES.get(str(key), str(dimension.get("project_argument", ""))),
                "defense_action": DIMENSION_ACTIONS.get(str(key), "Bind the claim to the listed evidence and state its boundary."),
            }
        )
    return readiness


def build_payload() -> dict[str, Any]:
    official = load_json(OFFICIAL_RUBRIC)
    final_audit = load_json(FINAL_ACCEPTANCE_AUDIT)
    action_pack = load_json(HARD_EVIDENCE_ACTION_PACK)
    policy = official.get("special_prize_policy", {})
    integrity_rules = official.get("integrity_rules", {})

    return {
        "report_type": REPORT_TYPE,
        "status": STATUS,
        "no_award_guarantee": True,
        "completion_claim_allowed": False,
        "can_mark_goal_complete": False,
        "official_basis": {
            "latest_public_result_source_id": str(policy.get("latest_public_result_source_id", "")),
            "max_special_prize_count": int(policy.get("max_special_prize_count") or 0),
            "may_be_vacant": policy.get("may_be_vacant") is True,
            "official_source_ids": [str(item.get("source_id", "")) for item in official.get("official_sources", [])],
        },
        "package_readiness": final_audit.get("package_readiness", {}),
        "rubric_readiness": build_rubric_readiness(official),
        "top_risks": [
            {
                "risk_id": "expert_feedback",
                "status": "unclosed_external_hard_evidence",
                "mitigation_file": "docs/challenge_cup/reproducibility/hard_evidence_action_pack.md",
            },
            {
                "risk_id": "timed_rehearsal",
                "status": "unclosed_external_hard_evidence",
                "mitigation_file": "docs/challenge_cup/reproducibility/hard_evidence_action_pack.md",
            },
            {
                "risk_id": "award_overclaim",
                "status": "controlled_by_boundary",
                "mitigation_file": "docs/challenge_cup/reproducibility/official_rubric_alignment.md",
            },
        ],
        "next_action_files": [
            "docs/challenge_cup/reproducibility/hard_evidence_action_pack.md",
            "docs/challenge_cup/reproducibility/expert_feedback_request_packet.md",
            "docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md",
            "docs/challenge_cup/reproducibility/final_acceptance_audit.md",
        ],
        "verification_commands": [
            "python scripts/build_challenge_cup_special_prize_readiness_dashboard.py",
            "python scripts/build_challenge_cup_package.py",
            "python scripts/check_challenge_cup_readiness.py",
            "python scripts/check_challenge_cup_goal_completion.py",
        ],
        "integrity_rules": {
            "official_no_award_guarantee": integrity_rules.get("no_award_guarantee") is True,
            "official_no_fake_external_validation": integrity_rules.get("no_fake_external_validation") is True,
            "action_pack_completion_claim_allowed": action_pack.get("completion_claim_allowed") is False,
            "final_audit_can_mark_goal_complete": final_audit.get("can_mark_goal_complete") is True,
            "final_audit_preserves_incomplete_goal": final_audit.get("can_mark_goal_complete") is False,
        },
        "boundary": BOUNDARY,
        "output_files": [repo_path(OUTPUT_MD), repo_path(OUTPUT_JSON)],
    }


def write_markdown(payload: dict[str, Any]) -> None:
    lines = [
        "# Special Prize Readiness Dashboard",
        "",
        f"- report_type: `{payload['report_type']}`",
        f"- status: `{payload['status']}`",
        f"- no_award_guarantee=True",
        f"- completion_claim_allowed: `{payload['completion_claim_allowed']}`",
        f"- can_mark_goal_complete: `{payload['can_mark_goal_complete']}`",
        f"- latest_public_result_source_id: `{payload['official_basis']['latest_public_result_source_id']}`",
        f"- max_special_prize_count: `{payload['official_basis']['max_special_prize_count']}`",
        f"- may_be_vacant: `{payload['official_basis']['may_be_vacant']}`",
        "",
        "## Rubric Readiness",
        "",
        "| Dimension | Readiness | Judge Message | Defense Action | Evidence Count |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for item in payload["rubric_readiness"]:
        lines.append(
            "| {label} | `{readiness_level}` | {judge_message} | {defense_action} | {count} |".format(
                count=len(item["evidence_files"]),
                **item,
            )
        )
    lines.extend(["", "## Top Risks", ""])
    for risk in payload["top_risks"]:
        lines.append(f"- `{risk['risk_id']}`: {risk['status']} -> `{risk['mitigation_file']}`")
    lines.extend(["", "## Next Action Files", ""])
    lines.extend(f"- `{item}`" for item in payload["next_action_files"])
    lines.extend(["", "## Verification Commands", ""])
    lines.extend(f"- `{item}`" for item in payload["verification_commands"])
    lines.extend(["", "## Boundary", "", payload["boundary"]])
    write_text(OUTPUT_MD, "\n".join(lines))


def write_outputs() -> dict[str, Any]:
    payload = build_payload()
    write_text(OUTPUT_JSON, json.dumps(payload, ensure_ascii=False, indent=2))
    write_markdown(payload)
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"special prize readiness dashboard: {repo_path(OUTPUT_MD)}")
    print(f"Status: {payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
