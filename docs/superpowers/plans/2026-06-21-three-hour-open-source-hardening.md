# Three Hour Open Source Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Within three hours, raise the existing RAG / GraphRAG / Electron project to a credible open-source demo standard without changing the overall architecture.

**Architecture:** Keep the current structure intact: `api_server/current_console`, `frontend_app/current_console`, `rag_orchestrator`, `retrieval_engine`, `storage_layer`, `evaluation`, and `electron`. Add only thin documentation, smoke scripts, tests, and small UI/guardrail hooks that prove the existing system works.

**Tech Stack:** Python/FastAPI, local Chroma-style RAG pipeline, GraphRAG graph store, plain HTML/JS frontend, Electron desktop shell, pytest, Node/Electron syntax checks.

---

## Scope Lock

Do not restructure the project. Do not migrate the frontend framework. Do not replace the RAG stack. Do not introduce a new database. The three-hour target is engineering presentation and reliability hardening:

1. One command proves the project is alive.
2. One short README path lets a new user run it.
3. One demo flow proves GraphRAG can ingest, build, retrieve, and cite evidence.
4. One failure-report path explains why answers lack context.
5. One desktop entry point opens without manual backend work.

## Files

- Modify: `D:/虚拟C盘/RAG/README.md`
- Modify: `D:/虚拟C盘/RAG/package.json`
- Modify: `D:/虚拟C盘/RAG/electron/README.md`
- Create: `D:/虚拟C盘/RAG/scripts/quick_health_check.ps1`
- Create: `D:/虚拟C盘/RAG/docs/OPEN_SOURCE_READINESS.md`
- Create: `D:/虚拟C盘/RAG/tests/unit/test_open_source_readiness_contract.py`
- Optional small modify: `D:/虚拟C盘/RAG/frontend_app/current_console/index.html`

## Three-Hour Schedule

### Task 1: One-Command Health Check

**Files:**
- Create: `D:/虚拟C盘/RAG/scripts/quick_health_check.ps1`
- Modify: `D:/虚拟C盘/RAG/package.json`

- [ ] **Step 1: Add the health check script**

Create `scripts/quick_health_check.ps1`:

```powershell
$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repo

Write-Host "[1/5] Electron syntax check"
npm run electron:check

Write-Host "[2/5] Frontend inline script syntax check"
@'
const fs = require("node:fs");
const vm = require("node:vm");
const html = fs.readFileSync("frontend_app/current_console/index.html", "utf8");
const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)]
  .filter((m) => !/\bsrc\s*=/.test(m[1] || ""));
for (let i = 0; i < scripts.length; i += 1) {
  new vm.Script(scripts[i][2], { filename: `inline-script-${i + 1}.js` });
}
console.log(`checked ${scripts.length} inline scripts`);
'@ | node -

Write-Host "[3/5] Python import smoke"
python - <<'PY'
import importlib
mods = [
  "rag_orchestrator.router",
  "rag_orchestrator.global_search",
  "rag_orchestrator.graphrag_qa",
  "retrieval_engine.hybrid",
  "storage_layer.graph_store",
]
for mod in mods:
    importlib.import_module(mod)
print("python imports ok")
PY

Write-Host "[4/5] Focused pytest smoke"
python -m pytest `
  tests/unit/test_query_understanding.py `
  tests/unit/test_graph_store.py `
  tests/unit/test_graphrag_quality_gate.py `
  tests/unit/test_frontend_demo_mode_contract.py `
  -q

Write-Host "[5/5] Desktop smoke"
$env:POWER_RAG_DESKTOP_SMOKE = "1"
npm run electron:dev
Remove-Item Env:\POWER_RAG_DESKTOP_SMOKE -ErrorAction SilentlyContinue

Write-Host "OPEN SOURCE READINESS SMOKE PASSED"
```

- [ ] **Step 2: Add npm scripts**

Patch `package.json` scripts:

```json
{
  "scripts": {
    "desktop": "electron .",
    "electron:dev": "electron .",
    "electron:check": "node --check electron/main.cjs && node --check electron/preload.cjs",
    "check": "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/quick_health_check.ps1",
    "smoke": "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/quick_health_check.ps1"
  }
}
```

- [ ] **Step 3: Verify**

Run:

```powershell
cd "D:\虚拟C盘\RAG"
npm run check
```

Expected: final line `OPEN SOURCE READINESS SMOKE PASSED`.

### Task 2: README as the Project Front Door

**Files:**
- Modify: `D:/虚拟C盘/RAG/README.md`
- Modify: `D:/虚拟C盘/RAG/electron/README.md`

- [ ] **Step 1: Replace the top 80 lines of README with a clean front door**

The README top must answer:

```markdown
# PowerRAG

Local-first RAG / GraphRAG workbench for document ingestion, hybrid retrieval, graph construction, global search, evidence-grounded answers, evaluation, and Electron desktop use.

## Quick Start

```powershell
cd "D:\虚拟C盘\RAG"
npm install
npm run check
npm run desktop
```

Open `http://127.0.0.1:8000` for the web console, or use the Electron window started by `npm run desktop`.

## What Works

