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
3. REST/CLI cursor interoperability across processes requires the same configured `FMEA_GOVERNANCE_CURSOR_SECRET`; an unset secret remains process-local on REST by design. The shared codec, binding, and inner-cursor confidentiality are covered.
4. The interface tests use an application-service fake for command forwarding and a real SQLite-backed composition check for runtime acquisition. They do not claim a deployed external provider configuration or full end-to-end production data fixture.
