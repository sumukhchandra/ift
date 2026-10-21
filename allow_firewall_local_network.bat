@echo off
title Allow Port 8000 in Windows Firewall for Local Network Access
:: Auto-elevate to Administrator
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo [INFO] Requesting Administrator Permission to allow Local Network access...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    set params = %*:"=""
    echo UAC.ShellExecute "cmd.exe", "/c ""%~s0"" %params%", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    del "%temp%\getadmin.vbs"
    exit /B

:gotAdmin
    pushd "%CD%"
    CD /D "%~dp0"

echo ===============================================================================
echo       Opening Port 8000 in Windows Defender Firewall for Local Network
echo ===============================================================================
echo.
netsh advfirewall firewall delete rule name="AlphaNSE Port 8000" >nul 2>&1
netsh advfirewall firewall add rule name="AlphaNSE Port 8000" dir=in action=allow protocol=TCP localport=8000 profile=any
netsh advfirewall firewall delete rule name="AlphaNSE Port 8501" >nul 2>&1
netsh advfirewall firewall add rule name="AlphaNSE Port 8501" dir=in action=allow protocol=TCP localport=8501 profile=any
echo.
echo [SUCCESS] Windows Firewall rules added for ports 8000 and 8501!
echo.
echo Your Local Network (Wi-Fi) IP Address is:
for /f "tokens=4" %%a in ('route print ^| findstr 0.0.0.0 ^| findstr /v "Default"') do (
    set LOCAL_IP=%%a
)
echo    %LOCAL_IP%
echo.
echo Open these links on your phone, tablet, or laptop connected to the same Wi-Fi:
echo.
echo    Mobile Live App:      http://%LOCAL_IP%:8000/app
echo    Mobile Website:       http://%LOCAL_IP%:8000/
echo    AI Lab & Simulation:  http://%LOCAL_IP%:8000/lab
echo    Streamlit Analytics:  http://%LOCAL_IP%:8501/
echo.
echo ===============================================================================
echo.
pause