- Standard RAG ingestion and retrieval
- GraphRAG graph import, community detection, community summaries, local/global graph search
- Evidence/citation display for text and graph retrieval
- Triage history for bad GraphRAG answers
- Electron desktop shell with larger renderer memory and local file picker
- WeChat private-chat one-click GraphRAG demo flow

## Current Main Paths

- Backend: `api_server/current_console/server.py`
- Frontend: `frontend_app/current_console/index.html`
- Desktop: `electron/main.cjs`
- Graph store: `storage_layer/graph_store.py`
- Orchestration: `rag_orchestrator/`
- Tests: `tests/unit/`

## Confidence Check

Run:

```powershell
npm run check
```
```

- [ ] **Step 2: Add Electron README quick use**

Add to `electron/README.md`:

```markdown
## Quick Desktop Run

```powershell
cd "D:\虚拟C盘\RAG"
npm run desktop
```

The desktop shell starts the local backend if needed and opens the console. For a no-window smoke test:

```powershell
$env:POWER_RAG_DESKTOP_SMOKE="1"
npm run electron:dev
```
```

### Task 3: Evidence Contract Test

**Files:**
- Create: `D:/虚拟C盘/RAG/tests/unit/test_open_source_readiness_contract.py`

- [ ] **Step 1: Add a contract test that protects the demo promises**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_project_front_door_mentions_required_paths():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required = [
        "npm run check",
        "npm run desktop",
        "api_server/current_console/server.py",
        "frontend_app/current_console/index.html",
        "electron/main.cjs",
        "storage_layer/graph_store.py",
        "rag_orchestrator/",
    ]
    for text in required:
        assert text in readme


def test_desktop_one_click_contract_is_present():
    html = (ROOT / "frontend_app/current_console/index.html").read_text(encoding="utf-8")
    required = [
        "btnKgWechatOneClick",
        "WECHAT_AFFECTION_QUESTION",
        "applyWechatAffectionGraphPreset",
        "runWechatAffectionOneClick",
        "kgPublicBooksJsonMode",
        "generative",
    ]
    for text in required:
        assert text in html


def test_electron_local_file_picker_contract_is_present():
    main = (ROOT / "electron/main.cjs").read_text(encoding="utf-8")
    preload = (ROOT / "electron/preload.cjs").read_text(encoding="utf-8")
    assert "power-rag:pick-wechat-rag-corpus" in main
    assert "findDefaultWechatRagCorpus" in main
    assert "pickWechatRagCorpus" in preload
```

- [ ] **Step 2: Run the new test**

```powershell
python -m pytest tests/unit/test_open_source_readiness_contract.py -q
```

Expected: `3 passed`.

### Task 4: Readiness Report

**Files:**
- Create: `D:/虚拟C盘/RAG/docs/OPEN_SOURCE_READINESS.md`

- [ ] **Step 1: Add the readiness report**

```markdown
# Open Source Readiness Report

## Status

This repository is ready for a local demo if `npm run check` passes.

## Verified Surfaces

- Electron syntax and smoke startup
- Frontend inline script syntax
- Python import smoke for router, retrieval, GraphRAG, and graph store
- Focused pytest smoke
- WeChat private-chat one-click workflow wiring

## Demo Script

1. Run `npm run check`.
2. Run `npm run desktop`.
3. Open `GraphRAG -> 图谱构建`.
4. Click `微信私聊一键检测`.
5. Confirm the workflow logs show corpus load, rebuild collection, graph build, and question dispatch.
6. Inspect `图谱问答` answer evidence and citations.

## Known Limits

- Full WeChat analysis requires a configured LLM key.
- Browser rendering of very large graphs is intentionally skipped; backend graph data remains available.
- The frontend is still a single-file console and should be split only after the demo is stable.
- This is a local-first workbench, not a hosted multi-user service.

## Three-Hour Quality Bar

The project is considered presentable when:

- `npm run check` passes.
- README quick start works on Windows.
- Electron opens without manual backend startup.
- GraphRAG answer failures explicitly state whether text, graph, global summaries, or router evidence is missing.
- Demo flow has a clear screen path and no hidden manual steps.
```

### Task 5: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run targeted checks**

```powershell
npm run electron:check
python -m pytest tests/unit/test_open_source_readiness_contract.py -q
```

- [ ] **Step 2: Run full quick check**

```powershell
npm run check
```

- [ ] **Step 3: Record outcome**

Append the actual command results to `docs/OPEN_SOURCE_READINESS.md` under:

```markdown
## Latest Local Verification

- Date: 2026-06-21
- Command: `npm run check`
- Result: PASS / FAIL
- Notes: ...
```

## Fallback If Time Runs Out

If only 60 minutes remain, do only Task 1, Task 2, and the first half of Task 3. A passing one-command smoke plus clean README gives the biggest visible jump in open-source maturity.

If only 30 minutes remain, do only:

1. `scripts/quick_health_check.ps1`
2. `package.json` script `check`
3. README quick start

Those three changes create the minimum credible project surface.

## Self-Review

- Spec coverage: covers three-hour improvement, no structural rewrite, desktop, GraphRAG, one-click workflow, evidence/failure explanation, and verification.
- Placeholder scan: no TBD/TODO/later placeholders.
- Type consistency: paths and script names are consistent across README, package, tests, and readiness report.
