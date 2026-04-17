@echo off
chcp 65001 >nul 2>&1
title 动力装备知识库 RAG v2.0

echo.
echo ══════════════════════════════════════════════════
echo   动力装备知识库 RAG Pipeline v2.0
echo   正在启动服务器...
echo ══════════════════════════════════════════════════
echo.

:: 设置路径
set "PROJECT_DIR=%~dp0"
set "PYTHONPATH=%PROJECT_DIR%chroma_rag_poc\src"

:: 查找可用的 Python（优先全局 Python3.11，因为依赖装在那里）
set "PYTHON="

:: 方法1: 全局 Python 3.11
if exist "C:\Users\15410\AppData\Local\Programs\Python\Python311\python.exe" (
    set "PYTHON=C:\Users\15410\AppData\Local\Programs\Python\Python311\python.exe"
    goto :found
)

:: 方法2: PATH 中的 python
where python >nul 2>&1
if %errorlevel%==0 (
    :: 检查这个 python 有没有 fastapi
    python -c "import fastapi" >nul 2>&1
    if %errorlevel%==0 (
        set "PYTHON=python"
        goto :found
    )
)

:: 方法3: 项目 venv
if exist "%PROJECT_DIR%..\..\..\.venv\Scripts\python.exe" (
    set "PYTHON=%PROJECT_DIR%..\..\..\.venv\Scripts\python.exe"
    goto :found
)

echo [错误] 未找到带有 fastapi 的 Python
echo 请运行: pip install fastapi uvicorn chromadb sentence-transformers
pause
exit /b 1

:found
echo [OK] Python: %PYTHON%
echo [OK] 项目:  %PROJECT_DIR%
echo.

:: 先打开浏览器
timeout /t 2 /nobreak >nul
start "" "http://localhost:8000"

echo ══════════════════════════════════════════════════
echo   浏览器地址: http://localhost:8000
echo   按 Ctrl+C 或关闭此窗口停止服务器
echo ══════════════════════════════════════════════════
echo.

:: 启动服务器
"%PYTHON%" "%PROJECT_DIR%app_server.py"

pause
