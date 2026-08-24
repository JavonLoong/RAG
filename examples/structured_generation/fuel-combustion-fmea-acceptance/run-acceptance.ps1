[CmdletBinding()]
param(
    [string]$OutputDirectory = "",
    [string]$RegistryDirectory = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
    [Console]::Error.WriteLine(
        "DEEPSEEK_API_KEY is required. Set it in the current process before running live acceptance."
    )
    exit 3
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..\.."))
$pythonPath = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$templateSkill = Join-Path $repositoryRoot "scripts\output_template_skill.py"
$generationSkill = Join-Path $repositoryRoot "scripts\structured_generation_skill.py"
$acceptanceRunner = Join-Path $repositoryRoot "scripts\run_structured_generation_acceptance.py"
$verifier = Join-Path $repositoryRoot "scripts\verify_structured_generation_acceptance.py"
$templateSource = Join-Path $repositoryRoot "templates\examples\fuel-combustion-fmea-full.yaml"
$profile = Join-Path $repositoryRoot "templates\fmea_profiles\fuel-combustion-fmea-full.json"
$pack = Join-Path $PSScriptRoot "evidence-pack.json"
$analysis = Join-Path $PSScriptRoot "analysis.json"
$request = Join-Path $PSScriptRoot "request.json"

$requiredFiles = @(
    $pythonPath,
    $templateSkill,
    $generationSkill,
    $acceptanceRunner,
    $verifier,
    $templateSource,
    $profile,
    $pack,
    $analysis,
    $request
)
foreach ($requiredFile in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        [Console]::Error.WriteLine(
            "Acceptance prerequisite is missing. Restore the repository files and virtual environment."
        )
        exit 3
    }
}

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDirectory = Join-Path $repositoryRoot ".local\structured-generation-acceptance\$timestamp"
}
if ([string]::IsNullOrWhiteSpace($RegistryDirectory)) {
    $RegistryDirectory = Join-Path $repositoryRoot ".local\template-registry"
}

$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
$RegistryDirectory = [System.IO.Path]::GetFullPath($RegistryDirectory)
[System.IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
[System.IO.Directory]::CreateDirectory($RegistryDirectory) | Out-Null
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = $utf8WithoutBom
[Console]::OutputEncoding = $utf8WithoutBom
$env:PYTHONUTF8 = "1"

function Invoke-CapturedPython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [string]$Destination = "",
        [Parameter(Mandatory = $true)]
        [int[]]$AllowedExitCodes,
        [Parameter(Mandatory = $true)]
        [string]$StepName
    )

    $lines = & $script:pythonPath @Arguments 2>$null
    $commandExitCode = $LASTEXITCODE
    $capturedText = [string]::Join([Environment]::NewLine, [string[]]$lines)
    if (-not [string]::IsNullOrWhiteSpace($Destination)) {
        [System.IO.File]::WriteAllText(
            $Destination,
            $capturedText + [Environment]::NewLine,
            $script:utf8WithoutBom
        )
    }
    if ($AllowedExitCodes -notcontains $commandExitCode) {
        if (-not [string]::IsNullOrWhiteSpace($capturedText)) {
            Write-Output $capturedText
        }
        [Console]::Error.WriteLine("$StepName failed with exit code $commandExitCode.")
        exit $commandExitCode
    }
    return $capturedText
}

$null = Invoke-CapturedPython `
    -Arguments @(
        $templateSkill,
        "register",
        $templateSource,
        "--registry",
        $RegistryDirectory
    ) `
    -Destination (Join-Path $OutputDirectory "template-register.json") `
    -AllowedExitCodes @(0) `
    -StepName "Template registration"

$null = Invoke-CapturedPython `
    -Arguments @($generationSkill, "smoke") `
    -Destination (Join-Path $OutputDirectory "smoke.json") `
    -AllowedExitCodes @(0) `
    -StepName "DeepSeek smoke"

$verificationText = Invoke-CapturedPython `
    -Arguments @(
        $acceptanceRunner,
        "--registry",
        $RegistryDirectory,
        "--output-directory",
        $OutputDirectory,
        "--pack",
        $pack,
        "--analysis",
        $analysis,
        "--request",
        $request
    ) `
    -AllowedExitCodes @(0) `
    -StepName "FMEA generation and offline acceptance verification"

Write-Output $verificationText
exit 0
