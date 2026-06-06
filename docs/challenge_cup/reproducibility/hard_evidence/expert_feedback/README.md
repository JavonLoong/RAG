# Expert Feedback Evidence

放入真实专家反馈证据：签字页、邮件回复、会议纪要或聊天截图。
每份证据应能看到 reviewer identity、role/org、date、review dimensions 和 remediation record。
Required JSON fields: evidence_type, reviewer_identity, role_or_org, review_date, feedback_source_path, review_dimensions, remediation_record, real_feedback_confirmed.
Use YYYY-MM-DD for review_date. feedback_source_path must point to the real source attachment, not the JSON summary itself.
Preflight CLI: `python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id <real-feedback-id> --source <real-feedback-file> --evidence-type email_reply --reviewer-identity <real-reviewer-identity> --role-or-org <real-reviewer-role-or-org> --review-date <real-review-date-yyyy-mm-dd> --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback`.
Recommended CLI: `python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id <real-feedback-id> --source <real-feedback-file> --evidence-type email_reply --reviewer-identity <real-reviewer-identity> --role-or-org <real-reviewer-role-or-org> --review-date <real-review-date-yyyy-mm-dd> --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue <issue> --remediation-action <action> --confirm-real-feedback`.
