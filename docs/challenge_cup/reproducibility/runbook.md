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
.\.venv\Scripts\python.exe scripts/record_challenge_cup_hard_evidence.py expert_feedback --id advisor-a --source <真实专家反馈附件路径> --evidence-type email_reply --reviewer-identity advisor-a --role-or-org advisor --review-date 2026-06-06 --review-dimension 实用性 --review-dimension 创新性 --review-dimension 边界严谨性 --remediation-issue 演示节奏 --remediation-action 压缩开场
```

真实外发专家反馈请求后，先记录外发凭证；这不等同于专家反馈硬证据：

```powershell
.\.venv\Scripts\python.exe scripts/record_challenge_cup_expert_outreach.py --id advisor-a-20260606 --source <真实外发邮件或聊天凭证路径> --recipient-alias advisor-a --recipient-role advisor --channel email --sent-date 2026-06-06 --status sent --requested-review-dimension 实用性 --requested-review-dimension 创新性 --requested-review-dimension 边界严谨性 --requested-attachment docs/challenge_cup/00_项目一页纸.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date 2026-06-09 --confirm-real-outreach
```

真实计时彩排排期或观察员准备完成后，先记录排期凭证；这不等同于真实计时彩排硬证据：

```powershell
.\.venv\Scripts\python.exe scripts/record_challenge_cup_timed_rehearsal_schedule.py --id rehearsal-schedule-20260606 --source <真实日历邀请或观察员准备记录路径> --scheduled-date 2026-06-06 --observer observer-a --venue-or-channel meeting-room-a --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item "timer visible to observer" --checklist-item "browser smoke report opened" --checklist-item "offline fallback archive ready" --checklist-item "five killer questions assigned" --confirm-real-schedule
```

完成真实计时彩排后，首选用测得秒数生成观察员记录并归档：

```powershell
.\.venv\Scripts\python.exe scripts/run_challenge_cup_timed_rehearsal.py --id rehearsal-1 --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal
```

如果已有真实计时截图、录屏或观察员笔记附件，也可以直接归档：

```powershell
.\.venv\Scripts\python.exe scripts/record_challenge_cup_hard_evidence.py timed_rehearsal --id rehearsal-1 --source <真实计时记录附件路径> --evidence-type observer_note --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29
```

## 刷新硬证据台账

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_expert_outreach_ledger.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_timed_rehearsal_schedule_ledger.py
.\.venv\Scripts\python.exe scripts/build_challenge_cup_hard_evidence_ledger.py
```

## 运行结项 readiness gate

```powershell
.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py
```

## 运行总目标完成门禁

```powershell
.\.venv\Scripts\python.exe scripts/check_challenge_cup_goal_completion.py
```

当前缺少真实专家反馈和真实计时彩排时，该门禁应返回 fail；这不是包生成失败，而是防止把 package readiness 误写成总目标已完成。
