# Task 4 subpackage A report — canonical JSON exporter

## Scope

- Added `fmea_infrastructure/export_json.py` only.
- Added `tests/unit/test_fmea_export_json.py` only.
- No application service, port, composition, repository, artifact store, narrative generator, or unrelated test files were modified.
- No database, model, network, filesystem, or clock access is performed by the exporter.

## TDD evidence

1. RED: the new test module failed during collection with `ModuleNotFoundError` because `fmea_infrastructure.export_json` did not exist.
2. GREEN: after the minimal exporter implementation, the required command passed:

   `.venv\\Scripts\\python.exe -m pytest tests/unit/test_fmea_export_json.py tests/unit/test_fmea_snapshot_contracts.py -q`

   Result: `33 passed`.

3. Static checks passed:

   - `.venv\\Scripts\\ruff.exe check fmea_infrastructure/export_json.py tests/unit/test_fmea_export_json.py`
   - `.venv\\Scripts\\ruff.exe format --check fmea_infrastructure/export_json.py tests/unit/test_fmea_export_json.py`

## Contract and projection

`CanonicalJsonExporter` exposes `format == "json"`, `media_type == "application/json"`, and `render(snapshot) -> bytes`.

The output is a compact UTF-8 JSON object with sorted keys and one trailing newline. Its only schema marker is the top-level `schema_version` value `graphrag.fmea.export.v1`. The remaining keys are the complete normalized snapshot projection: snapshot/workspace/analysis/revision/publication/manifest identities, rows and row count, risk records, propagation, evidence summary, decision summary, version manifest, unresolved readiness items, audit summary, snapshot hash, and immutable creation timestamp. DomainPack/template/scoring/propagation identities and retrieval provenance remain inside `version_manifest` exactly as supplied by the normalized snapshot contract.

Before encoding, the exporter revalidates JSON compatibility, finite numbers, bounded depth/string/collection/object sizes, path/URI markers, private-field markers, and the snapshot content hash. Failure messages are stable and do not include object representations or private values. Projection is built from fresh JSON values, so rendering does not mutate the frozen snapshot.

The fixture hash assertion is:

`b6b8ebdab2777fd3752226867e2a22c6c28b0c6934071c6efac644043ef76a47`

## Handoff to later subpackages

- B (Office adapters) should parse this flat semantic envelope and preserve the same identity/hash/row/evidence/risk/propagation/readiness fields. It should not recalculate or re-source values.
- C (service/store/composition) should treat the returned bytes and their SHA-256 as the canonical payload, bind them to an export run/manifest, and keep storage atomic. This subpackage intentionally does not create export runs, artifacts, narrative suggestions, or runtime wiring.
- The exporter is provider-neutral and has no live DeepSeek or other model dependency; model-assisted narrative work belongs to the separate service/generator boundary.

# Task 4 subpackage B report — contained atomic artifact store

## Scope

- Added `fmea_infrastructure/artifact_store.py` only for production code.
- Added `tests/unit/test_fmea_artifact_store.py` only for focused coverage.
- No ports, export service, composition, repository, exporter, narrative, or unrelated tests were modified.
- This report is intentionally Git-ignored and is not part of the implementation commit.

## TDD and verification

1. RED: the focused test command failed at collection with `ModuleNotFoundError` because the artifact store did not exist.
2. GREEN: `.venv\\Scripts\\python.exe -m pytest tests/unit/test_fmea_artifact_store.py tests/unit/test_fmea_export_json.py -q` passed with `23 passed, 1 skipped`.
3. Static verification passed:

   - `.venv\\Scripts\\ruff.exe check fmea_infrastructure/artifact_store.py tests/unit/test_fmea_artifact_store.py`
   - `.venv\\Scripts\\ruff.exe format --check fmea_infrastructure/artifact_store.py tests/unit/test_fmea_artifact_store.py`
   - `.venv\\Scripts\\python.exe -m compileall -q fmea_infrastructure/artifact_store.py tests/unit/test_fmea_artifact_store.py`
   - `git diff --check`

