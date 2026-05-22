# Current Console Integration Notes

This directory contains the current static console UI source:

```text
frontend_app/current_console/index.html
```

The real RAG backend entry is:

```text
api_server/current_console/server.py
```

The frontend can be reused for the real RAG console, but GitHub Pages alone cannot run the backend. Pages must call a separately hosted API server.

## Local Development

### Backend-backed mode

Run the API server:

```powershell
cd "D:\虚拟C盘\RAG\api_server\current_console"
$env:PYTHONPATH="$PWD\chroma_rag_poc\src"
python server.py
```

Then open:

```text
http://localhost:8000
```

This path is the easiest local integration mode because the FastAPI app serves the frontend and the API from the same origin. API requests such as `/api/health`, `/api/stats`, and `/api/search` resolve against `http://localhost:8000`.

The backend writes runtime data under:

```text
storage_layer/runtime/current_console/
  uploads/
  chroma/
  logs/
```

### Static-file mode

Opening `frontend_app/current_console/index.html` directly from the filesystem starts browser-local mode because the page detects `file:` protocol.

That is useful for UI preview and lightweight browser-side demos, but it is not the same as using the real backend:

- no FastAPI process is running;
- no server-side ChromaDB persistence is used;
- uploads are not saved to `storage_layer/runtime/current_console/uploads`;
- backend logs are not produced.

## Current API Calls Used by the Console

The existing page already has API-oriented calls for server mode:

| Purpose | Method and path |
| --- | --- |
| Health | `GET /api/health` |
| All collection stats | `GET /api/stats` |
| One collection stats | `GET /api/stats?collection=...` |
| Upload one file | `POST /api/upload` |
| List uploaded files | `GET /api/uploads` |
| Process selected uploaded files | `POST /api/process` |
| Search | `GET /api/search?q=...&top_k=...&collection=...` |
| Benchmark | `POST /api/benchmark` |
| Delete one upload | `DELETE /api/uploads/{filename}?purge_vectors=true|false` |
| Delete multiple uploads | `POST /api/uploads/delete` |
| Delete collection | `DELETE /api/collections/{name}` |
| List logs | `GET /api/logs?limit=50` |
| Read log | `GET /api/logs/{filename}` |

The backend also exposes `POST /api/ingest` for upload-and-ingest in one request, but the current UI mostly uses the staged flow: upload first, then process selected files.

## GitHub Pages Deployment

The public page is:

```text
https://javonloong.github.io/RAG/
```

For this page to become the real RAG entry, it needs an API base URL that points to a deployed backend, for example:

```js
window.RAG_CONSOLE_CONFIG = {
  API_BASE_URL: "https://rag-api.example.com"
};
```

Future frontend wiring should use this value when building request URLs:

```js
const API_BASE = window.RAG_CONSOLE_CONFIG?.API_BASE_URL || "";
```

It should also avoid forcing browser-local mode on `*.github.io` when a non-empty API base URL is configured.

Expected production flow:

```text
https://javonloong.github.io/RAG/
  -> https://rag-api.example.com/api/health
  -> https://rag-api.example.com/api/upload
  -> https://rag-api.example.com/api/process
  -> https://rag-api.example.com/api/search
```

Do not point the Pages frontend at `http://localhost:8000` for normal users. That only works on the developer's own machine and only while the local backend is running.

## CORS Notes

When frontend and backend are on different origins, the backend must allow the Pages origin.

For production, prefer an allowlist instead of `*`, for example:

```text
https://javonloong.github.io
```

During local testing, also allow:

```text
http://localhost:8000
http://127.0.0.1:8000
```

Uploads and JSON POST requests may trigger browser preflight requests. The API must allow the needed methods and headers for:

- `GET`
- `POST`
- `DELETE`
- `Content-Type`

The current backend has permissive CORS in `create_app()`, which is convenient for development. It should be tightened before exposing the write/delete/log endpoints publicly.

## Log Endpoint Caveat

`GET /api/logs` and `GET /api/logs/{filename}` exist, but the backend applies a same-origin style guard before returning logs.

If the frontend is served from GitHub Pages and the API is on another domain, log listing or log file links may fail until the log access policy is made explicit. Reasonable options:

- keep logs available only in same-origin local/admin deployments;
- allow the Pages origin for log reads after auth is added;
- hide or disable log detail links in public Pages mode;
- serve the frontend and API through the same production reverse proxy.

## Browser File Limitations

The hosted page can only access files the user chooses through browser file input or drag-and-drop. It cannot scan arbitrary local folders by path.

Folder upload depends on browser support for `webkitdirectory`. It works in Chromium-based browsers, but should not be treated as a universal filesystem API.

For real ingestion:

1. The user selects files in the browser.
2. The frontend sends the file bytes to `POST /api/upload`.
3. The backend saves them under its own upload directory.
4. The frontend calls `POST /api/process`.
5. The backend parses, chunks, embeds, and writes to ChromaDB.
6. Search calls use `GET /api/search` or `POST /api/search`.

## Minimum Safe Integration Tasks

1. Add a frontend config source for `API_BASE_URL`.
2. Make GitHub Pages use server mode when `API_BASE_URL` is present.
3. Deploy `api_server/current_console/server.py` behind HTTPS.
4. Configure CORS for the Pages origin.
5. Add authentication before public upload, process, benchmark, delete, and log access.
6. Decide whether log detail links are available from Pages.

Until those are done, the Pages console should be described as a reusable static UI and browser-local demo, not as a complete backend-backed RAG service.
