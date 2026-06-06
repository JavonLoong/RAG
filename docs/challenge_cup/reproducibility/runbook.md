# 可复现运行手册

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -q
.\.venv\Scripts\python.exe -m pytest api_server/current_console/chroma_rag_poc/tests -q
```

## 扩展评测集

```powershell
.\.venv\Scripts\python.exe scripts/extend_challenge_cup_eval_questions.py
```

## 运行现场演示烟测

```powershell
.\.venv\Scripts\python.exe scripts/run_challenge_cup_live_demo_smoke.py
node scripts/run_challenge_cup_browser_demo_smoke.mjs
```

## 重新生成 Day3 baseline

```powershell
.\.venv\Scripts\python.exe scripts/run_day3_retrieval_baselines.py --dataset evaluation/system_eval_questions.jsonl --top-k 5
```

## 重新生成 Day4 失败分析

```powershell
.\.venv\Scripts\python.exe scripts/analyze_day4_failure_cases.py
```

## 生成 Day4 失败整改 before/after

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_failure_remediation_before_after.py
```

## 生成应用价值量化报告

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_application_value_quantification.py
```

## 生成数值追溯一致性报告

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_numeric_traceability_report.py
```

## 生成无答案边界评测报告

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_no_answer_boundary_evaluation.py
```

## 生成评审主张诚信报告

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_claim_integrity_report.py
```

## 生成官方评分维度答辩覆盖报告

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_rubric_defense_coverage.py
```

## 生成运行环境复现快照

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_runtime_reproducibility_snapshot.py
```

## 生成复核转录摘要

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_verification_transcript.py
```

## 重新生成挑战杯成果包

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_package.py
```

## 刷新终审答辩 PPT

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_defense_deck.py --force
```

## 刷新官方评审口径对齐表

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_official_rubric_alignment.py
```

## 归档真实硬证据

收到真实专家反馈附件后运行：

```powershell
.\.venv\Scripts\python.exe scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id <real-feedback-id> --source <real-feedback-file> --evidence-type email_reply --reviewer-identity <real-reviewer-identity> --role-or-org <real-reviewer-role-or-org> --review-date <real-review-date-yyyy-mm-dd> --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback
.\.venv\Scripts\python.exe scripts/record_challenge_cup_hard_evidence.py expert_feedback --id <real-feedback-id> --source <real-feedback-file> --evidence-type email_reply --reviewer-identity <real-reviewer-identity> --role-or-org <real-reviewer-role-or-org> --review-date <real-review-date-yyyy-mm-dd> --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback
```

真实外发专家反馈请求后，先记录外发凭证；这不等同于专家反馈硬证据：

```powershell
.\.venv\Scripts\python.exe scripts/record_challenge_cup_expert_outreach.py --id <real-outreach-id> --source <real-outreach-proof> --recipient-alias <real-reviewer-alias> --recipient-role <real-reviewer-role> --channel email --sent-date <real-sent-date-yyyy-mm-dd> --status sent --requested-review-dimension practicality --requested-review-dimension innovation --requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/00_项目一页纸.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date <real-followup-due-date-yyyy-mm-dd> --confirm-real-outreach
```

真实计时彩排排期或观察员准备完成后，先记录排期凭证；这不等同于真实计时彩排硬证据：

```powershell
.\.venv\Scripts\python.exe scripts/record_challenge_cup_timed_rehearsal_schedule.py --id <real-rehearsal-schedule-id> --source <real-calendar-or-observer-prep-file> --scheduled-date <real-scheduled-date-yyyy-mm-dd> --observer <real-observer-alias> --venue-or-channel <real-venue-or-channel> --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible --checklist-item browser-smoke-opened --checklist-item offline-archive-ready --checklist-item five-killer-questions-assigned --confirm-real-schedule
```

完成真实计时彩排后，首选用测得秒数生成观察员记录并归档：

```powershell
.\.venv\Scripts\python.exe scripts/run_challenge_cup_timed_rehearsal.py --id <real-rehearsal-id> --source <real-timer-or-observer-file> --rehearsal-date <real-rehearsal-date-yyyy-mm-dd> --observer <real-observer-alias> --opening-actual-seconds <actual-opening-seconds> --demo-actual-seconds <actual-demo-seconds> --offline-fallback-actual-seconds <actual-offline-fallback-seconds> --killer-question-seconds <q1-seconds> <q2-seconds> <q3-seconds> <q4-seconds> <q5-seconds> --confirm-real-rehearsal
```

如果已有真实计时截图、录屏或观察员笔记附件，也可以直接归档：

```powershell
.\.venv\Scripts\python.exe scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal --id <real-rehearsal-id> --source <real-timer-or-observer-file> --evidence-type observer_note --rehearsal-date <real-rehearsal-date-yyyy-mm-dd> --observer <real-observer-alias> --opening-actual-seconds <actual-opening-seconds> --demo-actual-seconds <actual-demo-seconds> --offline-fallback-actual-seconds <actual-offline-fallback-seconds> --killer-question-seconds <q1-seconds> <q2-seconds> <q3-seconds> <q4-seconds> <q5-seconds> --confirm-real-rehearsal
.\.venv\Scripts\python.exe scripts/record_challenge_cup_hard_evidence.py timed_rehearsal --id <real-rehearsal-id> --source <real-timer-or-observer-file> --evidence-type observer_note --rehearsal-date <real-rehearsal-date-yyyy-mm-dd> --observer <real-observer-alias> --opening-actual-seconds <actual-opening-seconds> --demo-actual-seconds <actual-demo-seconds> --offline-fallback-actual-seconds <actual-offline-fallback-seconds> --killer-question-seconds <q1-seconds> <q2-seconds> <q3-seconds> <q4-seconds> <q5-seconds> --confirm-real-rehearsal
```

## 刷新硬证据台账

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_expert_outreach_ledger.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_timed_rehearsal_schedule_ledger.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_hard_evidence_closure_board.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_hard_evidence_action_pack.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_external_evidence_execution_kit.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_hard_evidence_ledger.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_judge_objection_matrix.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_special_prize_readiness_dashboard.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_defense_slide_traceability.py
```

## 运行结项 readiness gate

```powershell
.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py
```

## 运行总目标完成门禁

```powershell
.\.venv\Scripts\python.exe scripts/check_challenge_cup_goal_completion.py
.\.venv\Scripts\python.exe docs/challenge_cup/reproducibility/verify_submission_package.py --root .
.\.venv\Scripts\python.exe scripts/build_challenge_cup_final_acceptance_audit.py
```

当前缺少真实专家反馈和真实计时彩排时，该门禁应返回 fail；这不是包生成失败，而是防止把 package readiness 误写成总目标已完成。
