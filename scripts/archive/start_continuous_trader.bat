@echo off
title AlphaNSE 24/7 Continuous Trading Desk & Supervisor
echo ===============================================================================
echo          AlphaNSE 24/7 Continuous Automated Compounding Trading Desk
echo ===============================================================================
echo.
echo Launching Continuous Supervisor with Auto-Crash Recovery & Watchdog...
echo Server & Dashboard will be live on: http://localhost:8000
echo.

cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

:loop
%PYTHON_EXE% QA\monitoring\continuous_supervisor.py
echo.
echo [WARNING] Supervisor exited at %TIME%. Restarting in 5 seconds...
timeout /t 5 /nobreak >nul
goto loop
