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

## Task 3 fix round 2

### Scope

This round addresses only the six Important findings assigned against reviewed head `939de37b`: database-enforced manifest/snapshot/publication lineage, complete replay-chain validation, readiness cut-point rollback coverage, ambiguous migration-006 workspace backfill rejection, database-enforced revision/analysis lineage, and a distinct publication dependency-revision authority chain. Migration 007 is additive; migrations 005 and 006 remain byte/checksum stable. No Task 4+, service/transport/auth/UI work, plan/ledger change, subagent dispatch, push, or PR was performed.

### RED evidence

The preserved new SQLite tests were run before migration 007 or repository production edits:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_migration_007_enforces_workspace_qualified_publication_and_revision_lineage tests/integration/test_fmea_governance_sqlite.py::test_migration_007_rejects_ambiguous_legacy_analysis_workspaces tests/integration/test_fmea_governance_sqlite.py::test_publication_dependency_revision_has_its_own_authority_chain_and_replay_requires_it tests/integration/test_fmea_governance_sqlite.py::test_readiness_fault_at_actual_write_cut_point_rolls_back_every_readiness_dependency tests/integration/test_fmea_governance_sqlite.py::test_replay_rejects_tampered_result_record_and_dependency_ids tests/integration/test_fmea_governance_sqlite.py::test_publication_replay_recursively_rejects_tampered_dependency_chain -q
```

Actual: **10 failed, 4 passed**. Expected failure evidence:

- `fmea_publication_lineage_bindings` did not exist (`sqlite3.OperationalError`), so no mandatory database lineage could be written or consumed.
- Reinitializing a version-6 database containing the same `analysis_id` in two `fmea_rows.workspace_id` values did not raise.
- A publication-created revision had `(audit_event_id, outbox_event_id) = (NULL, NULL)` and no revision event binding.
- Tampered submission result versions and approval/publication-withdrawal/supersession result IDs replayed without raising.
- Tampered revision/submission/approval dependency authority IDs did not invalidate publication replay.

The readiness write-cut rollback test was one of the four passing cases because round 1 had already moved `fail("revision.readiness")` immediately after the actual readiness insert; this round adds the missing durable residue assertions rather than manufacturing a false production regression.

A focused lineage node was also rerun before migration 007 and failed **1 failed** with `no such table: fmea_publication_lineage_bindings`, including the direct mismatched-parent case in its test body.

### GREEN implementation by finding

1. Migration 007 creates immutable `fmea_publication_lineage_bindings` with workspace-qualified deferrable FKs to publication, manifest, snapshot, revision, and the exact `(workspace_id, revision_id, analysis_id)` revision-analysis binding. Its insert trigger requires the exact publication/manifest/snapshot/revision/analysis IDs and hashes to agree. Repository publication writes insert this binding in the publication transaction, and publication reads/replays require it. Direct SQLite tests reject valid-parent mismatches, cross-workspace references, orphans, and duplicate reuse.
2. Replay now compares every result resource ID and record version represented by its authority row, plus exact authority `idempotency_scope`, `payload_hash`, audit/outbox IDs, actor, command, canonical audit JSON/hash, outbox workspace/scope/type/canonical payload/hash, and immutable event binding. Publication replay recursively verifies its persisted revision, approval-submission, and approval idempotency/audit/outbox/event-binding chains and verifies manifest, snapshot, publication lineage, and export eligibility.
3. The readiness fault test injects at `revision.readiness`, immediately after the readiness insert, and proves the previous revision chain survives while readiness authority/audit/outbox/idempotency/event-binding residue remains absent.
4. Migration 007 begins with an ambiguity guard over legacy `fmea_rows`, rejecting any `analysis_id` sourced from more than one workspace. Because repository initialization applies migrations inside `BEGIN EXCLUSIVE`, the failing guard rolls back all version-7 DDL and leaves schema version 6 and source rows intact.
5. Migration 007 adds the non-partial `(workspace_id, analysis_id)` parent key required by SQLite and immutable `fmea_revision_analysis_bindings` with deferrable FKs to both `fmea_analyses` and `fmea_revisions`. Its trigger verifies analysis ID/version/hash against the revision and authoritative analysis. Revision writes insert the binding atomically, and revision reads/replays require it.
6. A publication-created revision now receives its own deterministic dependency idempotency scope, audit event, `revision.assembled` outbox event, event binding, completed response, and authority IDs. These IDs are distinct from publication IDs. The `publication.revision` injector fires after the revision and revision-analysis binding writes; rollback tests verify the complete dependency chain is removed.

Migration 007 also backfills both binding tables only from exact existing joins and fails the migration transaction if any existing revision or publication cannot receive its mandatory binding. It adds authority scope/payload columns to revisions and publications so exact replay does not treat those records as unchecked derived data.

### Fresh GREEN commands and exact counts

Focused round-2 behavior matrix:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_migration_007_enforces_workspace_qualified_publication_and_revision_lineage tests/integration/test_fmea_governance_sqlite.py::test_migration_007_rejects_ambiguous_legacy_analysis_workspaces tests/integration/test_fmea_governance_sqlite.py::test_publication_dependency_revision_has_its_own_authority_chain_and_replay_requires_it tests/integration/test_fmea_governance_sqlite.py::test_readiness_fault_at_actual_write_cut_point_rolls_back_every_readiness_dependency tests/integration/test_fmea_governance_sqlite.py::test_replay_rejects_tampered_result_record_and_dependency_ids tests/integration/test_fmea_governance_sqlite.py::test_nonpublication_replay_rejects_tampered_exact_authority_chain tests/integration/test_fmea_governance_sqlite.py::test_publication_replay_recursively_rejects_tampered_dependency_chain tests/integration/test_fmea_governance_sqlite.py::test_publication_replay_rejects_tampered_authority_chain_and_response tests/integration/test_fmea_governance_sqlite.py::test_fault_injected_publication_rolls_back_every_shared_write -q
```

