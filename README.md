# PowerRAG

Local-first RAG / GraphRAG workbench for document ingestion, hybrid retrieval, graph construction, global search, evidence-grounded answers, evaluation, and Electron desktop use.

The current runnable product is the console under `api_server/current_console/` with the frontend in `frontend_app/current_console/`. The repository also keeps supporting modules for graph storage, orchestration, retrieval, evaluation, experiments, and desktop packaging.

## Quick Start

```powershell
cd "<repo>"
npm install
npm run check
npm run desktop
```

Open `http://127.0.0.1:8000` for the web console, or use the Electron window started by `npm run desktop`.

## What Works

- Standard RAG ingestion and retrieval.
- GraphRAG graph import, community detection, community summaries, local/global graph search.
- Evidence and citation display for text and graph retrieval.
- Triage history for bad GraphRAG answers.
- Electron desktop shell with larger renderer memory, backend auto-start, and a scoped local file picker.
- WeChat private-chat one-click GraphRAG demo flow.

## Current Main Paths

- Backend: `api_server/current_console/server.py`
- Frontend: `frontend_app/current_console/index.html`
- Desktop: `electron/main.cjs`
- Desktop preload bridge: `electron/preload.cjs`
- Graph store: `storage_layer/graph_store.py`
- Orchestration: `rag_orchestrator/`
- Retrieval: `retrieval_engine/`
- Evaluation: `evaluation/`
- Tests: `tests/unit/`

## Confidence Check

Run:

```powershell
npm run check
```

The check covers:

1. Electron main/preload syntax.
2. Frontend inline script syntax.
3. Python imports for router, retrieval, GraphRAG, and graph store modules.
4. Focused pytest smoke tests.
5. Electron no-window startup smoke.

For the stricter open-source quality target, run:

```powershell
npm run quality:90
```

This applies the `open_source_90` profile in `evaluation/quality_profiles.py` and writes a target report under `evaluation/reports/`.

## GraphRAG Demo Flow

1. Start the desktop shell with `npm run desktop`.
2. Switch to `GraphRAG`.
3. Open the Graph Build page.
4. Use the WeChat private-chat one-click detector for the WeChat demo, or manually select a JSON/PDF/TXT/DOCX corpus.
5. Build the graph, then open the Graph QA page.
6. Ask a question and inspect text evidence, graph evidence, route metadata, and citations.

## Project Layout

```text
RAG/
|- api_server/               # FastAPI service and current console backend
|- frontend_app/             # Current console frontend
|- electron/                 # Desktop wrapper around the local console
|- kg_pipeline/              # Knowledge-graph extraction, communities, summaries
|- rag_orchestrator/         # Query routing, local/global GraphRAG, answer orchestration
|- retrieval_engine/         # Dense/sparse/graph/hybrid retrieval
|- storage_layer/            # Runtime graph/vector/document storage
|- evaluation/               # Evaluation harnesses and reports
|- scripts/                  # Operational scripts and smoke checks
|- tests/                    # Unit and regression tests
`- docs/                     # Architecture notes, readiness reports, plans
```

## Known Limits

- This is a local-first workbench, not a hosted multi-user SaaS.
- Full LLM-backed GraphRAG answers require a configured OpenAI-compatible API key.
- Very large graph visualization may skip full browser rendering; backend graph data and retrieval remain available.
- The current frontend is a single-file console and should be split only after the demo surface is stable.
