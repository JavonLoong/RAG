# External Hard Evidence Action Pack

- report_type: `challenge_cup_hard_evidence_action_pack`
- status: `ready_for_real_external_evidence_collection`
- completion_claim_allowed: `False`
- does_not_satisfy_goal_completion=True
- operator_outcome: package can be reviewed; goal cannot be closed
- boundary: This action pack is a human handoff for collecting real external hard evidence. It does not satisfy goal completion, does not claim expert approval, and does not claim a timed rehearsal has been completed.

## Integrity Rules

- 不伪造专家意见
- 不伪造计时彩排
- schedule or outreach records do not satisfy hard evidence until real feedback/rehearsal proof is archived

## Human Handoff Streams

### expert_feedback

- Human owner: project lead + external reviewer
- Human action: Send the prepared review packet to a real advisor, domain expert, or engineering reviewer; request signed comments, email reply, meeting minutes, or chat feedback against the listed dimensions.
- Acceptance gate: `hard_evidence_ledger.categories.expert_feedback.collected_count >= 1`
- Does not satisfy goal completion yet: `True`

Proof to collect:
- real outbound proof
- reviewer identity and role
- signed feedback form, email reply, meeting minutes, or chat screenshot
- remediation issue and action after feedback

Source integrity guardrails:
- preflight and record commands calculate source_sha256 from the real source attachment
- metadata source_sha256 must match the archived source attachment content
- --source must be the original evidence attachment, not the generated .json metadata summary; the source attachment must be non-empty and must not be a JSON metadata file
- do not edit or replace the source attachment after recording; changed bytes will fail readiness and goal gates

Ready packet files:
- `docs/challenge_cup/00_项目一页纸.md`
- `docs/challenge_cup/11_应用场景与专家验证.md`
- `docs/challenge_cup/reproducibility/expert_feedback_form.md`
- `docs/challenge_cup/reproducibility/expert_feedback_request_packet.md`
- `docs/challenge_cup/reproducibility/final_acceptance_audit.md`

Recording commands:
- `python scripts/record_challenge_cup_expert_outreach.py --id real-outreach-id --source path/to/real-outreach-proof.eml --recipient-alias real-reviewer-alias --recipient-role real-reviewer-role --channel email --sent-date YYYY-MM-DD --status sent --requested-review-dimension practicality --requested-review-dimension innovation --requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/00_项目一页纸.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date YYYY-MM-DD --confirm-real-outreach`
- `python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id --source path/to/real-feedback.eml --evidence-type email_reply --reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org --review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue issue --remediation-action action --confirm-real-feedback`
- `python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id --source path/to/real-feedback.eml --evidence-type email_reply --reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org --review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue issue --remediation-action action --confirm-real-feedback`

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

### timed_rehearsal

- Human owner: presenter + observer
- Human action: Schedule and run a real timed defense rehearsal with an observer, visible timer, offline backup check, and five killer questions; archive measured timings and missed evidence anchors.
- Acceptance gate: `hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1`
- Does not satisfy goal completion yet: `True`

Proof to collect:
- real schedule or observer preparation proof
- timer screenshot or screen recording
- observer note
- five killer-question timings and missed-question list

Source integrity guardrails:
- preflight and record commands calculate source_sha256 from the real source attachment
- metadata source_sha256 must match the archived source attachment content
- --source must be the original evidence attachment, not the generated .json metadata summary; the source attachment must be non-empty and must not be a JSON metadata file
- do not edit or replace the source attachment after recording; changed bytes will fail readiness and goal gates

Ready packet files:
- `docs/challenge_cup/04_系统演示脚本.md`
- `docs/challenge_cup/05_答辩问答手册.md`
- `docs/challenge_cup/10_答辩攻防与彩排卡.md`
- `docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md`
- `docs/challenge_cup/reproducibility/final_acceptance_audit.md`

Recording commands:
- `python scripts/record_challenge_cup_timed_rehearsal_schedule.py --id real-rehearsal-schedule-id --source path/to/real-calendar-or-observer-prep-file.txt --scheduled-date YYYY-MM-DD --observer real-observer-alias --venue-or-channel real-venue-or-channel --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible --checklist-item browser-smoke-opened --checklist-item offline-archive-ready --checklist-item five-killer-questions-assigned --confirm-real-schedule`
- `python scripts/run_challenge_cup_timed_rehearsal.py --id real-rehearsal-id --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds actual-opening-seconds --demo-actual-seconds actual-demo-seconds --offline-fallback-actual-seconds actual-offline-fallback-seconds --killer-question-seconds q1-seconds q2-seconds q3-seconds q4-seconds q5-seconds --confirm-real-rehearsal`
- `python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal --id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --evidence-type observer_note --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds actual-opening-seconds --demo-actual-seconds actual-demo-seconds --offline-fallback-actual-seconds actual-offline-fallback-seconds --killer-question-seconds q1-seconds q2-seconds q3-seconds q4-seconds q5-seconds --confirm-real-rehearsal`
- `python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal --id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --evidence-type observer_note --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds actual-opening-seconds --demo-actual-seconds actual-demo-seconds --offline-fallback-actual-seconds actual-offline-fallback-seconds --killer-question-seconds q1-seconds q2-seconds q3-seconds q4-seconds q5-seconds --confirm-real-rehearsal`

PowerShell execution block:

```powershell
Set-Location 'D:\虚拟C盘\RAG'
$rehearsalId = 'rehearsal-YYYYMMDD-01'
$rehearsalDate = 'YYYY-MM-DD'
$observer = 'real-observer-alias'
$opening = 88
$demo = 170
$offline = 18
$killer = 25,25,25,25,25
.\.venv\Scripts\python.exe .\scripts\run_challenge_cup_timed_rehearsal.py --id $rehearsalId --rehearsal-date $rehearsalDate --observer $observer --opening-actual-seconds $opening --demo-actual-seconds $demo --offline-fallback-actual-seconds $offline --killer-question-seconds $killer --confirm-real-rehearsal
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

Failed rehearsal archival rule:
- If any measured rehearsal segment exceeds the limit or a required killer-question timing is missing, still archive the real rehearsal evidence with timing_acceptance_pass=false; the hard evidence ledger must place the metadata in rejected_metadata_records and collected_count must not satisfy the acceptance gate.

## Verification Commands

- `python scripts/build_challenge_cup_hard_evidence_ledger.py`
- `python scripts/build_challenge_cup_package.py`
- `python scripts/check_challenge_cup_readiness.py`
- `python scripts/check_challenge_cup_goal_completion.py`
- `python scripts/build_challenge_cup_final_acceptance_audit.py`
