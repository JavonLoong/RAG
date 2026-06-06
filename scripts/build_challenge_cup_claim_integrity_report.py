from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_MD_RELATIVE = "docs/challenge_cup/reproducibility/claim_integrity_report.md"
OUTPUT_JSON_RELATIVE = "docs/challenge_cup/reproducibility/claim_integrity_report.json"
OUTPUT_MD = REPO_ROOT / OUTPUT_MD_RELATIVE
OUTPUT_JSON = REPO_ROOT / OUTPUT_JSON_RELATIVE

REPORT_TYPE = "challenge_cup_claim_integrity_report"
STATUS = "claim_integrity_verified_no_award_or_external_claim"
BOUNDARY = (
    "This report audits package-level defense claims for evidence links and forbidden overclaims. It does "
    "not guarantee an award, does not claim expert approval, does not claim timed rehearsal completion, "
    "does not claim production deployment, and does not satisfy goal completion without real expert feedback "
    "and real timed rehearsal evidence."
)

SCANNED_FILES = [
    "docs/challenge_cup/README_先看这里.md",
    "docs/challenge_cup/07_评审主张证据矩阵.md",
    "docs/challenge_cup/08_特等奖评审自评表.md",
    "docs/challenge_cup/13_评委现场速览卡.md",
    "docs/challenge_cup/14_现场答辩操作Runbook.md",
    "docs/challenge_cup/18_特等奖打分模拟与整改清单.md",
    "docs/challenge_cup/23_终审提交总目录与签收页.md",
    "docs/challenge_cup/reproducibility/judge_objection_response_matrix.md",
    "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md",
    "docs/challenge_cup/reproducibility/final_acceptance_audit.md",
    "docs/challenge_cup/reproducibility/goal_completion_report.md",
]

FORBIDDEN_PATTERNS = [
    r"保证获得特等奖",
    r"必获特等奖",
    r"肯定获得特等奖",
    r"100%\s*获得特等奖",
    r"已获得专家认可",
    r"已经获得专家认可",
    r"已通过专家验证",
    r"真实专家反馈已完成",
    r"真实计时彩排已完成",
    r"已经生产上线",
    r"生产级上线",
    r"可以替代工程师",
    r"最终目标已完成",
]

