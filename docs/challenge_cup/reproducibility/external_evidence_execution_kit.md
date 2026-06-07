# External Evidence Execution Kit

- report_type: `challenge_cup_external_evidence_execution_kit`
- status: `ready_for_external_execution_handoff`
- completion_claim_allowed: `False`
- does_not_satisfy_goal_completion=True
- boundary: This kit packages the final human handoff materials for collecting real external hard evidence. It does not satisfy goal completion, does not claim expert approval, and does not claim a timed rehearsal has been completed.

## Integrity Rules

- 不伪造真实专家反馈
- 不伪造真实计时彩排
- 外发材料、排期记录和执行包本身不满足 goal completion

## Operator Sequence

### verify_package_ready

- Phase: `machine_package_preflight`
- Category: `package_readiness`
- Command: `python scripts/check_challenge_cup_readiness.py`
- Human proof required: none; this is a machine gate before contacting reviewers or observers
- counts_as_hard_evidence: `False`
- Expected after step: readiness gate reports pass 64/64
- Guardrail: A passing package gate is not expert approval, timed rehearsal completion, or award proof.
- does_not_claim_award_or_completion: `True`

### record_expert_outreach

- Phase: `expert_feedback_outreach`
- Category: `expert_feedback`
- Command: `python scripts/record_challenge_cup_expert_outreach.py --id real-outreach-id --source path/to/real-outreach-proof.eml --recipient-alias real-reviewer-alias --recipient-role real-reviewer-role --channel email --sent-date YYYY-MM-DD --status sent --requested-review-dimension practicality --requested-review-dimension innovation --requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/00_项目一页纸.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date YYYY-MM-DD --confirm-real-outreach`
- Human proof required: real sent email, chat message, meeting notice, or follow-up screenshot
- counts_as_hard_evidence: `False`
- Expected after step: expert_feedback_outreach_ledger records the outreach but hard_evidence_ledger remains open
- Guardrail: Outreach proves a request was sent; it does not prove expert feedback was received.
- does_not_claim_award_or_completion: `True`

### record_rehearsal_schedule

- Phase: `timed_rehearsal_scheduling`
- Category: `timed_rehearsal`
- Command: `python scripts/record_challenge_cup_timed_rehearsal_schedule.py --id real-rehearsal-schedule-id --source path/to/real-calendar-or-observer-prep-file.txt --scheduled-date YYYY-MM-DD --observer real-observer-alias --venue-or-channel real-venue-or-channel --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible --checklist-item browser-smoke-opened --checklist-item offline-archive-ready --checklist-item five-killer-questions-assigned --confirm-real-schedule`
- Human proof required: real calendar invite, meeting notice, or observer preparation record
- counts_as_hard_evidence: `False`
- Expected after step: timed_rehearsal_schedule_ledger records the schedule but timed_rehearsal evidence remains open
- Guardrail: A schedule proves intent to rehearse; it does not prove a timed rehearsal happened.
- does_not_claim_award_or_completion: `True`

### preflight_expert_feedback

- Phase: `expert_feedback_validation`
- Category: `expert_feedback`
- Command: `python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id --source path/to/real-feedback.eml --evidence-type email_reply --reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org --review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue issue --remediation-action action --confirm-real-feedback`
- Human proof required: real signed form, email reply, meeting minutes, or chat screenshot from reviewer
- counts_as_hard_evidence: `False`
- Expected after step: preflight returns pass and does not write hard evidence
- Guardrail: Preflight is a dry run; only record_challenge_cup_hard_evidence.py archives evidence.
- does_not_claim_award_or_completion: `True`

### record_expert_feedback

- Phase: `expert_feedback_archival`
- Category: `expert_feedback`
- Command: `python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id --source path/to/real-feedback.eml --evidence-type email_reply --reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org --review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue issue --remediation-action action --confirm-real-feedback`
- Human proof required: same real reviewer feedback source that passed preflight
- counts_as_hard_evidence: `True`
- Expected after step: hard_evidence_ledger.categories.expert_feedback.collected_count >= 1
- Guardrail: Records feedback evidence only; it still does not guarantee an award.
- does_not_claim_award_or_completion: `True`

### run_timed_rehearsal

- Phase: `timed_rehearsal_archival`
- Category: `timed_rehearsal`
- Command: `python scripts/run_challenge_cup_timed_rehearsal.py --id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal`
- Human proof required: actual observed rehearsal timings from a visible timer or observer note
- counts_as_hard_evidence: `True`
- Expected after step: if timing_acceptance_pass=true, hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1; if timing_acceptance_pass=false, metadata is preserved in rejected_metadata_records and collected_count does not satisfy the gate
- Guardrail: Measured rehearsal timing supports defense readiness; it is not expert approval or award proof.
- does_not_claim_award_or_completion: `True`

### rebuild_package

