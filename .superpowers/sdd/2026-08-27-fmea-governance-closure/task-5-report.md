# FMEA Governance Closure Task 5 report

## Status and scope

- Worktree: `C:/Users/35551/Desktop/RAG/.worktrees/interface-output-v1`
- Starting HEAD: `be26eb298334576cfb70c98d6cec8730ae73da2d`
- Scope: close the inherited Task 5 REST/CLI interface diff, add behavior coverage, repair only transport/runtime gaps exposed by the coverage, and commit the owned changes.
- Explicitly excluded: Task 6, RAG/GraphRAG integration, export/UI, migrations, and migration 010. Migrations 005-009 were not modified.

## RED evidence

The inherited baseline was reproduced before extending coverage: the three Task 5 test files passed `20`, and the Task 5 plus propagation/risk/review REST matrix passed `75`. The new behavior tests were then used as mutation detectors. Each mutation was temporary, applied with `apply_patch`, run against the focused test, and restored immediately:

| Temporary production mutation | RED result | Restored |
| --- | --- | --- |
| REST submit dispatch called `approve` instead of `submit_for_approval` | `1 failed, 6 passed, 25 deselected` | yes |
| CLI reject dispatch called `approve` instead of `reject` | `1 failed, 14 passed, 20 deselected` | yes |
| CLI publication confirmation was disabled | `2 failed, 7 passed, 26 deselected` | yes |
| REST confirmation helper became a no-op | `8 failed, 24 deselected` | yes |
| REST publication-show ETag was removed | `1 failed, 31 deselected` | yes |
| REST history cursor resource binding was changed | `1 failed, 32 deselected` | yes |
| CLI history cursor resource binding was changed | `1 failed, 34 deselected` | yes |

The final source scan found no mutation markers, and the final green runs below passed with the production behavior restored.

## Coverage completed

REST behavior now exercises the real adapter-to-application command path for revision assemble, revision show/readiness, readiness suggestion, approval submit/approve/reject/withdraw/history, and publication publish/show/snapshot/withdraw/supersede/history. Authority writes verify exact command types and arguments, canonical lowercase UUID idempotency, quoted `If-Match`, confirmation-before-service behavior, success status, shared envelope, and applicable `ETag`/`Location` headers. History verifies the shared opaque cursor, workspace/resource/direction/page/filter binding, ordering query, and absence of the repository cursor from the response.

CLI behavior now exercises parser plus dispatch for every requested command group: revision assemble/show/readiness; approval readiness-suggest/submit/approve/reject/withdraw/history; and publication publish/show/snapshot/withdraw/supersede/history. Tests verify shared projection, exact command arguments and expected versions, canonical idempotency, one-JSON-object failures, nonzero failures, all authority confirmations before runtime creation, and rejection of provider/topology/DomainPack/rule-pack/EvidencePack/snapshot-path overrides.

The runtime checks prove REST and CLI acquire the governance application service rather than opening SQLite in an adapter. The default workspace composition creates the repository-backed service, while source providers remain explicitly fail-closed until deployment-owned typed providers are configured. Revision reads use the repository record version for both `record_version` and ETag; `analysis_record_version` is not substituted. Readiness suggestion tests prove `HTTP 202`, `applied=false`, model actor use, and unchanged deterministic readiness. REST and CLI use the same projection and cursor codec.

## GREEN evidence

Commands were run from the worktree with `.venv/Scripts/python.exe`:

- Task 5 tests: `99 passed`.
- Six-file planned matrix (Task 5 plus propagation/risk/review REST): `154 passed`.
- Governance service/composition focused suite: `122 passed`.
- `python -m compileall -q api_server/current_console/chroma_rag_poc/src fmea_application fmea_infrastructure scripts tests`: exit `0`.
- `git diff --check`: exit `0`; Git emitted only expected LF-to-CRLF working-copy warnings.
- Scoped `ruff check` on the eight Task 5 files other than the pre-existing mixed legacy `api.py`: passed.
- `ruff format --check` on the two new interface files and three Task 5 test files: `5 files already formatted`.

## Changed files

- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_governance_contracts.py` — single shared request/projection/envelope/cursor contract for REST and CLI.
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_governance_v1.py` — versioned REST handlers, runtime acquisition, preconditions, confirmation, errors, headers, and history.
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py` — register the governance runtime factory, router, error handler, and cursor secret.
- `fmea_application/governance_service.py` — expose the repository-backed revision record version needed for true revision ETags.
- `fmea_infrastructure/composition.py` — wire the default workspace governance application service to the workspace-owned SQLite repository with fail-closed source providers.
- `scripts/fmea_skill.py` — governance parser, runtime acquisition, command dispatch, shared projections, cursor handling, confirmation gate, and stable errors.
- `tests/unit/test_fmea_governance_api_contracts.py` — shared contract, cursor, ETag-version, and default runtime coverage.
- `tests/integration/test_fmea_governance_api_v1.py` — REST command/argument, precondition, confirmation, projection, cursor, ETag, and runtime coverage.
- `tests/integration/test_fmea_governance_cli.py` — complete CLI command-group, parser/dispatch, confirmation, idempotency, projection, cursor, and runtime coverage.
- `task-5-report.md` — this acceptance report.

The two existing production files outside the original interface-file list are necessary transport seams identified by the Task 5 ledger: application-level repository version read and production composition/runtime acquisition. The `api.py` router/error/runtime registration and `scripts/fmea_skill.py` adapter are part of the original interface-file list. No new business rule or persistence schema was added.

## Concerns

1. Full default Ruff on the inherited mixed legacy `api.py` remains non-clean (`69` existing findings), and a broad `--select F,E,I,UP` check also surfaces pre-existing E501 findings in `api.py` and `scripts/fmea_skill.py`. Cleaning those unrelated findings would violate the Task 5 scope; the Task 5-scoped default check and new-file format check pass.
2. The default composition intentionally fails closed for assembly/readiness when deployment-owned typed source providers are absent. This prevents the interface from inventing source state or reaching RAG/GraphRAG, but a deployment must provide those providers before those operations can succeed.
3. REST/CLI cursor interoperability across processes requires the same configured `FMEA_GOVERNANCE_CURSOR_SECRET`; an unset secret now fails with `FMEA_GOVERNANCE_WORKSPACE_CONFIGURATION_INVALID` and never falls back to a review token, an empty-derived key, or a process-local governance secret. The shared codec, binding, and inner-cursor confidentiality are covered.
4. The interface tests use an application-service fake for command forwarding and a real SQLite-backed composition check for runtime acquisition. They do not claim a deployed external provider configuration or full end-to-end production data fixture.

## Fix round 1/5 — governance transport hardening

### Scope and plan

- Fix base: `e1cd2ae6eb3dc9f02a52993f2a287c0593a1b10a`; the worktree was clean at that base.
- Read and applied every Critical/Important finding in `task-5-review-round-1.md` plus the latest two Task 5 rulings in `progress.md`.
- Work order was recursive projection/budgets, pre-runtime confirmation, dedicated cursor secret plus real cross-transport parity, typed provider injection/fail-closed mapping, then matrices/static checks/self-review.
- No Task 6 file, migration, RAG/GraphRAG, export/UI, plugin import, subagent, push, or PR work was performed.

### Finding closure and covering tests

| Finding | Minimal fix | Covering behavior tests |
| --- | --- | --- |
| Critical 1: recursive projection leak | Replaced permissive dataclass/mapping traversal with one generic recursive JSON sanitizer: string keys only; private/sensitive markers rejected at every depth; opaque objects, cycles, non-finite numbers, absolute paths/URLs, depth >8, strings >4096 chars, containers >500 items, >10,000 nodes, and envelopes >256 KiB rejected. Snapshot, lifecycle, suggestion, history/event, REST envelopes, and CLI governance envelopes share the boundary. Fixed domain/template fields remain data-driven rather than allowlisted. | `test_projection_safe_json_rejects_recursive_private_or_unbounded_values`; `test_snapshot_lifecycle_and_event_share_recursive_projection_boundary`; REST/CLI nested-private snapshot rejection tests. |
| Important 2: REST confirmation after runtime | Split authenticated workspace access from runtime acquisition. Every authority handler calls its confirmation gate before `_runtime_for`; path IDs are also bounded before runtime acquisition. | Seven-case `test_rest_authority_confirmation_blocks_service_call` now counts the runtime factory; `test_rest_governance_path_ids_use_shared_bound_before_runtime_creation`. |
| Important 3: cursor secret fallback/divergence | Added one domain-separated `derive_governance_cursor_secret`; REST and CLI use only `FMEA_GOVERNANCE_CURSOR_SECRET`. Missing/blank configuration maps to `FMEA_GOVERNANCE_WORKSPACE_CONFIGURATION_INVALID`; review token and empty/process-local fallback paths were removed. | `test_governance_cursor_secret_uses_one_dedicated_required_derivation`; REST and CLI missing-secret tests; actual cross-transport parity/interoperability test. |
| Important 4: missing provider typed seam/error | `build_default_workspace_governance_runtime(..., providers=GovernanceRepositoryProviders)` is the explicit typed seam. The default sentinel raises the stable workspace-configuration error; REST maps it to 503 and CLI to configuration exit 3. No dynamic/plugin loader was added. | Two unit composition tests plus `test_rest_default_runtime_missing_source_providers_maps_to_503_configuration` and `test_cli_default_runtime_missing_source_providers_maps_to_configuration`. |
| Important 5: unbounded requests/responses | `PublicationBody.revision_hash` is required; REST bodies and application commands use 256-char IDs/500-char reasons; REST path IDs are bounded; existing 256 KiB POST middleware remains authoritative; every governance response uses the 256 KiB recursive envelope budget. | strict/bounded request contract test; CLI ID/reason dispatch test; total envelope budget test; REST path-ID pre-runtime test. |
| Important 6: false REST parity | Added a single test using the same fake application service and configured secret through actual FastAPI `TestClient` and actual CLI `main`. It compares snapshot data and history item ordering, sends a REST cursor to CLI, then sends the CLI-issued cursor back to REST. | `test_rest_and_cli_snapshot_history_parity_and_cursor_interoperability`. |

### RED and mutation evidence

All mutations were temporary and restored immediately.

| RED command/failure | Evidence that the test detects the finding |
| --- | --- |
| Unit projection/request focused run | `9 failed, 5 deselected`: missing required publication hash, absent recursive sanitizer, nested lifecycle/snapshot/event leaks, and absent total response budget. |
| REST confirmation focused run | `1 failed, 42 deselected`: runtime factory count was `1`, expected `0`. |
| Dedicated-secret REST/CLI/unit focused run | `3 failed`: derivation import absent; REST returned 400 instead of 503; CLI used review-token fallback and exited 0 instead of config exit 3. |
| Typed-provider focused run | explicit `providers=` seam raised unexpected-keyword `TypeError`; the valid fail-closed mutation later made REST emit `FMEA_GOVERNANCE_STORAGE_UNAVAILABLE` and CLI exit 7 (`2 failed`). |
| REST/CLI unsafe snapshot focused run | `2 failed`: REST leaked an uncaught projection `ValueError`; CLI mapped it to generic workspace config exit 3 instead of governance storage exit 7. |
| CLI ID/reason bounds focused run | `1 failed, 48 deselected`: a 501-char reason dispatched successfully instead of failing request validation. |
| REST path-ID bounds focused run | `1 failed`: a 257-char revision ID acquired runtime and returned 503 instead of request-invalid 400. |
| Cursor interoperability mutation | Temporarily returned a different CLI signing key; the actual REST-to-CLI cursor test failed (`1 failed`) with CLI exit 2 / `FMEA_GOVERNANCE_CURSOR_INVALID`; production key handling was restored. |
| Missing-provider mutation | Temporarily restored the generic `ValueError`; REST kept HTTP 503 but wrong storage code, while CLI exited 7 instead of 3 (`2 failed`); typed configuration error was restored. |

### GREEN commands and outputs

- Three Task 5 files: `121 passed in 4.09s`.
- Six-file transport matrix from the Task 5 brief: `176 passed in 11.77s`.
- Governance service/source/SQLite focused suite: `191 passed in 25.62s`.
- Scoped Ruff check across the eight changed Task 5 implementation/test files excluding legacy `api.py`: `All checks passed!`.
- Ruff format check on seven safely format-scoped governance/application/composition/test files: `7 files already formatted`.
- `python -m compileall -q api_server/current_console/chroma_rag_poc/src fmea_application fmea_infrastructure scripts tests`: exit `0`.
- `git diff --check`: exit `0`; only expected LF-to-CRLF working-copy warnings were emitted.

### Fix-round changed files and necessity

- `fmea_governance_contracts.py`: required recursive sanitizer, shared byte budget, bounded bodies, required publication revision hash, and shared secret derivation.
- `routes_fmea_governance_v1.py`: required pre-runtime confirmation/path validation, safe projection error mapping, runtime acquisition split, and missing-secret mapping.
- `api.py`: necessary production REST secret configuration seam; removes random governance fallback.
- `fmea_application/governance_contracts.py`: necessary transport-neutral ID/reason bounds so CLI and REST commands share conventions.
- `fmea_infrastructure/composition.py`: necessary typed provider injection seam and fail-closed configuration error.
- `scripts/fmea_skill.py`: necessary dedicated-secret use, safe governance envelope/output mapping, and no review-token fallback.
- The three existing Task 5 test files: direct behavior, RED, cross-transport, and regression coverage. No new test file or shared fake module was needed.
- This report: required round evidence and acceptance record. No migration file was changed or added.

### Open concerns after fix round 1

1. Deployment must explicitly provide typed source query providers before assemble/readiness can succeed; absence intentionally returns REST 503 / CLI configuration exit 3.
2. Deployment must set the same nonblank `FMEA_GOVERNANCE_CURSOR_SECRET` for REST and CLI history interoperability. Rotation invalidates outstanding cursors; no multi-key rotation scheme is in Task 5 scope.
3. The sanitizer is intentionally conservative (including recursive private-key markers and path/URL rejection). Future domain/template extensions must remain projection-safe JSON and within depth/container/node/string/256 KiB budgets.
4. Legacy `api.py` and non-governance portions of `scripts/fmea_skill.py` were not globally reformatted; scoped Ruff passed, and unrelated legacy cleanup remains outside Task 5.

## Fix round 2/5 — governance transport review closure

### Scope and findings closed

- Fix base: `7a01b79f22a39fba1d43c7b5ab632b466c9ac1f8`; the worktree was clean at that base.
- Applied all four fixed findings in `task-5-review-round-2.md` and the latest two Task 5 rulings: cursor-secret resolution remains command-scoped, and generic URI rejection preserves an explicitly validated canonical `sha256:<hex>` hash.
- No Task 6, migration, RAG/GraphRAG, export/UI, plugin, subagent, push, or PR work was performed.

| Finding | Minimal fix | Covering behavior tests |
| --- | --- | --- |
| Critical: recursive sanitizer gaps | Added generic recursive rejection for private key markers, UNC/root-relative/drive paths, traversal segments, and every URI scheme. Canonical SHA-256 lineage hashes are validated before URI rejection. Existing nonfinite/cycle/depth/container/node/string/total-byte checks remain shared by snapshot, lifecycle, event, and envelope projections. | `test_projection_safe_json_rejects_private_tokens_paths_and_any_uri_scheme`; `test_projection_safe_json_rejects_nonfinite_numbers`; `test_projection_safe_json_rejects_recursive_cycles`; `test_projection_safe_json_preserves_hash_timestamp_and_cross_domain_text`; existing shared snapshot/lifecycle/event boundary tests. |
| Important: false CLI secret derivation evidence | Reworked the cross-transport test so CLI calls use the real `build_cli_runtime` dependency composition, environment read, and domain-separated derivation. REST-issued cursors are consumed by CLI and CLI-issued cursors by REST. | `test_rest_and_cli_snapshot_history_parity_and_cursor_interoperability`; `test_cli_runtime_acquires_the_governance_application_service`. |
| Important: pretty output exceeds budget | Governance CLI output is fully serialized first, including pretty whitespace and final newline, then its UTF-8 bytes are checked against 256 KiB before one atomic stdout write. Oversize output maps to one bounded stable storage error with no payload prefix. | `test_cli_snapshot_budgets_the_final_pretty_stdout_bytes_without_partial_payload` uses a compact `261619`-byte-class fixture whose pretty form exceeds 256 KiB. |
| Important: missing secret breaks all CLI commands | `CliRuntime.governance_cursor_secret` remains optional. `build_cli_runtime` derives it only when the dedicated environment value is nonblank; only approval/publication history calls the existing secret requirement. Non-history governance and the review/risk services remain acquired without the variable. | `test_cli_runtime_without_cursor_secret_keeps_non_history_governance_available`; existing dedicated-secret history test; review/risk/propagation CLI compatibility matrix. |

### RED and mutation evidence

Every production mutation below was temporary and restored immediately. The initial system-Python attempt failed during collection because it lacked project dependencies and was not counted as RED evidence; all recorded commands use `.venv/Scripts/python.exe`.

| RED command | Observed output and diagnosed gap |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest tests/unit/test_fmea_governance_api_contracts.py::test_projection_safe_json_rejects_private_tokens_paths_and_any_uri_scheme -q` | `8 failed in 0.17s`; every new private-key/path/URI case was accepted by the old sanitizer. |
| After temporarily bypassing `math.isfinite` and active-cycle checks: `.venv/Scripts/python.exe -m pytest tests/unit/test_fmea_governance_api_contracts.py::test_projection_safe_json_rejects_nonfinite_numbers tests/unit/test_fmea_governance_api_contracts.py::test_projection_safe_json_rejects_recursive_cycles -q` | `4 failed in 0.33s`; nonfinite values reached JSON encoding with the wrong failure and a cycle reached depth/cleanup failure instead of the cycle guard. |
| After temporarily removing the immutable-hash exemption: `.venv/Scripts/python.exe -m pytest tests/unit/test_fmea_governance_api_contracts.py::test_projection_safe_json_preserves_hash_timestamp_and_cross_domain_text -q` | `1 failed`; canonical `sha256:<64 hex>` was rejected as a URI, proving the positive case kills overbroad sanitization. |
| `.venv/Scripts/python.exe -m pytest tests/integration/test_fmea_governance_cli.py::test_cli_runtime_without_cursor_secret_keeps_non_history_governance_available -q` | `1 failed in 1.24s`; real `build_cli_runtime` raised `FMEA_GOVERNANCE_WORKSPACE_CONFIGURATION_INVALID` before dispatch. |
| After temporarily suffixing the CLI derivation input: `.venv/Scripts/python.exe -m pytest tests/integration/test_fmea_governance_cli.py::test_rest_and_cli_snapshot_history_parity_and_cursor_interoperability -q` | `1 failed in 1.15s`; CLI returned exit `2` / `FMEA_GOVERNANCE_CURSOR_INVALID` while consuming the REST cursor. |
| `.venv/Scripts/python.exe -m pytest tests/integration/test_fmea_governance_cli.py::test_cli_snapshot_budgets_the_final_pretty_stdout_bytes_without_partial_payload -q` | `1 failed in 1.14s`; old code returned exit `0` and wrote the over-budget pretty payload. |