CLAIMS = [
    {
        "claim_id": "package_review_ready",
        "allowed_claim": "The current package can be reviewed as a reproducible project-closure package.",
        "evidence_files": [
            "docs/challenge_cup/package_manifest.json",
            "docs/challenge_cup/reproducibility/evidence_hashes.json",
            "docs/challenge_cup/reproducibility/readiness_gate_report.md",
            "docs/challenge_cup/reproducibility/verify_submission_package.py",
        ],
        "boundary": "Package review readiness is not final goal completion and is not an award guarantee.",
        "forbidden_overclaim": "Do not say package readiness proves the special-prize result.",
    },
    {
        "claim_id": "graphrag_innovation_bounded",
        "allowed_claim": "GraphRAG is used for evidence organization over fixed, auditable subsets.",
        "evidence_files": [
            "docs/challenge_cup/02_技术白皮书.md",
            "evaluation/reports/challenge_cup_graphrag_answer_benchmark.md",
            "evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.md",
        ],
        "boundary": "This does not claim GraphRAG beats every baseline question or proves online LLM win-rate.",
        "forbidden_overclaim": "Do not claim universal GraphRAG superiority.",
    },
    {
        "claim_id": "evaluation_transparency",
        "allowed_claim": "The project discloses the evaluation set, baselines, weak cases, and remediation records.",
        "evidence_files": [
            "evaluation/system_eval_questions.jsonl",
            "evaluation/reports/day4_failure_analysis_20260605_210642.md",
            "evaluation/reports/challenge_cup_failure_remediation_before_after.md",
        ],
        "boundary": "Transparent local evaluation is not external validation or production acceptance.",
        "forbidden_overclaim": "Do not hide failure cases or imply the evaluation proves production readiness.",
    },
    {
        "claim_id": "application_value_bounded",
        "allowed_claim": "The GT-07 scenario provides a fixed, evidence-linked application-value demonstration.",
        "evidence_files": [
            "docs/challenge_cup/11_应用场景与专家验证.md",
            "docs/challenge_cup/reproducibility/application_validation_report.md",
            "docs/challenge_cup/reproducibility/application_value_quantification.md",
            "docs/challenge_cup/reproducibility/numeric_traceability_report.md",
        ],
        "boundary": "The GT-07 demonstration does not replace engineers and does not claim production validation.",
        "forbidden_overclaim": "Do not present local scenario evidence as signed industry deployment validation.",
    },
    {
        "claim_id": "defense_demo_fallback_ready",
        "allowed_claim": "The defense has a browser-smoke snapshot and offline fallback materials.",
        "evidence_files": [
            "docs/challenge_cup/04_系统演示脚本.md",
            "docs/challenge_cup/14_现场答辩操作Runbook.md",
            "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md",
            "docs/challenge_cup/defense_console/index.html",
        ],
        "boundary": "Fallback readiness is not a completed real timed rehearsal.",
        "forbidden_overclaim": "Do not say a real timed rehearsal has been completed before hard evidence is archived.",
    },
    {
        "claim_id": "external_hard_evidence_not_closed",
        "allowed_claim": "Real expert feedback and real timed rehearsal evidence are prepared for collection but not closed.",
        "evidence_files": [
            "docs/challenge_cup/reproducibility/hard_evidence_ledger.md",
            "docs/challenge_cup/reproducibility/expert_feedback_request_packet.md",
            "docs/challenge_cup/reproducibility/timed_rehearsal_schedule_ledger.md",
            "docs/challenge_cup/reproducibility/goal_completion_report.md",
        ],
        "boundary": "Outreach packets and ledgers do not equal real expert approval or real timed rehearsal completion.",
        "forbidden_overclaim": "Do not present internal forms, request packets, or schedules as completed hard evidence.",
    },
    {
        "claim_id": "special_prize_competition_argument",
        "allowed_claim": "The special-prize argument is evidence density, innovation framing, completion, and defense readiness.",
        "evidence_files": [
            "docs/challenge_cup/08_特等奖评审自评表.md",
            "docs/challenge_cup/reproducibility/official_rubric_alignment.md",
            "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md",
        ],
        "boundary": "This is an argument for competition readiness, not an award probability or guarantee.",
        "forbidden_overclaim": "Do not promise, imply, or quantify a special-prize result.",
    },
    {
        "claim_id": "human_decision_boundary",
        "allowed_claim": "The system is an evidence assistant for professional review, not an autonomous maintenance decision-maker.",
        "evidence_files": [
            "docs/challenge_cup/05_答辩问答手册.md",
            "docs/challenge_cup/reproducibility/no_answer_boundary_evaluation.md",
            "docs/challenge_cup/21_知识产权与开源合规说明.md",
        ],
        "boundary": "High-risk maintenance conclusions still require human confirmation and source evidence.",
        "forbidden_overclaim": "Do not say the system replaces engineers or makes final maintenance decisions.",
    },
]


def repo_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def scan_forbidden_patterns() -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    negation_markers = ("不", "未", "不得", "不能", "不可", "禁止", "no ", "not ", "do not")
    for relative in SCANNED_FILES:
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in FORBIDDEN_PATTERNS:
            for match in re.finditer(pattern, text):
                prefix = text[max(0, match.start() - 12) : match.start()].lower()
                if any(marker in prefix for marker in negation_markers):
                    continue
                hits.append({"path": relative, "pattern": pattern})
    return hits


