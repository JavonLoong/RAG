# Timed Rehearsal Schedule Intake

This directory records real timed-rehearsal scheduling and observer-preparation records.
Schedule records prove that a real timed rehearsal was scheduled or observer preparation was recorded. They do not prove a timed rehearsal was completed and do not satisfy the timed_rehearsal hard-evidence requirement.

- Use `python scripts/record_challenge_cup_timed_rehearsal_schedule.py ... --confirm-real-schedule` after a real calendar invite, meeting notice, or observer preparation note exists.
- Keep the calendar invite, meeting notice, chat confirmation, or observer checklist as the source attachment.
- Do not count schedule records as timed rehearsal completion. A real run must be archived with `python scripts/run_challenge_cup_timed_rehearsal.py ... --confirm-real-rehearsal` or `python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal ... --confirm-real-rehearsal`.
