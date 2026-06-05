# Live Demo Smoke Report

- Status: `pass`
- Passed: 5/5
- Scope: local FastAPI app factory, health route, CORS, search guard, GraphRAG path guard

| Check | Result | Detail |
| --- | --- | --- |
| health endpoint | pass | GET /api/health -> 200 |
| missing frontend fallback | pass | GET / -> 404 |
| trusted cors origin | pass | localhost origin accepted; arbitrary origin rejected |
| search top_k guard | pass | GET /api/search?top_k=999 -> 400 |
| graphrag path guard | pass | POST /api/graphrag/stats outside runtime root -> 400 |

## Boundary

This smoke test verifies local API readiness and route guards; it does not replace browser or production-load verification.
