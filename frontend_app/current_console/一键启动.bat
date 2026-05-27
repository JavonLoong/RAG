@echo off
chcp 65001 >nul 2>&1
title RAG 知识库控制台 - 一键启动

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║    RAG 知识库控制台 - 一键启动               ║
echo  ║    OCR Server v4 + 前端界面                  ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: ─── 路径配置 ───
set "RAG_ROOT=%~dp0..\.."
set "FRONTEND=%~dp0index.html"
set "OCR_SERVER=%~dp0ocr_server.py"
set "VENV_PYTHON=%RAG_ROOT%\.venv\Scripts\python.exe"
set "UV_EXE=uv"

:: ─── 检查 Python 环境 ───
echo [1/4] 检查 Python 环境...
if exist "%VENV_PYTHON%" (
    set "PYTHON=%VENV_PYTHON%"
    echo       √ 使用 venv: %VENV_PYTHON%
) else (
    :: 尝试 uv run
    where uv >nul 2>&1
    if %errorlevel%==0 (
        set "PYTHON=uv run python"
        echo       √ 使用 uv run python
    ) else (
        where python >nul 2>&1
        if %errorlevel%==0 (
            set "PYTHON=python"
            echo       √ 使用系统 python
        ) else (
            echo       × 未找到 Python！请安装 Python 3.10+
            pause
            exit /b 1
        )
    )
)

:: ─── 检查 OCR 服务器是否已运行 ───
echo [2/4] 检查 OCR 服务器状态...
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8765/health 2>nul | findstr "200" >nul 2>&1
if %errorlevel%==0 (
    echo       √ OCR 服务器已在运行中
    goto :open_browser
)

:: ─── 启动 OCR 服务器 ───
echo [3/4] 启动 OCR 服务器...
echo       引擎: RapidOCR + Tesseract
echo       端口: http://127.0.0.1:8765

:: 用 start /min 在后台窗口运行服务器
start "OCR-Server" /min cmd /c "cd /d "%RAG_ROOT%" && %PYTHON% "%OCR_SERVER%" 2>&1"

:: 等待服务器就绪 (最多 30 秒)
echo       等待服务器就绪...
set /a attempts=0
:wait_loop
timeout /t 1 /nobreak >nul
set /a attempts+=1
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8765/health 2>nul | findstr "200" >nul 2>&1
if %errorlevel%==0 (
    echo       √ OCR 服务器已就绪 ^(%attempts% 秒^)
    goto :open_browser
)
if %attempts% lss 30 goto :wait_loop
echo       ! 服务器启动超时，继续打开网页...

:open_browser
:: ─── 打开前端界面 ───
echo [4/4] 打开前端界面...
if exist "%FRONTEND%" (
    start "" "%FRONTEND%"
    echo       √ 已打开: index.html
) else (
    echo       × 未找到 index.html: %FRONTEND%
)

echo.
echo  ════════════════════════════════════════════════
echo   √ 全部就绪！
echo   - OCR 服务器: http://127.0.0.1:8765
echo   - 关闭此窗口不影响 OCR 服务器运行
echo   - 要停止 OCR 服务器，关闭标题为 "OCR-Server" 的窗口
echo  ════════════════════════════════════════════════
echo.
echo  按任意键退出此启动器窗口...
pause >nul
