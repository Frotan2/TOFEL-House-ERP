@echo off
rem Safe recovery: restarts services and reruns migrations (never deletes data).
rem Style rule (proven on real Windows runs, 2026-09-30): fully linear flow -
rem single-line IF ... GOTO with dedicated labels, no multi-line
rem parenthesized blocks and no FOR commands, so the script parses
rem identically with LF or CRLF line endings regardless of how this folder
rem was delivered (Git checkout or GitHub ZIP).
cd /d "%~dp0.."
title Repairing TOEFL House ERP
docker info >nul 2>nul
if errorlevel 1 goto :daemondown
:daemondown
echo  Docker Desktop is not running. Please start it, wait a minute, then run this again.
pause
exit /b 1
if not exist data\secrets\db.env goto :nosecret
docker compose down
docker compose up -d db redis-queue redis-cache
timeout /t 10 /nobreak >nul
docker compose up -d
if errorlevel 1 goto :failed
echo  Waiting until TOEFL House ERP answers after repair...
set READY_TRIES=30
:waitready
timeout /t 10 /nobreak >nul
curl --fail --silent http://127.0.0.1:8000/ >nul 2>nul && goto :ready
set /a READY_TRIES-=1
if READY_TRIES GTR 0 goto :waitready
echo  TOEFL House ERP did not answer within 5 minutes.
goto :failed
:ready
echo  Repair complete. Starting TOEFL House ERP in your browser...
start "" "http://127.0.0.1:8000/"
pause
exit /b 0
:nosecret
docker volume inspect toefl-house-erp_db-data >nul 2>nul
if errorlevel 1 goto :nosecretfresh
echo  The database password file is missing, but a database already exists
echo  on this PC.
echo  Do NOT run the installer: it would write a new password that does not
echo  match the existing database. Contact TOEFL House support, or restore
echo  from your last backup.
pause
exit /b 1
:nosecretfresh
echo  The database password file is missing.
echo  Double-click "Install TOEFL House ERP.cmd" to create it. No database
echo  exists yet, so the installer only creates the missing file.
pause
exit /b 1
:failed
echo.
echo  Automatic repair could not finish. Current service state:
echo.
docker compose ps
echo.
echo  Last lines of the application log:
docker compose logs --tail 5 web 2>&1
echo.
echo  Web restart count since the last Docker start:
docker inspect --format {{.RestartCount}} toefl-house-erp-web 2>nul
echo.
echo  What the state above usually means:
echo    no rows, or rows "not running"     the ERP services are not up.
echo    db "unhealthy" or "restarting"      the database is not ready yet.
echo    web "Restarting" or exiting          the app stops right after starting.
echo    web restart count above 1            the app is crash-looping; the log
echo                                         lines above show why it stops.
echo.
echo  Try this Repair script once more. If it repeats, contact TOEFL House
echo  support with a photo of this window plus the contents of the data\logs folder.
pause
exit /b 1
