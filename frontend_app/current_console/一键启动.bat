@echo off
chcp 65001 >nul 2>&1
title RAG 控制台 - 启动中...

:: ─── 用 app.py 统一启动 (OCR + Web + 自动开浏览器) ───
set "SCRIPT_DIR=%~dp0"
set "APP_PY=%SCRIPT_DIR%app.py"
set "RAG_ROOT=%SCRIPT_DIR%..\.."
set "VENV_PYTHON=%RAG_ROOT%\.venv\Scripts\python.exe"

:: 检查 Python
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" "%APP_PY%"
) else (
    where uv >nul 2>&1
    if %errorlevel%==0 (
        uv run python "%APP_PY%"
    ) else (
        python "%APP_PY%"
    )
)
pause
