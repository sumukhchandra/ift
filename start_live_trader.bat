@echo off
title AlphaNSE V3 - Real Market Live Trading Engine (Kotak Neo Live)
color 0A

echo ===============================================================================
echo     AlphaNSE V3 -- PRODUCTION REAL MARKET LIVE TRADING ENGINE
echo     Broker: Kotak Neo Trade API (Client Code: 116K1)
echo     Mode:   LIVE REAL-MONEY TRADING (Dual-Key Gates Unlocked)
echo ===============================================================================
echo.

cd /d "%~dp0"

set "PY_EXE=python"

echo [*] Starting Production Real Trading Engine...
echo [*] Standby mode will automatically engage until 09:15:00 IST opening bell.
echo.

%PY_EXE% -u run_live_trader.py

pause
