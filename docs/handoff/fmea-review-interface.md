# FMEA review interface handoff

This handoff covers the local FMEA review/output slice: a versioned review
context, immutable model suggestions, human-only decisions, optimistic
locking, exact idempotent replay, bounded audit provenance, selectable RAG /
GraphRAG evidence profiles, and the deterministic Task 11 acceptance/security
pack. It does not replace the upstream retrieval systems.

## Scope and hard boundaries

RAG and GraphRAG produce an immutable `EvidencePack`; the review interface
consumes that pack and never reconnects to Chroma, Neo4j, a graph index, or a
retrieval implementation. The supported requested profiles are `auto`,
`rag_only`, `graphrag_local_only`, `graphrag_global_only`, `graphrag_only`,
`combined`, and `custom`. Each context records requested profile, resolved
profile, evidence types, warnings, incomplete state, and a stable retrieval
trace.

The model may create only an immutable suggestion with `actor_type=model`,
`source_record_version=1`, and `applied=false`. Only a human reviewer may
submit `review.decision`; decisions advance the row from version 1 to version
2 with optimistic locking and leave `publication_status=unpublished`. There
is no scoring, approval, publication, or UI implementation in this slice.

## Operator setup

Use the project `.venv` and configure these environment variables in the
process that starts the API or CLI:

```powershell
$env:RAG_WORKSPACE_CONFIG = "C:\path\to\workspaces.json"
$env:FMEA_LOCAL_AUTH_ENABLED = "true"
$env:FMEA_REVIEW_TOKEN = "task11-local-review-token-placeholder-0001"
$env:FMEA_REVIEW_ACTOR_ID = "reviewer-1"
$env:FMEA_REVIEW_WORKSPACE_ID = "ws-1"
```

The optional paid live gate additionally reads `DEEPSEEK_API_KEY` from the
environment. Never place it in workspace JSON, request bodies, templates,
EvidencePacks, logs, artifacts, or command output. The live check is a model
suggestion smoke test and never submits a human decision.
Real secrets remain environment-only; the token shown above is an explicit
documentation placeholder, not a credential.

The FMEA routes are loopback-only by contract. Run the console behind a
loopback binding or a separately authenticated reverse proxy; do not expose
the local token-bearing review routes directly to an untrusted network.

Each workspace must keep these paths separate and contained by its configured
`allowed_root`:

```json
{
  "allowed_root": "runtime",
  "workspaces": {
    "ws-1": {
      "chroma_persist_dir": "runtime/chroma",
      "chroma_collection": "workspace",
      "graph_db_path": "runtime/graph/graph.sqlite3",
      "fmea_db_path": "runtime/fmea/fmea.sqlite3",
      "fmea_template_registry_path": "runtime/fmea/templates",
      "supported_modes": ["vector"],
      "default_mode": "vector"
    }
  }
}
```

The FMEA database must not equal the GraphStore path, and the database and
template registry may not overlap. Parent escapes and UNC paths are rejected
before directories are created.

## Template registration

The built-in review adapter registers the immutable `fmea-row-review@1.0.0`
template into the workspace's `fmea_template_registry_path`. A new review
runtime compiles and registers the same template identity before creating the
service. A different body at the same template identity is a conflict; bump
the semantic template version instead.

## CLI examples

All CLI operations emit one bounded JSON object. The CLI requires the local
auth environment above and uses the server-owned actor; it does not accept a
model, endpoint, prompt, or API-key override.

```powershell
.venv\Scripts\python.exe scripts\fmea_skill.py review context --row-id row-1
.venv\Scripts\python.exe scripts\fmea_skill.py review suggest `
  --row-id row-1 --record-version 1 `
  --idempotency-key 00000000-0000-4000-8000-000000000001
.venv\Scripts\python.exe scripts\fmea_skill.py review suggestion-status --run-id run-...
.venv\Scripts\python.exe scripts\fmea_skill.py review decide `
  --request-file .local\decision.json --confirm-human-review
.venv\Scripts\python.exe scripts\fmea_skill.py review decisions --row-id row-1
```

Stable provider failures are exposed as
`FMEA_MODEL_SUGGESTION_UNAVAILABLE`; invalid model output is
`FMEA_MODEL_SUGGESTION_INVALID`. Other stable boundary codes include
`FMEA_ROW_NOT_FOUND`, `FMEA_VERSION_CONFLICT`,
`FMEA_IDEMPOTENCY_CONFLICT`, `FMEA_REVIEW_TERMINAL`,
`FMEA_EVIDENCE_INVALID`, and `FMEA_REVIEW_STORAGE_UNAVAILABLE`. Raw provider
exceptions, authorization headers, private paths, prompts, and tracebacks do
not cross the CLI boundary.

## REST examples

Read context without a write precondition:

```powershell
curl.exe http://127.0.0.1:8000/api/v1/fmea/rows/row-1/review-context `
  -H "Authorization: Bearer task11-local-review-token-placeholder-0001"
```

Start a durable suggestion run with exact replay identity:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/fmea/rows/row-1/review-suggestion-runs `
  -H "Authorization: Bearer task11-local-review-token-placeholder-0001" `
  -H 'If-Match: "1"' `
  -H "Idempotency-Key: 00000000-0000-4000-8000-000000000001" `
  -H "Content-Type: application/json" `
  -d '{"review_policy":"default","focus_fields":[]}'
