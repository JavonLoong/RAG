$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$packageJson = Join-Path $repoRoot "package.json"

if (-not (Test-Path -LiteralPath $packageJson)) {
  Write-Host "[PowerRAG] Cannot find package.json:" -ForegroundColor Red
  Write-Host $packageJson -ForegroundColor Red
  Read-Host "Press Enter to close"
  exit 1
}

Set-Location -LiteralPath $repoRoot
Write-Host "[PowerRAG] Starting desktop app from:" -ForegroundColor Cyan
Write-Host $repoRoot
Write-Host "[PowerRAG] Keep this window open if startup fails." -ForegroundColor DarkGray

npm run desktop

if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "[PowerRAG] Startup failed. Check the error above." -ForegroundColor Red
  Read-Host "Press Enter to close"
}
