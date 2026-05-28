@echo off
chcp 65001 >nul 2>&1

cd /d "%~dp0"

set "VENV_PYTHON=%~dp0..\..\\.venv\Scripts\python.exe"

if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" "%~dp0app.py"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        python "%~dp0app.py"
    ) else (
        echo [ERROR] Python not found
        echo Please install Python or create .venv
    )
)
pause