def build_payload() -> dict[str, Any]:
    failures: list[str] = []
    forbidden_hits = scan_forbidden_patterns()
    if forbidden_hits:
        failures.extend(f"forbidden overclaim hit: {hit['path']} / {hit['pattern']}" for hit in forbidden_hits)

    for claim in CLAIMS:
        if not claim["evidence_files"]:
            failures.append(f"{claim['claim_id']}: evidence_files missing")
        for relative in claim["evidence_files"]:
            if not (REPO_ROOT / relative).exists():
                failures.append(f"{claim['claim_id']}: missing evidence file {relative}")
        if not claim["boundary"]:
            failures.append(f"{claim['claim_id']}: boundary missing")
        if not claim["forbidden_overclaim"]:
            failures.append(f"{claim['claim_id']}: forbidden_overclaim missing")

    return {
        "report_type": REPORT_TYPE,
        "status": STATUS if not failures else "claim_integrity_failed",
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "award_guarantee_claimed": False,
        "expert_approval_claimed": False,
        "timed_rehearsal_completion_claimed": False,
        "production_deployment_claimed": False,
        "all_claims_evidence_bound": not any("evidence" in failure for failure in failures),
        "forbidden_hit_count": len(forbidden_hits),
        "forbidden_hits": forbidden_hits,
        "claim_count": len(CLAIMS),
        "claims": CLAIMS,
        "scanned_files": SCANNED_FILES,
        "forbidden_patterns": FORBIDDEN_PATTERNS,
        "failures": failures,
        "boundary": BOUNDARY,
        "verification_commands": [
            "python scripts/build_challenge_cup_claim_integrity_report.py",
            "python scripts/check_challenge_cup_readiness.py",
        ],
        "output_files": [OUTPUT_MD_RELATIVE, OUTPUT_JSON_RELATIVE],
    }


def build_markdown(payload: dict[str, Any]) -> str:
    rows = [
        "| Claim ID | Allowed claim | Evidence | Boundary | Forbidden overclaim |",
        "| --- | --- | --- | --- | --- |",
    ]
    for claim in payload["claims"]:
        evidence = "<br>".join(f"`{item}`" for item in claim["evidence_files"])
        rows.append(
            f"| `{claim['claim_id']}` | {claim['allowed_claim']} | {evidence} | "
            f"{claim['boundary']} | {claim['forbidden_overclaim']} |"
        )
    hits = "\n".join(
        f"- `{hit['path']}` matched `{hit['pattern']}`" for hit in payload["forbidden_hits"]
    ) or "- none"
    failures = "\n".join(f"- {failure}" for failure in payload["failures"]) or "- none"
    commands = "\n".join(f"- `{command}`" for command in payload["verification_commands"])
    return f"""# Claim Integrity Report

- report_type: `{payload["report_type"]}`
- status: `{payload["status"]}`
- completion_claim_allowed: `{payload["completion_claim_allowed"]}`
- does_not_satisfy_goal_completion: `{payload["does_not_satisfy_goal_completion"]}`
- award_guarantee_claimed: `{payload["award_guarantee_claimed"]}`
- expert_approval_claimed: `{payload["expert_approval_claimed"]}`
- timed_rehearsal_completion_claimed: `{payload["timed_rehearsal_completion_claimed"]}`
- production_deployment_claimed: `{payload["production_deployment_claimed"]}`
- all_claims_evidence_bound: `{payload["all_claims_evidence_bound"]}`
- forbidden_hit_count: `{payload["forbidden_hit_count"]}`

## Claim Registry

{chr(10).join(rows)}

## Forbidden Overclaim Scan

{hits}

## Failures

{failures}

## Verification

{commands}

## Boundary

{payload["boundary"]}
"""


def write_outputs(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or build_payload()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(build_markdown(payload).rstrip() + "\n", encoding="utf-8")
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"Wrote {repo_path(OUTPUT_MD)}")
    print(f"Wrote {repo_path(OUTPUT_JSON)}")
    print(f"Status: {payload['status']}")
    return 0 if payload["status"] == STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
