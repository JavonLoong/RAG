# Phase 3 Task 4 — Governance Service

## TDD evidence

The original Task 4 Step 1 RED was preserved before production implementation:

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_service.py tests/unit/test_fmea_governance_authority.py tests/integration/test_fmea_governance_lifecycle.py -q
3 errors during collection
```

After Step 0 expanded the authorized persistence boundary, its contract and real-SQLite RED were also preserved:

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_application_contracts.py tests/unit/test_fmea_governance_repository_contract.py -q
19 passed, 3 failed

.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py -k "public_current_reads" -q
2 failed, 94 deselected
```

Round 1 began with direct failing tests before each production hardening:

- command-bound approval/publish replay: `5 failed, 3 deselected`;
- omitted/forged publication audit marker: `2 failed, 101 deselected`;
- mandatory getter/version/cache-fallback cases: `5 failed, 6 deselected`;
- all-write replay-before-state-guard matrix: `5 failed, 1 passed, 11 deselected`;
- persisted command reconstruction and audit-head restart group: `2 failed, 2 passed, 103 deselected`;
- stable aggregate IDs plus supersession traversal: `4 failed, 2 passed, 17 deselected`;
- forged snapshot/manifest/chain/outbox fields: `1 failed, 5 passed, 107 deselected`;
- wrong revision/submission identities from mandatory reads: `2 failed, 6 passed, 23 deselected`.

Focused GREEN results after the corresponding fixes:

- command-bound replay and unconditional audit marker validation: `5 passed, 3 deselected` and `2 passed, 101 deselected`;
- mandatory reads and all-write early replay: `14 passed, 3 deselected`;
- persisted replay/audit-head/restart/stale-predecessor group: `4 passed, 103 deselected`;
- stable aggregate IDs and bounded repository-backed supersession: `6 passed, 17 deselected`;
- forged publication bundle fields: `6 passed, 107 deselected`;
- mandatory read identity and missing-port checks: `8 passed, 23 deselected`;
- generic command-bound replay for every write kind, including approve/reject distinction: `8 passed, 113 deselected`;
- two service instances chaining publications through one SQLite database: `1 passed, 2 deselected`;
- operation/result type and replay-flag mismatch: `2 passed, 31 deselected`;
- restored post-mutation target group: `23 passed, 129 deselected`.

## Final verification

- Revised Task 4 scoped matrix (10 files): `222 passed in 25.79s`.
- Six-file persistence/migration regression: `131 passed in 24.88s`.
- Full governance SQLite integration file: `121 passed in 23.35s`.
- Governance and snapshot contracts: `60 passed in 0.59s`.
- Migration stability subset: `19 passed, 102 deselected in 2.76s`.
- Targeted Ruff check: passed.
- Targeted Ruff format check: passed (`8 files already formatted`).
- Targeted `compileall`: passed.
- `git diff --check`: passed.
- Migrations 005–009 byte diff: empty; no migration 010 exists.

Mutation verification temporarily removed each new guard and restored it before final verification:

- early replay removal: target group failed `8` tests;
- command canonical-compare removal: changed-command conflict test failed;
- unconditional publication-chain removal: both audit-marker tests failed;
- transaction-local predecessor removal: stale competing publication test failed;
- mandatory revision/submission identity removal: both binding tests failed;
- scope-stable aggregate ID removal: deterministic-ID test failed;
- repository-backed supersession traversal removal: multihop test failed;
- approve/reject operation-match removal: operation mismatch test failed;
- outbox event-type binding removal: forged-outbox test failed.

## Round 1 closure

1. Mandatory reads are now public `GovernanceRepository` calls only. The service has no revision, submission, approval, withdrawal, publication, snapshot, supersession, or audit-head authority caches, no `getattr` port fallback, and no revision-version default.
2. `replay_governance_command(kind, scope, command)` accepts only the eight explicit governance write kinds, reconstructs the command from persisted authority, excludes only the raw idempotency key from canonical comparison, verifies the complete replay chain, and returns the kind-specific typed result. Changed commands map to the stable governance idempotency conflict.
3. Every governance write performs typed command-bound replay after authority/type validation but before mutable/current-state reads, clock use, event-ID generation, or aggregate reconstruction.
4. Publication persistence always recomputes snapshot, version-manifest, manifest, audit-chain, eligibility, payload, audit marker, and outbox bindings. No marker switch or legacy fixture bypass remains.
5. Publication predecessor authority comes from persisted SQLite state. The service reads the public current head; the repository re-reads and compares it under the existing `BEGIN IMMEDIATE`, rejecting a stale predecessor atomically.
6. Publication, manifest, snapshot, and export-eligibility identities are deterministic from the idempotency scope. The injected factory can affect first-attempt event IDs only; exact replay returns before regeneration.
7. Supersession follows repeated public lifecycle reads with `seen` cycle detection and a fixed depth of 64. Old and replacement withdrawals fail closed, while SQLite remains authoritative for transaction-local withdrawal, outgoing-link, lineage, and cycle guards.
8. Restart and multi-instance tests prove replay, audit-head continuity, linear manifest predecessors, typed operation matching, and stale concurrent predecessor rollback without process-local memory.