Result: **48 passed**.

Brief-specified Task 3 three-file matrix, no deselection:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py -q
```

Result: **70 passed**.

Brief-specified six-file persistence matrix, no deselection:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py -q
```

Result: **76 passed**.

Relevant governance/snapshot contract matrix:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_source.py -q
```

Result: **142 passed**.

Additive migration compatibility node:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_propagation_sqlite.py::test_propagation_migration_is_additive_and_creates_required_schema -q
```

Result: **1 passed**; it asserts the exact additive set `[1, 2, 3, 4, 5, 6, 7]`.

### Static, compile, migration, and diff checks

```powershell
.venv\Scripts\python.exe -m ruff check fmea_infrastructure/governance_repository_sqlite.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_propagation_sqlite.py
.venv\Scripts\python.exe -m ruff format --check fmea_infrastructure/governance_repository_sqlite.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_propagation_sqlite.py
.venv\Scripts\python.exe -m compileall -q fmea_infrastructure/governance_repository_sqlite.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_propagation_sqlite.py
git diff --check
git diff --exit-code -- fmea_infrastructure/migrations/005_fmea_governance_closure.sql fmea_infrastructure/migrations/006_fmea_governance_integrity.sql
```

Results: Ruff check **passed**; Ruff format check reported **3 files already formatted**; compileall exited **0** with no output; `git diff --check` exited **0**; the 005/006 diff check exited **0**, proving both checksum-stable migrations are unchanged.

### Self-review, compatibility, and concerns

- The schema remains additive. Legacy `fmea_rows.publication_status`, review/risk/propagation APIs, and the existing shared `fmea_outbox_events`/`idempotency_records` authorities are unchanged. Migration 007 creates no parallel audit, outbox, or idempotency table.
- Binding inserts occur only inside the existing governance transaction. Published payloads and all new bindings remain immutable; publication withdrawal and supersession stay append-only.
- Publication dependency scopes now derive from their actual command idempotency keys; dependency audit/outbox/event IDs remain unique and cannot reuse the publication authority pair.
- Direct SQL and restart replay tests exercise behavior rather than source-text assertions.
- No Important finding remains open. The previously ledgered minor `ApprovalWithdrawalResult` placement concern remains outside this round and is unchanged.

