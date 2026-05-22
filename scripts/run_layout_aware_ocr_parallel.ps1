param(
    [string]$Root = "",
    [string]$OutputRoot = "data_pipeline\ocr_layout_aware\tsinghua_gas_turbine_books",
    [string]$Engine = "rapidocr",
    [int]$TesseractPsm = 4,
    [double]$RenderScale = 1.0,
    [int]$Threads = 1,
    [int]$ProgressEvery = 100
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = Resolve-Path (Join-Path $PSScriptRoot "..")
}
$python = Join-Path $Root ".venv\Scripts\python.exe"
$script = Join-Path $Root "scripts\ocr_scanned_pdfs.py"
$logDir = Join-Path $Root "observability\logs\layout_aware_ocr_parallel"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$groups = @(
    @{ name = "worker_01"; indexes = "1,5,6" },
    @{ name = "worker_02"; indexes = "2,3" },
    @{ name = "worker_03"; indexes = "4,7" },
    @{ name = "worker_04"; indexes = "8,9,11" },
    @{ name = "worker_05"; indexes = "10,13" },
    @{ name = "worker_06"; indexes = "12" }
)

$started = @()
foreach ($group in $groups) {
    $stdout = Join-Path $logDir "$($group.name).out.log"
    $stderr = Join-Path $logDir "$($group.name).err.log"
    $args = @(
        "-S",
        $script,
        "--output-root", $OutputRoot,
        "--layout-aware",
        "--engine", $Engine,
        "--tesseract-psm", "$TesseractPsm",
        "--render-scale", "$RenderScale",
        "--onnx-threads", "$Threads",
        "--pdf-indexes", $group.indexes,
        "--progress-every", "$ProgressEvery"
    )
    $process = Start-Process -FilePath $python `
        -ArgumentList $args `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden `
        -PassThru
    $started += [pscustomobject]@{
        name = $group.name
        indexes = $group.indexes
        pid = $process.Id
        stdout = $stdout
        stderr = $stderr
    }
}

$statePath = Join-Path $logDir "run_state.json"
$payload = [pscustomobject]@{
    started_at = (Get-Date).ToString("s")
    output_root = $OutputRoot
    engine = $Engine
    render_scale = $RenderScale
    workers = $started
}
$payload | ConvertTo-Json -Depth 5 | Set-Content -Path $statePath -Encoding UTF8
$payload | ConvertTo-Json -Depth 5
