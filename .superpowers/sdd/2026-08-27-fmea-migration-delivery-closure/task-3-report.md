# Task 3 Delivery Report

## Subpackage A — registry and application service

Status: implemented and locally verified within the assigned unit-test boundary.

Owned implementation:

- `fmea_infrastructure/migration_registry.py`: explicit in-memory adapter allowlist; deterministic single-path resolution; missing, ambiguous, cyclic, and invalid graphs fail closed; no discovery or dynamic imports.
- `fmea_application/migration_service.py`: frozen provider-neutral commands, candidates, prepared migration units, and results; bounded ID/hash/idempotency validation; human `template_admin` authority; exact-workspace source revision and target DomainPack checks; deterministic dry-run report persistence/replay; explicit confirmation preconditions; one prepared atomic unit delegated to `MigrationRepository`.
- `fmea_application/ports.py`: typed `MigrationAdapter` and `MigrationRepository` boundaries without SQLite or composition concerns.
- `tests/unit/test_fmea_migration_service.py`: focused RED/GREEN coverage for authority, source staleness, deterministic replay, graph ambiguity/cycles, bounded contracts, safe error normalization, exact report confirmation, atomic-unit delegation, and final adapter target-hash mismatch.

Target-hash TDD evidence:

1. Fixture-error reproduction: `10 passed, 1 failed`; missing `dataclasses.replace` caused a test-double `NameError`, correctly normalized as `FMEA_MIGRATION_ADAPTER_FAILED`.
2. Semantic RED after restoring the import: `10 passed, 1 failed`; wrong target hash was accepted (`DID NOT RAISE`).
3. GREEN after preserving and validating the final candidate's full target identity before aggregation: `11 passed`.

Scoped verification:

- `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_migration_service.py -q` → `11 passed in 0.14s`.
- `.venv\Scripts\python.exe -m ruff check fmea_application/migration_service.py fmea_application/ports.py fmea_infrastructure/migration_registry.py tests/unit/test_fmea_migration_service.py` → `All checks passed!`.
- `.venv\Scripts\python.exe -m ruff format --check fmea_application/migration_service.py fmea_application/ports.py fmea_infrastructure/migration_registry.py tests/unit/test_fmea_migration_service.py` → `4 files already formatted`.
- Staged diff scope before commit: exactly the four owned code/test files above; `git diff --cached --check` clean.

Commit: `2a5d76d0` (`feat(fmea): add deterministic migration service`).

## Subpackage B — remaining

Not implemented or verified by subpackage A:

- additive SQL migration `010_fmea_migration_delivery.sql`;
- SQLite `MigrationRepository` implementation and durable dry-run/confirmation replay;
- atomic child revision, risk/propagation invalidation, audit/outbox persistence, idempotency, and rollback behavior.

## Subpackage C — remaining

Not implemented or verified by subpackage A:

- composition/runtime wiring;
- ownership and execution of the existing integration/regression migration tests;
- combined Task 3 delivery, rollback, governance compatibility, and acceptance verification.

The existing untracked integration/regression test files were preserved untouched and excluded from this subpackage's commit.

## Subpackage B — implementation and verification

Status: implemented in the assigned live worktree; local commit is pending after the final verification pass.

Owned implementation:

- `fmea_infrastructure/migrations/010_fmea_migration_delivery.sql`: strictly additive delivery schema with the eight required tables, workspace-scoped identity constraints, canonical payload/hash columns, relational links to governance revisions/publications/snapshots, lifecycle checks, indexes, and immutable triggers for draft/candidate/decision/report/confirmation/artifact records.
- `fmea_infrastructure/delivery_repository_sqlite.py`: governance-compatible repository subclass implementing durable report persistence and `MigrationRepository`; report reads verify canonical JSON and plan hashes; confirmation creates deterministic child revision, confirmation, audit, outbox, governance binding, and idempotency completion inside one `BEGIN IMMEDIATE` transaction. Replay validates the complete persisted chain before returning `replayed=True`.
- `tests/integration/test_fmea_delivery_sqlite.py`: additive schema, deterministic dry-run, immutable child/invalidation, same-process replay, and repository-restart replay coverage.
- `tests/regression/test_fmea_migration_rollback.py`: fault at `migration.after_revision` proves child, confirmation, audit, outbox, event binding, and idempotency writes roll back while the source remains unchanged.

