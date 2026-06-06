# Judge Objection Response Matrix

- report_type: `challenge_cup_judge_objection_response_matrix`
- status: `ready_for_judge_objection_drill_no_external_claims`
- completion_claim_allowed: `False`
- does_not_satisfy_goal_completion: `True`
- boundary: This matrix prepares judge-objection responses for defense rehearsal. It does not claim expert approval, real timed rehearsal completion, production validation, award probability, or goal completion.

## Response Rules

- max answer time: 30 seconds
- must cite at least one evidence file
- must state missing-boundary facts when real expert feedback or real timed rehearsal is absent
- no award guarantee; readiness gate is not an award guarantee

## Objection Matrix

| ID | Severity | Judge objection | 30-second answer | Evidence | Forbidden overclaim |
| --- | --- | --- | --- | --- | --- |
| OJ-01-normal-rag | P0 | Is this just a normal RAG demo with a nicer interface? | No: the project turns OCR sources into evidence-bound RAG, KG triples, GraphRAG subsets, failure analysis, and reproducible package gates. | `docs/challenge_cup/02_技术白皮书.md`<br>`docs/challenge_cup/07_评审主张证据矩阵.md`<br>`evaluation/reports/challenge_cup_graphrag_same_question_report.md` | Do not say every answer requires GraphRAG or that GraphRAG is always better. |
| OJ-02-graphrag-baseline | P0 | Your own evaluation says GraphRAG is not always better than keyword or hybrid retrieval. | Correct: the claim is narrower and stronger, because GraphRAG improves relationship evidence organization on the fixed subset while baseline strengths and failures remain disclosed. | `docs/challenge_cup/03_实验评测报告.md`<br>`docs/challenge_cup/22_同类方案对比与创新性证据卡.md`<br>`evaluation/reports/challenge_cup_graphrag_answer_benchmark.md` | Do not claim universal GraphRAG superiority. |
| OJ-03-engineer-replacement | P0 | Can this replace maintenance engineers for real turbine decisions? | No: it is an evidence assistant for finding thresholds, mechanisms, symptoms, repair records, and source paths; high-risk maintenance still requires human confirmation. | `docs/challenge_cup/05_答辩问答手册.md`<br>`docs/challenge_cup/reproducibility/application_validation_report.md`<br>`docs/challenge_cup/21_知识产权与开源合规说明.md` | Do not say the system makes final maintenance decisions. |
| OJ-04-production-data | P0 | Is the data volume enough to support a production-grade claim? | The production-grade claim is not made; the package proves a course/project-stage, fixed-scenario knowledge-engineering workflow with auditable data boundaries. | `docs/challenge_cup/11_应用场景与专家验证.md`<br>`docs/challenge_cup/reproducibility/dataset_manifest.md`<br>`docs/challenge_cup/reproducibility/final_acceptance_audit.md` | Do not imply unauthorized production data or full production coverage. |
| OJ-05-live-demo-failure | P0 | What if the live browser demo or local service fails during defense? | The runbook requires a 20-second switch to offline fallback evidence: screenshots, browser smoke, KG artifacts, readiness, and the defense control console. | `docs/challenge_cup/14_现场答辩操作Runbook.md`<br>`docs/challenge_cup/defense_console/index.html`<br>`docs/challenge_cup/reproducibility/browser_demo_smoke_report.md` | Do not debug live or pretend the service never fails. |
| OJ-06-cherry-picked-evaluation | P1 | Did you only show successful questions and hide weak cases? | No: the package includes 60 evaluation questions, baseline comparison, failure analysis, GraphRAG answer benchmark, and gap remediation records. | `evaluation/system_eval_questions.jsonl`<br>`evaluation/reports/day4_failure_analysis_20260605_210642.md`<br>`evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.md` | Do not remove or downplay failure cases. |
| OJ-07-expert-validation | P0 | Where is real expert validation or advisor feedback? | It is not yet claimed: the package includes request packets and recording commands, but real expert feedback must be archived before goal completion. | `docs/challenge_cup/reproducibility/expert_feedback_request_packet.md`<br>`docs/challenge_cup/reproducibility/hard_evidence_ledger.md`<br>`docs/challenge_cup/reproducibility/goal_completion_report.md` | Do not present internal review material as real expert feedback. |
| OJ-08-special-prize-claim | P0 | Why can this compete for a special prize instead of only ordinary completion? | The argument is evidence density: real data processing, GraphRAG innovation, transparent evaluation, demo readiness, and strict boundaries; no award guarantee is made. | `docs/challenge_cup/08_特等奖评审自评表.md`<br>`docs/challenge_cup/reproducibility/official_rubric_alignment.md`<br>`docs/challenge_cup/reproducibility/special_prize_readiness_dashboard.md` | Do not promise or imply a special-prize result. |
| OJ-09-ip-and-compliance | P1 | Are there IP, open-source, data authorization, or academic-integrity risks? | The package separates originality, dependency, data-source, citation, and no-patent/no-paper claims so the defense does not overstate legal or academic status. | `docs/challenge_cup/21_知识产权与开源合规说明.md`<br>`docs/challenge_cup/package_manifest.json`<br>`docs/challenge_cup/reproducibility/evidence_hashes.json` | Do not claim a patent, publication, or production-data authorization that is not present. |
| OJ-10-project-closure | P1 | Can this be accepted as a closure package today? | Yes for package review: the submission archive, verifier, hashes, and 55 readiness gates prove the materials are organized and reproducible, while goal completion still waits for real hard evidence. | `docs/challenge_cup/reproducibility/readiness_gate_report.md`<br>`docs/challenge_cup/reproducibility/verify_submission_package.py`<br>`docs/challenge_cup/reproducibility/final_acceptance_audit.md` | Do not say package readiness equals final goal completion. |

## Verification Commands

- `python scripts/build_challenge_cup_judge_objection_matrix.py`
- `python scripts/build_challenge_cup_package.py`
- `python scripts/check_challenge_cup_readiness.py`
