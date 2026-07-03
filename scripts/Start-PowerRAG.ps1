$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$packageJson = Join-Path $repoRoot "package.json"
$electronCmd = Join-Path $repoRoot "node_modules\.bin\electron.cmd"
$electronPs1 = Join-Path $repoRoot "node_modules\.bin\electron.ps1"

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

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  Write-Host ""
  Write-Host "[PowerRAG] Cannot find npm. Please install Node.js, then start PowerRAG again." -ForegroundColor Red
  Read-Host "Press Enter to close"
  exit 1
}

if (-not (Test-Path -LiteralPath $electronCmd) -and -not (Test-Path -LiteralPath $electronPs1)) {
  Write-Host ""
  Write-Host "[PowerRAG] Electron is not installed locally. Installing desktop dependencies..." -ForegroundColor Yellow
  npm install --no-audit --fund=false

  if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[PowerRAG] Dependency installation failed. Check the error above." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit $LASTEXITCODE
  }
}

npm run desktop

if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "[PowerRAG] Startup failed. Check the error above." -ForegroundColor Red
  Read-Host "Press Enter to close"
}
