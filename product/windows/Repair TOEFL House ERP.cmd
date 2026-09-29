@echo off
rem Safe recovery: restarts services and reruns migrations (never deletes data).
cd /d "%~dp0.."
title Repairing TOEFL House ERP
docker info >nul 2>nul
if errorlevel 1 (
  echo  Docker Desktop is not running. Please start it, wait a minute, then run this again.
  pause
  exit /b 1
)
docker compose down
docker compose up -d db redis-queue redis-cache
timeout /t 10 /nobreak >nul
docker compose up -d
if errorlevel 1 goto :failed
echo  Waiting until TOEFL House ERP answers after repair...
:waitready
timeout /t 10 /nobreak >nul
curl --silent http://127.0.0.1:8000/ >nul 2>nul && goto :ready
echo  Still preparing...
goto :waitready
:ready
echo  Repair complete. Starting TOEFL House ERP in your browser...
start "" "http://127.0.0.1:8000/"
pause
exit /b 0
:failed
echo  Automatic repair could not finish. Contact TOEFL House support with the
echo  contents of the data\logs folder.
pause
exit /b 1
