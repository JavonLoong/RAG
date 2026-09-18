param(
    [string]$EnvId = "env_e_6a1f8edee64883338c051cd20bd6e889",
    [string]$InstallationId = "3ff00c9d-e1f5-4a0c-bc5b-9ea960430928",
    [string]$HostNamePattern = "",
    [string]$NewName = "",
    [int]$OfflineWaitSeconds = 300,
    [int]$NewEnvironmentWaitSeconds = 180,
    [switch]$KillCodex
)

$ErrorActionPreference = "Stop"

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

$CodexHome = Join-Path $env:USERPROFILE ".codex"
$AuthPath = Join-Path $CodexHome "auth.json"
$StatePath = Join-Path $CodexHome "state_5.sqlite"
$GlobalStatePath = Join-Path $CodexHome ".codex-global-state.json"
$ApiBase = "https://chatgpt.com/backend-api"
$DefaultHostName = -join ([char[]](0x9F99, 0x54E5, 0x5B9D, 0x672C))

if ([string]::IsNullOrWhiteSpace($HostNamePattern)) {
    $HostNamePattern = $DefaultHostName
}

if ([string]::IsNullOrWhiteSpace($NewName)) {
    $NewName = $DefaultHostName
}

function Get-RemoteControlHeaders {
    if (!(Test-Path -LiteralPath $AuthPath)) {
        throw "Missing auth file: $AuthPath"
    }

    $auth = Get-Content -LiteralPath $AuthPath -Raw | ConvertFrom-Json
    $token = $auth.tokens.access_token
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "Missing ChatGPT access token in $AuthPath"
    }

    $headers = @{
        Authorization = "Bearer $token"
        originator = "Codex Desktop"
        "User-Agent" = "Codex Desktop/26.601.2237.0 (Windows NT 10.0; x64)"
    }

    try {
        $payloadPart = $token.Split(".")[1].Replace("-", "+").Replace("_", "/")
        while (($payloadPart.Length % 4) -ne 0) {
            $payloadPart += "="
        }
        $payloadJson = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payloadPart))
        $payload = $payloadJson | ConvertFrom-Json
        $accountId = $payload.'https://api.openai.com/auth'.chatgpt_account_id
        if (![string]::IsNullOrWhiteSpace($accountId)) {
            $headers["ChatGPT-Account-Id"] = $accountId
        }
    } catch {
        Write-Host "Could not decode account id from token; continuing without ChatGPT-Account-Id."
    }

    return $headers
}

function Invoke-RemoteControlApi {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null,
        [switch]$AllowFailure
    )

    $headers = Get-RemoteControlHeaders
    $uri = "$ApiBase$Path"
    $params = @{
        Uri = $uri
        Method = $Method
        Headers = $headers
        UseBasicParsing = $true
    }

    if ($null -ne $Body) {
        $json = $Body | ConvertTo-Json -Compress -Depth 20
        $params["ContentType"] = "application/json; charset=utf-8"
        $params["Body"] = [System.Text.Encoding]::UTF8.GetBytes($json)
    }

    try {
        $response = Invoke-WebRequest @params
        if ([string]::IsNullOrWhiteSpace($response.Content)) {
            return $null
        }
        return $response.Content | ConvertFrom-Json
    } catch {
        if ($AllowFailure) {
            return $_
        }
        throw
    }
}

function Get-RemoteEnvironment {
    return Get-RemoteEnvironments | Where-Object {
        Test-IsTargetEnvironment $_
    } | Select-Object -First 1
}

function Get-RemoteEnvironments {
    $result = Invoke-RemoteControlApi -Method "GET" -Path "/codex/remote/control/environments?limit=100"
    return @($result.items)
}

function Test-IsTargetEnvironment {
    param([object]$Environment)

    if ($null -eq $Environment) {
        return $false
    }

    if ($Environment.env_id -eq $EnvId -or $Environment.installation_id -eq $InstallationId) {
        return $true
    }

    foreach ($field in @("name", "display_name", "host_name")) {
        $value = $Environment.$field
        if (![string]::IsNullOrWhiteSpace($value) -and $value -like "*$HostNamePattern*") {
            return $true
        }
    }

    return $false
}

function Stop-CodexProcesses {
    $processes = Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -ieq "Codex.exe" -and $_.CommandLine -like "*OpenAI.Codex*") -or
        ($_.Name -ieq "codex.exe" -and $_.CommandLine -like "*OpenAI.Codex*app*resources*codex.exe*app-server*")
    }

    if (!$processes) {
        return
    }

    Write-Host "Stopping Codex Desktop processes..."
    foreach ($p in ($processes | Sort-Object ProcessId -Descending)) {
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            Write-Host "Stopped PID $($p.ProcessId)"
        } catch {
            Write-Host "Could not stop PID $($p.ProcessId): $($_.Exception.Message)"
        }
    }
}

