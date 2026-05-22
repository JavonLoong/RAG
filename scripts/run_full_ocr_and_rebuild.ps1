$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$OcrScript = Join-Path $RepoRoot "scripts\ocr_scanned_pdfs.py"
$BuildScript = Join-Path $RepoRoot "scripts\build_ocr_enriched_rag_chroma.py"
$RetrievalScript = Join-Path $RepoRoot "scripts\run_retrieval_smoke_tests.py"
$RunDir = Join-Path $RepoRoot "observability\logs\ocr_full_pipeline"
New-Item -ItemType Directory -Path $RunDir -Force | Out-Null

$MainLog = Join-Path $RunDir ("full_ocr_pipeline_{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

function Write-Log {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "s"), $Message
    Add-Content -Path $MainLog -Value $line -Encoding UTF8
    Write-Output $line
}

Write-Log "pipeline_start repo=$RepoRoot"

$stale = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*ocr_scanned_pdfs.py*" }
foreach ($proc in $stale) {
    Write-Log "stop_stale_ocr pid=$($proc.ProcessId)"
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
}

$groups = @("12,5,6,11", "1,8,4", "13,9,2", "7,10,3")
$processes = @()
for ($i = 0; $i -lt $groups.Count; $i++) {
    $group = $groups[$i]
    $label = "group_{0}" -f ($i + 1)
    $stdout = Join-Path $RunDir "$label.out.log"
    $stderr = Join-Path $RunDir "$label.err.log"
    $args = @(
        "-S",
        $OcrScript,
        "--pdf-indexes",
        $group,
        "--render-scale",
        "0.85",
        "--onnx-threads",
        "1",
        "--progress-every",
        "25"
    )
    Write-Log "start_ocr_group label=$label pdf_indexes=$group"
    $proc = Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $RepoRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $processes += [PSCustomObject]@{
        Label = $label
        Group = $group
        Id = $proc.Id
        Stdout = $stdout
        Stderr = $stderr
    }
}

$processes | ConvertTo-Json -Depth 3 | Set-Content -Path (Join-Path $RunDir "ocr_group_processes.json") -Encoding UTF8

foreach ($item in $processes) {
    Write-Log "wait_ocr_group label=$($item.Label) pid=$($item.Id)"
    Wait-Process -Id $item.Id
    $exitCode = (Get-Process -Id $item.Id -ErrorAction SilentlyContinue).ExitCode
    $errSize = if (Test-Path $item.Stderr) { (Get-Item $item.Stderr).Length } else { 0 }
    Write-Log "ocr_group_finished label=$($item.Label) pid=$($item.Id) err_bytes=$errSize"
    if ($errSize -gt 0) {
        Write-Log "ocr_group_stderr label=$($item.Label) path=$($item.Stderr)"
    }
}

Write-Log "aggregate_ocr_summary_start"
& $Python -S $OcrScript --render-scale 0.85 --onnx-threads 1 --progress-every 100
Write-Log "aggregate_ocr_summary_done"

Write-Log "build_ocr_enriched_chroma_start"
& $Python -S $BuildScript
Write-Log "build_ocr_enriched_chroma_done"

Write-Log "retrieval_smoke_start"
& $Python -S $RetrievalScript --library "storage_layer/runtime/ocr_enriched_rag_chroma" --collection "gas_turbine_ocr_enriched_rag" --top-k 3
Write-Log "retrieval_smoke_done"

Write-Log "pipeline_done"