## Public interfaces and service behavior

`GovernanceRepository` now exposes:

- `replay_governance_command(kind, scope, command)`;
- `get_current_publication_audit_head(workspace_id)`;
- the six mandatory workspace-qualified current-state reads for revision version, submission, approval decision, decision by submission, approval withdrawal, and publication lifecycle.

`RevisionGovernanceService` covers assemble, readiness, submit, approve, reject, approval withdrawal, publish, publication withdrawal, supersede, revision/publication/snapshot queries, and approval/publication history. It consumes only the existing assembler, readiness policy, public repository/source ports, and `ActorContext`; it does not read SQLite directly, duplicate repository replay/atomicity, call RAG/GraphRAG/LLM providers, or expose REST/CLI behavior.

## Authority matrix

| Operation | Required actor type | Required role |
| --- | --- | --- |
| assemble / submit | `HUMAN` | `reviewer` |
| approve / reject / withdraw approval | `HUMAN` | `approver` |
| publish / withdraw publication / supersede | `HUMAN` | `publisher` |
| governance query | `HUMAN` | `reviewer`, `approver`, or `publisher` |
| model/system authority writes | forbidden | never accepted |

The loopback simple account receives exactly `reviewer`, `risk_reviewer`, `propagation_reviewer`, `approver`, and `publisher` only when the existing simple-account switch is enabled. It remains a convenience identity rather than a general authority seam.

## Hash, authority, replay, and concurrency boundaries

- Workspace, current versions, revision hashes, submissions, decisions, withdrawals, lifecycle state, snapshots, and publication audit heads are server-loaded through public ports and validated for type, identifier, and workspace where represented by the DTO.
- Approval applies only to the current `PENDING` submission. Publication requires the current exact `APPROVED` decision and revision hash, rejects withdrawn approval, and reruns readiness against server-loaded inputs.
- Publication hash order is stable ID derivation → normalized snapshot hash → version-manifest hash → manifest hash with persisted predecessor → audit-chain head → publication/eligibility/payload/audit/outbox binding. SQLite recomputes the same order inside the transaction.
- Existing `BEGIN IMMEDIATE` writers remain authoritative for one decision per submission, one withdrawal per approval/publication, no publication after approval withdrawal, one outgoing supersession, non-withdrawn targets, version/lineage/cycle checks, and atomic replay completion.
- Exact retries return persisted typed results before current-state guards. A changed command in the same scope conflicts; an operation/result mismatch or corrupt replay chain fails closed.

## Changed files

Code/test commit:

- `fmea_application/governance_service.py`
- `fmea_application/ports.py`
- `fmea_infrastructure/governance_repository_sqlite.py`
- `tests/fmea_governance_fixtures.py`
- `tests/integration/test_fmea_governance_lifecycle.py`
- `tests/integration/test_fmea_governance_sqlite.py`
- `tests/unit/test_fmea_governance_repository_contract.py`
- `tests/unit/test_fmea_governance_service.py`

Documentation-only follow-up:

- `.superpowers/sdd/2026-08-27-fmea-governance-closure/task-4-report.md`

`progress.md`, migrations 005–009, service factory, composition, local auth, and all Task 5 files were not modified in round 1.

## Commits and residual risk

Code commit: `1a85410cab76f15f00503bf094679b6877e43a8a` (`fix(fmea): harden governance replay authority`).

The fixed supersession traversal limit deliberately fails closed beyond 64 lifecycle links; unusually deep valid histories therefore require an explicit future contract change rather than an unbounded read. First-attempt event IDs and timestamps remain server-generated as authorized, while aggregate IDs and exact retry outcomes are stable. No unresolved Task 4 blocker remains.
