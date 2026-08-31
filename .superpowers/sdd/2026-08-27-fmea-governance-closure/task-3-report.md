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

The controller reproduced the initial final-matrix failure at `tests/integration/test_fmea_propagation_sqlite.py:25`. The compatibility test now asserts the exact additive migration set `[1, 2, 3, 4, 5]`; it remains selected and passes in the fresh final matrix.

Controller ruling: BASE has no `fmea_audit_events`. The legacy `audit_events` table has a `row_id` foreign key to `fmea_rows`, so it cannot serve revision/publication governance aggregate IDs. Creating the shared governance `fmea_audit_events` table in migration 005 is therefore the minimal correct implementation. The repository continues to reuse the existing `fmea_outbox_events` and `idempotency_records` authority chain. This is resolved for Task 3; the reviewer must verify the migration schema and the shared outbox/idempotency chain interpretation during review.

After this authorized compatibility correction, the fresh brief-specified final matrix result is **25 passed**.

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
