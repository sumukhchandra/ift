@echo off
title AlphaNSE 1-Minute Compounding Trader
echo ===============================================================================
echo        AlphaNSE 1-Minute Stock Prediction & Compounding Trading Desk
echo ===============================================================================
echo.
echo Starting FastAPI Server & WebSocket Hub on http://localhost:8000 ...
echo Next NSE Market Session: Tomorrow (Tuesday) at 09:15 AM IST
echo.
python -m uvicorn QA.server.api:app --host 0.0.0.0 --port 8000
pause
