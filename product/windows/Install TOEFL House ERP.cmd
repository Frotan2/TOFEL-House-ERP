@echo off
setlocal enableextensions
rem ============================================================
rem  TOEFL House ERP - one-time installer (double-click; no typing)
rem  Requires: Docker Desktop for Windows (free, installs with WSL2).
rem  What it does, automatically:
rem    1. Verifies Docker Desktop is installed and running
rem    2. Generates a private database password (stored locally only)
rem    3. Builds the application image from the pinned, reviewed sources
rem    4. Starts the app, database, background worker and scheduler
rem    5. Opens TOEFL House ERP in your browser when it is ready
rem  First build needs ~20-60 minutes depending on your connection.
rem ============================================================
title Installing TOEFL House ERP
cd /d "%~dp0.."

where docker >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Docker Desktop is not installed yet.
  echo  1. Install it from https://www.docker.com/products/docker-desktop/
  echo  2. Restart your PC when it asks.
  echo  3. Double-click this file again.
  start "" "https://www.docker.com/products/docker-desktop/"
  goto :pause
)

docker info >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Docker Desktop is installed but not running.
  echo  Starting it now - this can take a minute...
  start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  :waitdaemon
  timeout /t 5 /nobreak >nul
  docker info >nul 2>nul && goto :daemonok
  echo  Waiting for Docker Desktop to finish starting...
  goto :waitdaemon
  :daemonok
)

if not exist data\secrets mkdir data\secrets
rem  Note: do not wrap the FOR /F line below in a parenthesized IF block.
rem  cmd's block parser folds the ')' inside PowerShell's ToString('N') into
rem  the FOR IN (...) clause and aborts with ") was unexpected at this time."
if exist data\secrets\db.env goto :secretok
echo  Generating a private database password for this computer...
for /f "usebackq delims=" %%G in (`powershell -NoProfile -Command "[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')"`) do set "DBPW=%%G"
>data\secrets\db.env echo MARIADB_ROOT_PASSWORD=%DBPW%
:secretok
attrib +h data\secrets >nul 2>nul

echo.
echo  Building TOEFL House ERP for the first time. Please keep this window open.
docker compose build
if errorlevel 1 goto :failed

docker compose up -d
if errorlevel 1 goto :failed

echo.
echo  First launch is finishing inside the app (site setup + data install).
echo  You can watch progress in Docker Desktop, or simply wait for the browser.
:waitready
timeout /t 10 /nobreak >nul
curl --silent http://127.0.0.1:8000/api/method/frappe.auth.get_logged_user >nul 2>nul && goto :ready
echo  Still preparing... (site setup can take 15-40 minutes on first run)
goto :waitready
:ready

if exist data\sites\toeflhouse.localhost\private\first-run-credentials.txt (
  echo.
  echo  --------------------------------------------------------------
  echo  Your Administrator login is below. Write it down and keep it private.
  echo  --------------------------------------------------------------
  type data\sites\toeflhouse.localhost\private\first-run-credentials.txt
  echo  --------------------------------------------------------------
)

start "" "http://127.0.0.1:8000/"
echo.
echo  Install finished. From now on use the "Start TOEFL House ERP" shortcut.
pause
exit /b 0

:failed
echo.
echo  ------------------------------------------------------------------
echo  Something went wrong. Double-click "Repair TOEFL House ERP.cmd";
echo  it restarts the system and reruns migrations safely.
echo  ------------------------------------------------------------------
:pause
pause
exit /b 1
