param(
    [string]$DistDir = (Join-Path $PSScriptRoot "dist\PowerRAG"),
    [string]$OutZip = (Join-Path $PSScriptRoot "dist\PowerRAG-customer-windows.zip")
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path (Join-Path $DistDir "PowerRAG.exe"))) {
    Write-Host "还没有 onedir 产物。请先运行 desktop_launcher/build_windows_exe.ps1"
    exit 1
}

New-Item -ItemType Directory -Force -Path (Split-Path $OutZip) | Out-Null
if (Test-Path $OutZip) { Remove-Item $OutZip -Force }
Compress-Archive -Path (Join-Path $DistDir "*") -DestinationPath $OutZip -CompressionLevel Optimal
Write-Host "已打包: $OutZip"
Write-Host "交给客户时请解压整个文件夹，不要只发 PowerRAG.exe"