```

The response is `202 Accepted` with a `Location` for polling. Decision POSTs
require `If-Match`, `Idempotency-Key`, and the strict human decision body;
they return a versioned problem detail on invalid input and a new `ETag` on
success. FMEA POST bodies are capped at 256 KiB.

## Acceptance and live gates

The offline runner writes exactly six canonical files beneath a timestamped
directory in `.local/fmea-review-acceptance/`:

```text
context.json
suggestion-run.json
suggestion.json
decision.json
audit-summary.json
acceptance-summary.json
```

The summary schema is `graphrag.fmea.review.acceptance.v1`. It is bounded and
contains counts, profile cases, row/template/schema hashes, and safe errors;
it does not contain full prompts, API keys, or unbounded evidence. The
independent verifier rejects missing, extra, non-canonical, tampered, or
private-marker-bearing files.

```powershell
.venv\Scripts\python.exe scripts\run_fmea_review_acceptance.py
.venv\Scripts\python.exe scripts\verify_fmea_review_acceptance.py --latest
```

The focused acceptance/security command is:

```powershell
.venv\Scripts\python.exe -m pytest `
  tests/integration/test_fmea_review_acceptance.py `
  tests/regression/test_fmea_review_security.py -q
```

Only after offline gates are green, and only with explicit paid-call
authorization, run the one live check. It uses a 90-second per-request
timeout and a 300-second total timeout:

```powershell
.venv\Scripts\python.exe -m pytest `
  tests/integration/test_fmea_review_live_deepseek.py `
  -m live_deepseek -q -s
```

This call can incur provider charges. A network, authentication, rate-limit,
timeout, or provider-schema failure is an external live-test failure, not
product acceptance. It must be reported with its stable safe code and must
not be converted into a success claim.

The complete focused matrix also records a known upstream baseline: the
repository's existing GraphRAG global-search integration has pre-existing
failures in `tests/unit/test_graphrag_integration.py` because the legacy
orchestrator defaults to local search while an injected global searcher is
unused. Those failures are not part of this review/output slice and are not
silently attributed to Task 11.

## Open-source alignment and migration

The following projects are behavioral references only; this implementation has
no runtime dependency on them:

- [Microsoft GraphRAG index overview](https://microsoft.github.io/graphrag/index/overview/)
  is the upstream evidence producer/indexing reference.
- [Microsoft GraphRAG query overview](https://microsoft.github.io/graphrag/query/overview/)
  distinguishes basic, local, and global retrieval; GraphRAG remains stronger
  and upstream for graph indexing and local/global graph retrieval.
- [Argilla model Suggestions](https://docs.argilla.io/latest/reference/argilla/records/suggestions/)
  and [user Responses](https://docs.argilla.io/latest/reference/argilla/records/responses/)
  inspire immutable model-suggestion versus human-response separation.
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
  and [persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
  inspire durable pause/resume and polling semantics.
- [OpenLineage object model](https://openlineage.io/docs/spec/object-model/)
  and [run cycle](https://openlineage.io/docs/spec/run-cycle/) inspire additive
  event provenance; they are not a runtime event dependency here.

| Concern | Microsoft GraphRAG | This review/output slice |
| --- | --- | --- |
| Indexing and retrieval | Stronger/upstream graph indexing, entity/community construction, and retrieval | Consumes an immutable `EvidencePack`; no retrieval implementation |
| Local/global evidence | Stronger/upstream local/global graph evidence production | Records explicit `graphrag_local_only` / `graphrag_global_only` profiles and warnings |
| Domain schema | Retrieval-oriented graph/schema contracts | FMEA row, source, suggestion, decision, and template contracts |
| Model suggestion vs human decision | Not the primary workflow boundary | Immutable model suggestions are separate from human-only decisions |
| Optimistic concurrency/idempotency | Not the primary review command contract | Exact replay identity and row-version optimistic locking |
| Audit provenance | Upstream retrieval lineage is external input | Additive immutable review start/complete/decision audit events |
| New-template migration | Upstream graph schema/index migration concerns | Compile/register template, explicit adapter/allowlist, deterministic fixture and gates |

The distinct choices here are one EvidencePack/profile contract for ordinary
RAG and GraphRAG evidence, immutable model suggestions separated from human
decisions, exact idempotent replay, and FMEA-specific rules outside the
generic template engine. Scoring, approval, publication, and UI remain
separate future boundaries.

To migrate a new domain, follow this exact recipe:

`author YAML → compile/register → implement domain adapter/allowlist → add deterministic fixture → run compiler/adapter/security/acceptance tests`

A model may draft the YAML and proposed mappings, but a human domain owner must
approve field semantics, state transitions, editable-field allowlists, and
the evidence policy before registration. The domain adapter must preserve the
same model-suggestion/human-decision boundary; it must not silently add
scoring, approval, publication, or retrieval fallbacks.

## Handoff checklist

- Operator owns workspace containment, loopback binding, token rotation, and
  template registry location.
- Retrieval owner supplies profile-resolved `EvidencePack` and trace
  provenance; GraphRAG remains upstream for graph indexing/local/global query.
- Domain owner approves YAML semantics, evidence bindings, and state changes.
- Review owner consumes suggestions and submits human decisions with the
  current `ETag`; no model result is an approval.
- Publication/scoring/UI owners remain unimplemented for this slice.