The one skip is the symlink test on platforms where the test process cannot create a symlink. The same test remains active when symlink creation is available.

## Storage contract

`WorkspaceArtifactStore(root, workspace_id)` requires an absolute root, validates every workspace identity segment, and creates only the contained `workspace/artifacts`, `workspace/runs`, and internal reservation directories. `publish(run_id, filename, payload, manifest)` accepts exact bytes and a validated `ExportArtifactManifest`; it checks run, artifact, filename, format, media type, byte length, and SHA-256 before allocating a temporary artifact.

The final layout is:

```text
<root>/<workspace_id>/artifacts/<artifact_id>/<filename>
<root>/<workspace_id>/artifacts/<artifact_id>/.manifest.json
<root>/<workspace_id>/runs/<run_id>/.latest.json
```

The payload and canonical manifest are written into a sibling temporary directory, file-synced, directory-synced, independently read back, and then atomically renamed. The latest pointer is a canonical JSON file replaced only after final verification. Reads revalidate containment, ordinary-file type, canonical manifest bytes, identity, length, and hash. Final directories are never overwritten; identical replay returns the verified existing `StoredArtifact`, while any identity/content/manifest difference raises a stable conflict.

The implementation rejects absolute/separator/dot-traversal/reserved names, malformed bytes/manifests, wrong workspaces, symlink/reparse components, unexpected directory entries, and oversized payloads. Fault hooks cover staged-write, temp verification, final rename, and latest-pointer boundaries; the fsync seam is injectable. Cleanup tracks the exact file identity created by the operation and never follows a replaced link or unrelated path. A fault before latest replacement leaves the prior pointer intact.

## Handoff to C

- Use `WorkspaceArtifactStore` as the concrete implementation behind the future `ArtifactStore` port.
- `publish`, `get`, and `latest` return immutable `StoredArtifact` values. Use `.payload`, `.manifest`, `.path`/`.payload_path`, and `.manifest_path`; `__fspath__` is provided for adapters that still need a path-like result.
- Store errors expose `.code` and bounded messages. Preserve the code-to-problem-details mapping in the application boundary; do not serialize exception causes.
- The artifact store intentionally has no export-run database state, publication authorization, or API/CLI route. C must bind the returned manifest/run state to the delivery repository and only mark an export run complete after `publish` returns a verified result.

## C1: durable export application service

Implemented the provider-neutral export boundary in `fmea_application/export_service.py`.
`StartExportCommand` is frozen and bounded, carries the exact workspace/revision/snapshot/publication identity and hash, explicit format, draft-preview flag, idempotency key, and a validated server-owned filename or filename token. `ExportService` accepts only human actors with `exporter`, `publisher`, or `admin` authority. It validates an exact snapshot, publication lineage/lifecycle, and export eligibility before rendering a published export; draft preview is explicit and has no publication identity.

The service selects only injected exporters and verifies their format/media type and returned `bytes`. It publishes through the existing `WorkspaceArtifactStore`, performs a second store read-back, and sends the immutable manifest to SQLite only after both verifications pass. It never invokes a model and leaves the C2 narrative-suggestion seam at the exporter injection boundary.

Extended the unreleased export section of migration 010 with request/idempotency, actor, audit/outbox bindings, canonical request hashes, strict lifecycle checks, immutable binding/terminal triggers, and artifact SHA-256 checks. `SqliteFmeaDeliveryRepository` now strictly reconstructs and validates canonical `ExportRun` and `ExportArtifactManifest` rows. Reservation, queued-to-running, terminal failure, and final success are persisted with legal chronology; successful run, manifest, idempotency completion, audit, and outbox records commit in one SQLite transaction.

The crash boundary is intentional: a failure before final DB commit leaves the run `running` and the immutable file available. A retry with the same idempotency key first reconciles the verified `.latest.json` artifact and completes the database exactly once; a mismatched artifact fails closed. Renderer/store failures persist bounded `failed` runs without an artifact row. Reads of a succeeded run always reverify the database binding and `ArtifactStore.get`, so a missing, corrupt, or unbound file is never exposed as a valid success.

## C1 TDD evidence