## Task 3 fix round 3

### Scope

This round fixes only the five scoped Important findings against reviewed head `383df3dd`: mandatory publication-lineage totality, persisted-authority-to-outbox-payload cross-binding, mandatory revision-analysis totality and analysis-hash lineage, exact authority validation before publication reuses an existing revision, and safe version-7 authority-metadata repair. It adds migration `008_fmea_governance_totality.sql`; committed migrations 005, 006, and 007 are unchanged. No Task 4+, service/transport/auth/UI work, plan/ledger modification, subagent dispatch, push, or PR was performed.

### RED evidence

The real-SQLite tests were added before migration 008 or repository production changes, then run as one focused matrix:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_migration_008_requires_total_publication_lineage_binding tests/integration/test_fmea_governance_sqlite.py::test_migration_008_requires_total_revision_analysis_binding tests/integration/test_fmea_governance_sqlite.py::test_migration_008_revision_binding_checks_authoritative_and_revision_json_hash tests/integration/test_fmea_governance_sqlite.py::test_replay_cross_binds_authority_dto_to_canonical_outbox_payload tests/integration/test_fmea_governance_sqlite.py::test_publication_rejects_existing_revision_without_exact_authority_chain tests/integration/test_fmea_governance_sqlite.py::test_migration_008_backfills_reconstructable_v7_authority_and_preserves_replay tests/integration/test_fmea_governance_sqlite.py::test_migration_008_rejects_unreconstructable_v7_authority_atomically tests/integration/test_fmea_propagation_sqlite.py::test_propagation_migration_is_additive_and_creates_required_schema -q
```

Actual RED: **17 failed in 2.47s**. The direct parent inserts/deletes committed because no reverse FK made either binding mandatory; a binding could not validate `revision_json.analysis_hash`; all eight compound authority-DTO/outbox tamper cases replayed; publication accepted two corrupted existing-revision chains; version 8 did not exist, so the reconstructable fixture remained at version 7 and the unreconstructable fixture did not attempt a fail-closed upgrade; and the compatibility node still expected schema versions through 7.

### GREEN design and implementation

1. Migration 008 rebuilds `fmea_revisions` and `fmea_publications` with workspace-qualified, deferrable reverse FKs to their exact migration-007 binding rows. The existing forward FKs remain, so the relation is total in both directions: a parent cannot commit without a binding and a binding cannot survive without its parent. Existing checks, primary/unique keys, query indexes, immutable no-update/no-delete triggers, and parent/dependency FKs are recreated. Authority metadata is mandatory for all new parent inserts through database triggers.
2. The revision-analysis binding trigger now normalizes and compares the binding hash with both authoritative `fmea_analyses.analysis_hash` and `revision_json.analysis_hash`, in addition to workspace, analysis ID, revision ID, and authoritative record version.
3. Migration 008 reconstructs nullable version-7 revision/publication `idempotency_scope` and `payload_hash` only from an exact shared event-binding/audit/outbox/completed-idempotency chain. A guard rejects missing or inconsistent lineage, resource IDs, event IDs, scope, payload hash, event type/command, result IDs, versions, or replay state. Failure occurs inside the migration transaction, leaving schema/data at version 7 with no partial version-8 object. A final `pragma_foreign_key_check` guard validates the rebuilt graph before clearing SQLite's transient deferred-FK counter caused by parent-table replacement.
4. Replay now reconstructs the expected canonical event payload from the decoded persisted authority DTO and its persisted dependencies for revision, readiness, approval submission, approval decision, approval withdrawal, publication, publication withdrawal, and supersession. It requires exact canonical equality with the shared outbox payload and requires the reconstructed governance payload hash to equal the authority hash. Publication replay continues recursively through revision/submission/approval plus manifest/snapshot/export-eligibility lineage.
5. Publication dependency reuse now calls the same exact persisted revision-chain verifier used by restart replay before accepting an existing revision. Missing event bindings or internally corrupted outbox payloads fail the publication transaction closed.
6. Direct SQLite tests isolate reverse-FK totality from the independent authority-required triggers, prove deletion cannot leave a valid parent, prove the three-way analysis-hash check, and exercise both reconstructable and unreconstructable real version-7 fixtures. The prior migration-007 lineage test restores the binding it temporarily removes so its transaction remains valid under the new mandatory reverse FK.

### Fresh GREEN commands and exact counts

Focused round-3 behavior matrix (same command as RED): **17 passed in 2.47s**.

The migration-007 compatibility node affected by mandatory binding was rerun directly:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_migration_007_enforces_workspace_qualified_publication_and_revision_lineage -q
```

