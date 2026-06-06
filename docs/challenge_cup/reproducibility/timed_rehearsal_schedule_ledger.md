# Timed Rehearsal Schedule Ledger

- report_type: `challenge_cup_timed_rehearsal_schedule_ledger`
- status: `ready_to_schedule_no_rehearsal_recorded`
- no_timed_rehearsal_claimed: `True`
- does_not_satisfy_goal_completion: `True`
- boundary: Schedule records prove that a real timed rehearsal was scheduled or observer preparation was recorded. They do not prove a timed rehearsal was completed and do not satisfy the timed_rehearsal hard-evidence requirement.
- schedule_record_count: `0`
- metadata_record_count: `0`

## Schedule Files

- No real timed rehearsal schedule has been recorded yet.

## Required Next Step

After the timed rehearsal is actually run, archive measured seconds and observer evidence with run_challenge_cup_timed_rehearsal.py --confirm-real-rehearsal or record_challenge_cup_hard_evidence.py timed_rehearsal ... --confirm-real-rehearsal.

## Rerun Commands

- `python scripts/build_challenge_cup_timed_rehearsal_schedule_ledger.py`
- `python scripts/build_challenge_cup_package.py`
- `python scripts/check_challenge_cup_readiness.py`