Verification:

- Requested focused suite: `18 passed in 1.24s`.
- Ruff check: passed for the owned Python files.
- Ruff format check: pending rerun after the final test-file formatting pass.
- Governance SQLite compatibility suite: `122 passed, 1 failed`; the only failure is the pre-existing test assertion expecting `MAX(schema_migrations)=9` after a fresh initialize, which is necessarily stale once additive migration 010 is present. No governance implementation file was changed.

Final B verification: the exact requested targeted suite completed with `18 passed in 2.60s`; Ruff check passed and Ruff format check reported `3 files already formatted`. No concrete failure required a code fix in this final pass.

Local commit: `684b5b20` (`feat(fmea): persist atomic migration delivery`). No push or PR was created.

## Subpackage C — composition and final integration

Status: implemented and verified in the shared checkout.

Owned implementation:

- `fmea_infrastructure/composition.py` now exposes a frozen `MigrationRuntime` containing the provider-neutral `MigrationService`, workspace-owned `SqliteFmeaDeliveryRepository`, explicit `MigrationRegistry`, injected `DomainPack` registry, and resolved template-registry root.
- `build_workspace_migration_runtime(...)` is injection-first: it accepts the workspace, a DomainPack registry, and an explicit adapter iterable; it performs no dynamic discovery, imports no hidden adapters, initializes the delivery repository, and wires the service without changing ordinary RAG, RAG-only, GraphRAG-only, hybrid, review, risk, propagation, or governance builders.
- `tests/unit/test_fmea_migration_composition.py` is the single focused composition test. It proves workspace database wiring, explicit adapter registration, and callable compatibility plus dry-run paths.
- `tests/integration/test_fmea_governance_sqlite.py` changed only the stale latest-schema assertion from `9` to `10`, after the fresh controller evidence showed it was the sole Step 4 compatibility failure.

Final verification:

- Exact Task 3 Step 4 suite → `150 passed in 28.15s`.
- Focused composition test → `1 passed in 0.18s`.
- Ruff check on modified Python files → passed after import ordering was applied; format check → `3 files already formatted`.
- `git diff --check` → clean; no service, repository, SQL, API, or CLI files were changed in C.

Task 3 caveat: API/CLI route exposure is intentionally not part of Task 3. Callers must provide the adapter allowlist and DomainPack registry explicitly; a default migration adapter discovery mechanism is deliberately not provided.

## Contract fixture follow-up after `a91e9128`

Scope: test-only alignment for the composition fixture; no production code changed.

- Root cause: the old fake DomainPack registry returned the target `2.0.0` hash for the source `1.0.0` lookup, and the fake adapter used the pre-`a91e9128` identity-only `MigrationCandidate` contract.
- RED evidence: focused composition test failed with `FMEA_MIGRATION_SOURCE_PACK_STALE` (`1 failed in 0.26s`).
- Fix: the registry now returns exact source and target hashes, while the adapter materializes a target `FmeaRevision` by preserving the source revision's row/domain state, changing only the DomainPack identity, and allowing the fixture builder to recompute the canonical revision hash.
- GREEN evidence: focused composition test `1 passed in 0.18s`; migration service unit suite `17 passed in 0.07s`.
- Static evidence: Ruff check passed and Ruff format reported `1 file already formatted` for the owned test file.

## Review round 1 — subpackage A application/domain fixes

Status: implemented for C1, I2, I3, and I4 in the authorized application/domain scope. Persistence finding I1 and schema finding M1 remain assigned to subpackage B.

Contract changes for subpackage B:

- `MigrationReport` now carries `source_domain_pack_identity`, `target_domain_pack_identity`, and `target_revision_hash`; all three participate in its canonical `report_hash`.
- `MigrationCandidate` now carries a complete, internally hashed `target_revision: FmeaRevision`; `target_domain_pack_identity` is derived from that revision.
- `PreparedMigration.candidate.target_revision` is the sole transformed revision payload for child construction. The repository must replace only server-owned child metadata (`revision_id`, parent ID/hash, and `created_at`) and recompute the child revision hash. It must preserve transformed analysis/row/risk/template/scoring/propagation/evidence/readiness fields from the candidate.
- The repository must persist and replay-check the report's source/target pack triples and target revision hash alongside its existing source revision/report bindings.

