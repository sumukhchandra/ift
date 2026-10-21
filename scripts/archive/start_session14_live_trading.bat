@echo off
title AlphaNSE V3 - Session 14 Real Market Trading Engine (Kotak Neo Live)
color 0A

echo ===============================================================================
echo     AlphaNSE V3 -- SESSION 14 REAL MARKET TRADING ENGINE
echo     Broker: Kotak Neo Trade API (Client Code: 116K1)
echo     Mode:   LIVE REAL-MONEY TRADING (Dual-Key Gates Unlocked)
echo ===============================================================================
echo.

cd /d "%~dp0"

set "PY_EXE=python"

echo [*] Starting Session 14 Real Market Trading Daemon...
echo [*] Standby mode will automatically engage until 09:15:00 IST open.
echo.

%PY_EXE% -u scripts\run_session14_kotak_live_trader.py

pause