- RED: the new integration module initially failed because `fmea_application.export_service` did not exist.
- GREEN: `.venv\\Scripts\\python.exe -m pytest tests/integration/test_fmea_export_runs.py tests/unit/test_fmea_export_json.py tests/unit/test_fmea_artifact_store.py tests/unit/test_fmea_snapshot_contracts.py -q` passed with `55 passed, 1 skipped`.
- Delivery regression: `.venv\\Scripts\\python.exe -m pytest tests/integration/test_fmea_delivery_sqlite.py tests/regression/test_fmea_migration_rollback.py -q` passed with `15 passed`.
- Static checks passed for all owned source/tests: Ruff check, Ruff format check, compileall, and `git diff --check`.

## Handoff to C2

C2 should inject any narrative-aware exporter or pre-render suggestion provider through `SnapshotExporter`/`ExportService` composition. It must preserve the C1 rule that narrative suggestions remain provisional input, the normalized snapshot remains the sole semantic source, and the final artifact manifest/hash is produced and verified by the same lifecycle. C2 should not alter SQLite lifecycle transitions, artifact-store semantics, publication eligibility, or the `ExportService` success/reconciliation boundary.

## C2: export narrative suggestion and composition finalization

Implemented only the narrative-assistance and runtime-composition boundary. The durable export lifecycle, SQLite delivery repository, migration 010, canonical JSON exporter, artifact store, Office/API/CLI layers, and retrieval query paths were left unchanged.

### Contract and safety

- Added frozen `ExportNarrativeDraft`, `ExportNarrativeSection`, `ExportNarrativeClaim`, `ExportNarrativeRequest`, `ExportNarrativeGenerationResult`, and `ExportNarrativeSuggestion` contracts.
- `ExportService.suggest_narrative` accepts the exact `NormalizedFmeaSnapshot` and a model `ActorContext`, builds a bounded projection, and returns the shared `AssistanceSuggestion` with `EXPORT_NARRATIVE_DRAFT`, `applied=False`.
- The method does not call the repository or artifact store and does not mutate the snapshot. Adoption, editing, and persistence remain future human-revision workflow responsibilities.
- Projection rows, evidence, and unresolved items are count- and item-bounded; source/workspace/document identities are replaced with safe aliases. Host paths, URI-like values, credentials, private IDs, and full source documents are excluded.
- Generator validation is exact-schema, finite-JSON, size-bounded, duplicate-free, and reference-closed against the supplied projection. Provider/configuration failures map to stable public error codes without leaking causes.

### Shared pipeline reuse

`EnvironmentExportNarrativeGenerator` lazily wires the existing configured DeepSeek gateway, `StructuredGenerationPipeline`, strict candidate/critic codecs, and generic candidate validator. `StructuredExportNarrativePipeline` supplies the narrative template and bounded projection as a normal `GenerationRunRequest`, preserving the existing Flash generation -> `deepseek-v4-pro` critic -> at most one repair flow. The final accepted or needs-review critic/repair trace and hashes are bound into the immutable assistance envelope; no model result is automatically applied.

### Composition and verification

Added frozen `ExportRuntime` and `build_workspace_export_runtime` with explicit exporter allowlisting, a workspace-contained default artifact root, injectable clock/id factory, optional narrative generator injection, and lazy environment/default generator construction. `__all__` exports the new runtime and builder.

TDD and verification:

- Narrative RED: focused collection failed before the new contracts existed; GREEN: `10 passed`.
- Task 4 Step 4 suite: `68 passed, 1 skipped`.
- Task 3 delivery regression: `15 passed`.
- Owned-file Ruff check, format check, compileall, and diff checks passed.
- No live network is used by normal tests; the default environment generator constructs the gateway only when generation is requested.

## C1 round-1 review closure: I-1, I-3, I-4

This follow-up supersedes the earlier C1 statement that Task 4 extended migration 010. Migration 010 is restored byte-for-byte to the accepted Task 3 blob at commit `99a73306` (`1062d952aef46fac45b4e09b1591f4bedbb46b3e`). All Task 4 export lifecycle columns, constraints, indexes, and triggers now live in additive migration 011.

