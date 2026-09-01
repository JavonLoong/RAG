# Phase 3 Task 4 — Governance Service

## TDD and verification

The original Step 1 RED was preserved before production implementation:

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_service.py tests/unit/test_fmea_governance_authority.py tests/integration/test_fmea_governance_lifecycle.py -q
3 errors during collection
```

After the revised Step 0 authorization, the contract/real-SQLite RED was run before the Step 0 production changes:

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_application_contracts.py tests/unit/test_fmea_governance_repository_contract.py -q
19 passed, 3 failed

.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py -k "public_current_reads" -q
0 passed, 2 failed, 94 deselected
```

GREEN and verification results:

- Step 0 application contracts: `22 passed`.
- Step 0 public current-read/canonical-corruption tests: `2 passed`.
- Transaction-local guard tests: `5 passed, 96 deselected`.
- Governance service/authority/lifecycle focused tests: `8 passed`.
- Revised scoped matrix (all Task 4 files plus existing review/risk/propagation authority regressions): `171 passed in 23.78s`.
- Migration stability subset: `19 passed, 82 deselected in 3.85s`.
- Targeted Ruff: passed with no remaining findings.
- Targeted `compileall`: passed.
- `git diff --check`: passed.

## Implementation summary

`RevisionGovernanceService` now coordinates the complete application lifecycle:

- server-loaded assembly and readiness evaluation;
- approval submission, approval/rejection, and approval withdrawal;
- publication with readiness re-evaluation, normalized snapshot, manifest, export eligibility, audit chain, outbox, and replay delegation;
- publication withdrawal and acyclic supersession;
- workspace-qualified revision/publication/snapshot queries and approval/publication history.

The service consumes only the application assembler, readiness policy, source, public governance repository port, and existing `ActorContext`. It does not read SQLite, call private repository decoders/helpers, call RAG/GraphRAG/LLM providers, or expose REST/CLI behavior.

Step 0 extends the public `GovernanceRepository` contract with six workspace-qualified canonical reads. SQLite reads fail closed on canonical corruption, duplicate effective rows, and workspace mismatch; publication lifecycle is projected through the domain projector. Existing `BEGIN IMMEDIATE` writers now close duplicate decision/withdrawal/publication/supersession and withdrawn-approval races atomically. Service-created publication bundles are rechecked in-transaction for the snapshot → manifest → audit-chain hash order before persistence.

## Authority matrix

| Operation | Required actor type | Required role |
| --- | --- | --- |
| assemble / submit | `HUMAN` | `reviewer` |
| approve / reject / withdraw approval | `HUMAN` | `approver` |
| publish / withdraw publication / supersede | `HUMAN` | `publisher` |
| governance query | `HUMAN` | `reviewer`, `approver`, or `publisher` |
| model/system authority writes | forbidden | never accepted |

Local loopback simple-account mode grants exactly `reviewer`, `risk_reviewer`, `propagation_reviewer`, `approver`, and `publisher`, and only while the existing enable switch is active. It remains a convenience identity and is not a general authority seam.

## Hash, authority, and replay boundaries

- Workspace, expected versions, revision hashes, current approval state, current withdrawal state, and publication lifecycle are loaded and checked server-side.
- Approval requires the current `PENDING` submission; publication requires the current `APPROVED` decision bound to the exact revision hash and reruns readiness.
- Publication IDs, manifest IDs, and snapshot IDs are derived from the idempotency scope. Nested snapshot values use export-safe hash projections.
- The repository remains authoritative for transaction atomicity and replay. The service delegates `replay_*` before every write and never duplicates repository replay logic.
- Publication withdrawal and supersession append immutable lifecycle evidence; original payloads remain retained. Supersession requires same workspace/analysis, a published descendant replacement, no withdrawal, and no cycle.
- Governance failures use the registered stable codes and public messages; repository/provider details are not returned.

## Changed files

- `.superpowers/sdd/2026-08-27-fmea-governance-closure/task-4-report.md`
- `fmea_application/governance_service.py`
- `fmea_application/service_factory.py`
- `fmea_application/ports.py`
- `fmea_application/review_errors.py`
- `fmea_infrastructure/composition.py`
- `fmea_infrastructure/governance_repository_sqlite.py`
- `fmea_infrastructure/local_auth.py`
- `tests/unit/test_fmea_application_contracts.py`
- `tests/unit/test_fmea_governance_repository_contract.py`
- `tests/unit/test_fmea_governance_service.py`
- `tests/unit/test_fmea_governance_authority.py`
- `tests/unit/test_fmea_local_auth.py`
- `tests/integration/test_fmea_governance_sqlite.py`
- `tests/integration/test_fmea_governance_lifecycle.py`

No migrations 005–009 or migration 010 were modified. `progress.md` was not modified. Task 5 was not started.

## Residual risks

- The provider-only governance composition remains backward-compatible and creates the service when an explicit public `GovernanceRepository` is supplied; REST/CLI wiring is intentionally deferred to Task 5.
- Pre-existing direct prepared-publication fixtures without a final service audit-chain marker retain their existing repository contract; service-generated publication bundles take the new in-transaction hash-chain check.

## Commit

Commit SHA: `724c84df` (amended only to record the final report SHA).
