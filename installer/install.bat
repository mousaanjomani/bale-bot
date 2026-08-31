@echo off
title Bale Bot Installer
rem =====================================================================
rem  Bale Bot - one-click installer for the customer server.
rem  Double-click this file; it elevates itself, downloads the latest
rem  installer from GitHub and runs it.
rem =====================================================================

rem ---- relaunch as Administrator if needed ----
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo === Bale Bot Installer ===
echo Downloading the installer from GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-RestMethod 'https://raw.githubusercontent.com/mousaanjomani/bale-bot/main/installer/install.ps1' -OutFile ($env:TEMP + '\balebot-install.ps1')"
if %errorlevel% neq 0 (
    echo.
    echo Download failed. Please check the internet connection and try again.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\balebot-install.ps1"
if %errorlevel% neq 0 (
    echo.
    echo Installation did not finish successfully.
    pause
    exit /b 1
)

rem ---- open the dashboard in the browser (Chrome, or default browser) ----
echo Opening the dashboard...
timeout /t 3 /nobreak >nul
start chrome http://localhost:8585 2>nul || start "" http://localhost:8585
echo.
pause
