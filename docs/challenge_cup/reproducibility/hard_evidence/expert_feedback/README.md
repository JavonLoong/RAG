# Expert Feedback Evidence

放入真实专家反馈证据：签字页、邮件回复、会议纪要或聊天截图。
每份证据应能看到 reviewer identity、role/org、date、review dimensions 和 remediation record。
Required JSON fields: evidence_type, reviewer_identity, role_or_org, review_date, feedback_source_path, review_dimensions, remediation_record, real_feedback_confirmed.
Use YYYY-MM-DD for review_date. feedback_source_path must point to the real source attachment, not the JSON summary itself.
Preflight CLI: `python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id advisor-a --source <real-feedback-file> --evidence-type email_reply --reviewer-identity advisor-a --role-or-org advisor --review-date 2026-06-06 --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue demo-pacing --remediation-action tighten-opening --confirm-real-feedback`.
Recommended CLI: `python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id advisor-a --source <real-feedback-file> --evidence-type email_reply --reviewer-identity advisor-a --role-or-org advisor --review-date 2026-06-06 --review-dimension 实用性 --review-dimension 创新性 --review-dimension 边界严谨性 --remediation-issue 演示节奏 --remediation-action 压缩开场 --confirm-real-feedback`.
