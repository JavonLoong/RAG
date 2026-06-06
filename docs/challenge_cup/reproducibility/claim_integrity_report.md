# Claim Integrity Report

- report_type: `challenge_cup_claim_integrity_report`
- status: `claim_integrity_verified_no_award_or_external_claim`
- completion_claim_allowed: `False`
- does_not_satisfy_goal_completion: `True`
- award_guarantee_claimed: `False`
- expert_approval_claimed: `False`
- timed_rehearsal_completion_claimed: `False`
- production_deployment_claimed: `False`
- all_claims_evidence_bound: `True`
- forbidden_hit_count: `0`

## Claim Registry

| Claim ID | Allowed claim | Evidence | Boundary | Forbidden overclaim |
| --- | --- | --- | --- | --- |
| `package_review_ready` | The current package can be reviewed as a reproducible project-closure package. | `docs/challenge_cup/package_manifest.json`<br>`docs/challenge_cup/reproducibility/evidence_hashes.json`<br>`docs/challenge_cup/reproducibility/readiness_gate_report.md`<br>`docs/challenge_cup/reproducibility/verify_submission_package.py` | Package review readiness is not final goal completion and is not an award guarantee. | Do not say package readiness proves the special-prize result. |
| `graphrag_innovation_bounded` | GraphRAG is used for evidence organization over fixed, auditable subsets. | `docs/challenge_cup/02_技术白皮书.md`<br>`evaluation/reports/challenge_cup_graphrag_answer_benchmark.md`<br>`evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.md` | This does not claim GraphRAG beats every baseline question or proves online LLM win-rate. | Do not claim universal GraphRAG superiority. |
| `evaluation_transparency` | The project discloses the evaluation set, baselines, weak cases, and remediation records. | `evaluation/system_eval_questions.jsonl`<br>`evaluation/reports/day4_failure_analysis_20260605_210642.md`<br>`evaluation/reports/challenge_cup_failure_remediation_before_after.md` | Transparent local evaluation is not external validation or production acceptance. | Do not hide failure cases or imply the evaluation proves production readiness. |
| `application_value_bounded` | The GT-07 scenario provides a fixed, evidence-linked application-value demonstration. | `docs/challenge_cup/11_应用场景与专家验证.md`<br>`docs/challenge_cup/reproducibility/application_validation_report.md`<br>`docs/challenge_cup/reproducibility/application_value_quantification.md`<br>`docs/challenge_cup/reproducibility/numeric_traceability_report.md` | The GT-07 demonstration does not replace engineers and does not claim production validation. | Do not present local scenario evidence as signed industry deployment validation. |
| `defense_demo_fallback_ready` | The defense has a browser-smoke snapshot and offline fallback materials. | `docs/challenge_cup/04_系统演示脚本.md`<br>`docs/challenge_cup/14_现场答辩操作Runbook.md`<br>`docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`<br>`docs/challenge_cup/defense_console/index.html` | Fallback readiness is not a completed real timed rehearsal. | Do not say a real timed rehearsal has been completed before hard evidence is archived. |
| `external_hard_evidence_not_closed` | Real expert feedback and real timed rehearsal evidence are prepared for collection but not closed. | `docs/challenge_cup/reproducibility/hard_evidence_ledger.md`<br>`docs/challenge_cup/reproducibility/expert_feedback_request_packet.md`<br>`docs/challenge_cup/reproducibility/timed_rehearsal_schedule_ledger.md`<br>`docs/challenge_cup/reproducibility/goal_completion_report.md` | Outreach packets and ledgers do not equal real expert approval or real timed rehearsal completion. | Do not present internal forms, request packets, or schedules as completed hard evidence. |
| `special_prize_competition_argument` | The special-prize argument is evidence density, innovation framing, completion, and defense readiness. | `docs/challenge_cup/08_特等奖评审自评表.md`<br>`docs/challenge_cup/reproducibility/official_rubric_alignment.md`<br>`docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md` | This is an argument for competition readiness, not an award probability or guarantee. | Do not promise, imply, or quantify a special-prize result. |
| `human_decision_boundary` | The system is an evidence assistant for professional review, not an autonomous maintenance decision-maker. | `docs/challenge_cup/05_答辩问答手册.md`<br>`docs/challenge_cup/reproducibility/no_answer_boundary_evaluation.md`<br>`docs/challenge_cup/21_知识产权与开源合规说明.md` | High-risk maintenance conclusions still require human confirmation and source evidence. | Do not say the system replaces engineers or makes final maintenance decisions. |

## Forbidden Overclaim Scan

- none

## Failures

- none

## Verification

- `python scripts/build_challenge_cup_claim_integrity_report.py`
- `python scripts/check_challenge_cup_readiness.py`

## Boundary

This report audits package-level defense claims for evidence links and forbidden overclaims. It does not guarantee an award, does not claim expert approval, does not claim timed rehearsal completion, does not claim production deployment, and does not satisfy goal completion without real expert feedback and real timed rehearsal evidence.
