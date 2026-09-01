# FMEA Migration Authority Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make governance migration acceptance recursively enforce the same revision, approval-submission, and approval-decision authority chains required by runtime publication replay, so unsafe version-7 and version-8 databases cannot advance to version 9.

**Architecture:** Keep migration SQL `005` through `009` immutable. The connection-local migration UDF will reuse the runtime repository's connection-level dependency-chain verifier through a late import executed only when the UDF runs, avoiding module-import cycles and preventing a second copied authority predicate from drifting again. Real SQLite tests will corrupt each publication dependency chain in an internally consistent way and prove the pending migration transaction leaves version 7 or 8 and all shared authority rows byte-for-byte unchanged.

**Tech Stack:** Python 3.11+, SQLite/WAL, application-defined SQLite functions, strict canonical JSON, SHA-256, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-08-27-full-fmea-modular-product-design.md` and Task 3 of `docs/superpowers/plans/2026-08-27-fmea-governance-closure.md`

## Global Constraints

- Governance starts at the immutable FMEA boundary and never calls `retrieval_engine`, `kg_pipeline`, `rag_orchestrator`, or a GraphRAG backend.
- Published revisions, manifests, snapshots, audit events, outbox events, and idempotency responses remain immutable.
- Every accepted migration must be replay-safe under the same authority rules used by runtime `replay_publication`.
- Unsafe version-7 data must remain exactly at version 7; unsafe version-8 data must remain exactly at version 8. No partial version-9 table, trigger, index, or shared-chain mutation may survive.
- Safe reconstructable version-7 data must still upgrade to version 9 and replay revision and publication successfully.
- Migration files `005` through `009` are checksum-stable and must not be edited. Do not add migration `010`.
- Reuse the existing shared `fmea_audit_events`, `fmea_outbox_events`, `idempotency_records`, and `fmea_governance_event_bindings`; create no parallel authority store.
- Preserve manifest/snapshot totality, workspace isolation, strict canonical JSON, finite values, duplicate-key rejection, hash verification, and the legacy `fmea_rows.publication_status` CHECK.
- Scope is persistence remediation only. Do not implement Task 4 services, auth, REST, CLI, export, UI, RAG, or GraphRAG behavior.
- Use only focused negative tests and the existing persistence/contract matrices; do not run the full repository test suite.

---

### Task 1: Reuse runtime dependency-chain verification during migration acceptance

**Files:**
- Modify: `fmea_infrastructure/governance_migration_validation.py`
- Test: `tests/integration/test_fmea_governance_sqlite.py`

**Interfaces:**
- Consumes: `GovernanceRepositorySQLite._verify_persisted_dependency_chain(connection, kind, workspace_id, resource_id)` for `revision`, `approval_submission`, and `approval`.
- Produces: migration UDF acceptance that rejects any publication whose persisted revision/submission/approval authority chain would fail runtime publication replay.

- [ ] **Step 1: Write real-SQLite publication dependency corruption tests**

Add a parameterized helper that initializes a database through version 7 or 8, persists one complete publication, then corrupts exactly one dependency kind from this literal set:

```python
DEPENDENCY_KINDS = ("revision", "approval_submission", "approval")
STARTING_VERSIONS = (7, 8)
```

For each pair, change the dependency authority DTO and its outbox payload consistently, recompute canonical authority JSON, audit/outbox/idempotency payload hashes, and leave the persisted dependency row semantically divergent from its event payload. Snapshot the schema version, dependency authority row, audit row, outbox row, event binding, idempotency row, publication row, and migration staging-object names before initialization.

```python
@pytest.mark.parametrize("starting_version", (7, 8))
@pytest.mark.parametrize("dependency_kind", ("revision", "approval_submission", "approval"))
def test_migration_009_rejects_publication_dependency_chain_divergence_atomically(
    tmp_path: Path,
    starting_version: int,
    dependency_kind: str,
) -> None:
    path = tmp_path / f"unsafe-{dependency_kind}-v{starting_version}.sqlite3"
    _initialize_through(path, starting_version)
    persisted = _persist_publication_migration_fixture(path)
    _tamper_publication_dependency_chain_consistently(
        path,
        persisted,
        dependency_kind=dependency_kind,
        clear_replay_metadata=starting_version == 7,
    )
    before = _publication_dependency_migration_probe_state(path, persisted, dependency_kind)

    with pytest.raises(
        (sqlite3.IntegrityError, sqlite3.OperationalError),
        match="authority|replay|binding|CHECK",
    ):
        SqliteGovernanceRepository(path).initialize()

    after = _publication_dependency_migration_probe_state(path, persisted, dependency_kind)
    assert after == before
    assert after[0] == (starting_version,)
    assert after[-1] == ()