### GREEN commands and outputs

- Sanitizer focused: `13 passed in 0.08s`; restored nonfinite/cycle guards: `4 passed in 0.07s`.
- Real runtime/secret/history focused: `3 passed in 0.97s`; restored cross-transport derivation: `1 passed in 0.93s`.
- Final-byte focused: `1 passed in 0.90s`.
- Three Task 5 files: `136 passed in 4.12s`.
- Six-file Task 5 plus prior REST transport matrix: `191 passed in 12.03s`.
- Review/risk/propagation CLI compatibility matrix with no inherited cursor secret: `36 passed in 0.92s`.
- Governance service/source/composition focused suite: `201 passed in 1.72s`.
- Scoped Ruff check over the changed contract/CLI/tests plus the Task 5 API test: `All checks passed!`.
- Ruff format check over the safely format-scoped contract and three Task 5 test files: `4 files already formatted`.
- `python -m compileall -q api_server/current_console/chroma_rag_poc/src fmea_application fmea_infrastructure scripts tests`: exit `0`.
- `git diff --check`: exit `0`; only expected LF-to-CRLF working-copy warnings were emitted.

The final GREEN pytest commands were the exact three-file and six-file commands from `task-5-brief.md`, plus `.venv/Scripts/python.exe -m pytest tests/integration/test_fmea_review_cli.py tests/integration/test_fmea_risk_cli.py tests/integration/test_fmea_propagation_cli.py -q` and `.venv/Scripts/python.exe -m pytest tests/unit/test_fmea_governance_service.py tests/unit/test_fmea_governance_source.py tests/unit/test_fmea_governance_authority.py tests/unit/test_fmea_governance_assistance.py tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_governance_api_contracts.py tests/integration/test_fmea_governance_lifecycle.py -q`.