Result: **1 passed in 0.21s**.

Brief-specified Task 3 three-file matrix, with no deselection:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py -q
```

Final fresh result: **86 passed in 13.14s**.

Brief-specified six-file persistence matrix, with no deselection:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py -q
```

Final fresh result: **92 passed in 13.10s**.

Relevant governance/snapshot contract matrix:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_source.py -q
```

Result: **142 passed in 0.79s**.

Exact additive migration compatibility node:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_propagation_sqlite.py::test_propagation_migration_is_additive_and_creates_required_schema -q
```

Result: **1 passed in 0.09s**; it asserts the meaningful exact set `[1, 2, 3, 4, 5, 6, 7, 8]`.

### Static, compile, migration, and diff checks

Controlled Python files were `fmea_infrastructure/governance_repository_sqlite.py`, `tests/integration/test_fmea_governance_sqlite.py`, and `tests/integration/test_fmea_propagation_sqlite.py`.

```powershell
.venv\Scripts\python.exe -m ruff check fmea_infrastructure/governance_repository_sqlite.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_propagation_sqlite.py
.venv\Scripts\python.exe -m ruff format --check fmea_infrastructure/governance_repository_sqlite.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_propagation_sqlite.py
.venv\Scripts\python.exe -m compileall -q fmea_infrastructure/governance_repository_sqlite.py fmea_application core_domain/fmea tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py tests/regression/test_fmea_governance_idempotency.py
git diff --check
git diff --exit-code -- fmea_infrastructure/migrations/005_fmea_governance_closure.sql fmea_infrastructure/migrations/006_fmea_governance_integrity.sql fmea_infrastructure/migrations/007_fmea_governance_lineage.sql
```

Final results: Ruff check **passed**; Ruff format check reported **3 files already formatted**; compileall exited **0** without errors; `git diff --check` exited **0**; and the 005/006/007 diff check exited **0**, proving all three committed migration files are byte/diff unchanged.

### Self-review, compatibility impact, and concerns

- The migration preserves the legacy `fmea_rows.publication_status` CHECK and the review/risk/propagation persistence APIs. It creates no parallel audit, outbox, or idempotency authority and continues to use `fmea_audit_events`, `fmea_outbox_events`, `idempotency_records`, and `fmea_governance_event_bindings`.
- Reverse FKs are deferrable, so repository insertion order remains atomic while transaction commit enforces totality. The migration's final FK guard proves no orphan is hidden when SQLite's transient rebuild counter is cleared.
- Published payloads and both binding relations remain immutable. Withdrawal and supersession remain append-only.
- Replay does not accept independent self-consistent hashes: the canonical outbox payload must now be exactly derivable from persisted typed authority state and dependencies.
- No scoped Important finding remains open. Previously ledgered minor findings, including `ApprovalWithdrawalResult` placement, remain intentionally unchanged and outside this fix round.

## Task 3 fix round 4

### Scope and root-cause diagnosis

This round addresses the two remaining Important findings against reviewed HEAD `972c3eef`. It adds only migration `009_fmea_governance_manifest_totality.sql`, the shared-runner migration validation hook, the focused SQLite regressions, and the migration-version compatibility assertion. Migrations 005, 006, 007, and 008 remain byte/diff unchanged. No Task 4+, service/transport/auth/REST/CLI/export/UI, RAG/GraphRAG, push, PR, or subagent work was performed.

