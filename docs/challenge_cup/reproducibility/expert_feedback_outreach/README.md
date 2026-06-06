# Expert Feedback Outreach Intake

This directory records real outbound expert-feedback requests and follow-ups.
Outreach records prove that a real request was sent or followed up. They do not prove expert approval and do not satisfy the expert_feedback hard-evidence requirement.

- Use `python scripts/record_challenge_cup_expert_outreach.py ... --confirm-real-outreach` after a real send or follow-up.
- Keep the sent email receipt, chat record, meeting invite, or follow-up note as the source attachment.
- The source attachment must be non-empty, must not be a JSON metadata file, and will be stored with source_sha256.
- Do not count outreach as expert feedback. A real response must be archived with `python scripts/record_challenge_cup_hard_evidence.py expert_feedback ... --confirm-real-feedback`.