- Phase: `post_evidence_package_refresh`
- Category: `package_readiness`
- Command: `python scripts/build_challenge_cup_package.py`
- Human proof required: archived expert feedback and archived timed rehearsal evidence are already present
- counts_as_hard_evidence: `False`
- Expected after step: package manifest, evidence hashes, and submission archive are refreshed
- Guardrail: Package rebuild is only a refresh; it does not prove readiness or goal completion.
- does_not_claim_award_or_completion: `True`

### check_readiness_gate

- Phase: `post_evidence_package_refresh`
- Category: `package_readiness`
- Command: `python scripts/check_challenge_cup_readiness.py`
- Human proof required: refreshed package files from the previous step
- counts_as_hard_evidence: `False`
- Expected after step: readiness gate reports the current package state
- Guardrail: A passing readiness gate is still package readiness, not award proof.
- does_not_claim_award_or_completion: `True`

### verify_submission_package

- Phase: `post_evidence_package_refresh`
- Category: `package_readiness`
- Command: `python docs/challenge_cup/reproducibility/verify_submission_package.py --root .`
- Human proof required: refreshed submission archive from the package rebuild step
- counts_as_hard_evidence: `False`
- Expected after step: submission package verifier passes against the refreshed archive
- Guardrail: Archive verification proves package integrity only; it does not close external evidence.
- does_not_claim_award_or_completion: `True`

### check_goal_completion_gate

- Phase: `post_evidence_package_refresh`
- Category: `goal_completion`
- Command: `python scripts/check_challenge_cup_goal_completion.py`
- Human proof required: archived hard evidence ledger and refreshed readiness report
- counts_as_hard_evidence: `False`
- Expected after step: goal-completion gate explicitly states whether completion is allowed
- Guardrail: Do not treat any previous step as proof unless goal completion explicitly passes.
- does_not_claim_award_or_completion: `True`

### refresh_final_audit

- Phase: `final_acceptance_refresh`
- Category: `final_audit`
- Command: `python scripts/build_challenge_cup_final_acceptance_audit.py`
- Human proof required: goal completion report and hard-evidence ledger from the refreshed package
- counts_as_hard_evidence: `False`
- Expected after step: final_acceptance_audit states whether package review or goal completion is allowed
- Guardrail: Final audit must preserve no-award-guarantee language even after hard evidence is collected.
- does_not_claim_award_or_completion: `True`


## Execution Packets

### expert_feedback_review

- Category: `expert_feedback`
- Owner: project lead + real external reviewer
- Handoff file: `docs/challenge_cup/reproducibility/external_evidence_execution_kit/expert_review_handoff.md`
- Acceptance gate: `hard_evidence_ledger.categories.expert_feedback.collected_count >= 1`
- Does not satisfy goal completion yet: `True`

Attachment files:
- `docs/challenge_cup/00_项目一页纸.md`
- `docs/challenge_cup/11_应用场景与专家验证.md`
- `docs/challenge_cup/22_同类方案对比与创新性证据卡.md`
- `docs/challenge_cup/reproducibility/application_validation_report.md`
- `docs/challenge_cup/reproducibility/expert_feedback_form.md`
- `docs/challenge_cup/reproducibility/expert_feedback_request_packet.md`
- `docs/challenge_cup/reproducibility/readiness_gate_report.md`

