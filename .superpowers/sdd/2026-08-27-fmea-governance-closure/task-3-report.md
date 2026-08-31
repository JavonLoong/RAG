# Phase 3 Task 3 — SQLite governance persistence report

## Scope

Implemented only the Task 3 SQLite governance persistence boundary:

- additive migration `005_fmea_governance_closure.sql` for immutable revisions, readiness reports, approval lifecycle records, publication manifests/publications, normalized snapshots, withdrawals, supersessions, export eligibility, indexes, and immutable triggers;
- `SqliteGovernanceRepository` with workspace-qualified strict reads, canonical payload/hash checks, optimistic revision/publication checks, atomic lifecycle writes, exact replay, history paging, supersession cycle detection, and fault injection;
- `GovernanceRepository`, `GovernanceHistoryPage`, and the missing approval-withdrawal result shape in `fmea_application/ports.py`;
- the three brief-specified Task 3 test files, including publication atomicity, rollback, immutable writes, binding checks, replay, workspace isolation, lifecycle history, and idempotency conflict coverage.

No governance service, auth, REST/CLI, export/UI, Task 4+, plan, ledger, push, or PR work was performed.

## Self-review

- Prepared submission/publication contracts use the persisted immutable revision record version as the optimistic evidence. Persistence metadata is not included in the revision content hash.
- Publication writes persist the revision, approval submission/decision dependencies, manifest, normalized snapshot, publication, export eligibility, shared idempotency record, governance audit record, and shared outbox event in one transaction.
- All lifecycle writes use `BEGIN IMMEDIATE`; failures roll back authority records and the shared idempotency/audit/outbox chain together.
- Reads re-decode strict canonical JSON and verify stored identity/hash metadata. Replays verify the persisted response, authority row, audit event, and outbox event after restart.
- Published records and append-only lifecycle records have no-update/no-delete triggers. Supersession requires existing publications and rejects a cycle in the transaction.
- Legacy `fmea_rows.publication_status`, review/risk/propagation tables, and existing shared `fmea_outbox_events`/`idempotency_records` APIs remain untouched.

## TDD RED evidence

Command run before the Task 3 production module and port existed:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py -q
```

Expected failure: migration/repository/port imports were absent. Actual result: collection failed with 3 errors (`GovernanceRepository` import missing and `fmea_infrastructure.governance_repository_sqlite` missing in the integration/regression modules).

## GREEN design

The repository validates each prepared contract before opening the transaction; reserves the canonical shared idempotency key; writes the immutable governance audit and authority records; writes the lifecycle-specific shared outbox event; completes the shared idempotency response; and commits. A conflict on the same scope/key with another payload fails with `FMEA_IDEMPOTENCY_CONFLICT`. Exact replay re-decodes and verifies the complete persisted chain instead of returning an unchecked cached object.

Publication dependencies are persisted as part of the atomic publication bundle when absent. Supersession deliberately does not synthesize publications: both old and replacement publications and their revision lineage must already exist.

## Fresh test commands and counts

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py -q
```

Result: **19 passed**.

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_source.py -q
```

Result: **142 passed**.

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py --deselect tests/integration/test_fmea_propagation_sqlite.py::test_propagation_migration_is_additive_and_creates_required_schema -q
```

Result: **5 passed, 1 deselected**.

Brief-specified final matrix:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py -q
```

Result at the initial implementation checkpoint: **24 passed, 1 failed**. The only failure was the pre-existing propagation migration assertion expecting schema versions `[1, 2, 3, 4]`; additive migration 005 makes the actual versions `[1, 2, 3, 4, 5]`. The compatibility correction and its fresh green rerun are recorded in the follow-up below.

## Static / compile / diff checks

Fresh checks on the controlled Python files:

```powershell
.venv\Scripts\python.exe -m ruff check fmea_application/ports.py fmea_infrastructure/governance_repository_sqlite.py tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py
.venv\Scripts\python.exe -m ruff format --check fmea_application/ports.py fmea_infrastructure/governance_repository_sqlite.py tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py
.venv\Scripts\python.exe -m compileall -q fmea_application/ports.py fmea_infrastructure/governance_repository_sqlite.py tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py
git diff --check
```

Results: Ruff check passed; Ruff format check passed for 5 files; compileall exited 0 with no output; `git diff --check` exited 0 with no output.

## Compatibility impact

Migration 005 is additive and leaves the legacy row publication-status CHECK and review/risk/propagation persistence schemas unchanged. Existing shared `fmea_outbox_events` and `idempotency_records` tables are reused. Governance audit events require aggregate IDs that cannot satisfy the legacy `audit_events.row_id -> fmea_rows` foreign key, so the migration creates the `fmea_audit_events` shape named by the Task 3 handoff; this is isolated from the legacy review/risk audit table.

## Concerns

1. `ApprovalWithdrawalResult` was absent from the existing governance contract module; the Task 3 port supplies the minimal immutable result shape needed by the specified protocol.

## Follow-up: controller compatibility ruling

The controller reproduced the initial final-matrix failure at `tests/integration/test_fmea_propagation_sqlite.py:25`. The compatibility test first asserted the exact additive migration set `[1, 2, 3, 4, 5]`; this review round adds migration 006, so the current exact set is `[1, 2, 3, 4, 5, 6]` and remains selected.

Controller ruling: BASE has no `fmea_audit_events`. The legacy `audit_events` table has a `row_id` foreign key to `fmea_rows`, so it cannot serve revision/publication governance aggregate IDs. Creating the shared governance `fmea_audit_events` table in migration 005 is therefore the minimal correct implementation. The repository continues to reuse the existing `fmea_outbox_events` and `idempotency_records` authority chain. This is resolved for Task 3; the reviewer must verify the migration schema and the shared outbox/idempotency chain interpretation during review.

After the authorized compatibility correction, the historical pre-review-round fresh brief-specified final matrix result was **25 passed**.

## Follow-up: fresh verification commands

Compatibility node:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_propagation_sqlite.py::test_propagation_migration_is_additive_and_creates_required_schema -q
```

