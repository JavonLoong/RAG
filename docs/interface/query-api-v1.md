# GraphRAG Query API v1

This document describes the implemented `graphrag.query.v1` contract. It is
derived from `core_domain/query_contracts.py`, the versioned FastAPI routes,
and `scripts/query_skill.py`; fields described here are not a proposal for a
future response shape.

## Endpoints and version marker

| Operation | Request | Success response |
| --- | --- | --- |
| `POST /api/v1/query` | JSON `QueryRequest` | JSON `QueryResponse`, HTTP `200` |
| `POST /api/v1/query/stream` | JSON `QueryRequest` | SSE frames containing typed v1 events, HTTP `200` after the first `meta` event |

Every success and error envelope has:

```json
{"schema_version":"graphrag.query.v1", "request_id":"...", "trace_id":"..."}
```

The stream endpoint uses `Content-Type: text/event-stream`, `Cache-Control:
no-cache`, and `X-Accel-Buffering: no`. The non-streaming route is the source
of the response models in the generated OpenAPI document. The stream route
currently sets `response_model=None`, so consumers should use the event
schemas below rather than infer the stream union from OpenAPI.

### Runtime and release gate

`pyproject.toml` declares `requires-python = ">=3.11,<4.0"` and retains the
3.11 and 3.12 classifiers. The release gate must run the contract and
interface integration tests on both Python 3.11 and 3.12 before publishing
v1. The local acceptance run used the repository virtual environment's Python
3.13.5; it did not execute the 3.11/3.12 matrix.

## Request contract

The request object rejects unknown fields. `query` is stripped before length
validation, so a whitespace-only value is invalid.

| Field | Type | Required | Default | Constraints / meaning |
| --- | --- | --- | --- | --- |
| `query` | string | yes | — | 1–65,536 characters after trimming |
| `workspace_id` | string | yes | — | 1–128 characters; logical registry ID |
| `mode` | string enum | no | `"auto"` | `auto`, `vector`, `local`, `global`, or `hybrid` |
| `top_k` | integer | no | `5` | inclusive range 1–100 |
| `include_context` | boolean | no | `false` | include the rendered retrieval context and context items |
| `include_debug` | boolean | no | `false` | include the redacted prompt and raw mode result |

The equivalent CLI flags are `--query`, `--workspace`, `--mode`, `--top-k`,
`--include-context`, and `--include-debug`. `--pretty` changes formatting
only and is not part of the API request.

## Mode semantics

`mode.requested` records the request value. `mode.used` records the mode that
actually ran, and `mode.reason` is a server-generated explanation. `auto` is
resolved through the configured query router when available; otherwise the
workspace default is used. The runtime maps router strategies
`VECTOR_ONLY`/`VECTOR`, `LOCAL_SEARCH`/`LOCAL`, `GLOBAL_SEARCH`/`GLOBAL`, and
`HYBRID` to the corresponding modes. If the workspace default is `auto`, the
implemented fallback is `local`.

| Mode | Implemented behavior |
| --- | --- |
| `auto` | Selects another mode through the router or workspace default; inspect `mode.used` rather than assuming a mode. |
| `vector` | Runs text retrieval and returns the retrieved text quotes as the answer. It does not call the answer LLM. A text retrieval failure is a `QUERY_FAILED` error. |
| `local` | Runs text and graph retrieval, renders their citations as LLM context, and generates an answer. Missing or failed graph retrieval and other recoverable degradation produce warnings and `partial`. |
| `global` | Runs the configured global searcher and uses its answer, falling back to community answers when present. Global-search degradation produces a warning; the global search implementation remains outside this interface contract. |
| `hybrid` | Runs text, graph, and global retrieval, passes the combined citations to the LLM, and reports recoverable subsystem failures as warnings. |

Explicit modes are checked against the workspace's `supported_modes` and
required index paths before runtime execution. `local` and `hybrid` require an
LLM; `vector` does not. The selected mode can therefore fail with
`MODE_UNAVAILABLE`, `INDEX_NOT_READY`, or `LLM_UNAVAILABLE` before a response
is generated.

## Success, partial, and error

### Success envelope

`QueryResponse.status` is either `"ok"` or `"partial"`; it never has the
value `"error"`. Its fixed top-level fields are:

```text
schema_version, request_id, trace_id, status, mode, answer, citations,
context, retrieval, usage, warnings, debug
```

The contract test `test_query_response_top_level_fields_are_stable_for_v1`
guards this set. The nested fields are:

- `answer`: required `text` and `finish_reason`; the finish reason is one of
  `stop`, `length`, `content_filter`, or `error`.
- `citations`: an array, empty by default. Each citation has required `id`,
  `type`, and `quote`; `source`, `score`, and `triple` may be `null`, and
  `metadata` defaults to `{}`.
- `retrieval`: `text_hits`, `graph_hits`, `community_hits`, and
  `communities_searched` default to `0`; `reranked` defaults to `false`.
