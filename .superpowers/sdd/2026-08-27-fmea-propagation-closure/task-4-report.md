# Task 4 report: persist graph revisions and apply human edge decisions

## Outcome

Implemented Task 4 on `feat/interface-output-v1` from base `660131e7a03e08a378cf8bf086b32e3ddc59697f`.
The intended commit subject is:

`feat(fmea): review propagation graphs atomically`

No push, PR, external service, paid call, or subagent was used.

## RED/GREEN evidence

RED command from the brief:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_propagation_sqlite.py tests/unit/test_fmea_propagation_review.py tests/regression/test_fmea_propagation_idempotency.py -q
```

RED was confirmed during collection because `fmea_infrastructure.propagation_repository_sqlite` and `ConfirmPropagationCommand` did not yet exist.

Final GREEN command from the brief:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_propagation_sqlite.py tests/unit/test_fmea_propagation_review.py tests/unit/test_fmea_local_auth.py tests/regression/test_fmea_propagation_idempotency.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py -q
```

Result: `29 passed in 0.75s`.

Prior propagation regressions:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_propagation_service.py tests/integration/test_fmea_fuel_combustion_propagation_pack.py tests/regression/test_fmea_propagation_prompt_injection.py -q
```

Result: `18 passed in 0.29s`.

Additional verification passed:

- `ruff check --no-fix` on all changed Python files: all checks passed.
- `ruff format --check` on all changed Python files: 13 files already formatted.
- `python -m compileall -q fmea_application fmea_infrastructure tests`: passed.
- `git diff --check`: passed; only expected Git LF/CRLF warnings were emitted.

## Persistence, replay, and security evidence

- Additive migration `004_fmea_propagation_closure.sql` persists topology snapshots, runs, immutable graph revisions, ordered edges and paths, unresolved issues, edge decisions, and graph decisions. Schema versions remain `[1, 2, 3, 4]`; migrations 001-003 are unchanged.
- Confirmation requires a human actor with `propagation_reviewer`, the exact workspace, graph revision, optimistic record version, one decision for every edge, and acknowledgements for retained long/cyclic/high-risk/conflicting and related issue codes.
- Confirmation creates a child `CONFIRMED` revision with accepted edges and a parent link. Invalidation likewise creates an additive child `INVALIDATED` revision; graph payloads cannot be updated or deleted because migration 004 installs immutable triggers.
- Review and invalidation writes use canonical UUID idempotency scopes and canonical payload hashes. Each transaction writes the child state, decision rows, shared audit event, outbox event, and idempotency response together under `BEGIN IMMEDIATE`.
- Same-key/same-payload replay is exact, including after repository restart. Same-key/different-payload conflicts without additional writes. Rollback coverage verifies no partial decision, audit, outbox, or idempotency state remains after failure. The invalidation replay test also verifies replay occurs before dependency reload.
- Repository reads and writes carry explicit workspace predicates. Stored JSON is decoded through the strict existing codec with canonical round-trip and hash/identity checks; no pickle or permissive arbitrary JSON path was added.
- The generic graph validator remains unchanged and continues to reject `CONFIRMED` graphs. The separate `PropagationReviewService` is the persistence-backed human authority, while `PropagationAnalysisService` remains proposal-only.
- `build_workspace_propagation_runtime` composes the persisted review service and repositories. Local loopback auth now returns `reviewer`, `risk_reviewer`, and `propagation_reviewer`; disabled or non-loopback production paths remain fail-closed.

## Files

Task 4 production files:

- `fmea_infrastructure/migrations/004_fmea_propagation_closure.sql`
- `fmea_infrastructure/propagation_repository_sqlite.py`
- `fmea_application/ports.py`
- `fmea_application/propagation_service.py`
- `fmea_infrastructure/composition.py`
- `fmea_infrastructure/local_auth.py`

Tests and public exports/support:

- `tests/integration/test_fmea_propagation_sqlite.py`
- `tests/unit/test_fmea_propagation_review.py`
- `tests/unit/test_fmea_local_auth.py`
- `tests/regression/test_fmea_propagation_idempotency.py`
- `tests/fmea_propagation_fixtures.py`
- `tests/conftest.py`
- `fmea_application/__init__.py`
- `fmea_infrastructure/__init__.py`

## Self-review and concerns

- Review dependency resolution uses persisted, workspace-scoped topology snapshots; it does not silently fall back to a live unscoped topology source.
- Server timestamps remain stored in immutable graph/audit rows but are excluded from semantic retry payload hashes so a retry does not become a false payload conflict solely because a new clock value was generated.
- The pre-existing shared `idempotency_records` table has no separate workspace column. Its canonical scope key includes workspace, actor, command, resource path, and key hash, and all propagation replay checks revalidate the workspace-bound decision, audit, graph, and outbox rows.
- Task 3 assistance-suggestion persistence remains its existing operation. Task 4 confirmation and invalidation themselves are atomic across propagation state, decisions, audit, outbox, and idempotency as required.
