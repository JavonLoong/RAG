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

## Source Integrity Guardrails

- preflight and record commands calculate source_sha256 from the real source attachment
- metadata source_sha256 must match the archived source attachment content
- do not edit or replace the source attachment after recording; changed bytes will fail readiness and goal gates

## Recording Commands

- `python scripts/record_challenge_cup_expert_outreach.py --id <real-outreach-id> --source <real-outreach-proof> --recipient-alias <real-reviewer-alias> --recipient-role <real-reviewer-role> --channel email --sent-date <real-sent-date-yyyy-mm-dd> --status sent --requested-review-dimension practicality --requested-review-dimension innovation --requested-review-dimension boundary_rigor --requested-attachment docs/challenge_cup/00_项目一页纸.md --requested-attachment docs/challenge_cup/reproducibility/expert_feedback_form.md --followup-due-date <real-followup-due-date-yyyy-mm-dd> --confirm-real-outreach`
- `python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id <real-feedback-id> --source <real-feedback-file> --evidence-type email_reply --reviewer-identity <real-reviewer-identity> --role-or-org <real-reviewer-role-or-org> --review-date <real-review-date-yyyy-mm-dd> --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback`
- `python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id <real-feedback-id> --source <real-feedback-file> --evidence-type email_reply --reviewer-identity <real-reviewer-identity> --role-or-org <real-reviewer-role-or-org> --review-date <real-review-date-yyyy-mm-dd> --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback`
