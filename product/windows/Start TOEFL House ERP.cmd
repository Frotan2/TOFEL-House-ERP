@echo off
rem Daily launcher: double-click. Starts the already-installed app and
rem opens it in your browser. Never deletes data.
rem Style rule (proven on real Windows runs, 2026-09-30): fully linear flow -
rem single-line IF ... GOTO with dedicated labels, no multi-line
rem parenthesized blocks and no FOR commands, so the script parses
rem identically with LF or CRLF line endings regardless of how this folder
rem was delivered (Git checkout or GitHub ZIP).
cd /d "%~dp0.."
title Starting TOEFL House ERP
docker info >nul 2>nul
if errorlevel 1 goto :startdaemon
goto :up
:startdaemon
echo  Starting Docker Desktop - this can take a minute...
if exist "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe" goto :startuserdocker
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
goto :desktopstarted
:startuserdocker
start "" "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
:desktopstarted
set DAEMON_TRIES=60
:waitdaemon
powershell -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 5" >nul 2>nul
docker info >nul 2>nul && goto :up
set /a DAEMON_TRIES-=1
if DAEMON_TRIES GTR 0 goto :waitdaemon
echo  Docker Desktop did not finish starting within 5 minutes.
goto :failed
:up
if not exist data\secrets\db.env goto :nosecret
echo [TH_STAGE] Verifying preserved site and database before starting...
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Test Existing Installation.ps1"
if errorlevel 1 goto :datapreservationhold
if not exist data\activation mkdir data\activation
icacls data\activation /inheritance:r /grant:r "%USERDOMAIN%\%USERNAME%:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" /T >nul 2>nul
if errorlevel 1 goto :failed
echo [TH_STAGE] Starting the installed TOEFL House ERP...
docker compose up -d --no-build
if errorlevel 1 goto :failed
echo  Waiting until TOEFL House ERP answers...
set READY_TRIES=60
:waitready
powershell -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 10" >nul 2>nul
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Test Existing Installation.ps1" -CheckServices >nul 2>nul
if errorlevel 1 goto :waitservices
goto :ready
:waitservices
set /a READY_TRIES-=1
if READY_TRIES GTR 0 goto :waitready
echo  TOEFL House ERP services did not all become ready within 10 minutes.
goto :failed
:ready
echo [TH_STAGE] TOEFL House ERP is ready.
if not defined TH_GUI_MODE start "" "http://127.0.0.1:8000/"
echo  TOEFL House ERP is open in your browser. You may close this window.
if not defined TH_GUI_MODE powershell -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 6" >nul 2>nul
exit /b 0
:nosecret
echo [TH_STAGE] Checking if old site or database data must be preserved...
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Test Fresh Installation.ps1"
if errorlevel 1 goto :nosecretblocked
echo  The database password file is missing.
echo  No existing TOEFL House site or named database volume was found by the
echo  storage preflight. This is NOT proof that old data cannot exist elsewhere.
echo  Only on a genuinely new computer, use "Install TOEFL House ERP.cmd".
echo  If this computer was used for ERP before, stop and contact support.
if not defined TH_GUI_MODE pause
exit /b 1
:nosecretblocked
echo  Missing database credentials with existing or unverified site/storage.
echo  Do NOT reinstall, delete data or create a replacement database password.
echo  Recover the original credentials or contact TOEFL House support.
if not defined TH_GUI_MODE pause
exit /b 1
:datapreservationhold
echo  Start was blocked to protect an existing site or missing database volume.
echo  Do NOT reinstall, delete data or make a new password.
echo  Choose Check This PC in the Windows launcher, then share only
echo  Copy Safe Support Status with trusted support. No raw logs.
if not defined TH_GUI_MODE pause
exit /b 1
:failed
echo.
echo  TOEFL House ERP could not start. Current service state:
echo.
docker compose ps
echo.
echo  Last lines of the application logs:
docker compose logs --tail 5 bootstrap web worker socketio scheduler 2>&1
echo.
echo  Container state and restart counts:
docker inspect --format "{{.Name}} status={{.State.Status}} exit={{.State.ExitCode}} restarts={{.RestartCount}} oom={{.State.OOMKilled}}" toefl-house-erp-web toefl-house-erp-worker toefl-house-erp-socketio toefl-house-erp-scheduler 2>nul
echo.
echo  What the state above usually means:
echo    no rows, or rows "not running"     the ERP services are not up.
echo    db "unhealthy" or "restarting"      the database is not ready yet.
echo    web "Restarting" or exiting          the app stops right after starting.
echo    web restart count above 1            the app is crash-looping; the log
echo                                         lines above show why it stops.
echo.
echo  Stop and contact trusted support before using Repair.
echo  Use Check This PC, then Copy Safe Support Status in the Windows GUI.
echo  Do not send entire log folders, passwords or student records.
if not defined TH_GUI_MODE pause
exit /b 1
