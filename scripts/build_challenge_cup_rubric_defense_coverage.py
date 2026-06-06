from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_challenge_cup_claim_integrity_report import build_payload as build_claim_integrity_payload
from build_challenge_cup_judge_objection_matrix import build_payload as build_judge_objection_payload
from build_challenge_cup_official_rubric_alignment import build_payload as build_official_rubric_payload


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_MD_RELATIVE = "docs/challenge_cup/reproducibility/rubric_defense_coverage.md"
OUTPUT_JSON_RELATIVE = "docs/challenge_cup/reproducibility/rubric_defense_coverage.json"
OUTPUT_MD = REPO_ROOT / OUTPUT_MD_RELATIVE
OUTPUT_JSON = REPO_ROOT / OUTPUT_JSON_RELATIVE
STATUS = "rubric_defense_coverage_ready_no_award_claim"
FAIL_STATUS = "rubric_defense_coverage_gap"
BOUNDARY = (
    "This report maps public rubric dimensions to local defense assets, judge-objection answers, "
    "and evidence-bound claims. It does not guarantee an award, does not claim expert approval, "
    "does not claim timed rehearsal completion, and does not satisfy goal completion without real "
    "expert feedback and real timed rehearsal evidence."
)
REQUIRED_DIMENSIONS = [
    "academic_or_practical_value",
    "innovation",
    "completion",
    "defense_performance",
    "academic_norms_and_rigor",
]


COVERAGE_PLAN: dict[str, dict[str, Any]] = {
    "academic_or_practical_value": {
        "judge_objection_ids": ["OJ-03-engineer-replacement", "OJ-04-production-data"],
        "claim_ids": ["application_value_bounded", "human_decision_boundary"],
        "defense_assets": [
            "docs/challenge_cup/reproducibility/application_validation_report.md",
            "docs/challenge_cup/reproducibility/application_value_quantification.md",
            "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md",
        ],
        "boundary": "Application value is local GT-07 evidence, not production validation or engineer replacement.",
    },
    "innovation": {
        "judge_objection_ids": ["OJ-01-normal-rag", "OJ-02-graphrag-baseline"],
        "claim_ids": ["graphrag_innovation_bounded", "evaluation_transparency"],
        "defense_assets": [
            "evaluation/reports/challenge_cup_graphrag_context_demo.md",
            "evaluation/reports/challenge_cup_graphrag_answer_benchmark.md",
            "evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.md",
        ],
        "boundary": "Innovation is argued through evidence-bound GraphRAG support, not every-question win-rate.",
    },
    "completion": {
        "judge_objection_ids": [
            "OJ-05-live-demo-failure",
            "OJ-06-cherry-picked-evaluation",
            "OJ-10-project-closure",
        ],
        "claim_ids": ["package_review_ready", "evaluation_transparency"],
        "defense_assets": [
            "docs/challenge_cup/package_manifest.json",
            "docs/challenge_cup/reproducibility/verify_submission_package.py",
            "docs/challenge_cup/reproducibility/final_acceptance_audit.md",
        ],
        "boundary": "Package completeness is review readiness, not final goal completion or award certainty.",
    },
    "defense_performance": {
        "judge_objection_ids": ["OJ-05-live-demo-failure", "OJ-08-special-prize-claim"],
        "claim_ids": ["defense_demo_fallback_ready", "special_prize_competition_argument"],
        "defense_assets": [
            "docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx",
            "docs/challenge_cup/defense_deck/challenge_cup_defense_speaker_notes.md",
            "docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md",
            "docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md",
        ],
        "boundary": "Defense assets prove rehearsal readiness and fallback preparation, not completed timed rehearsal.",
    },
    "academic_norms_and_rigor": {
        "judge_objection_ids": ["OJ-07-expert-validation", "OJ-08-special-prize-claim", "OJ-09-ip-and-compliance"],
        "claim_ids": [
            "external_hard_evidence_not_closed",
            "human_decision_boundary",
            "special_prize_competition_argument",
        ],
        "defense_assets": [
            "docs/challenge_cup/reproducibility/claim_integrity_report.md",
            "docs/challenge_cup/reproducibility/hard_evidence_ledger.md",
            "docs/challenge_cup/reproducibility/no_answer_boundary_evaluation.md",
        ],
        "boundary": "Rigor means explicit evidence boundaries, no fake external validation, and no award guarantee.",
    },
}