```

Keep test-only mutation and snapshot helpers in `tests/integration/test_fmea_governance_sqlite.py`; do not add mutation helpers to production classes. Derive expected version and unchanged-row tuples directly from captured SQLite rows, not from production validators.

- [ ] **Step 2: Run the focused node and confirm RED**

Run:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_sqlite.py::test_migration_009_rejects_publication_dependency_chain_divergence_atomically -q
```

Expected: six failing cases. Each failure must be `DID NOT RAISE` or equivalent evidence that version 9 was accepted; fixture, SQL, import, and cleanup errors are not acceptable RED evidence.

- [ ] **Step 3: Reuse the runtime dependency verifier inside the migration UDF**

In the publication branch of migration validation, after the persisted dependency DTO rows and cross-table lineage have been validated, call one small helper for all three runtime chains:

```python
def _verify_publication_dependency_authority_chains(
    connection: sqlite3.Connection,
    *,
    workspace_id: str,
    revision_id: str,
    submission_id: str,
    approval_id: str,
) -> None:
    # Late import is required: repository_sqlite imports this migration module.
    from .governance_repository_sqlite import GovernanceRepositorySQLite

    for kind, resource_id in (
        ("revision", revision_id),
        ("approval_submission", submission_id),
        ("approval", approval_id),
    ):
        GovernanceRepositorySQLite._verify_persisted_dependency_chain(
            connection,
            kind,
            workspace_id,
            resource_id,
        )
```

Invoke this helper only after the decoded publication and dependency rows have been bound to the actual workspace-qualified database rows. Let `ValueError`, strict-JSON errors, and SQLite errors flow into the existing UDF fail-closed return path. Do not weaken or duplicate `_verify_persisted_dependency_chain`, and do not open another connection.

- [ ] **Step 4: Run focused GREEN and mutation checks**

Run the new six-case node together with the existing safe-upgrade, revision-ID divergence, authority/outbox divergence, and manifest/snapshot totality nodes. Expected: all selected cases pass.

Mentally mutate each runtime call by removing `revision`, `approval_submission`, or `approval`; the parameterized test for that exact kind must fail. Confirm unsafe version-7 and version-8 fixtures retain their pre-migration schema versions and row snapshots.

- [ ] **Step 5: Run the scoped persistence and contract matrices**

Run:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py -q
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py -q
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_source.py -q
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m pytest tests/integration/test_fmea_propagation_sqlite.py::test_propagation_migration_is_additive_and_creates_required_schema -q
```

Expected: all selected tests pass with no deselection and the exact migration set remains `[1, 2, 3, 4, 5, 6, 7, 8, 9]`.

- [ ] **Step 6: Run static, compile, migration-stability, and diff checks**

Run:

```powershell
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m ruff check fmea_infrastructure/governance_migration_validation.py tests/integration/test_fmea_governance_sqlite.py
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m ruff format --check fmea_infrastructure/governance_migration_validation.py tests/integration/test_fmea_governance_sqlite.py
$env:PYTHONPATH='.;tests'; .venv\Scripts\python.exe -m compileall -q fmea_infrastructure/governance_migration_validation.py fmea_infrastructure/governance_repository_sqlite.py fmea_infrastructure/repository_sqlite.py tests/integration/test_fmea_governance_sqlite.py
git diff --check
git diff --exit-code -- fmea_infrastructure/migrations/005_fmea_governance_closure.sql fmea_infrastructure/migrations/006_fmea_governance_integrity.sql fmea_infrastructure/migrations/007_fmea_governance_lineage.sql fmea_infrastructure/migrations/008_fmea_governance_totality.sql fmea_infrastructure/migrations/009_fmea_governance_manifest_totality.sql
```

Expected: Ruff, formatting, compileall, whitespace, and migration-stability checks pass.

- [ ] **Step 7: Commit the remediation**

```powershell
git add fmea_infrastructure/governance_migration_validation.py tests/integration/test_fmea_governance_sqlite.py
git commit -m "fix(fmea): validate migrated publication authority chains"
```

The implementation report must include the RED command and actual six-case failure, the exact GREEN commands/counts, proof that safe version-7 replay still succeeds, proof that unsafe version-7/version-8 state is unchanged, migration checksum stability, and any concern about the late-import/runtime-helper dependency.
