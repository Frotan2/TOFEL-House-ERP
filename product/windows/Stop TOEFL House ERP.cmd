@echo off
rem Stops all TOEFL House ERP services. Your data stays safe on this PC.
cd /d "%~dp0.."
title Stopping TOEFL House ERP
docker compose down
if errorlevel 1 (
  echo  Could not stop cleanly. If the problem repeats, use the Repair script.
  pause
  exit /b 1
)
echo  TOEFL House ERP has stopped. You may close this window.
timeout /t 5 >nul
exit /b 0
