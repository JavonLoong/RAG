@echo off
chcp 65001 >nul 2>&1
title 动力装备知识库 RAG 控制台
setlocal

set "APP_DIR=%~dp0"
set "PYTHONPATH=%APP_DIR%chroma_rag_poc\src"
set "PYTHON_EXE="

echo.
echo ============================================================
echo   动力装备知识库 RAG 控制台
echo   正在检查 Python 环境...
echo ============================================================
echo.

if exist "C:\Users\15410\AppData\Local\Programs\Python\Python311\python.exe" (
    set "PYTHON_EXE=C:\Users\15410\AppData\Local\Programs\Python\Python311\python.exe"
    goto :found
)

where python >nul 2>&1
if %errorlevel%==0 (
    python -c "import fastapi" >nul 2>&1
    if %errorlevel%==0 (
        set "PYTHON_EXE=python"
        goto :found
    )
)

if exist "%APP_DIR%..\..\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%APP_DIR%..\..\.venv\Scripts\python.exe"
    goto :found
)

echo [ERROR] 没有找到可用的 Python 运行环境。
echo 请先安装依赖: pip install fastapi uvicorn chromadb sentence-transformers
pause
exit /b 1

:found
echo [OK] Python: %PYTHON_EXE%
echo [OK] App dir: %APP_DIR%
echo [OK] Frontend: http://localhost:8000
echo [OK] Docs: http://localhost:8000/docs
echo.

timeout /t 2 /nobreak >nul
start "" "http://localhost:8000"

"%PYTHON_EXE%" "%APP_DIR%server.py"
pause
