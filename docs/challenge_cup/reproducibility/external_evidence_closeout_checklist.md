# External Evidence Closeout Checklist

- report_type: `challenge_cup_external_evidence_closeout_checklist`
- status: `ready_for_real_external_evidence_closeout`
- completion_claim_allowed: `False`
- does_not_satisfy_goal_completion=True
- day-of closeout owner: project lead
- boundary: Day-of closeout support only: this checklist does not satisfy goal completion, does not claim expert approval, does not claim a timed rehearsal was completed, and provides no award guarantee.

## Integrity Rules

- real expert feedback must come from a real reviewer source attachment
- real timed rehearsal must come from a real timer or observer attachment
- source_sha256 and source_origin=external_attachment are required for hard evidence closure
- goal completion can pass only after both categories are archived and the goal gate passes
- no award guarantee is made by this checklist or by any local gate

## Day-Of Closeout Items

| ID | Phase | Evidence | Counts As Hard Evidence | Command | Acceptance Signal |
| --- | --- | --- | --- | --- | --- |
| `package_preflight_clean` | before_external_execution | package_readiness | `False` | `python scripts/check_challenge_cup_readiness.py` | docs/challenge_cup/reproducibility/readiness_gate_report.md contains Status: `pass` and Passed: 64/64 |
| `expert_feedback_source_ready` | expert_feedback_preflight | expert_feedback | `False` | `python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id --source path/to/real-feedback.eml --evidence-type email_reply --reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org --review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue issue --remediation-action action --confirm-real-feedback` | preflight returns status=pass and reports source_sha256 for the real feedback attachment |
| `expert_feedback_archived` | expert_feedback_archival | expert_feedback | `True` | `python scripts/record_challenge_cup_hard_evidence.py expert_feedback --id real-feedback-id --source path/to/real-feedback.eml --evidence-type email_reply --reviewer-identity real-reviewer-identity --role-or-org real-reviewer-role-or-org --review-date YYYY-MM-DD --review-dimension practicality --review-dimension innovation --review-dimension boundary_rigor --remediation-issue issue --remediation-action action --confirm-real-feedback` | metadata has real_feedback_confirmed=true, source_origin=external_attachment, source_sha256, reviewer identity, dimensions, and remediation record |
| `timed_rehearsal_source_ready` | timed_rehearsal_preflight | timed_rehearsal | `False` | `python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal --id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --evidence-type observer_note --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal` | preflight returns status=pass and reports source_sha256 for the real timed rehearsal attachment |
| `timed_rehearsal_archived` | timed_rehearsal_archival | timed_rehearsal | `True` | `python scripts/run_challenge_cup_timed_rehearsal.py --id real-rehearsal-id --source path/to/real-timer-or-observer-file.txt --rehearsal-date YYYY-MM-DD --observer real-observer-alias --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal` | metadata has real_rehearsal_confirmed=true, source_origin=external_attachment, source_sha256, and timing_acceptance_pass=true |
| `hard_evidence_ledger_rebuilt` | post_evidence_refresh | hard_evidence | `False` | `python scripts/build_challenge_cup_hard_evidence_ledger.py` | hard_evidence_ledger.json has status=hard_evidence_complete and completion_claim_allowed=true |
| `package_rebuilt_after_evidence` | post_evidence_refresh | package_readiness | `False` | `python scripts/build_challenge_cup_package.py` | package_manifest.json, evidence_hashes.json, and challenge_cup_submission_archive_manifest.json reference the new evidence |
| `readiness_gate_rerun` | post_evidence_refresh | package_readiness | `False` | `python scripts/check_challenge_cup_readiness.py` | readiness_gate_report.md contains Status: `pass` and Passed: 64/64 |
| `submission_archive_verified` | post_evidence_refresh | package_integrity | `False` | `python docs/challenge_cup/reproducibility/verify_submission_package.py --root .` | verifier prints Status: pass and verifies hashed files |
| `goal_completion_gate_rerun` | goal_completion_decision | goal_completion | `False` | `python scripts/check_challenge_cup_goal_completion.py` | goal_completion_report.md contains Status: `pass` and completion_claim_allowed=True |
| `final_acceptance_audit_refreshed` | final_review | final_audit | `False` | `python scripts/build_challenge_cup_final_acceptance_audit.py` | final_acceptance_audit.json preserves no award guarantee while reflecting the latest goal status |

## Cannot Substitute

- `package_preflight_clean`: a clean package preflight does not substitute for real expert feedback or real timed rehearsal evidence
- `expert_feedback_source_ready`: expert outreach, generated summaries, and metadata JSON do not substitute for the real feedback attachment
- `expert_feedback_archived`: outreach proof alone does not substitute for received expert feedback
- `timed_rehearsal_source_ready`: schedule proof or a generated note without independent source does not substitute for a real observed run
- `timed_rehearsal_archived`: a scheduled rehearsal or over-limit rehearsal does not substitute for a passing timed rehearsal
- `hard_evidence_ledger_rebuilt`: manual edits to the ledger do not substitute for recorded source attachments and metadata
- `package_rebuilt_after_evidence`: source files copied outside the package do not substitute for regenerated manifests and archive
- `readiness_gate_rerun`: a stale readiness report does not substitute for a rerun after evidence changes
- `submission_archive_verified`: readiness pass alone does not substitute for archive/hash verification
- `goal_completion_gate_rerun`: final audit, archive verification, or reviewer enthusiasm do not substitute for the goal completion gate
- `final_acceptance_audit_refreshed`: final audit cannot override a failing goal completion gate
