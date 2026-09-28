@echo off
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows_exe.ps1" %*
exit /b %ERRORLEVEL%