TDD and focused evidence:

- Initial review RED after materialized-candidate/source-registry/two-hop tests: `12 failed, 5 passed`.
- Narrow target-revision report-binding RED: `1 failed, 16 passed` because `MigrationReport.target_revision_hash` was absent.
- GREEN migration-service unit suite: `17 passed in 0.08s`.
- Source registry absence and hash mismatch fail with `FMEA_MIGRATION_SOURCE_PACK_MISSING` and `FMEA_MIGRATION_SOURCE_PACK_STALE` respectively.
- Every adapter receives the preceding materialized revision; each result is checked for revision hash integrity, workspace/analysis scope, registered edge identity, and exact registry content hash before the next hop.
- Confirmation forwards the validated final candidate unchanged in `PreparedMigration`; no aggregation/rebinding step discards transformed domain state.

Files intentionally unchanged in this review fix: SQLite delivery repository, migration 010, composition, integration/regression delivery tests, governance test, registry implementation, and unrelated application ports.

## Review round 3 — I7 application contract fix

Status: implemented and verified in the application/port unit boundary. SQLite persistence adaptation remains assigned to subpackage B.

Port and command contract changes:

- `MigrationRepository.get_migration_report(...)` now requires the complete canonical dry-run `MigrationCommand` as the keyword-only `command` argument.
- A valid stored dry run bound to a different canonical command is signaled with the provider-neutral `MigrationReportRequestConflict`; `MigrationService` maps it to `FMEA_MIGRATION_IDEMPOTENCY_CONFLICT` without exposing persistence details.
- `ConfirmMigrationCommand` now carries the complete frozen `dry_run_command` separately from its own confirmation `idempotency_key`. Same-process confirmation passes the cached original command; fresh-process confirmation passes this explicit original command. The confirmation key is never substituted for the dry-run request key.

Subpackage B must validate the stored run's canonical request JSON/hash and request-idempotency-key hash against the supplied command before returning its report. It must raise `MigrationReportRequestConflict` only for a valid stored request bound to a different command; malformed/corrupt persisted data and storage failures must retain their existing safe normalization.

TDD evidence:

- RED: fresh service with a K1 report accepted the same migration semantics under K2 (`DID NOT RAISE`; focused test `1 failed`).
- GREEN: focused I7 test `1 passed`; full migration-service unit suite `18 passed in 0.09s`.
- The fake repository stores the exact command alongside each report and requires command equality on every lookup. The K1/K2 conflict occurs before adapter execution.

Files intentionally untouched: SQLite delivery repository, migration 010, composition, integration/regression tests, governance tests, registry, and domain report schema.

## Review round 1 — subpackage B persistence fixes

Status: implemented and locally verified in the authorized persistence scope.

Persistence changes:

- Migration reports now round-trip the complete source DomainPack identity, target DomainPack identity, and materialized target revision hash. The same values are stored as relational columns on migration runs, reports, and confirmations and are compared against the command, prepared candidate, and canonical report before any confirmation write.
- Child revisions are rebuilt from `PreparedMigration.candidate.target_revision`, not from the source revision. Only the server-owned child ID, exact parent ID/hash, confirmation timestamp, cleared risk versions, cleared propagation ID/hash, and recomputed revision hash replace candidate values.
- Replay now validates the completed run request JSON/hash and terminal state before validating report, confirmation, child authority, idempotency, audit, outbox, event binding, and stored response. Corrupted durable state fails closed.
- Migration 010 adds workspace-composite source revision foreign keys to runs, reports, and confirmations; run links to report, child revision, and idempotency evidence; complete hash checks; immutable run-binding protection; one-way dry-run terminal transitions; terminal immutability; and no-delete protection. Migrations 001-009 remain byte-for-byte untouched.
- Confirmation remains one `BEGIN IMMEDIATE` transaction. Child revision, confirmation, audit, outbox, event binding, idempotency completion, and run transition commit or roll back together.

Focused adversarial coverage:

