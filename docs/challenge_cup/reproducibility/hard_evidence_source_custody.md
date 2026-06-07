# Hard Evidence Source Custody

- report_type: `challenge_cup_hard_evidence_source_custody`
- status: `ready_for_real_source_custody_no_external_evidence_claim`
- completion_claim_allowed: `False`
- does_not_satisfy_goal_completion=True
- boundary: Source custody preflight only: this pack does not satisfy goal completion, does not claim expert approval, does not claim a timed rehearsal was completed, and provides no award guarantee.

## Integrity Guardrails

- do not fabricate evidence or create placeholder hard evidence attachments
- do not claim expert approval before source archival and hard_evidence_ledger rebuild
- do not claim a timed rehearsal before source archival and hard_evidence_ledger rebuild
- no award guarantee is created by this source custody pack, readiness gate, or verifier
- source_sha256 must be calculated from the original source attachment before and after archival
- override_log.jsonl is mandatory for intentional replacement of archived metadata or source copies

## expert_feedback

- source_role: real reviewer signed form, email reply, meeting minutes, or chat screenshot
- counts_as_hard_evidence_after_record_only: `True`
- does_not_satisfy_goal_completion_before_record: `True`

### Source Restrictions

- the source must be the original evidence attachment received from the reviewer, observer, timer, or meeting record
- the source attachment must be non-empty before preflight and before record
- the source attachment must not be a JSON metadata file
- --source must not point inside docs/challenge_cup/reproducibility/hard_evidence/**; that tree is for archived intake outputs
- duplicate source_sha256 values within a hard evidence category must be rejected by the ledger
- --force is allowed only for a deliberate correction and must include a non-empty --force-reason
- every --force overwrite must append docs/challenge_cup/reproducibility/hard_evidence/override_log.jsonl with previous and new source_sha256 values

### Custody Checkpoints

| ID | State | Command | Acceptance Signal |
| --- | --- | --- | --- |
| `source_received` | external source exists outside archived hard_evidence intake | `manual source receipt check before running preflight` | source file path, source owner, source date, and source type are known |
| `source_sha256_preflighted` | source hash calculated without writing intake files | `python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id --source path/to/original-real-feedback.eml --evidence-type email_reply --reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org --review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue issue --remediation-action action --confirm-real-feedback` | preflight status=pass and source_sha256 is recorded for the original source attachment |
| `record_command_archives_source` | source copied into the hard_evidence intake tree by the record command | `python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id --source path/to/original-real-feedback.eml --evidence-type email_reply --reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org --review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue issue --remediation-action action --confirm-real-feedback` | hard_evidence metadata for expert_feedback records source_origin=external_attachment and matching source_sha256 |
| `ledger_rebuilt` | hard evidence ledger rebuilt from archived intake files | `python scripts/build_challenge_cup_hard_evidence_ledger.py` | hard_evidence_ledger.categories.expert_feedback reflects the recorded source status |
| `package_rebuilt` | package manifests and archive regenerated after source archival | `python scripts/build_challenge_cup_package.py` | package_manifest.json, evidence_hashes.json, and challenge_cup_submission_archive_manifest.json are refreshed |
| `submission_verifier_rerun` | submission archive verified after package rebuild | `python docs/challenge_cup/reproducibility/verify_submission_package.py --root .` | submission package verifier reports Status: pass |
| `readiness_gate_rerun` | readiness gate rerun after package rebuild | `python scripts/check_challenge_cup_readiness.py` | readiness gate reports Status: pass for the current gate count |
| `goal_gate_rerun` | goal completion decision made only by the goal gate | `python scripts/check_challenge_cup_goal_completion.py` | goal_completion_report.md explicitly states whether completion_claim_allowed is True or False |

### Operator Commands

- `python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id --source path/to/original-real-feedback.eml --evidence-type email_reply --reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org --review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue issue --remediation-action action --confirm-real-feedback`
- `python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id --source path/to/original-real-feedback.eml --evidence-type email_reply --reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org --review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue issue --remediation-action action --confirm-real-feedback`
- `python scripts/build_challenge_cup_hard_evidence_ledger.py`
- `python scripts/build_challenge_cup_package.py`
- `python docs/challenge_cup/reproducibility/verify_submission_package.py --root .`
- `python scripts/check_challenge_cup_readiness.py`
- `python scripts/check_challenge_cup_goal_completion.py`

## timed_rehearsal

- source_role: real timer screenshot, screen recording, observer note, or missed-question list
- counts_as_hard_evidence_after_record_only: `True`
- does_not_satisfy_goal_completion_before_record: `True`

### Source Restrictions

- the source must be the original evidence attachment received from the reviewer, observer, timer, or meeting record
- the source attachment must be non-empty before preflight and before record
- the source attachment must not be a JSON metadata file
- --source must not point inside docs/challenge_cup/reproducibility/hard_evidence/**; that tree is for archived intake outputs
- duplicate source_sha256 values within a hard evidence category must be rejected by the ledger
- --force is allowed only for a deliberate correction and must include a non-empty --force-reason
- every --force overwrite must append docs/challenge_cup/reproducibility/hard_evidence/override_log.jsonl with previous and new source_sha256 values

### Custody Checkpoints

| ID | State | Command | Acceptance Signal |
| --- | --- | --- | --- |
| `source_received` | external source exists outside archived hard_evidence intake | `manual source receipt check before running preflight` | source file path, source owner, source date, and source type are known |
| `source_sha256_preflighted` | source hash calculated without writing intake files | `python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal --id real-rehearsal-id --source path/to/original-real-timer-or-observer-file.txt --evidence-type observer_note --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal` | preflight status=pass and source_sha256 is recorded for the original source attachment |
| `record_command_archives_source` | source copied into the hard_evidence intake tree by the record command | `python scripts/run_challenge_cup_timed_rehearsal.py --id real-rehearsal-id --source path/to/original-real-timer-or-observer-file.txt --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal` | hard_evidence metadata for timed_rehearsal records source_origin=external_attachment and matching source_sha256 |
| `ledger_rebuilt` | hard evidence ledger rebuilt from archived intake files | `python scripts/build_challenge_cup_hard_evidence_ledger.py` | hard_evidence_ledger.categories.timed_rehearsal reflects the recorded source status |
| `package_rebuilt` | package manifests and archive regenerated after source archival | `python scripts/build_challenge_cup_package.py` | package_manifest.json, evidence_hashes.json, and challenge_cup_submission_archive_manifest.json are refreshed |
| `submission_verifier_rerun` | submission archive verified after package rebuild | `python docs/challenge_cup/reproducibility/verify_submission_package.py --root .` | submission package verifier reports Status: pass |
| `readiness_gate_rerun` | readiness gate rerun after package rebuild | `python scripts/check_challenge_cup_readiness.py` | readiness gate reports Status: pass for the current gate count |
| `goal_gate_rerun` | goal completion decision made only by the goal gate | `python scripts/check_challenge_cup_goal_completion.py` | goal_completion_report.md explicitly states whether completion_claim_allowed is True or False |

### Operator Commands

- `python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal --id real-rehearsal-id --source path/to/original-real-timer-or-observer-file.txt --evidence-type observer_note --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal`
- `python scripts/run_challenge_cup_timed_rehearsal.py --id real-rehearsal-id --source path/to/original-real-timer-or-observer-file.txt --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal`
- `python scripts/build_challenge_cup_hard_evidence_ledger.py`
- `python scripts/build_challenge_cup_package.py`
- `python docs/challenge_cup/reproducibility/verify_submission_package.py --root .`
- `python scripts/check_challenge_cup_readiness.py`
- `python scripts/check_challenge_cup_goal_completion.py`
