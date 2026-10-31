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
goto :repair
:daemondown
echo  Docker Desktop is not running. Please start it, wait a minute, then run this again.
if not defined TH_GUI_MODE pause
exit /b 1
:repair
rem Never revert an independently signed update to the original factory image.
rem Even completed update journals require a version-aware supported recovery.
if exist data\updates\journal.json goto :updaterepairhold
if not exist data\secrets\db.env goto :nosecret
echo [TH_STAGE] Verifying preserved site and database before repair...
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Test Existing Installation.ps1"
if errorlevel 1 goto :datapreservationhold
if not exist data\activation mkdir data\activation
icacls data\activation /inheritance:r /grant:r "%USERDOMAIN%\%USERNAME%:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" /T >nul 2>nul
if errorlevel 1 goto :failed
rem Repair only ever reinstalls the verified prebuilt image that ships with
rem the customer kit.  Building from source here would compile a different
rem application on the customer PC and could replace a working installation
rem with an unverified build, so a missing image is a safe refusal instead.
if exist "release\toefl-house-erp-app.tar" goto :packageimage
goto :packagemissing
:packageimage
echo [TH_STAGE] Verifying the packaged application image...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Verify Package Image.ps1"
if errorlevel 1 goto :failed
echo [TH_STAGE] Loading the verified application image for repair...
docker load -i "release\toefl-house-erp-app.tar"
if errorlevel 1 goto :failed
rem A bare tag-existence check cannot prove exact-version identity: bind
rem the loaded image to the verified manifest labels before any restart.
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Verify Package Image.ps1" -VerifyLoadedImage
if errorlevel 1 goto :failed
goto :sourcesready
:sourcesready
echo [TH_STAGE] Restarting application services without removing database volumes...
docker compose down
docker compose up -d db redis-queue redis-cache
powershell -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 10" >nul 2>nul
docker compose up -d --no-build
if errorlevel 1 goto :failed
echo [TH_STAGE] Waiting for database and application health checks...
echo  Waiting until TOEFL House ERP answers after repair...
set READY_TRIES=300
:waitready
powershell -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 10" >nul 2>nul
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Test Existing Installation.ps1" -CheckServices >nul 2>nul
if errorlevel 1 goto :waitservices
goto :ready
:waitservices
set /a READY_TRIES-=1
if %READY_TRIES% GTR 0 goto :waitready
echo  TOEFL House ERP services did not all become ready within 50 minutes.
goto :failed
:ready
echo  Repair complete. Starting TOEFL House ERP in your browser...
echo [TH_STAGE] ERP repair completed successfully.
if not defined TH_GUI_MODE start "" "http://127.0.0.1:8000/"
if not defined TH_GUI_MODE pause
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
:updaterepairhold
echo  Repair refused: a signed update journal exists.
echo  The original factory image must not replace a later approved release.
echo  Stop and request preservation-safe, version-aware recovery from trusted support.
if not defined TH_GUI_MODE pause
exit /b 1
:datapreservationhold
echo  Repair was blocked to protect the existing site or database.
echo  Do NOT reinstall, delete Docker volumes or regenerate passwords.
echo  Ask trusted support. Use Check This PC and Copy Safe Support Status.
if not defined TH_GUI_MODE pause
exit /b 1

:packagemissing
echo.
echo  This folder is not a complete TOEFL House ERP customer package.
echo  The verified application image release\toefl-house-erp-app.tar is missing.
echo  Repair did not build, start, stop or change anything on this computer.
echo  Your students, payments, invoices and other records were not touched.
echo  Ask authorized TOEFL House support for a complete package download.
if not defined TH_GUI_MODE pause
exit /b 1

:failed
echo.
echo  Automatic repair could not finish. Current service state:
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
echo  Stop here. Contact trusted TOEFL House support.
echo  Use Check This PC and Copy Safe Support Status; do not share raw
echo  logs, personal data, passwords, site configuration or backups.
if not defined TH_GUI_MODE pause
exit /b 1
