# expert_feedback_review Handoff

- hard_evidence_category: `expert_feedback`
- owner: project lead + real external reviewer
- acceptance_gate: `hard_evidence_ledger.categories.expert_feedback.collected_count >= 1`
- does_not_satisfy_goal_completion: `True`

## Integrity Boundary

不伪造真实专家反馈；不伪造真实计时彩排；未归档真实硬证据前不能标记目标完成。

## Attachment Files

- `docs/challenge_cup/00_项目一页纸.md`
- `docs/challenge_cup/11_应用场景与专家验证.md`
- `docs/challenge_cup/22_同类方案对比与创新性证据卡.md`
- `docs/challenge_cup/reproducibility/application_validation_report.md`
- `docs/challenge_cup/reproducibility/expert_feedback_form.md`
- `docs/challenge_cup/reproducibility/expert_feedback_request_packet.md`
- `docs/challenge_cup/reproducibility/readiness_gate_report.md`

## Execution Steps

- Send the handoff file and attachments to a real advisor, domain expert, or engineering reviewer.
- Ask the reviewer to comment on practicality, innovation, evidence quality, defense clarity, and boundaries.
- Archive the original signed form, email reply, meeting minutes, or chat screenshot before claiming feedback.
- Record at least one remediation issue and action after receiving the real feedback.

## Done When

- a real reviewer identity and role are recorded
- a real feedback source file is archived
- record_challenge_cup_hard_evidence.py expert_feedback records metadata, source path, and --confirm-real-feedback
- hard_evidence_ledger.categories.expert_feedback.collected_count >= 1

## Recording Commands

- `python scripts/record_challenge_cup_expert_outreach.py --id advisor-a-20260606 --source <real-outreach-proof> --recipient-alias advisor-a --recipient-role advisor --channel email --sent-date 2026-06-06 --status sent --requested-review-dimension practicality --requested-review-dimension innovation --requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/00_项目一页纸.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date 2026-06-09 --confirm-real-outreach`
- `python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id advisor-a --source <real-feedback-file> --evidence-type email_reply --reviewer-identity advisor-a --role-or-org advisor --review-date 2026-06-06 --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback`