Finding A root cause: migration 008 added the publication-parent reverse FK to `fmea_publication_lineage_bindings`, but `fmea_publication_manifests` and `fmea_normalized_snapshots` retained only their forward references or no parent-side totality. A direct SQL insert could therefore commit a manifest with valid revision/approval/snapshot identifiers and no exact binding. Migration 009 rebuilds both parent tables with deferrable workspace-qualified reverse FKs to the binding table's unique `(workspace_id, manifest_id)` and `(workspace_id, snapshot_id)` keys, while preserving the existing columns, checks, keys, indexes, triggers, and FKs.

Finding B root cause: migration 008 reconstructed nullable revision/publication scope and payload hashes from scalar audit/outbox/idempotency pointers, but did not decode or canonicalize `audit.event_json`, recompute outbox JSON/SHA, or rebuild the exact runtime authority DTO-to-outbox payload. A fully populated v7 chain could therefore have mutually consistent scalar hashes while its outbox payload diverged from the persisted authority DTO. The shared runner is already the transaction owner (`BEGIN EXCLUSIVE` around all pending migrations), so it now registers an application-defined SQLite function on every migration connection. Migration 009 invokes that function after 008; it strictly decodes the reconstructed revision/publication and all publication dependencies, recomputes canonical JSON/SHA, validates audit/outbox/idempotency/result bindings, and compares the exact runtime-equivalent revision/publication payload. A failed predicate raises a migration CHECK failure, rolling back both 008 and 009.

### TDD RED evidence

The focused real-SQLite tests were added before migration 009 and the shared validation hook:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_migration_009_rejects_direct_manifest_without_lineage_binding tests/integration/test_fmea_governance_sqlite.py::test_migration_009_adds_snapshot_reverse_lineage_foreign_key tests/integration/test_fmea_governance_sqlite.py::test_migration_009_rejects_v7_authority_dto_outbox_divergence_atomically -q
```

Actual RED: **3 failed in 0.54s**. The direct SQL manifest insert reported `DID NOT RAISE`; the normalized snapshot reverse-FK assertion was false; and the internally consistent but authority-DTO/outbox-divergent v7 fixture initialized without raising instead of remaining at version 7.

### GREEN design and implementation

1. `SqliteFmeaRepository._connect()` registers `fmea_validate_governance_replay` for the shared migration runner. The hook is application-defined because SQLite SQL alone cannot recompute the repository's canonical JSON/SHA or instantiate the typed audit and authority DTOs. The function returns 0 on any malformed, non-canonical, hash-inconsistent, identity-inconsistent, or DTO/outbox-divergent input; migration 009 converts that result into a database CHECK failure.
2. Migration 009 runs the replay guard after 008's reconstruction and before parent replacement. It validates every revision and publication row, including canonical authority JSON, canonical audit JSON, outbox canonical JSON and SHA, idempotency response, result identity, and the exact expected runtime payload. Publication validation additionally checks revision, submission, approval, manifest, normalized snapshot, and export-eligibility DTOs against their persisted row columns and canonical hashes.
3. Migration 009 rebuilds only `fmea_publication_manifests` and `fmea_normalized_snapshots`, adding deferrable reverse FKs to the exact binding table. It temporarily removes and restores the existing binding insert trigger while those two parent table names are transiently absent. The final `pragma_foreign_key_check` guard clears the transient deferred-FK state only after the completed graph is valid.
4. The new v7 divergence fixture changes the canonical outbox revision DTO, updates outbox/audit/idempotency scalar hashes and canonical audit JSON consistently, nulls the v7 revision replay metadata, and applies pending migrations through the normal runner. The 009 guard rejects it and the outer transaction leaves schema/data at v7. The existing exact reconstructable v7 fixture still upgrades to v9 and both revision/publication replays pass.

### Fresh GREEN commands and exact counts

Focused round-4 behavior matrix:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_migration_009_rejects_direct_manifest_without_lineage_binding tests/integration/test_fmea_governance_sqlite.py::test_migration_009_adds_snapshot_reverse_lineage_foreign_key tests/integration/test_fmea_governance_sqlite.py::test_migration_009_rejects_v7_authority_dto_outbox_divergence_atomically -q
```

Result: **3 passed in 0.39s**.

