# PowerRAG Electron Desktop Shell

This is a thin desktop wrapper around the existing FastAPI-served console.

## Quick Desktop Run

```powershell
cd "<repo>"
npm run desktop
```

The desktop shell starts the local backend if needed and opens the console. For a no-window smoke test:

```powershell
$env:POWER_RAG_DESKTOP_SMOKE="1"
npm run electron:dev
```

## Development

```powershell
cd "<repo>"
npm install
npm run electron:dev
```

## Behavior

The Electron main process:

- reuses `http://127.0.0.1:8000` if `/api/health` is already healthy;
- otherwise starts `api_server/current_console/server.py`;
- prefers `.venv\Scripts\python.exe`;
- writes backend startup logs to `storage_layer/runtime/current_console/logs/electron-backend.log`;
- loads the existing frontend from the FastAPI server, so existing `/api/...` calls keep working;
- exposes only scoped desktop bridge methods through `electron/preload.cjs`.

## Optional Environment Variables

- `POWER_RAG_PYTHON`: absolute path to a Python executable.
- `POWER_RAG_HOST`: host for the local backend health/app URL, defaults to `127.0.0.1`.
- `POWER_RAG_PORT`: backend port, defaults to `8000`.
- `POWER_RAG_BACKEND_TIMEOUT_MS`: startup timeout, defaults to `90000`.
- `POWER_RAG_RENDERER_OLD_SPACE_MB`: renderer V8 heap limit for large local imports, defaults to `8192`.
- `POWER_RAG_DISK_CACHE_MB`: Chromium disk cache budget, defaults to `2048`.
- `POWER_RAG_DISABLE_BACKGROUND_THROTTLING`: keep long imports active while the window is covered/backgrounded, defaults to `1`.
- `POWER_RAG_ENABLE_GPU_TUNING`: enable GPU rasterization hints for large graph surfaces, defaults to `0` for stability.
