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
- run_challenge_cup_timed_rehearsal.py records actual timing metadata only with an independent --source attachment
- hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1 only when timing_acceptance_pass=true

## Source Integrity Guardrails

- preflight and record commands calculate source_sha256 from the real source attachment
- metadata source_sha256 must match the archived source attachment content
- --source must be the original evidence attachment, not the generated .json metadata summary; the source attachment must be non-empty and must not be a JSON metadata file
- do not edit or replace the source attachment after recording; changed bytes will fail readiness and goal gates

## Recording Commands

- `python scripts/record_challenge_cup_timed_rehearsal_schedule.py --id real-rehearsal-schedule-id --source path/to/real-calendar-or-observer-prep-file.txt --scheduled-date YYYY-MM-DD --observer real-observer-alias --venue-or-channel real-venue-or-channel --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible --checklist-item browser-smoke-opened --checklist-item offline-archive-ready --checklist-item five-killer-questions-assigned --confirm-real-schedule`
- `python scripts/run_challenge_cup_timed_rehearsal.py --id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal`
- `python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal --id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --evidence-type observer_note --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal`
- `python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal --id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --evidence-type observer_note --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal`

## Pre-hard-evidence PowerShell block

```powershell
Set-Location 'D:\虚拟C盘\RAG'
$scheduleId = 'rehearsal-schedule-YYYYMMDD-01'
$scheduleSource = 'D:\path\to\real-calendar-or-observer-prep-file.txt'
$scheduledDate = 'YYYY-MM-DD'
$observer = 'real-observer-alias'
$venue = 'real-venue-or-channel'
.\.venv\Scripts\python.exe .\scripts\record_challenge_cup_timed_rehearsal_schedule.py --id $scheduleId --source $scheduleSource --scheduled-date $scheduledDate --observer $observer --venue-or-channel $venue --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible --checklist-item browser-smoke-opened --checklist-item offline-archive-ready --checklist-item five-killer-questions-assigned --confirm-real-schedule
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

## PowerShell execution block

```powershell
Set-Location 'D:\虚拟C盘\RAG'
$rehearsalId = 'rehearsal-YYYYMMDD-01'
$rehearsalSource = 'D:\path\to\real-timer-or-observer-file.txt'
$rehearsalDate = 'YYYY-MM-DD'
$observer = 'real-observer-alias'
$opening = 88
$demo = 170
$offline = 18
$killer = 25,25,25,25,25
.\.venv\Scripts\python.exe .\scripts\run_challenge_cup_timed_rehearsal.py --id $rehearsalId --source $rehearsalSource --rehearsal-date $rehearsalDate --observer $observer --opening-actual-seconds $opening --demo-actual-seconds $demo --offline-fallback-actual-seconds $offline --killer-question-seconds $killer --confirm-real-rehearsal
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

## Failed Rehearsal Archival Rule

If any measured rehearsal segment exceeds the limit or a required killer-question timing is missing, still archive the real rehearsal evidence with timing_acceptance_pass=false; the hard evidence ledger must place the metadata in rejected_metadata_records and collected_count must not satisfy the acceptance gate.