Migration 011 safely rebuilds the two placeholder export tables when upgrading a fresh database or an empty database already initialized through v10. Because v10 rows lack actor, request, idempotency, audit, and outbox authority, 011 has an explicit named guard that aborts atomically when either legacy export table is non-empty. It does not infer or fabricate missing authority.

Every governance/export-repository read or mutation used by `start`, replay, `get_run`, and `get_artifact` is now translated to bounded application errors without exception causes or backend text. Provider results are type-checked and re-bound to the exact actor workspace, run, snapshot, revision, publication, manifest, lifecycle, eligibility, hash, format, preview, and filename requested.

Successful delivery now has a repository-owned chain verifier. In one SQLite snapshot it reconstructs the canonical run and artifact, exact request and idempotency scope, audit event, outbox event, and completed idempotency response. It verifies deterministic event IDs, actor/workspace/resource/command bindings, canonical payloads, dedicated request/outbox hashes, lifecycle timestamps, and all cross-links. The verifier runs inside the success transaction before commit and on every completed replay/read path; the application then re-verifies the immutable stored file. Missing or independently corrupted chain links fail closed.

Focused RED coverage was added for v10-to-v11 upgrade and guarded legacy rows, adversarial governance/query exceptions and wrong types, individual audit/outbox/idempotency removals or corruption, all completed read paths, and pre-commit verification rollback. GREEN evidence before final verification: export + Task 3 delivery/governance compatibility passed with `169 passed`.

Final targeted verification passed with `217 passed, 1 skipped` across Task 4 export runs, Task 3 delivery/governance compatibility and rollback, JSON export, artifact-store, and snapshot-contract suites. Owned-file Ruff check, Ruff format check, compileall, migration hash comparison, and `git diff --check` also passed.

## Artifact-store round-1 closure: I-2, M-1, M-2

This scoped follow-up changes only the filesystem artifact store and its focused/unit service-integration tests. It does not alter the export service, repository, migrations, composition, narrative, JSON exporter, or ports.

The latest-pointer `os.replace` is now the explicit publication commit point. If the run-directory sync or `after_latest` hook raises after replacement, `publish` independently rereads the immutable final directory and latest pointer and compares their workspace/run/artifact/filename/manifest/payload bindings to the original request. It returns success only when both views are exact. If either view is missing, corrupt, or different, the bounded store error remains visible; pre-commit failures still remove only this operation's identity-matched final directory and preserve the previous latest pointer. A verified final not owned by the current cleanup path is not removed. Identical replay can also repair a missing latest pointer for a previously verified orphan final.

Cross-process reservations now use an exclusive artifact lock directory plus a canonical random owner token. Contenders use injected monotonic deadline and poll seams, re-read the final artifact while waiting, and converge when the committed bytes are identical. Different bytes remain an immutable conflict. A lock that does not complete within the bound returns `FMEA_ARTIFACT_BUSY` with `retryable=True`; stale locks are deliberately not auto-deleted because liveness cannot be proved portably. Release rereads the exact owner file and removes the reservation only when both file identity and token still match, so a replaced/foreign owner is preserved.

Coverage adds post-latest reconciliation, run-directory sync after pointer replacement, artifact-parent sync before latest, prior-latest preservation, missing-pointer replay repair, deterministic foreign-lock timeout, ownership-token replacement, a Windows `FILE_ATTRIBUTE_REPARSE_POINT` simulation that runs without symlink privilege, the retained real-symlink test, a real spawn-based two-process convergence test using bounded events, and an `ExportService` proof that post-latest faults finish and replay as `succeeded` without rerendering.

## Artifact-store round-2 closure: I8

Cleanup now carries the originally captured filesystem identity through every directory-tree, regular-file, owner-file, and reservation-directory removal. Recursive cleanup snapshots each child without following links, revalidates the parent identity before each child, passes each child's expected identity into the removal operation, aborts immediately on a mismatch/reparse/unexpected type, and removes a directory only after an identity-safe empty check.