def repo_path(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def is_safe_repo_path(relative: str) -> bool:
    posix = PurePosixPath(relative)
    return (
        bool(relative)
        and not relative.startswith(("http://", "https://"))
        and not posix.is_absolute()
        and ".." not in posix.parts
        and "\\" not in relative
        and relative.startswith(("docs/", "evaluation/"))
    )


def existing_repo_file(relative: str) -> bool:
    path = REPO_ROOT / relative
    return path.exists() and path.stat().st_size > 0


def unique_paths(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        relative = str(value).strip()
        if relative and relative not in seen:
            seen.add(relative)
            unique.append(relative)
    return unique


def build_payload() -> dict[str, Any]:
    official_payload = build_official_rubric_payload()
    objection_payload = build_judge_objection_payload()
    claim_payload = build_claim_integrity_payload()

    official_dimensions = official_payload.get("dimensions", {})
    official_source_ids = {
        str(item.get("source_id", ""))
        for item in official_payload.get("official_sources", [])
        if isinstance(item, dict)
    }
    objection_ids = {
        str(item.get("objection_id", ""))
        for item in objection_payload.get("objections", [])
        if isinstance(item, dict)
    }
    claim_ids = {
        str(item.get("claim_id", ""))
        for item in claim_payload.get("claims", [])
        if isinstance(item, dict)
    }

    gaps: list[str] = []
    dimensions: list[dict[str, Any]] = []
    for key in REQUIRED_DIMENSIONS:
        plan = COVERAGE_PLAN[key]
        official_dimension = official_dimensions.get(key, {}) if isinstance(official_dimensions, dict) else {}
        row_gaps: list[str] = []
        official_refs = [str(item) for item in official_dimension.get("official_source_ids", [])]
        if not official_refs:
            row_gaps.append(f"{key}: official_source_ids missing")
        unknown_sources = sorted(source_id for source_id in official_refs if source_id not in official_source_ids)
        if unknown_sources:
            row_gaps.append(f"{key}: unknown official_source_ids {unknown_sources}")

        defense_assets = [str(path) for path in plan["defense_assets"]]
        evidence_files = unique_paths(
            [str(path) for path in official_dimension.get("evidence_files", [])] + defense_assets
        )
        if len(evidence_files) < 2:
            row_gaps.append(f"{key}: fewer than 2 evidence files")
        for relative in evidence_files:
            if not is_safe_repo_path(relative):
                row_gaps.append(f"{key}: unsafe evidence path {relative}")
            elif not existing_repo_file(relative):
                row_gaps.append(f"{key}: evidence file missing or empty {relative}")

        missing_objections = sorted(item for item in plan["judge_objection_ids"] if item not in objection_ids)
        if missing_objections:
            row_gaps.append(f"{key}: missing judge_objection_ids {missing_objections}")
        missing_claims = sorted(item for item in plan["claim_ids"] if item not in claim_ids)
        if missing_claims:
            row_gaps.append(f"{key}: missing claim_ids {missing_claims}")
        for relative in defense_assets:
            if not is_safe_repo_path(relative):
                row_gaps.append(f"{key}: unsafe defense asset {relative}")
            elif not existing_repo_file(relative):
                row_gaps.append(f"{key}: defense asset missing or empty {relative}")
        boundary = str(plan["boundary"]).strip()
        if not boundary:
            row_gaps.append(f"{key}: boundary missing")

        coverage_status = "covered" if not row_gaps else "gap"
        gaps.extend(row_gaps)
        dimensions.append(
            {
                "dimension_key": key,
                "label": str(official_dimension.get("label", key)),
                "coverage_status": coverage_status,
                "official_source_ids": official_refs,
                "evidence_files": evidence_files,
                "judge_objection_ids": list(plan["judge_objection_ids"]),
                "claim_ids": list(plan["claim_ids"]),
                "defense_assets": defense_assets,
                "boundary": boundary,
            }
        )

    covered_dimension_count = sum(1 for item in dimensions if item["coverage_status"] == "covered")
    coverage_complete = covered_dimension_count == len(REQUIRED_DIMENSIONS) and not gaps
    return {
        "report_type": "challenge_cup_rubric_defense_coverage",
        "checked_at": str(official_payload.get("official_source_lock", {}).get("current_as_of", "2026-06-06")),
        "status": STATUS if coverage_complete else FAIL_STATUS,
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "award_guarantee_claimed": False,
        "expert_approval_claimed": False,
        "timed_rehearsal_completion_claimed": False,
        "coverage_complete": coverage_complete,
        "dimension_count": len(REQUIRED_DIMENSIONS),
        "covered_dimension_count": covered_dimension_count,
        "dimensions": dimensions,
        "gaps": gaps,
        "source_reports": {
            "official_rubric_alignment": "docs/challenge_cup/reproducibility/official_rubric_alignment.md",
            "judge_objection_response_matrix": "docs/challenge_cup/reproducibility/judge_objection_response_matrix.md",
            "claim_integrity_report": "docs/challenge_cup/reproducibility/claim_integrity_report.md",
        },
        "boundary": BOUNDARY,
        "verification_commands": [
            "python scripts/build_challenge_cup_rubric_defense_coverage.py",
            "python scripts/build_challenge_cup_package.py",
            "python scripts/check_challenge_cup_readiness.py",
        ],
        "output_files": [OUTPUT_MD_RELATIVE, OUTPUT_JSON_RELATIVE],
    }


def build_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Rubric Defense Coverage",
        "",
        f"- status: `{payload['status']}`",
        f"- coverage_complete: `{payload['coverage_complete']}`",
        f"- covered dimensions: {payload['covered_dimension_count']}/{payload['dimension_count']}",
        "- boundary: no award guarantee; no fake expert approval; no timed rehearsal completion claim",
        "",
        "## Dimension Coverage",
        "",
        "| Dimension | Status | Judge Objections | Claim IDs | Evidence | Boundary |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in payload["dimensions"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{item['dimension_key']}`",
                    str(item["coverage_status"]),
                    "<br>".join(f"`{value}`" for value in item["judge_objection_ids"]),
                    "<br>".join(f"`{value}`" for value in item["claim_ids"]),
                    "<br>".join(f"`{value}`" for value in item["evidence_files"]),
                    str(item["boundary"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Source Reports",
            "",
        ]
    )
    for label, relative in payload["source_reports"].items():
        lines.append(f"- {label}: `{relative}`")
    lines.extend(
        [
            "",
            "## Gaps",
            "",
        ]
    )
    if payload["gaps"]:
        lines.extend(f"- {gap}" for gap in payload["gaps"])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            str(payload["boundary"]),
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_outputs() -> dict[str, Any]:
    payload = build_payload()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(build_markdown(payload), encoding="utf-8")
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"rubric defense coverage: {repo_path(OUTPUT_MD)}")
    print(f"Status: {payload['status']}")
    return 0 if payload["status"] == STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