- `usage`: required `latency_ms`; `llm_calls`, `prompt_tokens`, and
  `completion_tokens` may be `null`.
- `warnings`: an array of `{code, message}` objects, empty when there is no
  warning.
- `context` and `debug`: `null` unless their request gates are enabled.

The status is `ok` when no warning is produced. It is `partial` whenever at
least one recoverable warning is present, including retrieval, reranking,
answer-generation, or hallucination-guard degradation. A partial response
can still contain an answer, citations, context, and debug data.
Warning messages are stable public summaries; internal exception text is not
part of the v1 contract and is not exposed.

### Error envelope

Errors use `QueryErrorResponse` instead of `QueryResponse`:

```json
{
  "schema_version": "graphrag.query.v1",
  "request_id": "req-123",
  "trace_id": "trace-123",
  "status": "error",
  "error": {
    "code": "INDEX_NOT_READY",
    "message": "The workspace index is not ready.",
    "retryable": true,
    "details": {}
  }
}
```

The HTTP adapter intentionally replaces internal exception messages and
details with the fixed public message and an empty `details` object. The CLI
does the same. A validation failure is returned in this envelope rather than
FastAPI's usual `detail` array.

## Citations

Citation IDs are carried in the answer's evidence convention when a caller
or model references them, and the same IDs are available in `citations`.
Generated fallback IDs are `T1`, `G1`, and `C1` (with the rank incremented);
source-provided IDs are preserved when available. A source can be incomplete
and is represented by `null` fields rather than by a fabricated path.

### Text citation

```json
{
  "id": "T1",
  "type": "text",
  "source": {
    "document_id": "doc-17",
    "file": "maintenance-manual.pdf",
    "page": 12,
    "chunk_id": "chunk-008"
  },
  "quote": "Deposits reduce compressor flow capacity.",
  "score": 0.91,
  "metadata": {},
  "triple": null
}
```

### Graph citation

```json
{
  "id": "G1",
  "type": "graph",
  "source": {
    "document_id": "doc-17",
    "file": "maintenance-manual.pdf",
    "page": 12,
    "chunk_id": "edge-22"
  },
  "quote": "compressor --affected_by--> fouling",
  "score": 0.84,
  "metadata": {},
  "triple": {
    "subject": "compressor",
    "predicate": "affected_by",
    "object": "fouling"
  }
}
```

### Community citation

```json
{
  "id": "community-3",
  "type": "community",
  "source": {
    "document_id": "community-3",
    "file": "Combustor instability"
  },
  "quote": "The community summary links instability to fuel-air distribution.",
  "score": null,
  "metadata": {"community_id": "community-3"},
  "triple": null
}
```

`SourceRef` has nullable `document_id`, `file`, `page`, and `chunk_id`.
`page` accepts an integer or string. Graph citations add `triple` only when
all three node/relation values are available. Community citations derive
from global-search partial answers and use `score: null`.

## Context and debug gates

With the default `include_context: false`, `context` is `null`. With
`include_context: true`, the service returns `context.items`, one item per
citation, plus `rendered_text` in this form:

```text
Question: <query>

[T1] <citation quote>

[G1] <citation quote>
```

With the default `include_debug: false`, `debug` is `null`. With
`include_debug: true`, `debug.prompt` contains the generated prompt when one
was built and `debug.raw_mode_result` contains JSON-safe raw mode data. The
debug serializer redacts absolute paths and secret-like values, including
values under secret-like keys. Debug is diagnostic data, not an authorization
boundary; expose it only to trusted callers. Error envelopes do not include
the prompt or raw runtime result even when the request asked for debug.

## Stable errors and adapter mappings

These are the seven stable codes used by the v1 HTTP/stream surface. The
stream-only code is emitted after an SSE stream has already started.

| Code | HTTP status / behavior | HTTP `retryable` | CLI JSON code | CLI exit |
| --- | ---: | :---: | --- | ---: |
| `INVALID_REQUEST` | `422` | `false` | `INVALID_REQUEST` | `2` |
| `WORKSPACE_NOT_FOUND` | `404` | `false` | `WORKSPACE_NOT_FOUND` | `3` |
| `INDEX_NOT_READY` | `409` | `true` | `INDEX_NOT_READY` | `4` |
| `MODE_UNAVAILABLE` | `409` | `false` | `QUERY_FAILED` fallback | `10` |
| `LLM_UNAVAILABLE` | `503` | `true` | `LLM_UNAVAILABLE` | `5` |
| `QUERY_FAILED` | `500` | `true` | `QUERY_FAILED` | `10` |
| `STREAM_FAILED` | HTTP `200` stream after `meta`; emitted as `event: error` | `true` | not emitted by this non-streaming CLI | — |

