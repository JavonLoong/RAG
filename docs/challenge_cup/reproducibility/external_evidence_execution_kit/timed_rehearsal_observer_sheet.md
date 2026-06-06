# timed_rehearsal_observer Handoff

- hard_evidence_category: `timed_rehearsal`
- owner: presenter + real observer
- acceptance_gate: `hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1`
- does_not_satisfy_goal_completion: `True`

## Integrity Boundary

不伪造真实专家反馈；不伪造真实计时彩排；未归档真实硬证据前不能标记目标完成。

## Attachment Files

- `docs/challenge_cup/04_系统演示脚本.md`
- `docs/challenge_cup/05_答辩问答手册.md`
- `docs/challenge_cup/10_答辩攻防与彩排卡.md`
- `docs/challenge_cup/14_现场答辩操作Runbook.md`
- `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`
- `docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md`
- `docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md`
- `docs/challenge_cup/reproducibility/final_acceptance_audit.md`

## Execution Steps

- Assign a real observer and make the timer visible before the rehearsal starts.
- Run the 90-second opening, three-minute demo, offline fallback switch, and five killer questions.
- Record actual seconds for every segment and mark missed evidence anchors immediately.
- Archive the timer screenshot, screen recording, observer note, or missed-question list before claiming completion.

## Done When

- a real observer is recorded
- opening/demo/offline fallback/killer-question seconds are measured
- run_challenge_cup_timed_rehearsal.py records actual timing metadata
- hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1

## Recording Commands

- `python scripts/record_challenge_cup_timed_rehearsal_schedule.py --id rehearsal-schedule-20260606 --source <real-calendar-or-observer-prep-file> --scheduled-date 2026-06-06 --observer observer-a --venue-or-channel meeting-room-a --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible --checklist-item browser-smoke-opened --checklist-item offline-archive-ready --checklist-item five-killer-questions-assigned --confirm-real-schedule`
- `python scripts/run_challenge_cup_timed_rehearsal.py --id rehearsal-1 --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal`
- `python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal --id rehearsal-1 --source <real-timer-or-observer-file> --evidence-type observer_note --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal`
- `python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal --id rehearsal-1 --source <real-timer-or-observer-file> --evidence-type observer_note --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal`
