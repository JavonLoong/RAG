param(
    [string]$Token = "ec852093a34e49c39850"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$TargetDir = Join-Path $RepoRoot "data_pipeline\raw\tsinghua_gas_turbine_books"
$TempDir = Join-Path $TargetDir ".download_tmp"
$LogPath = Join-Path $TargetDir "download.log"
$ManifestPath = Join-Path $TargetDir "download_manifest.json"

New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogPath -Value $line -Encoding UTF8
    Write-Host $line
}

function New-ZipTask {
    param([string]$FileName)
    $headers = @{
        "X-Requested-With" = "XMLHttpRequest"
        "Accept" = "application/json, text/plain, */*"
        "Referer" = "https://cloud.tsinghua.edu.cn/d/$Token/"
        "User-Agent" = "Mozilla/5.0"
    }
    $payload = @{
        token = $Token
        parent_dir = "/"
        dirents = @($FileName)
    } | ConvertTo-Json -Compress

    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($payload)

    Invoke-RestMethod `
        -Uri "https://cloud.tsinghua.edu.cn/api/v2.1/share-link-zip-task/" `
        -Method Post `
        -ContentType "application/json; charset=utf-8" `
        -Headers $headers `
        -Body $bodyBytes `
        -TimeoutSec 120
}

function Wait-ZipTask {
    param([string]$ZipToken)
    while ($true) {
        $progress = Invoke-RestMethod `
            -Uri "https://cloud.tsinghua.edu.cn/api/v2.1/query-zip-progress/?token=$ZipToken" `
            -TimeoutSec 120

        if ($progress.failed -eq 1) {
            throw "zip task failed: $($progress.failed_reason)"
        }
        if ($progress.total -eq $progress.zipped) {
            return
        }
        Start-Sleep -Seconds 2
    }
}

function Download-Url {
    param(
        [string]$Url,
        [string]$OutputPath
    )

    for ($attempt = 1; $attempt -le 1; $attempt++) {
        & curl.exe `
            -L `
            --ssl-no-revoke `
            --http1.1 `
            --connect-timeout 60 `
            --max-time 900 `
            --speed-limit 1 `
            --speed-time 30 `
            --output $OutputPath `
            $Url

        if ($LASTEXITCODE -eq 0) {
            return
        }
        Write-Log "WARN curl attempt $attempt failed with exit code $LASTEXITCODE"
    }

    throw "curl failed"
}

function Download-One {
    param(
        [object]$Item,
        [int]$Index,
        [int]$Total
    )

    $fileName = [string]$Item.file_name
    $expectedSize = [int64]$Item.size
    $dest = Join-Path $TargetDir $fileName

    if (Test-Path -LiteralPath $dest) {
        $existing = Get-Item -LiteralPath $dest
        if ($existing.Length -eq $expectedSize) {
            Write-Log "SKIP [$Index/$Total] already complete: $fileName"
            return @{
                file_name = $fileName
                expected_size = $expectedSize
                actual_size = $existing.Length
                status = "skipped"
            }
        }
    }

    Write-Log "START [$Index/$Total] $fileName"
    $zipPath = Join-Path $TempDir ("item_{0:000}.zip" -f $Index)
    $extractDir = Join-Path $TempDir ("item_{0:000}" -f $Index)

    for ($fileAttempt = 1; $fileAttempt -le 3; $fileAttempt++) {
        try {
            if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
            if (Test-Path -LiteralPath $extractDir) { Remove-Item -LiteralPath $extractDir -Recurse -Force }

            $task = New-ZipTask -FileName $fileName
            $zipToken = [string]$task.zip_token
            Wait-ZipTask -ZipToken $zipToken
            Start-Sleep -Seconds 3

            $downloadUrl = "https://cloud.tsinghua.edu.cn/seafhttp/zip/$zipToken"
            Download-Url -Url $downloadUrl -OutputPath $zipPath

            Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
            $extracted = Get-ChildItem -LiteralPath $extractDir -Recurse -File | Where-Object { $_.Name -eq $fileName } | Select-Object -First 1
            if (-not $extracted) {
                $extracted = Get-ChildItem -LiteralPath $extractDir -Recurse -File | Sort-Object Length -Descending | Select-Object -First 1
            }
            if (-not $extracted) {
                throw "no extracted file found"
            }

            break
        }
        catch {
            Write-Log "WARN file attempt $fileAttempt failed: $($_.Exception.Message)"
            if ($fileAttempt -eq 3) { throw }
            Start-Sleep -Seconds (8 * $fileAttempt)
        }
    }

    Move-Item -LiteralPath $extracted.FullName -Destination $dest -Force
    $actual = (Get-Item -LiteralPath $dest).Length
    if ($actual -ne $expectedSize) {
        throw "size mismatch for $fileName expected=$expectedSize actual=$actual"
    }

    Remove-Item -LiteralPath $zipPath -Force
    Remove-Item -LiteralPath $extractDir -Recurse -Force
    Write-Log "DONE [$Index/$Total] $fileName"

    return @{
        file_name = $fileName
        expected_size = $expectedSize
        actual_size = $actual
        status = "downloaded"
    }
}

Write-Log "Fetching shared directory list"
$list = Invoke-RestMethod `
    -Uri "https://cloud.tsinghua.edu.cn/api/v2.1/share-links/$Token/dirents/?path=/" `
    -TimeoutSec 120

$items = @($list.dirent_list | Where-Object { -not $_.is_dir })
$total = $items.Count
Write-Log "Found $total files"

$results = @()
for ($i = 0; $i -lt $total; $i++) {
    try {
        $results += Download-One -Item $items[$i] -Index ($i + 1) -Total $total
    }
    catch {
        Write-Log "ERROR [$($i + 1)/$total] $($_.Exception.Message)"
        throw
    }
}

$summary = @{
    token = $Token
    target_dir = [string]$TargetDir
    file_count = $total
    total_bytes = [int64](($items | Measure-Object -Property size -Sum).Sum)
    completed_at = (Get-Date).ToString("s")
    files = $results
}
$summary | ConvertTo-Json -Depth 5 | Set-Content -Path $ManifestPath -Encoding UTF8
Write-Log "ALL_DONE file_count=$total manifest=$ManifestPath"