Task 3 three-file matrix:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py -q
```

Result: **89 passed in 13.78s**.

Task 3 six-file persistence matrix:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py -q
```

Result: **95 passed in 14.59s**.

Governance/snapshot contract matrix:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_source.py -q
```

Result: **142 passed in 0.80s**.

Exact additive migration node:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_propagation_sqlite.py::test_propagation_migration_is_additive_and_creates_required_schema -q
```

Result: **1 passed in 0.11s**; the exact schema migration set is `[1, 2, 3, 4, 5, 6, 7, 8, 9]`.

The temporary real-SQLite v8-to-v9 schema comparison reported that both parent tables preserved columns, user indexes, immutable triggers, and every pre-existing FK; it reported only the expected new manifest and snapshot reverse FKs. The final `pragma_foreign_key_check` was empty and `schema_migrations` reached version 9. The exact reconstructable v7 fixture upgraded to version 9 and replayed both revision and publication successfully; the divergent fixture remained at version 7 with no v8/v9 staging tables.

### Static, compile, migration, and diff checks

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m ruff check fmea_infrastructure/repository_sqlite.py fmea_infrastructure/governance_migration_validation.py fmea_infrastructure/governance_repository_sqlite.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_propagation_sqlite.py
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m ruff format --check fmea_infrastructure/repository_sqlite.py fmea_infrastructure/governance_migration_validation.py fmea_infrastructure/governance_repository_sqlite.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_propagation_sqlite.py
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m compileall -q fmea_infrastructure/repository_sqlite.py fmea_infrastructure/governance_migration_validation.py fmea_infrastructure/governance_repository_sqlite.py fmea_application core_domain/fmea tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py tests/regression/test_fmea_governance_idempotency.py
git diff --check
git diff --exit-code -- fmea_infrastructure/migrations/005_fmea_governance_closure.sql fmea_infrastructure/migrations/006_fmea_governance_integrity.sql fmea_infrastructure/migrations/007_fmea_governance_lineage.sql fmea_infrastructure/migrations/008_fmea_governance_totality.sql
```

Results: Ruff check passed; Ruff format check reported all 5 controlled files already formatted; compileall exited 0 with no output; `git diff --check` exited 0; and the committed 005–008 diff check exited 0.

### Compatibility impact and concerns

- The change is additive at migration version 009. Shared `fmea_audit_events`, `fmea_outbox_events`, `idempotency_records`, immutable published payloads, append-only withdrawal/supersession, legacy `fmea_rows.publication_status`, and existing migration history remain unchanged.
- Exact v7 authority that is reconstructable by the same runtime-equivalent predicate remains supported and replays after upgrade. Unsafe v7 data fails closed before version 8/9 is recorded and is transactionally unchanged.
- A database already advanced to the pre-acceptance v8 schema with unsafe replay contents is intentionally not silently repaired; migration 009 rejects it and leaves it at v8 for explicit repair. Running migration 009 outside the shared Python migration runner is also intentionally unsupported because the application-defined validation function is part of the runner's transaction boundary.
- Previously deferred minor findings, including `ApprovalWithdrawalResult` placement, remain outside this round.

## Task 3 fix round 5

### Scope and root-cause predicate comparison

This breaker round addresses the remaining Important finding on reviewed HEAD `7933d3c8`. It changes only `fmea_infrastructure/governance_migration_validation.py`, adds the two focused real-SQLite regressions in `tests/integration/test_fmea_governance_sqlite.py`, and appends this report. Migrations 005–009, services, auth, transport, RAG/GraphRAG, push, PR, reset/clean, and subagents remain out of scope.

The round-4 UDF already decoded canonical authority/dependency DTOs and checked most scalar event-chain bindings, but its acceptance predicate was still weaker than runtime replay. In particular, for a revision it compared `workspace_id`, `analysis_id`, `analysis_record_version`, parent identity, and `revision_hash`, but never compared the decoded DTO `revision_id` with the persisted row `resource_id`. The reviewer probe changed the v7 `revision_json` DTO to a different revision ID, rebuilt its revision hash, replaced the outbox revision DTO, and consistently rebuilt the outbox, audit, and idempotency payload hashes. Migration 008 repaired the nullable replay metadata and round-4 accepted the internally consistent-looking chain; runtime `_revision_from_connection` then queried the original row ID and rejected the DTO identity. The same construction against an already-v8 database bypassed 008 and was accepted by 009.

The migration predicate is now checked against the runtime contracts in `governance_repository_sqlite.py` as follows:

| Runtime contract | Runtime predicates traced | Migration-time coverage in round 5 |
| --- | --- | --- |
| Revision row decoder and analysis lineage (`:1696–1719`, `:1510–1521`) | Workspace-qualified row lookup; DTO/row `revision_id`, `analysis_id`, `analysis_record_version`, parent ID/hash, `revision_hash`, canonical JSON hash, fixed record version 1; required revision-analysis binding with matching analysis ID/version/hash. | `_validate_revision_runtime_row` performs the same row and binding checks on the migration connection, and the authority/result predicate explicitly binds DTO `revision_id` to `resource_id`. |
| Publication row decoder and publication lineage (`:1797–1823`, `:1543–1561`) | Workspace-qualified publication lookup; publication ID, analysis ID, revision ID/hash, approval ID, manifest ID/hash, snapshot ID/hash, audit-chain head, publisher actor, record version, canonical JSON hash; exact seven-field publication lineage binding. | `_validate_publication_runtime_row` performs every row-field and exact lineage tuple check, plus the authority/result publication ID and all authority scalar bindings. |
| Publication dependencies (`:1564–1794`) | Submission ID/workspace/revision ID/hash/status/submitter/version/canonical hash; approval ID/submission ID/revision ID/hash/status/approver/reason/version/canonical hash; manifest IDs/hashes and canonical hash; snapshot workspace/IDs/hashes/analysis ID and canonical hash; export eligibility ID/workspace/publication/manifest/boolean/eligibility hash, canonical source-hash JSON, and canonical JSON hash. | Six connection-local dependency row validators compare decoded DTOs to their actual persisted rows. The cross-table predicate also binds approval/submission/manifest/snapshot/publication IDs, analysis IDs, revision hashes, versions, export eligibility IDs/boolean, and all migration-009 dependency scalar columns rather than relying only on DTO-to-DTO equality. |
| Publication dependency replay (`:964–1013`, `:1042–1087`) | Replays the revision, submission, and approval authority chains; checks dependency audit/idempotency scope, payload hash/state/resource ID, response identity, and recursively validates event chains. | Publication validation performs the dependency-row checks before rebuilding the exact `publication.publish` payload, verifies revision/approval/submission/manifest/snapshot/eligibility lineage, and requires eligibility source hashes for revision, manifest, and snapshot to equal the current dependency hashes. |
| Shared event/replay chain (`:818–946`) | Authority result IDs and event IDs; audit JSON canonicality, event/workspace/actor/command/row/scope/payload bindings; outbox canonical JSON, workspace/aggregate/event/scope/payload bindings; completed idempotency state/resource/response identity; exact canonical authority-to-outbox payload hash. | Existing round-4 checks are retained. Round 5 additionally reconstructs the `IdempotencyScope` from the authority path and audit key hash, checks its scope key, checks decoded audit analysis identity, and runs all row/lineage checks through the same connection-local UDF before accepting the migration. |

The UDF registration now closes over the migration runner's connection so it can inspect the actual revision-analysis and publication-lineage rows as runtime decoders do. It remains read-only and returns `0` for malformed/invalid data; migration 009's existing CHECK converts that into a transaction failure. No migration SQL was edited.

### TDD RED evidence

The unsafe-v7 and unsafe-v8 tests were written before the production validator change. At RED they were represented by the parameterized node below; the node was subsequently split into explicit unsafe-v7 and unsafe-v8 names without changing the probe behavior:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_migration_009_rejects_revision_id_divergence_at_v7_and_v8_atomically -q
```

