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
- Expected after step: readiness gate reports pass 62/62
- Guardrail: A passing package gate is not expert approval, timed rehearsal completion, or award proof.
- does_not_claim_award_or_completion: `True`

### record_expert_outreach

- Phase: `expert_feedback_outreach`
- Category: `expert_feedback`
- Command: `python scripts/record_challenge_cup_expert_outreach.py --id advisor-a-20260606 --source <real-outreach-proof> --recipient-alias advisor-a --recipient-role advisor --channel email --sent-date 2026-06-06 --status sent --requested-review-dimension practicality --requested-review-dimension innovation --requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/reproducibility/final_acceptance_audit.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date 2026-06-09 --confirm-real-outreach`
- Human proof required: real sent email, chat message, meeting notice, or follow-up screenshot
- counts_as_hard_evidence: `False`
- Expected after step: expert_feedback_outreach_ledger records the outreach but hard_evidence_ledger remains open
- Guardrail: Outreach proves a request was sent; it does not prove expert feedback was received.
- does_not_claim_award_or_completion: `True`

### record_rehearsal_schedule

- Phase: `timed_rehearsal_scheduling`
- Category: `timed_rehearsal`
- Command: `python scripts/record_challenge_cup_timed_rehearsal_schedule.py --id rehearsal-schedule-20260606 --source <real-calendar-or-observer-prep-file> --scheduled-date 2026-06-06 --observer observer-a --venue-or-channel meeting-room-a --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible --checklist-item browser-smoke-opened --checklist-item offline-archive-ready --checklist-item five-killer-questions-assigned --confirm-real-schedule`
- Human proof required: real calendar invite, meeting notice, or observer preparation record
- counts_as_hard_evidence: `False`
- Expected after step: timed_rehearsal_schedule_ledger records the schedule but timed_rehearsal evidence remains open
- Guardrail: A schedule proves intent to rehearse; it does not prove a timed rehearsal happened.
- does_not_claim_award_or_completion: `True`

### preflight_expert_feedback

- Phase: `expert_feedback_validation`
- Category: `expert_feedback`
- Command: `python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id advisor-a --source <real-feedback-file> --evidence-type email_reply --reviewer-identity advisor-a --role-or-org advisor --review-date 2026-06-06 --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback`
- Human proof required: real signed form, email reply, meeting minutes, or chat screenshot from reviewer
- counts_as_hard_evidence: `False`
- Expected after step: preflight returns pass and does not write hard evidence
- Guardrail: Preflight is a dry run; only record_challenge_cup_hard_evidence.py archives evidence.
- does_not_claim_award_or_completion: `True`

### record_expert_feedback

- Phase: `expert_feedback_archival`
- Category: `expert_feedback`
- Command: `python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id advisor-a --source <real-feedback-file> --evidence-type email_reply --reviewer-identity advisor-a --role-or-org advisor --review-date 2026-06-06 --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback`
- Human proof required: same real reviewer feedback source that passed preflight
- counts_as_hard_evidence: `True`
- Expected after step: hard_evidence_ledger.categories.expert_feedback.collected_count >= 1
- Guardrail: Records feedback evidence only; it still does not guarantee an award.
- does_not_claim_award_or_completion: `True`

### run_timed_rehearsal

- Phase: `timed_rehearsal_archival`
- Category: `timed_rehearsal`
- Command: `python scripts/run_challenge_cup_timed_rehearsal.py --id rehearsal-1 --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal`
- Human proof required: actual observed rehearsal timings from a visible timer or observer note
- counts_as_hard_evidence: `True`
- Expected after step: hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1
- Guardrail: Measured rehearsal timing supports defense readiness; it is not expert approval or award proof.
- does_not_claim_award_or_completion: `True`

### rebuild_package_and_gates

- Phase: `post_evidence_package_refresh`
- Category: `package_readiness`
- Command: `python scripts/build_challenge_cup_package.py && python scripts/check_challenge_cup_readiness.py && python docs/challenge_cup/reproducibility/verify_submission_package.py --root . && python scripts/check_challenge_cup_goal_completion.py`
- Human proof required: archived expert feedback and archived timed rehearsal evidence are already present
- counts_as_hard_evidence: `False`
- Expected after step: package, readiness, archive verifier, and goal-completion gate reflect the new evidence
- Guardrail: Do not treat rebuild success as proof unless goal completion explicitly passes.
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

Recording commands:
- `python scripts/record_challenge_cup_expert_outreach.py --id advisor-a-20260606 --source <real-outreach-proof> --recipient-alias advisor-a --recipient-role advisor --channel email --sent-date 2026-06-06 --status sent --requested-review-dimension practicality --requested-review-dimension innovation --requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/00_项目一页纸.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date 2026-06-09 --confirm-real-outreach`
- `python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id advisor-a --source <real-feedback-file> --evidence-type email_reply --reviewer-identity advisor-a --role-or-org advisor --review-date 2026-06-06 --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback`
- `python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id advisor-a --source <real-feedback-file> --evidence-type email_reply --reviewer-identity advisor-a --role-or-org advisor --review-date 2026-06-06 --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback`

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

Recording commands:
- `python scripts/record_challenge_cup_timed_rehearsal_schedule.py --id rehearsal-schedule-20260606 --source <real-calendar-or-observer-prep-file> --scheduled-date 2026-06-06 --observer observer-a --venue-or-channel meeting-room-a --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible --checklist-item browser-smoke-opened --checklist-item offline-archive-ready --checklist-item five-killer-questions-assigned --confirm-real-schedule`
- `python scripts/run_challenge_cup_timed_rehearsal.py --id rehearsal-1 --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal`
- `python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal --id rehearsal-1 --source <real-timer-or-observer-file> --evidence-type observer_note --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal`
- `python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal --id rehearsal-1 --source <real-timer-or-observer-file> --evidence-type observer_note --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal`

## Verification Commands

- `python scripts/build_challenge_cup_external_evidence_execution_kit.py`
- `python scripts/build_challenge_cup_hard_evidence_ledger.py`
- `python scripts/build_challenge_cup_package.py`
- `python scripts/check_challenge_cup_readiness.py`
- `python scripts/check_challenge_cup_goal_completion.py`
- `python scripts/build_challenge_cup_final_acceptance_audit.py`
