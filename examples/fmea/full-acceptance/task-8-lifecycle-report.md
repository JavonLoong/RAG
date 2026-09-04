# Task 8 lifecycle slice

Historical checkpoint: bounded candidate -> review -> risk slice verified.
This report describes the early slice only. Current integration and final gate
status are recorded in `docs/handoff/full-fmea-product.md`; the full runner now
connects the later lifecycle stages described in this directory's README.

Runnable helper:

```python
run_candidate_review_risk(work_dir: str | Path) -> CandidateReviewRiskRun
```

The helper dynamically loads from `examples/fmea/full-acceptance/candidate_review_risk_slice.py`, creates immutable filesystem registries from the checked-in fuel domain/scoring sources, and runs candidate generation, candidate persistence, synchronous review suggestion generation, human review acceptance, risk proposal, and human risk confirmation against one SQLite database.

Recorded native DTOs are `ScoringRulePack` (`rule_pack_id`, `version`, and native scoring limits), `EvidencePack`, `FmeaRow`, `ReviewDecisionResult`, `RiskAssessmentRecord`, persisted `AuditEvent`, and persisted risk `OutboxEvent`. The confirmed assessment contains the derived RPN `96` from the deterministic dimensions `8*3*4`; the rule limits are read from the registered pack.

The connected evidence preserves the origin source snapshot at `source_record_version=1` while the accepted current row is `record_version=2`. Risk proposal and confirmation use the controller-owned bridge fix and retain row CAS/hash validation. No direct SQL rewrite or preconstructed risk state is used.

Safe reproduction:

```text
.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_full_acceptance.py -q
```

Replay evidence records the actual first/replayed result plus `event_counts_before` and `event_counts_after`; the replay path does not add audit or outbox events. The bounded helper writes only its evidence. The current full CLI is separate from this historical checkpoint and publishes a manifest only after independent verification.

Full manifest semantics, governance, propagation, export, template import and
migration are intentionally outside this bounded helper; they are connected by
the full runner and the other helpers in this directory.
