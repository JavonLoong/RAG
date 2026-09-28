# Build the PowerRAG Windows onedir executable with PyInstaller.
# Not Electron. Output: desktop_launcher/dist/PowerRAG/PowerRAG.exe
# Keep this file ASCII-only so Windows PowerShell 5.x can parse it.

[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$LauncherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $LauncherDir
$SpecPath = Join-Path $LauncherDir "power_rag_desktop.spec"
$DistDir = Join-Path $LauncherDir "dist"
$WorkDir = Join-Path $env:TEMP "power_rag_pyinstaller"

function Resolve-Python {
    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return $py.Source
    }
    throw "Python not found. Install Python 3.11+ or create repo .venv."
}

Set-Location $RepoRoot
$Python = Resolve-Python
Write-Host "[OK] Python: $Python"
Write-Host "[OK] Spec: $SpecPath"
Write-Host "[OK] WorkDir (ASCII): $WorkDir"
Write-Host "[OK] DistDir: $DistDir"

if (-not $SkipInstall) {
    & $Python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[INFO] Installing PyInstaller ..."
        & $Python -m pip install "pyinstaller>=6.0"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install PyInstaller."
        }
    }
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

& $Python -m PyInstaller --noconfirm --clean `
    --workpath $WorkDir `
    --distpath $DistDir `
    $SpecPath

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$ExePath = Join-Path $DistDir "PowerRAG\PowerRAG.exe"
if (Test-Path $ExePath) {
    $size = (Get-Item $ExePath).Length
    Write-Host "[OK] Built: $ExePath ($size bytes)"
} else {
    Write-Host "[WARN] Missing $ExePath . Check $DistDir"
}