On Windows, cleanup no longer performs `lstat` followed by a path-based `unlink`/`rmdir`. It opens the target with `CreateFileW`, `FILE_FLAG_OPEN_REPARSE_POINT`, delete access, and delete sharing; compares the handle's file index/type/attributes with the captured `st_ino` and expected type; then applies `FileDispositionInfo` to that verified handle. A same-name replacement made after handle verification is therefore not the object marked for deletion. On platforms supporting `dir_fd`, cleanup uses parent-directory descriptors plus `follow_symlinks=False` and repeated identity checks. Other platforms conservatively skip cleanup rather than use an unsafe named fallback.

TDD evidence includes a deterministic directory replacement between `_remove_owned_tree`'s identity check and recursive removal, with `foreign-sentinel.txt` required to survive, plus a Windows handle test that renames the checked file and creates a same-name foreign replacement after handle verification. A separate fail-closed test verifies that parent containment/identity revalidation failure cannot escape from cleanup or remove the owned object. Existing symlink/reparse, fault recovery, immutable replay/conflict, token-safe reservation release, and spawn-based cross-process convergence tests remain in the focused matrix.

## Narrative round-1 closure: I-5

Replaced arbitrary serialized-string truncation with deterministic structural selection. The narrative task now has a dual contract of at most 4,000 Unicode code points and at most 4,000 UTF-8 bytes. Evidence entries are considered first, then unresolved entries whose references are already included, then rows; each category is ordered by its safe alias and retains the previous item caps. A candidate is added only when the complete canonical JSON envelope still fits both limits. Oversized candidates are omitted whole, and bounded source/included/omitted counts are embedded in `context_budget`.

The minimum envelope is canonicalized and must fit before selection begins. Every accepted candidate task is encoded as canonical JSON, UTF-8 sized, decoded with `json.loads`, and canonicalized again before it can reach `GenerationRunRequest`. Failure to fit the minimum envelope raises the stable `FMEA_EXPORT_NARRATIVE_INVALID` context error; no malformed or partial JSON is emitted.

The structurally selected evidence entries now define all three views: task evidence, synthetic model `EvidencePack`, and permitted output references. `ExportNarrativePipelineResult` returns that exact included-reference set, and both the shared bridge and outer generator reject any claim referencing an omitted or foreign alias. Flash generation, deepseek-v4-pro criticism/repair, provisional `applied=False` semantics, and no-write behavior are unchanged.

TDD reproduction used 12 evidence excerpts of 512 Chinese characters, eight near-boundary rows, eight unresolved entries, and private source identities. Before the fix, the task failed `json.loads` with an unterminated string and an output citing omitted `evidence-012` was accepted. After the fix, the deterministic task measured 1,839 characters and 3,879 UTF-8 bytes, included two complete evidence entries, omitted the remaining entries with exact counts, contained no private document identity, and rejected `evidence-012`.

Verification: narrative unit `12 passed`; exact Task 4 relevant suite `103 passed, 1 skipped`; owned-file Ruff check, Ruff format check, compileall, and `git diff --check` passed. No live network was used.

## Round-2 closure: I-6 and I-7

Migration 011 now preserves the complete Task 1 `RunStatus` vocabulary: `queued`, `running`, `succeeded`, `cancelling`, `cancelled`, and `failed`. Its row invariants mirror `delivery_contracts._LIFECYCLE_REQUIREMENTS`, including required lifecycle timestamps, forbidden artifact/error bindings for cancellation, and chronological `created_at <= started_at <= finished_at` checks. Cancellation is deliberately two-phase: `queued` or `running` may enter `cancelling` (recording `started_at` when needed), then only `cancelling` may enter `cancelled`; `cancelling` may also fail. `cancelled`, `succeeded`, and `failed` are immutable terminal states. Existing succeeded-run artifact, audit, outbox, and idempotency authority checks remain unchanged.

Fresh v11 and empty-v10-to-v11 tests persist and reload both `cancelling` and `cancelled` rows across repository restarts. They also reject missing lifecycle timestamps, backwards cancellation transitions, and mutation of a cancelled terminal row. The pre-existing fail-closed guard for non-empty legacy export tables remains intact.

