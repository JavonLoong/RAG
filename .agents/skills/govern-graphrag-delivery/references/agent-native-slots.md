# Agent-native API slots

The console and FastAPI server were built to call external model APIs. When `govern-graphrag-delivery` is invoked, **the calling agent fills those slots**. Use the agent's own reading and tokens. Do not prompt the user for `llm_api_key`, OpenAI base URL, embedding cloud keys, or a paid graph-extraction provider.

Then write the structured result into the local governance APIs. The server still owns persistence, review, versions, and publication.

## Split

| Keep on the local server | Fill with the agent |
| --- | --- |
| File upload, project workspace, SQLite governance | Schema recommendation |
| Native parse, local OCR if already installed | Entity/relation extraction and aliases |
| `POST /documents/*` review, publish, rollback | Quality notes, OCR-gap transcription when the page is visible |
| Keyword index, hashing / local embedding fallback | Community / cluster summaries |
| `POST /graphs/candidates` validation and storage | Graph triples and evidence bindings |
| `POST /graphs/*/review` and publish | GraphRAG answer synthesis from retrieved evidence |
| `POST /fmea/tasks` create / export / audit trail | FMEA field values and review comments |
| Rules-graph deterministic baseline, if already selected | Conflict write-ups and missing-evidence flags |

Do **not** invent embedding vectors, S/O/D or RPN scores, or evidence locators that are not in the source.

World facts (百科里能当圭臬的那些：历史人物存在、喘振是真实现象、NPSH/RPN 是真方法) stay in the world column. Inventory the book in a second column. A world-true claim that the book never wrote is `本书未记载`, not a graph statement.

## How to write back

Base: `http://127.0.0.1:8000/api/delivery`. Actor: `local-user` unless the user named someone else.

### Schema (M2/M4)

Read published or intake text. Propose `entity_types` and `relation_types` in the project's gas-turbine / power-equipment schema. Put the result in the schema fields or `graph_schema` payload. Do not call a recommend-schema HTTP API if it needs an LLM key.

### Graph statements (M4)

Read each published document version's text and locators. Emit only schema-legal triples. Prefer `POST /graphs/candidates`:

```json
{
  "source_document_version_ids": ["manual-001:v1"],
  "statements": [
    {
      "subject": "润滑油系统",
      "predicate": "故障模式",
      "object": "过滤器堵塞",
      "subject_type": "COMPONENT",
      "object_type": "FAILURE_MODE",
      "evidence_ids": ["EV-..."],
      "confidence": 0.9
    }
  ],
  "metadata": { "actor": "local-user", "extractor": "agent-native" }
}
```

Compatible triple shape if working from chunks before intake:

```json
{
  "triples": [
    {
      "subject": "",
      "relation": "",
      "object": "",
      "evidence": "",
      "source": "",
      "page": "",
      "valid_time": ""
    }
  ]
}
```

Skip `POST /graphs/extract` with `backend=llm` unless a provider is already registered and the user explicitly wants the server job. Agent-authored `statements` are the Operate path.

### FMEA (M5)

Create the task from a **published** graph. If fields are null, submit a `modify` review with per-field `evidence_ids`. Leave unknown values `null`. Never invent S/O/D.

### Q&A / community summary

Retrieve with local `/api/query`, `/api/graphrag`, or delivery search first. The agent writes the answer or summary from those hits. If the server returns "need llm_api_key", do not collect a key — answer from the evidence already in context and label it as agent-native.

### OCR / embedding

- OCR: use installed local engines; if none and the image is visible to the agent, transcribe and mark `agent-native`.
- Embedding: use hashing or an already-local model. Do not ask for an OpenAI embedding key. Do not fabricate vectors.

## Honesty

- Operate: agent-filled statements **are** extraction for this run.
- Audit / Implement: agent fill does not prove `kg_pipeline/llm_extraction` or `/graphs/extract` is production-wired.
- Always keep evidence IDs, document versions, and human approve/reject on the server.
