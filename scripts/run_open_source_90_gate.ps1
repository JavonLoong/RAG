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

Invoke-Checked "[1/5] Base local readiness smoke" {
  npm run check
}

Invoke-Checked "[2/5] Open-source 90 unit gates" {
  & $python -m pytest `
    tests/unit/test_open_source_90_quality_profile.py `
    tests/unit/test_promoted_regression_fixtures.py `
    tests/unit/test_rag_evaluation_harness.py `
    tests/unit/test_graphrag_quality_gate.py `
    tests/unit/test_graphrag_triage_regression.py `
    -q
}

Invoke-Checked "[3/5] Seed promoted GraphRAG regression fixture" {
@'
import json
from pathlib import Path

from evaluation import seed_promoted_graphrag_regression_fixture

result = seed_promoted_graphrag_regression_fixture(
    persist_dir=Path("outputs") / "smoke_chroma",
    dataset_path=Path("outputs") / "smoke_chroma" / "evaluation" / "graphrag_triage_regression.jsonl",
    collection_name="rag_smoke",
    backend="hashing",
)
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
'@ | & $python -
}

Invoke-Checked "[4/5] Promoted GraphRAG triage regression" {
  & $python scripts/run_graphrag_triage_regression.py `
    --dataset outputs\smoke_chroma\evaluation\graphrag_triage_regression.jsonl `
    --persist-dir outputs\smoke_chroma `
    --collection rag_smoke `
    --top-k 10 `
    --backend hashing
}

Invoke-Checked "[5/5] Write open-source 90 target report" {
@'
from datetime import datetime
from pathlib import Path

from evaluation import render_quality_profile_markdown

report_dir = Path("evaluation") / "reports"
report_dir.mkdir(parents=True, exist_ok=True)
report_path = report_dir / f"open_source_90_gate_{datetime.now():%Y%m%d_%H%M%S}.md"
report_path.write_text(render_quality_profile_markdown(), encoding="utf-8")
print(report_path)
'@ | & $python -
}

Write-Host "OPEN SOURCE 90 QUALITY GATE PASSED"
