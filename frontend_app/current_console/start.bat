@echo off
chcp 65001 >nul 2>&1
title 动力装备知识库控制台 - 本地服务器
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   动力装备知识库控制台 - 本地启动器       ║
echo  ╚══════════════════════════════════════════╝
echo.

cd /d "%~dp0"

:: Try Python first
where python >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo  [✓] 检测到 Python

    :: Start OCR server in background if ocr_server.py exists
    if exist "%~dp0ocr_server.py" (
        echo  [✓] 启动本地 OCR 服务器 (RapidOCR 高精度中文识别)...
        start "OCR Server" /min python "%~dp0ocr_server.py"
        echo  [i] OCR 服务: http://localhost:8765
    ) else (
        echo  [!] 未找到 ocr_server.py，扫描PDF将使用浏览器端OCR (精度较低)
    )

    echo  [✓] 启动本地 Web 服务器...
    echo  [i] 服务地址: http://localhost:8080
    echo  [i] 按 Ctrl+C 停止服务器
    echo.
    start "" "http://localhost:8080"
    python -m http.server 8080
    goto :end
)

:: Try Python3
where python3 >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo  [✓] 检测到 Python3

    if exist "%~dp0ocr_server.py" (
        echo  [✓] 启动本地 OCR 服务器 (RapidOCR 高精度中文识别)...
        start "OCR Server" /min python3 "%~dp0ocr_server.py"
        echo  [i] OCR 服务: http://localhost:8765
    )

    echo  [✓] 启动本地 Web 服务器...
    echo  [i] 服务地址: http://localhost:8080
    echo  [i] 按 Ctrl+C 停止服务器
    echo.
    start "" "http://localhost:8080"
    python3 -m http.server 8080
    goto :end
)

:: Fallback: use PowerShell to create a simple HTTP server
echo  [!] 未检测到 Python，使用 PowerShell 启动本地服务器...
echo  [!] 无法启动 OCR 服务器，扫描PDF将使用浏览器端OCR
echo  [i] 服务地址: http://localhost:8080
echo  [i] 关闭此窗口停止服务器
echo.
start "" "http://localhost:8080"
powershell -ExecutionPolicy Bypass -Command "& { $listener = New-Object System.Net.HttpListener; $listener.Prefixes.Add('http://localhost:8080/'); $listener.Start(); Write-Host '  服务器已启动: http://localhost:8080'; while ($listener.IsListening) { $ctx = $listener.GetContext(); $path = $ctx.Request.Url.LocalPath; if ($path -eq '/') { $path = '/index.html' }; $file = Join-Path '%~dp0' ($path -replace '/','\\'); if (Test-Path $file -PathType Leaf) { $bytes = [IO.File]::ReadAllBytes($file); $ext = [IO.Path]::GetExtension($file).ToLower(); $mime = @{'.html'='text/html;charset=utf-8';'.js'='application/javascript';'.css'='text/css';'.json'='application/json';'.wasm'='application/wasm';'.png'='image/png';'.svg'='image/svg+xml';'.webp'='image/webp'}; $ctx.Response.ContentType = if ($mime[$ext]) {$mime[$ext]} else {'application/octet-stream'}; $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length) } else { $ctx.Response.StatusCode = 404; $msg = [Text.Encoding]::UTF8.GetBytes('Not Found'); $ctx.Response.OutputStream.Write($msg, 0, $msg.Length) }; $ctx.Response.Close() } }"

:end
pause
