---
name: govern-graphrag-delivery
description: Run, implement, audit, or report an evidence-governed M2-M5 GraphRAG delivery workflow from document parsing/OCR through canonical versioned materials, schema-constrained graphs, and reviewable FMEA outputs. When this skill is invoked, the agent fills every model-shaped API slot with its own capability and tokens instead of asking for OpenAI/LLM/embedding keys. Use when an agent is asked about GraphRAG module delivery, 解析与标注, 资料库构建, 图谱构建, FMEA generation, evidence binding, 自己的token, 不用配API, agent-native fill, human review, version publication or rollback, delivery APIs, acceptance testing, or completion reporting in this PowerRAG/RAG repository.
---

# Govern GraphRAG Delivery

Treat GraphRAG delivery as a governed evidence pipeline, not as a one-shot generation task. Preserve source traceability, human decisions, version lineage, and honest acceptance status from M2 through M5.

The complete implementation lives in [code/](code/). `agents/openai.yaml` is only the agent label. After changing repo modules, refresh the skill copy with `python scripts/pack_code.py`.

## Choose the operating mode

Identify the requested mode before acting:

- **Operate**: run an existing document → graph → FMEA flow.
- **Implement**: add or repair one or more M2–M5 capabilities.
- **Audit**: decide whether assigned tasks are complete, partial, or missing.
- **Report**: turn repository evidence into a concise progress or meeting update.

For this repository, read [references/repository-map.md](references/repository-map.md) before inspecting or changing code. Read [references/api-contract.md](references/api-contract.md) when calling or extending `/api/delivery`. Read [references/agent-native-slots.md](references/agent-native-slots.md) before any step that would have called an LLM, embedding, schema-recommend, graph-extract, community-summary, QA, or FMEA-generation API. Read [references/acceptance-matrix.md](references/acceptance-matrix.md) for audits, completion claims, or release decisions.

## Enforce the invariants

Apply these rules in every mode:

1. Keep every derived fact traceable to a stable source locator containing the document version, chunk or block, source file, and page when available.
2. Publish a document version only after source evidence exists and the latest human decision approves it.
3. Build graph candidates only from published document versions.
4. Bind every graph statement to evidence from the selected document versions. Block publication for unknown types, unknown relations, missing evidence, or out-of-scope evidence.
5. Normalize aliases and duplicates without erasing source disagreement. Surface conflicts for review.
6. Generate FMEA only from a published graph. Keep unknown fields null and attach evidence per field.
7. Never invent S/O/D or RPN scores without an approved evidence-backed scoring policy.
8. Persist approve, reject, modify, rollback, and feedback actions as auditable records.
9. Do not call a module complete merely because synthetic unit tests pass. Require implementation, integration, and representative acceptance evidence.
10. When this skill is invoked, the calling agent **is** the model. Fill every model-shaped slot with the agent's own reading, extraction, and writing. Do not ask the user to paste an API key, base URL, or cloud provider for those slots. Persist the agent's output through local `/api/delivery` and governance APIs. Local storage, review gates, and versioning stay on the server.
11. Treat encyclopedic world knowledge (Wikipedia / Britannica style: 秦始皇存在, compressor surge exists, NPSH and RPN are real methods) as world-true, not as document evidence. Say 书中有 / 书中无 separately. Do not write world-true facts into the book, and do not deny them just because the book is silent.

## Execute the M2–M5 workflow

### 1. Establish scope and baseline

- Record the repository root, branch or commit, requested modules, inputs, and expected outputs.
- Inspect the current worktree before edits. Preserve unrelated changes.
- Locate the implementation and tests instead of relying on documentation claims alone.
- For an audit, evaluate committed branch content separately from uncommitted workspace files.

### 2. Process M2 — parsing and annotation

- Classify the file and select native parsing, OCR, or an external layout parser.
- If the page image is already in context and local OCR is missing, the agent may supply text and locators itself. Do not ask for a cloud OCR key.
- Preserve original text and structural locators for headings, paragraphs, pages, tables, images, and captions when available.
- Record quality issues such as missing pages, malformed content, low OCR confidence, flattened tables, or absent page metadata.
- Create a reviewable document candidate; do not silently promote failed or OCR-required input.
- Preserve human corrections and decisions. If a correction changes content, create or update a canonical version rather than storing only a comment.

