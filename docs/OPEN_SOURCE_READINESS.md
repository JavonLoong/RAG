# Open Source Readiness Report

## Status

This repository is ready for a local demo when `npm run check` passes.

## Verified Surfaces

- Electron main/preload syntax.
- Frontend inline script syntax.
- Python import smoke for router, retrieval, GraphRAG, and graph store modules.
- Focused pytest smoke.
- WeChat private-chat one-click workflow wiring.
- Electron desktop startup in no-window smoke mode.

## Demo Script

1. Run `npm run check`.
2. Run `npm run desktop`.
3. Open `GraphRAG -> Graph Build`.
4. Click the WeChat private-chat one-click detector.
5. Confirm the workflow logs show corpus load, collection rebuild, graph build, and question dispatch.
6. Inspect Graph QA answer evidence and citations.

## Known Limits

- Full WeChat analysis requires a configured OpenAI-compatible LLM key.
- Browser rendering of very large graphs is intentionally skipped; backend graph data remains available.
- The frontend is still a single-file console and should be split only after the demo surface is stable.
- This is a local-first workbench, not a hosted multi-user service.

## Three-Hour Quality Bar

The project is considered presentable when:

- `npm run check` passes.
- README quick start works on Windows.
- Electron opens without manual backend startup.
- GraphRAG answer failures explicitly state whether text, graph, global summaries, or router evidence is missing.
- Demo flow has a clear screen path and no hidden manual steps.

## Latest Local Verification

- Date: 2026-06-21
- Command: `npm run check`
- Result: PASS
- Notes: Electron syntax check, frontend inline script syntax check, Python import smoke, focused pytest smoke (`32 passed`), and Electron no-window startup smoke all passed.

## Strict Quality Gate

- Command: `npm run quality:90`
- Result: PASS on 2026-06-21
- Notes: This validates the `open_source_90` profile wiring, current guardrail tests, hard routing for full private-contact affection sweeps, and a non-empty seeded promoted GraphRAG regression case. It does not prove real-corpus 90% quality until real promoted GraphRAG cases or an expert gold set are populated.

## External Benchmark Gap

- Legal 10: PASS on 2026-06-21 after keyword cleanup, `96.83 / 100`.
- Legal 50: FAIL on 2026-06-21 after query expansion v1, improved from `49.0 / 100` to `66.37 / 100`.
- Notes: This is the current public benchmark evidence against the 90% target. The external gate intentionally fails without `--allow-fail` until the external score reaches the `open_source_90` profile.