Source integrity guardrails:
- preflight and record commands calculate source_sha256 from the real source attachment
- metadata source_sha256 must match the archived source attachment content
- --source must be the original evidence attachment, not the generated .json metadata summary; the source attachment must be non-empty and must not be a JSON metadata file
- --source must not point inside docs/challenge_cup/reproducibility/hard_evidence/**; that directory is for archived intake outputs, not new source inputs
- hard_evidence_ledger rejects duplicate source_sha256 values within the same hard evidence category
- metadata already exists is treated as an input error unless --force is supplied intentionally with a non-empty --force-reason
- --force overwrites must append docs/challenge_cup/reproducibility/hard_evidence/override_log.jsonl with previous/new source and metadata sha256 values
- record_challenge_cup_expert_outreach.py rejects requested_attachment_paths that are unsafe, missing or empty
- do not edit or replace the source attachment after recording; changed bytes will fail readiness and goal gates

Recording commands:
- `python scripts/record_challenge_cup_expert_outreach.py --id real-outreach-id --source path/to/real-outreach-proof.eml --recipient-alias real-reviewer-alias --recipient-role real-reviewer-role --channel email --sent-date YYYY-MM-DD --status sent --requested-review-dimension practicality --requested-review-dimension innovation --requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/00_项目一页纸.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date YYYY-MM-DD --confirm-real-outreach`
- `python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id --source path/to/real-feedback.eml --evidence-type email_reply --reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org --review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue issue --remediation-action action --confirm-real-feedback`
- `python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id --source path/to/real-feedback.eml --evidence-type email_reply --reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org --review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue issue --remediation-action action --confirm-real-feedback`

Pre-hard-evidence PowerShell block:

```powershell
Set-Location 'D:\虚拟C盘\RAG'
$outreachId = 'outreach-YYYYMMDD-01'
$outreachSource = 'D:\path\to\real-outreach-proof.eml'
$sentDate = 'YYYY-MM-DD'
$followupDueDate = 'YYYY-MM-DD'
$reviewer = 'real-reviewer-alias'
$reviewerRole = 'real-reviewer-role'
.\.venv\Scripts\python.exe .\scripts\record_challenge_cup_expert_outreach.py --id $outreachId --source $outreachSource --recipient-alias $reviewer --recipient-role $reviewerRole --channel email --sent-date $sentDate --status sent --requested-review-dimension practicality --requested-review-dimension innovation --requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/00_椤圭洰涓€椤电焊.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date $followupDueDate --confirm-real-outreach
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

PowerShell execution block:

```powershell
Set-Location 'D:\虚拟C盘\RAG'
$feedbackId = 'advisor-a-YYYYMMDD-01'
$feedbackSource = 'D:\path\to\real-feedback.eml'
$reviewDate = 'YYYY-MM-DD'
$reviewer = 'real-reviewer-identity'
$reviewerRole = 'real-reviewer-role-or-org'
$remediationIssue = 'demo-pacing'
$remediationAction = 'tighten-opening'
.\.venv\Scripts\python.exe .\scripts\preflight_challenge_cup_hard_evidence.py expert_feedback --id $feedbackId --source $feedbackSource --evidence-type email_reply --reviewer-identity $reviewer --role-or-org $reviewerRole --review-date $reviewDate --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue $remediationIssue --remediation-action $remediationAction --confirm-real-feedback
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
.\.venv\Scripts\python.exe .\scripts\record_challenge_cup_hard_evidence.py expert_feedback --id $feedbackId --source $feedbackSource --evidence-type email_reply --reviewer-identity $reviewer --role-or-org $reviewerRole --review-date $reviewDate --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue $remediationIssue --remediation-action $remediationAction --confirm-real-feedback
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

### timed_rehearsal_observer

- Category: `timed_rehearsal`
- Owner: presenter + real observer
- Handoff file: `docs/challenge_cup/reproducibility/external_evidence_execution_kit/timed_rehearsal_observer_sheet.md`
- Acceptance gate: `hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1`
- Does not satisfy goal completion yet: `True`

Attachment files:
- `docs/challenge_cup/04_系统演示脚本.md`
- `docs/challenge_cup/05_答辩问答手册.md`
- `docs/challenge_cup/10_答辩攻防与彩排卡.md`
- `docs/challenge_cup/14_现场答辩操作Runbook.md`
- `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`
- `docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md`
- `docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md`
- `docs/challenge_cup/reproducibility/final_acceptance_audit.md`

Source integrity guardrails:
- preflight and record commands calculate source_sha256 from the real source attachment
- metadata source_sha256 must match the archived source attachment content
- --source must be the original evidence attachment, not the generated .json metadata summary; the source attachment must be non-empty and must not be a JSON metadata file
- --source must not point inside docs/challenge_cup/reproducibility/hard_evidence/**; that directory is for archived intake outputs, not new source inputs
- hard_evidence_ledger rejects duplicate source_sha256 values within the same hard evidence category
- metadata already exists is treated as an input error unless --force is supplied intentionally with a non-empty --force-reason
- --force overwrites must append docs/challenge_cup/reproducibility/hard_evidence/override_log.jsonl with previous/new source and metadata sha256 values
- record_challenge_cup_expert_outreach.py rejects requested_attachment_paths that are unsafe, missing or empty
- do not edit or replace the source attachment after recording; changed bytes will fail readiness and goal gates

Recording commands:
- `python scripts/record_challenge_cup_timed_rehearsal_schedule.py --id real-rehearsal-schedule-id --source path/to/real-calendar-or-observer-prep-file.txt --scheduled-date YYYY-MM-DD --observer real-observer-alias --venue-or-channel real-venue-or-channel --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible --checklist-item browser-smoke-opened --checklist-item offline-archive-ready --checklist-item five-killer-questions-assigned --confirm-real-schedule`
- `python scripts/run_challenge_cup_timed_rehearsal.py --id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal`
- `python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal --id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --evidence-type observer_note --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal`
- `python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal --id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --evidence-type observer_note --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal`

Pre-hard-evidence PowerShell block:

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

PowerShell execution block:

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

Failed rehearsal archival rule:
- If any measured rehearsal segment exceeds the limit or a required killer-question timing is missing, still archive the real rehearsal evidence with timing_acceptance_pass=false; the hard evidence ledger must place the metadata in rejected_metadata_records and collected_count must not satisfy the acceptance gate.

## Verification Commands

- `python scripts/build_challenge_cup_external_evidence_execution_kit.py`
- `python scripts/build_challenge_cup_hard_evidence_ledger.py`
- `python scripts/build_challenge_cup_package.py`
- `python scripts/check_challenge_cup_readiness.py`
- `python scripts/check_challenge_cup_goal_completion.py`
- `python scripts/build_challenge_cup_final_acceptance_audit.py`