### 3. Process M3 — canonical material library

- Maintain candidate, needs-review, published, and retired states.
- Bind chunks to the canonical document version and original evidence.
- Publish only the approved version and retain supersession lineage.
- Update the retrieval index from the published version; verify keyword, semantic, and hybrid retrieval against that version.
- Test compare, rollback, incremental update, no-answer behavior, index rebuild, and recovery.

### 4. Process M4 — governed graph

- Apply the gas-turbine entity and relation schema.
- In **Operate** mode, the agent extracts candidate statements itself from published document text, then `POST /graphs/candidates` with those `statements`. Do not wait for `/graphs/extract` plus an LLM provider.
- Normalize aliases, merge exact duplicates, and retain conflicts.
- Reject or block statements whose types, relations, or evidence bindings violate the schema.
- Publish a versioned graph and synchronize it with the graph store used by GraphRAG retrieval.
- Verify graph query, path display, export, ordinary-RAG comparison, and ordinary-RAG fallback.
- In **Audit/Implement** mode, do not describe server-side auto-extraction as integrated when the live endpoint still requires callers to supply `statements`. Agent-authored statements count as Operate extraction, not as a claim that `kg_pipeline/llm_extraction` is wired.

### 5. Process M5 — reviewable FMEA delivery

- Select published document and graph versions plus an approved output template.
- Derive equipment, component, failure mode, cause, effect, detection method, and recommended action **in the agent**. If `POST /fmea/tasks` returns empty or unknown fields, fill them with a `modify` review that keeps per-field `evidence_ids`.
- Attach evidence IDs per field and display missing, unsupported, or conflicting values.
- Apply human edits without losing the audit trail or evidence policy.
- Publish only approved results; verify JSON and CSV exports represent the same reviewed data.
- Route issues to their root module. Distinguish creating a feedback record from actually rebuilding and revalidating an upstream artifact.

### 6. Close the loop

- Re-run affected downstream stages after an upstream correction.
- Verify document, index, graph, and FMEA version consistency.
- Retain validation commands, results, fixtures, and known limitations as acceptance evidence.

## Audit completion honestly

Use this rubric for each checklist item:

- **Complete**: implemented, connected to its real upstream/downstream systems, and verified with representative acceptance evidence.
- **Partial**: a component, API, or test exists, but integration or representative validation is missing.
- **Missing**: no executable evidence exists, or only prose/plans describe the capability.
- **Deferred**: explicitly outside the accepted scope; do not count it as complete.

When evidence conflicts, prefer executable code and test behavior over comments or status documents. Report the exact limitation; avoid invented percentages unless the scoring method is stated.

## Validate proportionately

Run the focused smoke tests when the repository provides them:

```powershell
python -m pytest tests/unit/test_governed_delivery_workflow.py tests/unit/test_delivery_api.py -q
```

Treat those tests as smoke coverage. Before a full-completion claim, also cover representative native PDF, scanned PDF, DOCX, image, Chinese and English inputs; partial-page failure or timeout; human correction flow; index rebuild; alias and source conflicts; no-answer and RAG fallback; graph-store synchronization; and FMEA export round-trip consistency.

## Produce the result

For an operation or implementation task, return:

1. versions and artifacts created,
2. quality gates and review decisions,
3. validation results,
4. unresolved risks and required human decisions.

For an audit or report, use [assets/delivery-audit-report.md](assets/delivery-audit-report.md) and include:

1. audited branch or commit,
2. M2–M5 status table,
3. concrete code/test evidence,
4. gaps that prevent a completion claim,
5. the next smallest verifiable delivery step.

Use [assets/gas-turbine-fmea-minimum-v1.yaml](assets/gas-turbine-fmea-minimum-v1.yaml) when a portable minimum FMEA template is needed outside this repository.
