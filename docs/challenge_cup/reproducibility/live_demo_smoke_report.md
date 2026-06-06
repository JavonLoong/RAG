# Live Demo Smoke Report

- Status: `pass`
- Passed: 8/8
- Scope: local FastAPI app factory, project frontend root page, health route, CORS, search guard, GraphRAG path guard, temporary Chroma ingest/stats/search

| Check | Result | Detail |
| --- | --- | --- |
| health endpoint | pass | GET /api/health -> 200 |
| frontend root page | pass | GET / -> 200; frontend=frontend_app\current_console |
| trusted cors origin | pass | localhost origin accepted; arbitrary origin rejected |
| search top_k guard | pass | GET /api/search?top_k=999 -> 400 |
| graphrag path guard | pass | POST /api/graphrag/stats outside runtime root -> 400 |
| live retrieval ingest | pass | POST /api/ingest -> 200; collection=challenge_cup_live_retrieval_smoke; chunks=3; backend=hashing |
| live retrieval stats | pass | GET /api/stats -> 200; collection=challenge_cup_live_retrieval_smoke; chunks=3 |
| live retrieval search | pass | POST /api/search -> 200; results=3; ids=live-gt07-fault, live-gt07-threshold, live-gt07-repair; not public-demo=True |

## Live Retrieval Evidence

- Collection: `challenge_cup_live_retrieval_smoke`
- Backend: `hashing`
- Query: `GT-07 abnormal vibration compressor outlet temperature repair`
- Result count: `3`
- Record ids: `live-gt07-fault, live-gt07-threshold, live-gt07-repair`
- Backend boundary: not public-demo=`True`
- Stats chunks: `3`

This retrieval evidence is produced from a temporary Chroma collection through /api/ingest, /api/stats, and /api/search. It proves the live API retrieval path works, while the browser public-demo snapshot remains only an offline presentation fallback.

## Boundary

This smoke test verifies local API readiness, project frontend serving, route guards, and a temporary live Chroma retrieval path; it does not replace browser or production-load verification.