function Remove-LocalEnrollmentState {
    if (Test-Path -LiteralPath $StatePath) {
        $backup = "$StatePath.remote-reset-$(Get-Date -Format 'yyyyMMdd-HHmmss').bak"
        Copy-Item -LiteralPath $StatePath -Destination $backup -Force
        Write-Host "Backed up SQLite state to $backup"

        $env:CODEX_RESET_STATE_PATH = $StatePath
        $env:CODEX_RESET_ENV_ID = $EnvId
        $py = @'
import os
import sqlite3

path = os.environ["CODEX_RESET_STATE_PATH"]

con = sqlite3.connect(path)
try:
    cur = con.execute("delete from remote_control_enrollments")
    con.commit()
    print(f"Removed {cur.rowcount} remote_control_enrollments rows")
finally:
    con.close()
'@
        $py | python -
    }

    if (Test-Path -LiteralPath $GlobalStatePath) {
        $backup = "$GlobalStatePath.remote-reset-$(Get-Date -Format 'yyyyMMdd-HHmmss').bak"
        Copy-Item -LiteralPath $GlobalStatePath -Destination $backup -Force
        Write-Host "Backed up global state to $backup"

        $env:CODEX_RESET_GLOBAL_STATE_PATH = $GlobalStatePath
        $py = @'
import json
import os
from pathlib import Path

path = Path(os.environ["CODEX_RESET_GLOBAL_STATE_PATH"])
data = json.loads(path.read_text(encoding="utf-8-sig"))
keys = [
    "codex-mobile-has-connected-device",
    "electron-remote-control-client-enrollments",
    "electron-local-remote-control-environment-id",
    "electron-local-remote-control-installation-id",
]
removed = []
for key in keys:
    if key in data:
        removed.append(key)
        del data[key]
path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("Cleared global state keys: " + ", ".join(removed))
'@
        $py | python -
        Write-Host "Cleared local remote-control environment/install ids from global state."
    }
}

if ($KillCodex) {
    Stop-CodexProcesses
    Start-Sleep -Seconds 5
} else {
    $running = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -ieq "Codex.exe" -and $_.CommandLine -like "*OpenAI.Codex*"
    }
    if ($running) {
        Write-Host "Codex Desktop is still running. Close it completely, or rerun with -KillCodex."
        exit 2
    }
}

Write-Host "Waiting for target remote environments to become offline..."
$targetEnvironments = @()
$offlineAttempts = [Math]::Max(1, [Math]::Ceiling($OfflineWaitSeconds / 5))
for ($i = 0; $i -lt $offlineAttempts; $i++) {
    $targetEnvironments = @(Get-RemoteEnvironments | Where-Object { Test-IsTargetEnvironment $_ })
    if ($targetEnvironments.Count -eq 0) {
        Write-Host "Target remote environments are already absent from the cloud list."
        break
    }

    $summary = $targetEnvironments | ForEach-Object {
        "{0} online={1} last_seen_at={2}" -f $_.env_id, $_.online, $_.last_seen_at
    }
    Write-Host ("Attempt {0}/{1}: {2}" -f ($i + 1), $offlineAttempts, ($summary -join "; "))
    if (@($targetEnvironments | Where-Object { $_.online -eq $true }).Count -eq 0) {
        break
    }

    Start-Sleep -Seconds 5
}

$stillOnline = @($targetEnvironments | Where-Object { $_.online -eq $true })
if ($stillOnline.Count -gt 0) {
    throw "Timed out waiting for target remote environments to go offline. Make sure Codex Desktop is fully closed and try again."
}

foreach ($target in $targetEnvironments) {
    Write-Host "Deleting offline remote environment $($target.env_id)..."
    $deleteResult = Invoke-RemoteControlApi -Method "DELETE" -Path "/codex/remote/control/environments/$([uri]::EscapeDataString($target.env_id))" -AllowFailure
    if ($deleteResult -is [System.Management.Automation.ErrorRecord]) {
        throw "Delete failed: $($deleteResult.Exception.Message)"
    }
    Write-Host "Deleted remote environment $($target.env_id)."
}

Remove-LocalEnrollmentState

Write-Host "Opening Codex connection settings..."
Start-Process "codex://settings/connections"

Write-Host "Waiting for a newly created remote environment..."
$newAttempts = [Math]::Max(1, [Math]::Ceiling($NewEnvironmentWaitSeconds / 5))
$newEnvironment = $null
for ($i = 0; $i -lt $newAttempts; $i++) {
    Start-Sleep -Seconds 5
    $currentTargets = @(Get-RemoteEnvironments | Where-Object {
        $_.client_type -eq "CODEX_DESKTOP_APP" -and
        ($_.installation_id -eq $InstallationId -or $_.host_name -like "*$HostNamePattern*") -and
        ($_.env_id -ne $EnvId)
    })
    $newEnvironment = $currentTargets | Sort-Object last_seen_at -Descending | Select-Object -First 1
    if ($null -ne $newEnvironment) {
        break
    }
    Write-Host ("New environment wait {0}/{1}..." -f ($i + 1), $newAttempts)
}

if ($null -ne $newEnvironment) {
    Write-Host "Renaming new remote environment $($newEnvironment.env_id) to $NewName..."
    $renameResult = Invoke-RemoteControlApi `
        -Method "PATCH" `
        -Path "/codex/remote/control/environments/$([uri]::EscapeDataString($newEnvironment.env_id))" `
        -Body @{ name = $NewName } `
        -AllowFailure
    if ($renameResult -is [System.Management.Automation.ErrorRecord]) {
        Write-Host "Rename failed: $($renameResult.Exception.Message)"
    } else {
        Write-Host "Renamed new environment."
    }
} else {
    Write-Host "No new environment appeared yet. Finish QR binding in Codex Desktop, then run the script again without -KillCodex only if the phone still shows stale state."
}

Write-Host "Done. Re-scan the QR code and select the new $NewName device on the phone."
