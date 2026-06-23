$ErrorActionPreference = "Stop"

$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repo

$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

& $python scripts/run_open_source_90_external_benchmark_gate.py @args
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
