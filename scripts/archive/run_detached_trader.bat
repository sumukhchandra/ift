@echo off
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
"C:\Users\sumuk\AppData\Local\Programs\Python\Python312\python.exe" -u scripts\run_session14_kotak_live_trader.py > logs\session14_live_trading.log 2>&1