The public HTTP messages are fixed as follows: `Request validation failed.`,
`Workspace was not found.`, `The workspace index is not ready.`, `The requested
query mode is unavailable.`, `The language model service is unavailable.`,
and `Query execution failed.`. The CLI uses its own fixed messages: `Invalid
query request.`, `The requested workspace was not found.`, `The workspace index
is not ready.`, `The language model is unavailable.`, and `Query failed.`.

`MODE_UNAVAILABLE` is currently not in the CLI's public-code table, so the CLI
adapter deliberately maps it to `QUERY_FAILED` and exit code `10`. `STREAM_FAILED`
has no CLI mapping because the CLI invokes the non-streaming service. This
table documents current behavior; it does not imply that the CLI has a
streaming adapter.

## SSE events and lifecycle

Each frame is encoded as:

```text
event: <event-name>
data: <one JSON event object>

```

The five typed event names are:

| Event | Required payload |
| --- | --- |
| `meta` | `request_id`, `sequence`, `mode`, `token_streaming` |
| `citation` | `request_id`, `sequence`, `citation` |
| `delta` | `request_id`, `sequence`, `text` |
| `final` | `request_id`, `sequence`, `response` (`QueryResponse`) |
| `error` | `request_id`, `sequence`, `error` (`ErrorDetail`) |

The normal lifecycle is:

```text
meta → citation* → delta* → final
```

Sequences start at `1` and increase by one. The current synchronous
`QueryService.stream()` emits `meta → citation* → final`, with
`meta.token_streaming: false`; it does not fabricate delta events. The typed
`delta` event remains available for a genuine token-producing implementation.

If query setup fails before `meta`, the endpoint returns the normal HTTP JSON
error envelope and no SSE response is started. If the producer raises after
`meta`, the adapter emits exactly one redacted `error` event with code
`STREAM_FAILED`, then closes the stream; it does not emit `final`. Once a
`final` or `error` event is sent, the adapter closes the stream. There is no
resume token, replay store, or `Last-Event-ID` handling. A client that loses
the connection must issue a new query and must not assume that a prior stream
will resume; a transport-level disconnect can also prevent the client from
receiving the terminal event.

## Calling examples

### REST with JSON

```http
POST http://127.0.0.1:8000/api/v1/query
Content-Type: application/json

{
  "query": "What causes compressor fouling?",
  "workspace_id": "power-equipment",
  "mode": "auto",
  "top_k": 5,
  "include_context": false,
  "include_debug": false
}
```

The successful body is a `QueryResponse`; inspect `status`,
`mode.used`, `answer`, `citations`, and `warnings` rather than assuming the
requested mode ran.

### PowerShell

```powershell
$body = @{
  query = "What causes compressor fouling?"
  workspace_id = "power-equipment"
  mode = "auto"
  top_k = 5
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/query" `
  -ContentType "application/json" `
  -Body $body
```

### Python

```python
import requests

from core_domain.query_contracts import QueryErrorResponse, QueryResponse

payload = {
    "query": "What causes compressor fouling?",
    "workspace_id": "power-equipment",
    "mode": "auto",
    "top_k": 5,
}
response = requests.post(
    "http://127.0.0.1:8000/api/v1/query",
    json=payload,
    timeout=60,
)
body = response.json()
if response.ok:
    result = QueryResponse.model_validate(body)
    print(result.mode.used.value, result.answer.text)
else:
    error = QueryErrorResponse.model_validate(body)
    print(error.error.code, error.error.retryable)
```

### Skill CLI

```powershell
python scripts/query_skill.py `
  --query "What causes compressor fouling?" `
  --workspace power-equipment `
  --mode auto `
  --top-k 5
```

The CLI writes exactly one JSON object plus a newline to stdout. Operational
logs go to stderr. Add `--include-context`, `--include-debug`, or `--pretty`
as needed. Use the documented exit code together with the JSON `status` and
`error.code`; a successful response has exit code `0`, while `partial` is
still a successful response with exit code `0`.

For SSE, post the same JSON request to `/api/v1/query/stream` and parse
`event:` plus its JSON `data:` line. Do not concatenate `delta` text unless
`meta.token_streaming` is true; the current service sends the complete answer
only in `final.response.answer.text`.

## v1 compatibility rules

- `schema_version: "graphrag.query.v1"`, existing field names, field types,
  requiredness, and enum meanings are stable.
- A backward-compatible v1 release may add an optional response field. Clients
  must ignore unknown optional response fields so this does not become a
  parsing break.
- A v1 release must not delete an existing field, change its type or
  requiredness, repurpose an enum value, or change the meaning of `ok`,
  `partial`, or `error`.
- A breaking request or response change requires a new version such as v2.
- Request models currently reject unknown request fields (`extra="forbid"`),
  so callers should send only documented request fields.
- The legacy routes remain available, but new integrations should use
  `/api/v1/query` or `scripts/query_skill.py` and should not depend on legacy
  response details.