Actual RED: **2 failed in 0.48s**. Both v7 and v8 failed with `DID NOT RAISE`: the current validator accepted the internally consistent DTO/outbox/audit/idempotency divergence. The v7 test had cleared replay metadata so 008 would reconstruct it; the v8 test retained its existing scope and replaced its payload hash so 009 alone exercised the same unsafe state.

### GREEN implementation and exact evidence

The focused round-5 behavior command, including the safe reconstructable v7 fixture, existing unsafe v7 fixture, manifest/snapshot totality checks, prior outbox-created-at regression, and both new unsafe probes:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_migration_008_backfills_reconstructable_v7_authority_and_preserves_replay tests/integration/test_fmea_governance_sqlite.py::test_migration_008_rejects_unreconstructable_v7_authority_atomically tests/integration/test_fmea_governance_sqlite.py::test_migration_009_rejects_direct_manifest_without_lineage_binding tests/integration/test_fmea_governance_sqlite.py::test_migration_009_adds_snapshot_reverse_lineage_foreign_key tests/integration/test_fmea_governance_sqlite.py::test_migration_009_rejects_v7_authority_dto_outbox_divergence_atomically tests/integration/test_fmea_governance_sqlite.py::test_migration_009_rejects_unsafe_v7_revision_id_divergence_atomically tests/integration/test_fmea_governance_sqlite.py::test_migration_009_rejects_unsafe_v8_revision_id_divergence_atomically -q
```

Result: **7 passed in 1.06s**.

Task 3 three-file matrix:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py -q
```