Result: **1 passed**.

Brief-specified complete matrix, with all six requested files selected and no deselection:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py -q
```

Result: **25 passed**.

Fresh controlled-file checks, including the modified compatibility test:

```powershell
.venv\Scripts\python.exe -m ruff check fmea_application/ports.py fmea_infrastructure/governance_repository_sqlite.py tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py tests/integration/test_fmea_propagation_sqlite.py
.venv\Scripts\python.exe -m ruff format --check fmea_application/ports.py fmea_infrastructure/governance_repository_sqlite.py tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py tests/integration/test_fmea_propagation_sqlite.py
.venv\Scripts\python.exe -m compileall -q fmea_application/ports.py fmea_infrastructure/governance_repository_sqlite.py tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py tests/integration/test_fmea_propagation_sqlite.py
git diff --check
```

Results: Ruff check passed; Ruff format check passed for **6 files**; compileall exited 0 with no output; git diff --check exited 0 with no whitespace errors.

## Task 3 review round 1

### Scope and controller ruling

This round fixes the five confirmed Important findings on reviewed head `1b233b57`. It adds only the additive integrity migration `006_fmea_governance_integrity.sql`, the typed readiness/export-eligibility persistence path, exact authority-chain verification, authoritative-analysis optimistic checks, actual-write fault cut points, and the required compatibility-test update. No Task 4+, service/transport/UI, plan/ledger, push, or PR work was performed.

The controller ruling is resolved and is not a concern: BASE has no `fmea_audit_events`; legacy `audit_events` is foreign-key-bound through `row_id` to `fmea_rows`, so migration 005 creating one shared governance `fmea_audit_events` table is the minimal correct implementation. The repository continues to reuse the existing `fmea_outbox_events` and `idempotency_records` chain. The reviewer should verify the migration schema and these shared-chain bindings.

### Fix-round RED evidence

1. Manifest collision / lineage:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_publication_rejects_manifest_id_reuse_with_different_lineage -q
```

Expected failure: the persisted manifest was loaded and discarded instead of compared. Actual: **1 failed**, `DID NOT RAISE`.

2. Exact replay chain:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_publication_replay_rejects_tampered_authority_chain_and_response -q
```

Expected failure: publication authority IDs were absent, and audit hash, export eligibility, and response bindings were not fully verified. Actual: **5 failed, 8 passed**; the failures included missing `audit_event_id`/`outbox_event_id` columns and `DID NOT RAISE` for audit-hash, eligibility, and response-version tampering.

3. Authoritative optimistic analysis state:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_commit_revision_rejects_stale_or_cross_workspace_analysis_state -q
```

Expected failure: `commit_revision` did not read or compare current `fmea_analyses` workspace, record version, and canonical/hash identity. Actual: **3 failed**, each `DID NOT RAISE`.

4. Readiness/export persistence:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_readiness_report_is_immutable_and_exactly_replayable tests/integration/test_fmea_governance_sqlite.py::test_publication_persists_typed_export_eligibility_and_replays_it -q
```

Expected failure: the typed repository ports and persistence methods were absent. Actual: **2 failed**, with `AttributeError` for `commit_readiness` and `get_export_eligibility`.

5. Fault-injection cut points:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_publication_fault_injector_fires_at_the_snapshot_write_cut_point tests/integration/test_fmea_governance_sqlite.py::test_revision_fault_rolls_back_shared_chain tests/integration/test_fmea_governance_sqlite.py::test_approval_submission_fault_preserves_prior_revision_and_rolls_back_chain tests/integration/test_fmea_governance_sqlite.py::test_approval_decision_fault_preserves_prior_state_and_rolls_back_chain tests/integration/test_fmea_governance_sqlite.py::test_approval_withdrawal_fault_preserves_prior_state_and_rolls_back_chain tests/integration/test_fmea_governance_sqlite.py::test_publication_withdrawal_fault_preserves_publication_and_rolls_back_chain tests/integration/test_fmea_governance_sqlite.py::test_supersession_fault_preserves_both_publications_and_rolls_back_chain -q
```

