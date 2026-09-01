# Phase 3 FMEA governance final fix report

## Scope

This fix addresses exactly the two Important findings from the final review:

- I-1: repository-level supersession traversal was not bounded even though the service had a finite depth guard.
- I-2: `commit_publication` could auto-create the revision, approval submission, approval decision, and their governance dependencies from a caller-supplied `PreparedPublication`.

No migration 010, Phase 4 work, production bypass flag, or test-only bypass flag was added.

## RED evidence

The two new repository regressions were run before the production changes:

```text
tests/integration/test_fmea_governance_sqlite.py
2 failed, 123 deselected in 0.63s
```

The failing tests were:

- `test_publication_requires_persisted_authority_chain_without_auto_minting`
- `test_supersession_repository_bounds_depth_and_visited_nodes_before_unbounded_growth`

The first failure demonstrated that a clean authoritative-analysis database accepted a direct publication commit and minted missing authority dependencies. The second demonstrated that a direct repository supersession commit accepted a forged lineage beyond the intended finite traversal limit.

## GREEN implementation

### I-1 bounded repository supersession traversal

- Added the shared semantic maximum `MAX_SUPERSESSION_TRAVERSAL = 64` in the core governance module.
- The service and SQLite repository use the same named maximum.
- Repository `_would_cycle` now tracks both traversal depth and visited nodes, and fails closed with `FMEA_GOVERNANCE_SUPERSESSION_INVALID` before further lineage queries can grow without bound.
- Existing cycle rejection remains active with the same stable governance code.
- Short valid supersession chains remain supported.

### I-2 persisted publication authority

- Removed production `_persist_publication_dependencies` and its now-dead dependency-only helpers.
- `commit_publication` now requires the revision, approval submission, and approved human decision to already exist and match the prepared DTOs exactly.
- The repository validates the persisted authority chain, hashes, record versions, actor types and identities, audit/outbox/event bindings, idempotency records, and replay responses before writing publication state.
- Publication fixtures now explicitly commit revision -> submission -> approval through repository methods before publication. The production repository port was not widened with a bypass parameter.

## Verification evidence

The requested focused checks passed:

```text
Controller fresh targeted repository/service/lifecycle matrix: 159 passed in 29.19s
tests/integration/test_fmea_governance_sqlite.py: 123 passed in 34.06s
Task 6 acceptance/security/atomic tests: 32 passed in 27.02s
Migration stability filter: 19 passed, 104 deselected in 3.74s
```

The independent acceptance runner and verifier also passed:

```text
run_fmea_governance_acceptance.py: {"status":"passed","artifact_id":"acceptance-8c96e9e4-4ff8-4796-afc4-ab73199b2ee9"}
verify_fmea_governance_acceptance.py --latest: {"status":"passed","error_code":null}
```

Scoped static checks passed after formatting the four changed Python files:

```text
ruff check: All checks passed!
ruff format --check: 4 files already formatted
git diff --check: passed (line-ending warnings only)
```

The production FMEA governance modules contain no `_persist_publication_dependencies`, dependency-only helper, bypass, or auto-mint symbol.

## Residual risks

- Verification is intentionally scoped to the repository/service/lifecycle/Task 6 and migration checks requested here; unrelated project suites were not rerun.
- The implementation is SQLite-specific at the repository boundary tested in this phase; distributed database behavior and operational migration deployment remain outside this fix.
- A malformed pre-existing database still fails closed with the stable governance state code, but database repair/backfill remains the responsibility of migration-owned tooling rather than runtime publication.