`ExportService` now routes each repository, governance, exporter, artifact-store, and narrative-generator invocation through a narrow boundary translator. Every adapter exception, including an adapter-raised `ExportServiceError` carrying attacker-controlled code, retryability, or text, is replaced with a service-owned stable code/message and raised without a cause. Service validation remains outside those boundary calls, so trusted application errors are not accidentally rewritten. Idempotency conflict recognition is limited to the repository's exact plain-`ValueError` sentinel, while narrative invalid/unavailable classification is derived only from service policy and exception shape, never adapter-controlled fields.

TDD evidence: the focused Round-2 tests first produced `10 failed, 43 passed`, exposing the two missing cancellation statuses and typed-error leakage. After the fixes, export plus narrative passed with `65 passed`; migration delivery, governance, and rollback compatibility passed with `138 passed`. Ruff check/format check and `git diff --check` were rerun before commit.

## Narrative round-2 closure: I9

The structural budgeter now reserves a minimum quota of one complete FMEA row before filling the remaining budget in the existing evidence, unresolved, and remaining-row order. Candidate rows are considered in deterministic safe-alias order, so an oversized earlier row cannot prevent a later complete row from satisfying the quota. No JSON text or Unicode content is sliced: every candidate is inserted as a whole object, canonicalized, checked against both Unicode-character and UTF-8-byte limits, decoded, and canonicalized again.

The projection contract currently gives rows only `row_alias` and bounded `fields`; rows do not carry evidence references. Evidence closure therefore remains explicit where references exist: an unresolved item is retained only when all of its `evidence_refs` are already included, and generated narrative claims remain restricted to the exact included-evidence alias set. The quota metadata is deterministic: no source rows yields `minimum=0/status=not_applicable`, at least one retained row yields `minimum=1/status=satisfied`, and source rows with no complete row fitting the configured envelope yield `minimum=1/status=budget_insufficient` with exact omitted counts and no fabricated row content.

TDD RED reproduced I9 with two focused failures: the large multibyte projection retained zero rows, and the tiny-budget projection had no explicit row-quota outcome. GREEN retained one whole row in the reproduced large projection while remaining valid canonical JSON at 1,625 Unicode characters and 3,225 UTF-8 bytes; it omitted all 12 oversized evidence excerpts and reported exact row/evidence/unresolved counts. The tiny-budget case returns valid bounded JSON with zero rows, `budget_insufficient`, and the source row counted as omitted.

Final verification after commit: narrative unit `13 passed`; JSON export plus snapshot contracts `33 passed`; owned-file Ruff check, Ruff format check, and `git diff --check` passed. Commit `d83ce10b` contains only the narrative generator and narrative unit test; no push or PR was performed.

## Round-3 closure: cooperative cancellation and nominal delivery boundaries

The export application now implements real cooperative cancellation rather than relying on direct SQL test setup. `ExportRepository` exposes idempotent request/complete cancellation operations, and SQLite persists canonical `run_json` plus its hash for each legal `queued|running -> cancelling -> cancelled` transition. Completing cancellation atomically closes the original start idempotency reservation with a canonical cancelled response. Cancelled reads and replays verify that completed idempotency binding, including actor-derived scope, payload hash, timestamps, status, resource, and response. Fresh v11 and empty-v10-to-v11 databases both preserve the states across repository restart.

`ExportService.cancel(export_run_id, actor)` applies the same human export authority and workspace isolation as start/read operations. It completes a stranded `cancelling` run, returns an existing `cancelled` run idempotently, and never rewrites `succeeded` or `failed`. `start()` explicitly resolves both `cancelling` and `cancelled` same-key replays. Cooperative checkpoints surround rendering, physical publication, and durable completion. If cancellation wins, completion cannot replace `cancelled`; if completion holds the SQLite writer first, cancellation observes and returns the verified `succeeded` terminal. A deterministic two-thread test covers each winner.

