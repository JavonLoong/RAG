from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility"
OUTPUT_JSON = OUTPUT_DIR / "judge_objection_response_matrix.json"
OUTPUT_MD = OUTPUT_DIR / "judge_objection_response_matrix.md"

REPORT_TYPE = "challenge_cup_judge_objection_response_matrix"
STATUS = "ready_for_judge_objection_drill_no_external_claims"
BOUNDARY = (
    "This matrix prepares judge-objection responses for defense rehearsal. It does not claim expert "
    "approval, real timed rehearsal completion, production validation, award probability, or goal completion."
)


def repo_path(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def build_payload() -> dict[str, Any]:
    objections = [
        {
            "objection_id": "OJ-01-normal-rag",
            "severity": "P0",
            "judge_objection": "Is this just a normal RAG demo with a nicer interface?",
            "one_sentence_answer": (
                "No: the project turns OCR sources into evidence-bound RAG, KG triples, GraphRAG subsets, "
                "failure analysis, and reproducible package gates."
            ),
            "evidence_files": [
                "docs/challenge_cup/02_技术白皮书.md",
                "docs/challenge_cup/07_评审主张证据矩阵.md",
                "evaluation/reports/challenge_cup_graphrag_same_question_report.md",
            ],
            "fallback_if_challenged": "Open the claim-evidence matrix and point to KG/GraphRAG evidence paths.",
            "forbidden_overclaim": "Do not say every answer requires GraphRAG or that GraphRAG is always better.",
            "answer_time_limit_seconds": 30,
            "rubric_dimensions": ["innovation", "completion"],
        },
        {
            "objection_id": "OJ-02-graphrag-baseline",
            "severity": "P0",
            "judge_objection": "Your own evaluation says GraphRAG is not always better than keyword or hybrid retrieval.",
            "one_sentence_answer": (
                "Correct: the claim is narrower and stronger, because GraphRAG improves relationship evidence "
                "organization on the fixed subset while baseline strengths and failures remain disclosed."
            ),
            "evidence_files": [
                "docs/challenge_cup/03_实验评测报告.md",
                "docs/challenge_cup/22_同类方案对比与创新性证据卡.md",
                "evaluation/reports/challenge_cup_graphrag_answer_benchmark.md",
            ],
            "fallback_if_challenged": "Quote the boundary that GraphRAG does not beat every baseline question.",
            "forbidden_overclaim": "Do not claim universal GraphRAG superiority.",
            "answer_time_limit_seconds": 30,
            "rubric_dimensions": ["academic_or_practical_value", "innovation"],
        },
        {
            "objection_id": "OJ-03-engineer-replacement",
            "severity": "P0",
            "judge_objection": "Can this replace maintenance engineers for real turbine decisions?",
            "one_sentence_answer": (
                "No: it is an evidence assistant for finding thresholds, mechanisms, symptoms, repair records, "
                "and source paths; high-risk maintenance still requires human confirmation."
            ),
            "evidence_files": [
                "docs/challenge_cup/05_答辩问答手册.md",
                "docs/challenge_cup/reproducibility/application_validation_report.md",
                "docs/challenge_cup/21_知识产权与开源合规说明.md",
            ],
            "fallback_if_challenged": "Open the GT-07 report and show the human-confirmation boundary.",
            "forbidden_overclaim": "Do not say the system makes final maintenance decisions.",
            "answer_time_limit_seconds": 30,
            "rubric_dimensions": ["academic_or_practical_value", "defense_performance"],
        },
        {
            "objection_id": "OJ-04-production-data",
            "severity": "P0",
            "judge_objection": "Is the data volume enough to support a production-grade claim?",
            "one_sentence_answer": (
                "The production-grade claim is not made; the package proves a course/project-stage, fixed-scenario "
                "knowledge-engineering workflow with auditable data boundaries."
            ),
            "evidence_files": [
                "docs/challenge_cup/11_应用场景与专家验证.md",
                "docs/challenge_cup/reproducibility/dataset_manifest.md",
                "docs/challenge_cup/reproducibility/final_acceptance_audit.md",
            ],
            "fallback_if_challenged": "State the current scope and move to the dataset manifest.",
            "forbidden_overclaim": "Do not imply unauthorized production data or full production coverage.",
            "answer_time_limit_seconds": 30,
            "rubric_dimensions": ["completion", "defense_performance"],
        },
        {
            "objection_id": "OJ-05-live-demo-failure",
            "severity": "P0",
            "judge_objection": "What if the live browser demo or local service fails during defense?",
            "one_sentence_answer": (
                "The runbook requires a 20-second switch to offline fallback evidence: screenshots, browser smoke, "
                "KG artifacts, readiness, and the defense control console."
            ),
            "evidence_files": [
                "docs/challenge_cup/14_现场答辩操作Runbook.md",
                "docs/challenge_cup/defense_console/index.html",
                "docs/challenge_cup/reproducibility/browser_demo_smoke_report.md",
            ],
            "fallback_if_challenged": "Open the defense control console and desktop search-result screenshot.",
            "forbidden_overclaim": "Do not debug live or pretend the service never fails.",
            "answer_time_limit_seconds": 30,
            "rubric_dimensions": ["completion", "defense_performance"],
        },
        {
            "objection_id": "OJ-06-cherry-picked-evaluation",
            "severity": "P1",
            "judge_objection": "Did you only show successful questions and hide weak cases?",
            "one_sentence_answer": (
                "No: the package includes 60 evaluation questions, baseline comparison, failure analysis, "
                "GraphRAG answer benchmark, and gap remediation records."
            ),
            "evidence_files": [
                "evaluation/system_eval_questions.jsonl",
                "evaluation/reports/day4_failure_analysis_20260605_210642.md",
                "evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.md",
            ],
            "fallback_if_challenged": "Open the failure analysis and gap remediation plan before showing successes.",
            "forbidden_overclaim": "Do not remove or downplay failure cases.",
            "answer_time_limit_seconds": 30,
            "rubric_dimensions": ["completion", "academic_or_practical_value"],
        },
        {
            "objection_id": "OJ-07-expert-validation",
            "severity": "P0",
            "judge_objection": "Where is real expert validation or advisor feedback?",
            "one_sentence_answer": (
                "It is not yet claimed: the package includes request packets and recording commands, but real expert "
                "feedback must be archived before goal completion."
            ),
            "evidence_files": [
                "docs/challenge_cup/reproducibility/expert_feedback_request_packet.md",
                "docs/challenge_cup/reproducibility/hard_evidence_ledger.md",
                "docs/challenge_cup/reproducibility/goal_completion_report.md",
            ],
            "fallback_if_challenged": "Say real expert feedback is a remaining hard-evidence item and show the ledger.",
            "forbidden_overclaim": "Do not present internal review material as real expert feedback.",
            "answer_time_limit_seconds": 30,
            "rubric_dimensions": ["defense_performance"],
        },
        {
            "objection_id": "OJ-08-special-prize-claim",
            "severity": "P0",
            "judge_objection": "Why can this compete for a special prize instead of only ordinary completion?",
            "one_sentence_answer": (
                "The argument is evidence density: real data processing, GraphRAG innovation, transparent evaluation, "
                "demo readiness, and strict boundaries; no award guarantee is made."
            ),
            "evidence_files": [
                "docs/challenge_cup/08_特等奖评审自评表.md",
                "docs/challenge_cup/reproducibility/official_rubric_alignment.md",
                "docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md",
            ],
            "fallback_if_challenged": "Use the official-rubric alignment and say readiness gate is not an award guarantee.",
            "forbidden_overclaim": "Do not promise or imply a special-prize result.",
            "answer_time_limit_seconds": 30,
            "rubric_dimensions": [
                "academic_or_practical_value",
                "innovation",
                "completion",
                "defense_performance",
            ],
        },
        {
            "objection_id": "OJ-09-ip-and-compliance",
            "severity": "P1",
            "judge_objection": "Are there IP, open-source, data authorization, or academic-integrity risks?",
            "one_sentence_answer": (
                "The package separates originality, dependency, data-source, citation, and no-patent/no-paper claims "
                "so the defense does not overstate legal or academic status."
            ),
            "evidence_files": [
                "docs/challenge_cup/21_知识产权与开源合规说明.md",
                "docs/challenge_cup/package_manifest.json",
                "docs/challenge_cup/reproducibility/evidence_hashes.json",
            ],
            "fallback_if_challenged": "Open the compliance document and submission manifest.",
            "forbidden_overclaim": "Do not claim a patent, publication, or production-data authorization that is not present.",
            "answer_time_limit_seconds": 30,
            "rubric_dimensions": ["defense_performance", "completion"],
        },
        {
            "objection_id": "OJ-10-project-closure",
            "severity": "P1",
            "judge_objection": "Can this be accepted as a closure package today?",
            "one_sentence_answer": (
                "Yes for package review: the submission archive, verifier, hashes, and 61 readiness gates prove the "
                "materials are organized and reproducible, while goal completion still waits for real hard evidence."
            ),
            "evidence_files": [
                "docs/challenge_cup/reproducibility/readiness_gate_report.md",
                "docs/challenge_cup/reproducibility/verify_submission_package.py",
                "docs/challenge_cup/reproducibility/final_acceptance_audit.md",
            ],
            "fallback_if_challenged": "Run or cite the verifier, then disclose the two external hard-evidence blockers.",
            "forbidden_overclaim": "Do not say package readiness equals final goal completion.",
            "answer_time_limit_seconds": 30,
            "rubric_dimensions": ["completion"],
        },
    ]
    return {
        "report_type": REPORT_TYPE,
        "status": STATUS,
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "boundary": BOUNDARY,
        "response_rules": {
            "max_answer_seconds": 30,
            "must_cite_evidence": True,
            "must_state_boundary_when_external_validation_is_missing": True,
            "no_award_guarantee": True,
            "no_fake_external_validation": True,
        },
        "objection_count": len(objections),
        "objections": objections,
        "verification_commands": [
            "python scripts/build_challenge_cup_judge_objection_matrix.py",
            "python scripts/build_challenge_cup_package.py",
            "python scripts/check_challenge_cup_readiness.py",
        ],
        "evidence_files": [
            "docs/challenge_cup/reproducibility/judge_objection_response_matrix.md",
            "docs/challenge_cup/reproducibility/judge_objection_response_matrix.json",
        ],
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Judge Objection Response Matrix",
        "",
        f"- report_type: `{payload['report_type']}`",
        f"- status: `{payload['status']}`",
        f"- completion_claim_allowed: `{payload['completion_claim_allowed']}`",
        f"- does_not_satisfy_goal_completion: `{payload['does_not_satisfy_goal_completion']}`",
        f"- boundary: {payload['boundary']}",
        "",
        "## Response Rules",
        "",
        f"- max answer time: {payload['response_rules']['max_answer_seconds']} seconds",
        "- must cite at least one evidence file",
        "- must state missing-boundary facts when real expert feedback or real timed rehearsal is absent",
        "- no award guarantee; readiness gate is not an award guarantee",
        "",
        "## Objection Matrix",
        "",
        "| ID | Severity | Judge objection | 30-second answer | Evidence | Forbidden overclaim |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in payload["objections"]:
        evidence = "<br>".join(f"`{path}`" for path in item["evidence_files"])
        lines.append(
            "| {objection_id} | {severity} | {judge_objection} | {one_sentence_answer} | {evidence} | {forbidden_overclaim} |".format(
                evidence=evidence,
                **item,
            )
        )
    lines.extend(["", "## Verification Commands", ""])
    lines.extend(f"- `{command}`" for command in payload["verification_commands"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_outputs() -> dict[str, Any]:
    payload = build_payload()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(OUTPUT_MD, payload)
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"judge objection response matrix: {repo_path(OUTPUT_MD)}")
    print(f"Status: {payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