### Fix-round changed files and necessity

- `fmea_governance_contracts.py`: closes the generic recursive private/path/URI boundary while retaining validated hashes and ordinary cross-domain data.
- `scripts/fmea_skill.py`: makes cursor configuration optional outside history and enforces the actual final stdout-byte budget before writing.
- `test_fmea_governance_api_contracts.py`: direct sanitizer positive/negative and mutation-killing coverage.
- `test_fmea_governance_cli.py`: minimal shared real-runtime fixture, actual env derivation/cursor interoperability, missing-secret compatibility, and final-byte regression.
- This report: required round-2 evidence. No additional production/test file was needed.

### Open concerns after fix round 2

1. No Critical/Important round-2 finding remains open. Deployment still must provide the same dedicated cursor secret to REST and CLI for history; rotation invalidates outstanding cursors.
2. The sanitizer intentionally rejects locator-shaped values under any URI scheme and path traversal at every depth. New domains should expose reviewed semantic text or validated immutable hashes, not live locators.
3. Missing trusted source providers remains intentionally fail-closed as decided in round 1; deployment wiring is outside Task 5.
4. `scripts/fmea_skill.py` contains inherited formatting outside the Task 5 hunks. Whole-file formatting would create a large unrelated diff, so Ruff check covers it while format check remains restricted to safely format-scoped contract/test files.