Result: **91 passed in 13.37s**.

Task 3 six-file persistence matrix:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py -q
```

Result: **97 passed in 15.16s**.

Governance/snapshot contract matrix:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_source.py -q
```

Result: **142 passed in 0.74s**.

Exact additive migration node:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_propagation_sqlite.py::test_propagation_migration_is_additive_and_creates_required_schema -q
```

Result: **1 passed in 0.11s**; the migration set remains `[1, 2, 3, 4, 5, 6, 7, 8, 9]`.

Static and integrity checks:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m ruff check fmea_infrastructure/repository_sqlite.py fmea_infrastructure/governance_migration_validation.py fmea_infrastructure/governance_repository_sqlite.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_propagation_sqlite.py
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m ruff format --check fmea_infrastructure/repository_sqlite.py fmea_infrastructure/governance_migration_validation.py fmea_infrastructure/governance_repository_sqlite.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_propagation_sqlite.py
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m compileall -q fmea_infrastructure/repository_sqlite.py fmea_infrastructure/governance_migration_validation.py fmea_infrastructure/governance_repository_sqlite.py fmea_application core_domain/fmea tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py tests/regression/test_fmea_governance_idempotency.py
git diff --check
git diff --exit-code -- fmea_infrastructure/migrations/005_fmea_governance_closure.sql fmea_infrastructure/migrations/006_fmea_governance_integrity.sql fmea_infrastructure/migrations/007_fmea_governance_lineage.sql fmea_infrastructure/migrations/008_fmea_governance_totality.sql fmea_infrastructure/migrations/009_fmea_governance_manifest_totality.sql
```

Results: Ruff check passed; Ruff format reported **5 files already formatted**; compileall exited 0 with no output; `git diff --check` exited 0 with only the repository's LF-to-CRLF working-copy warnings; and the 005–009 diff check exited 0.

### Compatibility impact and concerns

- The safe reconstructable v7 fixture still upgrades to v9, restores replay metadata, and replays revision and publication successfully. The prior v7 outbox-created-at divergence remains rejected. The new internally consistent revision-ID divergence remains at v7 or v8 respectively, with no partial migration staging objects or changed shared chain state.
- The change is migration-runner-only and additive; no migration 010 was added and migrations 005–009 are unchanged. Existing manifest/snapshot totality, immutable triggers, shared audit/outbox/idempotency tables, workspace isolation, and prior addressed findings remain covered by the six-file and focused matrices.
- No scoped Important finding remains open. Operational concern: migration 009 must continue to run through the Python shared runner, because the application-defined UDF intentionally depends on the runner-owned connection; direct ad-hoc execution of SQL migration 009 remains unsupported. The added row-level reads are migration-time only and do not alter runtime service/transport behavior.