The trusted narrative error is now an exact application-owned `ExportNarrativeGenerationError`. Infrastructure raises that nominal type, and the service preserves only its allowlisted code/retryability while replacing its message. Subclasses, same-shaped third-party errors, and adapter-raised `ExportServiceError` are not trusted and are normalized to fixed service policy with no cause.

`ArtifactStore` now returns the application-owned immutable `VerifiedExportArtifact`, containing exact workspace/run/artifact/filename/manifest/payload bindings and no server path. The infrastructure keeps its path-bearing value private and converts only after contained filesystem verification; cleanup logic is unchanged. Service validation requires the exact owned value type and independently checks all identity, byte-length, payload, and SHA-256 bindings. Public `get_artifact()` therefore cannot expose a foreign workspace/id/path or any local path.

After physical publication, malformed or throwing store returns enter a deterministic recovery path: exact `get` and `latest` are independently retried and validated. A trusted match completes without rerendering; if neither view is trustworthy, the run is durably failed rather than left running. Existing physical artifacts are not deleted by the application. `_fail_run()` now accepts only an exact `FAILED` result with the expected timestamps/error, no artifact, and unchanged immutable binding.

TDD evidence: the Round-3 reviewer probes first produced `15 failed, 87 passed, 1 skipped`, reproducing the missing cancellation APIs/replays, unsafe store value, malicious comparison leak, malformed-publication gap, non-failed `_fail_run` acceptance, and narrative misclassification. Final verification passed with Task 4 exact `143 passed, 1 skipped` and Task 3/delivery/governance regression `138 passed`. Ruff check, Ruff format check, compileall, and `git diff --check` also passed. No migration, Task 5+, REST/CLI, composition, or cleanup algorithm was changed.

## Final Task 4 closure after review rounds 4-6

The final hardening rounds close the remaining adversarial and portability gaps without expanding into Task 5 transports or Office adapters.

- Cooperative cancellation is implemented through public service and repository operations. The durable two-stage transition is `queued|running -> cancelling -> cancelled`; cancellation closes the original start idempotency reservation, survives restart, and converges under cancel-versus-complete races to one legal terminal state.
- All repository, governance, exporter, artifact-store, narrative-generator, and public DTO boundaries rebuild exact plain values before comparison. Mutated exact dataclasses, malicious comparison/string/hash/length behavior, and attacker-controlled exception fields cannot leak through public errors.
- Physical publication followed by a malformed completion return is reconciled by rereading and verifying the durable delivery chain. A committed delivery returns verified `succeeded`; an uncommitted one becomes a strictly verified `failed` run. No reviewed path leaves a durable `running` run behind.
- Public artifact reads return path-free `VerifiedExportArtifact` values. Workspace, run, artifact, filename, manifest, byte length, payload, and SHA-256 are revalidated before exposure.
- Narrative input snapshots are rebuilt before workspace comparison, projection, or hashing. Narrative output keeps one complete FMEA row when one fits, preserves whole-entry JSON/Unicode and dual character/UTF-8 budgets, and permits claims only against included evidence aliases.
- Windows cleanup deletes only through a verified object handle. POSIX cleanup never performs unsafe pathname deletion; publication concurrency instead uses persistent regular lease files and kernel `flock` ownership, with fd release on normal exit or process death. Lease files are opened relative to a verified `.locks` dirfd under service-UID-owned, group/other-nonwritable roots; same-service-UID compromise is explicitly outside the filesystem adapter threat model.

Final independent Round 6 review verdict: **PASS**, with zero open Critical, Important, or Minor findings. Controller verification on Windows passed Task 4 with `181 passed, 3 skipped`, Task 3/governance regression with `138 passed`, Ruff/format checks, and `git diff --check`. The independent review reran its focused matrix and recorded `178 passed, 3 skipped` for its five-file Task 4 selection plus `138 passed` for Task 3/governance. The three Windows skips are two real POSIX multiprocessing `flock` tests and one symlink-privilege test; they remain explicit Linux CI residual validation and are not reported as executed evidence.

Accepted implementation head: `ec23bb3419029029d1e5590328526ad883827f19`. Final review: `task-4-review-round-6.md`.
