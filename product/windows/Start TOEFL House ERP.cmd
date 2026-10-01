@echo off
rem Daily launcher: double-click. Starts the app and opens it in your browser.
cd /d "%~dp0.."
title Starting TOEFL House ERP
docker info >nul 2>nul
if errorlevel 1 (
  echo  Starting Docker Desktop - this can take a minute...
  start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  :waitdaemon
  timeout /t 5 /nobreak >nul
  docker info >nul 2>nul && goto :up
  goto :waitdaemon
)
:up
docker compose up -d
if errorlevel 1 (
  echo.
  echo  Could not start. Please double-click "Repair TOEFL House ERP.cmd".
  pause
  exit /b 1
)
echo  Waiting until TOEFL House ERP answers...
:waitready
timeout /t 8 /nobreak >nul
curl --fail --silent http://127.0.0.1:8000/ >nul 2>nul && goto :ready
goto :waitready
:ready
start "" "http://127.0.0.1:8000/"
echo  TOEFL House ERP is open in your browser. You may close this window.
timeout /t 6 >nul
exit /b 0
