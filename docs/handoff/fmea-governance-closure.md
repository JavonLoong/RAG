# FMEA governance closure handoff

Task 6 closes the Phase 3 acceptance, replay, security, and atomic publication
boundary for the fuel-combustion fixture. It does not add a transport, export
format, browser surface, migration, or template-import workflow.

## Acceptance path

`scripts/run_fmea_governance_acceptance.py` creates a deterministic offline
fixture and composes it through the existing typed authority path:

`GovernanceRepositoryProviders` → `build_workspace_governance_runtime` →
`RevisionGovernanceService` → `SqliteGovernanceRepository`.

The fixture contains one accepted FMEA row, one confirmed risk record, one
confirmed propagation graph, a bounded evidence pack, and registry identities
resolved from the fuel-combustion domain pack. Its provenance provider exposes
`rag_only`, `graphrag_only`, `combined`, and `auto` (`auto` resolves to
`combined`) without invoking a retrieval backend. Prompts, model output,
credentials, provider failures, and private evidence locations are not stored.

The run executes and records:

- real readiness, human approval submission, human approval, and human publish;
- idempotent approval, publish, and publication-withdrawal replays;
- a child revision whose attempted reuse of the parent approval fails with
  `FMEA_GOVERNANCE_APPROVAL_STALE`;
- a new child approval, child publication, parent supersession, approval
  withdrawal, and publication withdrawal while retaining the immutable
  publication payloads;
- model and system probes for every authority command, each with a stable
  denial code and database count evidence proving no write;
- independent replay evidence for approval, publication, and withdrawal,
  plus the complete revision, approval, manifest, snapshot, publication,
  eligibility, lifecycle, audit, outbox, and idempotency lineage;
- bounded normalized snapshot pages, including a 10,000-row in-memory contract
  exercised at page size 250.

## Artifact contract

The runner writes a temporary, path-contained directory containing only the
canonical JSON artifacts listed in `ARTIFACT_NAMES`. Every file is UTF-8
canonical JSON with a terminal newline. The summary contains SHA-256 hashes of
all other files. `latest` is a one-line artifact ID and is switched only after
the independent verifier accepts the temporary directory.

`verify_fmea_governance_acceptance.py` independently performs component-wise
reparse checks for both artifact leaves and `latest`, exact file-set and
cardinality checks, size bounds, decoded component-aware private-path checks,
duplicate-key and non-finite-number rejection, canonical-byte checks, hash
recomputation, raw cross-artifact identity/version/workspace/analysis binding,
audit-chain binding, actor separation, lifecycle order and status checks,
independently derived summary claims, provenance checks, outbox/idempotency
and withdrawal evidence checks, and immutable payload retention checks. It
intentionally does not import the runner or reuse runner validation functions.

A write, directory replacement, pointer replacement, or independent
verification failure leaves the previous `latest` selection unchanged and
cleans both temporary and already-promoted orphan directories. On Windows,
existing path components and artifact/pointer leaves are checked with
`lstat`; symlinks and reparse points are rejected. The regression suite
includes unprivileged non-directory, deterministic reparse-leaf, and
stateful second-replace failure coverage.

## Operational commands

From the repository root:

```text
.venv\Scripts\python.exe scripts/run_fmea_governance_acceptance.py
.venv\Scripts\python.exe scripts/verify_fmea_governance_acceptance.py --latest
```

The default output root is `.local/fmea-governance-acceptance`. The generated
artifact directory is suitable for local acceptance evidence only; Phase 4
template import, XLSX/DOCX generation, browser UI, and migration workflow
remain out of scope.
