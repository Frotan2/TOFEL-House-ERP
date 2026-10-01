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
curl --fail --silent http://127.0.0.1:8000/ >nul 2>nul && goto :ready
echo  Still preparing...
goto :waitready
:ready
echo  Repair complete. Starting TOEFL House ERP in your browser...
start "" "http://127.0.0.1:8000/"
pause
exit /b 0
:failed
echo.
echo  Automatic repair could not finish. Current service state:
echo.
docker compose ps
echo.
echo  Last lines of the application log:
docker compose logs --tail 5 web 2>&1
echo.
echo  What the state above usually means:
echo    no rows, or rows "not running"     the ERP services are not up.
echo    db "unhealthy" or "restarting"      the database is not ready yet.
echo    web "Restarting" or exiting          the app stops right after starting.
echo.
echo  Try this Repair script once more. If it repeats, contact TOEFL House
echo  support with a photo of this window plus the contents of the data\logs folder.
pause
exit /b 1
