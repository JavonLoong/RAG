$ErrorActionPreference = "Stop"

$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repo

$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)][string]$Label,
    [Parameter(Mandatory = $true)][scriptblock]$Command
  )

  Write-Host $Label
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE"
  }
}

Invoke-Checked "[1/5] Electron syntax check" { npm run electron:check }

Invoke-Checked "[2/5] Frontend inline script syntax check" {
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
}

Invoke-Checked "[3/5] Python import smoke" {
@'
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
'@ | & $python -
}

Invoke-Checked "[4/5] Focused pytest smoke" {
  & $python -m pytest `
    tests/unit/test_query_understanding.py `
    tests/unit/test_graph_store.py `
    tests/unit/test_graphrag_quality_gate.py `
    tests/unit/test_frontend_demo_mode_contract.py `
    tests/unit/test_open_source_readiness_contract.py `
    -q
}

Invoke-Checked "[5/5] Desktop smoke" {
  $env:POWER_RAG_DESKTOP_SMOKE = "1"
  try {
    npm run electron:dev
  } finally {
    Remove-Item Env:\POWER_RAG_DESKTOP_SMOKE -ErrorAction SilentlyContinue
  }
}

Write-Host "OPEN SOURCE READINESS SMOKE PASSED"
