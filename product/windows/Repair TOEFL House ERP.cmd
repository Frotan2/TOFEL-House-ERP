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
if not exist data\secrets\db.env goto :nosecret
if not exist data\activation mkdir data\activation
icacls data\activation /inheritance:r /grant:r "%USERDOMAIN%\%USERNAME%:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" /T >nul 2>nul
if errorlevel 1 goto :failed
if exist "release\toefl-house-erp-app.tar" goto :packageimage
echo  Checking product source line endings before repair...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Normalize Product Sources.ps1"
set "NORMALIZE_STATUS=%ERRORLEVEL%"
if "%NORMALIZE_STATUS%"=="0" goto :rebuildimage
if "%NORMALIZE_STATUS%"=="10" goto :rebuildimage
goto :sourcefailed
:rebuildimage
rem Rebuild even when the prior image has an LF label: source code may be newer.
echo [TH_STAGE] Rebuilding the application from current source for repair...
docker compose build
if errorlevel 1 goto :failed
goto :sourcesready
:packageimage
echo [TH_STAGE] Verifying the packaged application image...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Verify Package Image.ps1"
if errorlevel 1 goto :failed
echo [TH_STAGE] Loading the verified application image for repair...
docker load -i "release\toefl-house-erp-app.tar"
if errorlevel 1 goto :failed
docker image inspect toefl-house-erp-app:local >nul 2>nul
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
docker inspect --format "{{.State.Health.Status}}" toefl-house-erp-web 2>nul | findstr /x /c:"healthy" >nul || goto :waitservices
docker inspect --format "{{.State.Health.Status}}" toefl-house-erp-db 2>nul | findstr /x /c:"healthy" >nul || goto :waitservices
docker inspect --format "{{.State.Health.Status}}" toefl-house-erp-redis-queue 2>nul | findstr /x /c:"healthy" >nul || goto :waitservices
docker inspect --format "{{.State.Health.Status}}" toefl-house-erp-redis-cache 2>nul | findstr /x /c:"healthy" >nul || goto :waitservices
docker inspect --format "{{.State.Health.Status}}" toefl-house-erp-socketio 2>nul | findstr /x /c:"healthy" >nul || goto :waitservices
docker inspect --format "{{.State.Status}}" toefl-house-erp-worker 2>nul | findstr /x /c:"running" >nul || goto :waitservices
docker inspect --format "{{.State.Status}}" toefl-house-erp-scheduler 2>nul | findstr /x /c:"running" >nul || goto :waitservices
goto :ready
:waitservices
set /a READY_TRIES-=1
if READY_TRIES GTR 0 goto :waitready
echo  TOEFL House ERP services did not all become ready within 50 minutes.
goto :failed
:ready
echo  Repair complete. Starting TOEFL House ERP in your browser...
echo [TH_STAGE] ERP repair completed successfully.
if not defined TH_GUI_MODE start "" "http://127.0.0.1:8000/"
if not defined TH_GUI_MODE pause
exit /b 0
:nosecret
docker volume inspect toefl-house-erp_db-data >nul 2>nul
if errorlevel 1 goto :nosecretfresh
echo  The database password file is missing, but a database already exists
echo  on this PC.
echo  Do NOT run the installer: it would write a new password that does not
echo  match the existing database. Contact TOEFL House support, or restore
echo  from your last backup.
if not defined TH_GUI_MODE pause
exit /b 1
:nosecretfresh
echo  The database password file is missing.
echo  Double-click "Install TOEFL House ERP.cmd" to create it. No database
echo  exists yet, so the installer only creates the missing file.
if not defined TH_GUI_MODE pause
exit /b 1
:sourcefailed
echo.
echo  Product source files could not be safely normalized. Runtime data was not changed.
echo  Resolve the source check and run Repair again.
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
echo  Try this Repair script once more. If it repeats, contact TOEFL House
echo  support with a photo of this window plus the contents of the data\logs folder.
if not defined TH_GUI_MODE pause
exit /b 1