Expected failure: the named publication/revision/approval labels fired after the writer completed, and the cross-connection snapshot observation could not see the uncommitted transaction. Actual: **5 failed, 2 passed**. The invalid cross-connection observation test was removed; the retained rollback tests use real SQLite state and now pass at the actual write cut points.

### GREEN design

- Migration 006 adds workspace binding to authoritative analysis rows, exact audit/outbox result IDs to revision/publication/readiness rows, canonical source-hash metadata to readiness/export rows, and an immutable workspace-qualified event-binding table with deferred outbox linkage. Migration 005 remains checksum-stable and legacy schemas/checks remain unchanged.
- `commit_revision` validates the current authoritative analysis inside `BEGIN IMMEDIATE`, including workspace, analysis ID, record version, and normalized canonical hash, before inserting the immutable revision. Lifecycle readers now compare persisted DTO fields and record versions against their table columns.
- Every top-level authority row is bound to its exact audit/outbox result IDs. Replay verifies response resource IDs, audit metadata/event JSON/scope/hash, outbox canonical payload/scope/hash/type, the authority binding row, and— for publication—revision, approval, manifest, snapshot, export eligibility, and all lineage hashes.
- Fault calls occur immediately after the named actual write. Publication dependencies, revision, approval submission/decision/withdrawal, publication withdrawal, and supersession remain one transaction with shared idempotency, audit, outbox, and event-binding rows.
- Readiness reports are persisted as typed immutable records with canonical report/source hashes and a minimal `commit_readiness`/`get_readiness`/`replay_readiness` port. Export eligibility is a typed immutable object persisted in the publication transaction, source-hash verified, workspace/FK bound, and checked during publication replay.
- The existing review repository now writes and checks `fmea_analyses.workspace_id`, preserving workspace authority for future governance revision commits.

### Fix-round GREEN and fresh test evidence

Focused amended tests after implementation:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_publication_rejects_manifest_id_reuse_with_different_lineage -q
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_publication_replay_rejects_tampered_authority_chain_and_response -q
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_commit_revision_rejects_stale_or_cross_workspace_analysis_state -q
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_readiness_report_is_immutable_and_exactly_replayable tests/integration/test_fmea_governance_sqlite.py::test_publication_persists_typed_export_eligibility_and_replays_it -q
```

Results: **1 passed; 13 passed; 3 passed; 2 passed**, respectively.

The retained fault/rollback focused set, including all publication cut points, was run fresh as one command and returned **15 passed** (six lifecycle cut-point tests plus nine publication shared-write cut points).

The brief-specified Task 3 matrix was rerun fresh with no deselection:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py -q
```

Result: **44 passed**.

The full brief-specified six-file persistence matrix was rerun fresh with no deselection:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py -q
```

Result: **50 passed**. The propagation compatibility node alone returned **1 passed** and now asserts the exact migration set `[1, 2, 3, 4, 5, 6]`, retaining migration 005 and the round-1 additive migration 006 in the selected matrix.

Relevant governance/snapshot contract matrix:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_source.py -q
```

Result: **142 passed**.

### Static / compile / diff checks

The controlled Python set was:
`fmea_application/governance_contracts.py`, `fmea_application/ports.py`, `fmea_infrastructure/governance_repository_sqlite.py`, `fmea_infrastructure/repository_sqlite.py`, `tests/fmea_governance_fixtures.py`, `tests/unit/test_fmea_governance_contracts.py`, `tests/unit/test_fmea_governance_repository_contract.py`, `tests/integration/test_fmea_governance_sqlite.py`, `tests/integration/test_fmea_propagation_sqlite.py`, and `tests/regression/test_fmea_governance_idempotency.py`.

Fresh `ruff check` over all 10 controlled files: **passed**. Fresh `ruff format --check` over all 10: **10 files already formatted**. Fresh `compileall -q` over all 10: **exit 0**. Fresh `git diff --check`: **exit 0**, no whitespace errors.

### Compatibility impact and concerns

The only schema compatibility change is additive migration 006. It leaves the legacy `fmea_rows.publication_status` CHECK, review/risk/propagation APIs, migration 005 checksum, and shared outbox/idempotency tables intact. Existing analysis rows are backfilled to a workspace when that information is available from `fmea_rows`; unbound legacy analysis rows are rejected by governance revision commits until explicitly workspace-qualified by the owning persistence flow. No source-hash migration or FileTemplateRegistry manifest migration was added.

No Important finding remains unresolved. The previously ledgered minor placement concern for `ApprovalWithdrawalResult` remains intentionally outside this fix round and is the only reported concern.
