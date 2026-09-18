# Three-Hour Open-Source Hardening Plan

## Goal

Make the local PowerRAG demo presentable with a clear setup path, stable smoke checks, and evidence-grounded GraphRAG quality gates.

## Scope

- Keep the current FastAPI + single-file frontend + Electron shell runnable.
- Preserve the generic PowerRAG one-click flow.
- Validate graph build, query routing, evidence display, graph quality gate, and triage regression.
- Keep local-only behavior explicit.

## Checklist

1. Run `npm run check`.
2. Run `npm run desktop`.
3. Verify the web console opens through Electron.
4. Select a JSON/PDF/TXT/DOCX corpus or use the generic one-click flow.
5. Build the graph and confirm nodes, edges, communities, and summaries are generated.
6. Ask a question and confirm text evidence, graph evidence, route metadata, and citations are visible.
7. Run `npm run quality:90` and confirm the promoted GraphRAG regression fixture is non-empty.

## Required Contracts

- `frontend_app/current_console/index.html` exposes the generic PowerRAG one-click flow.
- `electron/main.cjs` exposes a scoped local corpus picker.
- `/api/query` returns route metadata, capabilities, citations, and graph quality diagnostics.
- Evaluation fixtures use generic equipment/document evidence cases.

## Known Limits

- Full LLM-backed GraphRAG answers require an OpenAI-compatible API key.
- Large graph rendering may downgrade to summarized views.
- The frontend is still a single-file console and should be split only after the demo surface stabilizes.
