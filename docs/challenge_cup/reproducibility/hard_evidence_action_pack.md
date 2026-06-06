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

Ready packet files:
- `docs/challenge_cup/00_项目一页纸.md`
- `docs/challenge_cup/11_应用场景与专家验证.md`
- `docs/challenge_cup/reproducibility/expert_feedback_form.md`
- `docs/challenge_cup/reproducibility/expert_feedback_request_packet.md`
- `docs/challenge_cup/reproducibility/final_acceptance_audit.md`

Recording commands:
- `python scripts/record_challenge_cup_expert_outreach.py --id advisor-a-20260606 --source <real-outreach-proof> --recipient-alias advisor-a --recipient-role advisor --channel email --sent-date 2026-06-06 --status sent --requested-review-dimension practicality --requested-review-dimension innovation --requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/00_项目一页纸.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date 2026-06-09 --confirm-real-outreach`
- `python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id advisor-a --source <real-feedback-file> --evidence-type email_reply --reviewer-identity advisor-a --role-or-org advisor --review-date 2026-06-06 --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action>`

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

Ready packet files:
- `docs/challenge_cup/04_系统演示脚本.md`
- `docs/challenge_cup/05_答辩问答手册.md`
- `docs/challenge_cup/10_答辩攻防与彩排卡.md`
- `docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md`
- `docs/challenge_cup/reproducibility/final_acceptance_audit.md`

Recording commands:
- `python scripts/record_challenge_cup_timed_rehearsal_schedule.py --id rehearsal-schedule-20260606 --source <real-calendar-or-observer-prep-file> --scheduled-date 2026-06-06 --observer observer-a --venue-or-channel meeting-room-a --status scheduled --opening-planned-seconds 90 --demo-planned-seconds 180 --offline-fallback-planned-seconds 20 --killer-question-planned-seconds 30 --killer-question-count 5 --checklist-item timer-visible --checklist-item browser-smoke-opened --checklist-item offline-archive-ready --checklist-item five-killer-questions-assigned --confirm-real-schedule`
- `python scripts/run_challenge_cup_timed_rehearsal.py --id rehearsal-1 --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal`
- `python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal --id rehearsal-1 --source <real-timer-or-observer-file> --evidence-type observer_note --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29`

## Verification Commands

- `python scripts/build_challenge_cup_hard_evidence_ledger.py`
- `python scripts/build_challenge_cup_package.py`
- `python scripts/check_challenge_cup_readiness.py`
- `python scripts/check_challenge_cup_goal_completion.py`
- `python scripts/build_challenge_cup_final_acceptance_audit.py`
