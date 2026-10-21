@echo off
title AlphaNSE 1-Minute Compounding Trader
echo ===============================================================================
echo        AlphaNSE 1-Minute Stock Prediction & Compounding Trading Desk
echo ===============================================================================
echo.

cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting FastAPI Server & WebSocket Hub on http://localhost:8000 ...
echo Next NSE Market Session: Tomorrow at 09:15 AM IST
echo.
%PYTHON_EXE% -m uvicorn QA.server.api:app --host 0.0.0.0 --port 8000
pause