- fresh-process target hash drift is rejected with zero child and zero completion event;
- transformed row/template identities from the materialized target revision appear in the child;
- corrupted completed-run replay is rejected without a second child, event, or confirmation;
- all three delivery tables expose workspace-composite source revision foreign keys, and a cross-workspace run insert fails;
- `migration.after_revision` fault injection leaves the run at `dry_run` and leaves zero confirmation-side residue; `PRAGMA foreign_key_check` remains empty.

Final verification:

- Exact requested suite: `27 passed in 1.67s`.
- Ruff check: `All checks passed!` for the three owned Python files.
- Ruff format check: `3 files already formatted`.
- `git diff --check`: clean apart from informational Windows LF-to-CRLF warnings.

## Review round 2 — subpackage B replay metadata fixes

Status: I5 and I6 implemented in the authorized persistence scope; application, domain, composition, and unrelated tests remain unchanged.

Persistence design:

- Migration 010 now stores `request_idempotency_key_hash` independently on both the migration run and immutable migration report. The run request is decoded through `MigrationCommand`, which validates the raw key as a canonical lowercase UUID, and its canonical JSON hash plus key hash must agree with both durable copies.
- Same-process confirmation requires the complete durable request to equal `PreparedMigration.dry_run_command`. The existing fresh-process service reconstruction uses the confirmation key in its temporary dry-run command, so the repository permits only that explicitly identifiable key substitution while requiring every semantic field to match; the immutable report key hash remains authoritative for the original dry-run request.
- The dry-run key hash is included in the immutable confirmation/outbox payload. It is distinct from the confirmation command key, whose hash continues to derive the confirmation `IdempotencyScope` and is checked through confirmation, audit, outbox, event binding, and idempotency rows.
- Confirmation replay now binds dedicated `created_at` columns for the confirmation, child revision, audit event, and outbox event to their decoded canonical object and `MigrationReport.created_at` values. Existing run/report timestamp checks remain active.
- The complete replay verifier is also executed after all normal-confirmation writes and before the single `BEGIN IMMEDIATE` transaction commits, so the normal and replay paths share the same metadata-chain checks.

TDD evidence:

- RED: replacing the persisted dry-run UUID with another valid UUID and recomputing the request hash still replayed; each of four isolated confirmation/child/audit/outbox timestamp mutations also replayed (`5 failed`).
- Focused GREEN: the five adversarial cases passed (`5 passed in 1.09s`).
- Final exact target suite: `31 passed in 2.70s`.
- Ruff check: `All checks passed!`; Ruff format: `3 files already formatted`; `git diff --check` clean apart from informational Windows LF-to-CRLF warnings.

## Review round 3 — subpackage B I7 persistence adaptation

Status: implemented and verified in the authorized SQLite persistence and delivery-test scope.

Persistence changes:

- `SqliteFmeaDeliveryRepository.get_migration_report(...)` now implements the keyword-only `command: MigrationCommand` port and validates the canonical durable run request before returning a report.
- Durable validation reconstructs the stored `MigrationCommand`, validates its canonical lowercase UUID, canonical JSON shape/value, request hash, request-key hash, command columns, workspace/migration/run identity, actor binding, report linkage, timestamps, and dry-run/confirmed lifecycle state.
- Validation order distinguishes corruption from reuse: malformed or internally inconsistent durable state remains a safe storage failure, while a valid durable command that differs from the supplied command raises `MigrationReportRequestConflict` for service-level `FMEA_MIGRATION_IDEMPOTENCY_CONFLICT` mapping.
- Confirmation tests now pass the exact original `dry_run_command` separately from the confirmation idempotency key. The obsolete fresh-process key-substitution allowance was removed from repository replay validation.
- Migration 010 required no change because separate immutable request-key hashes already exist on runs and reports.

TDD and verification evidence:

- RED: the new fresh-process persistence test failed with `FMEA_MIGRATION_STORAGE_UNAVAILABLE` because the SQLite repository still exposed the old two-argument report lookup.
- GREEN: the focused K1/K2 test passed; K1 replays from a new service/repository instance, while K2 returns `FMEA_MIGRATION_IDEMPOTENCY_CONFLICT` and leaves run, report, confirmation, revision, audit, and outbox row counts unchanged.
- Exact target suite: `33 passed in 2.64s`.
- Ruff check: `All checks passed!`; Ruff format: `3 files already formatted`; `git diff --check` clean apart from informational Windows LF-to-CRLF warnings.
