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
rem
rem  Author note: NO multi-line parenthesized blocks and NO FOR commands are
rem  used anywhere in this script on purpose. cmd.exe parses "( ... )" blocks
rem  correctly only with CRLF line endings, and its block/FOR parsers are
rem  quote-blind about "(" and ")" inside arguments. A checkout could deliver
rem  LF endings (no .gitattributes existed), making the first multi-line
rem  block abort with ") was unexpected at this time." on real Windows runs
rem  (2026-09-30, three independent reproductions). Flow is therefore fully
rem  linear: single-line IF ... GOTO with dedicated labels; the only
rem  parentheses left are inside one double-quoted PowerShell argument of a
rem  plain top-level call.
rem ============================================================
title Installing TOEFL House ERP
cd /d "%~dp0.."

where docker >nul 2>nul
if not errorlevel 1 goto :dockerfound
echo.
echo  Docker Desktop is not installed yet.
echo  1. Install it from https://www.docker.com/products/docker-desktop/
echo  2. Restart your PC when it asks.
echo  3. Double-click this file again.
start "" "https://www.docker.com/products/docker-desktop/"
goto :pause
:dockerfound

docker info >nul 2>nul
if not errorlevel 1 goto :dockerup
echo.
echo  Docker Desktop is installed but not running.
echo  Starting it now - this can take a minute...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
set DAEMON_TRIES=60
:waitdaemon
timeout /t 5 /nobreak >nul
docker info >nul 2>nul && goto :dockerup
set /a DAEMON_TRIES-=1
if DAEMON_TRIES GTR 0 goto :waitdaemon
echo  Docker Desktop did not finish starting within 5 minutes.
goto :failed
:dockerup

echo  Checking product source line endings before the image build...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Normalize Product Sources.ps1"
set "NORMALIZE_STATUS=%ERRORLEVEL%"
if "%NORMALIZE_STATUS%"=="0" goto :sourcesready
if "%NORMALIZE_STATUS%"=="10" goto :sourceschanged
goto :sourcefailed
:sourceschanged
echo  Existing checkout source endings were repaired safely.
:sourcesready

if not exist data\secrets mkdir data\secrets
rem  Restrict database credentials before writing any temporary password.
rem  The interactive Docker Desktop user, LocalSystem and local admins need
rem  access; inherited access for unrelated local accounts is removed.
icacls data\secrets /inheritance:r /grant:r "%USERDOMAIN%\%USERNAME%:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" /T >nul 2>nul
if errorlevel 1 goto :secretaclfailed
if not exist data\activation mkdir data\activation
icacls data\activation /inheritance:r /grant:r "%USERDOMAIN%\%USERNAME%:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" /T >nul 2>nul
if errorlevel 1 goto :secretaclfailed
rem  Secret generation: no FOR /F here. cmd's FOR parser mishandles the ')'
rem  inside PowerShell's ToString('N') even at top level (proven on a real
rem  Windows run: ") was unexpected at this time."). Instead PowerShell
rem  writes the one-time password to a temp file and CMD reads it with
rem  SET /P - no parentheses and no FOR constructs touch CMD's parser.
if exist data\secrets\db.env goto :secretok
echo  Generating a private database password for this computer...
powershell -NoProfile -Command "[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')" > data\secrets\.dbpw.tmp
set /p DBPW=<data\secrets\.dbpw.tmp
del data\secrets\.dbpw.tmp >nul 2>nul
if not defined DBPW goto :failed
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
echo  First launch is finishing inside the app - site setup and data install.
echo  You can watch progress in Docker Desktop, or simply wait for the browser.
set READY_TRIES=300
:waitready
timeout /t 10 /nobreak >nul
curl --fail --silent http://127.0.0.1:8000/ >nul 2>nul || goto :preparing
docker inspect --format "{{.State.Health.Status}}" toefl-house-erp-web 2>nul | findstr /x /c:"healthy" >nul || goto :preparing
docker inspect --format "{{.State.Health.Status}}" toefl-house-erp-db 2>nul | findstr /x /c:"healthy" >nul || goto :preparing
docker inspect --format "{{.State.Health.Status}}" toefl-house-erp-redis-queue 2>nul | findstr /x /c:"healthy" >nul || goto :preparing
docker inspect --format "{{.State.Health.Status}}" toefl-house-erp-redis-cache 2>nul | findstr /x /c:"healthy" >nul || goto :preparing
docker inspect --format "{{.State.Health.Status}}" toefl-house-erp-socketio 2>nul | findstr /x /c:"healthy" >nul || goto :preparing
docker inspect --format "{{.State.Status}}" toefl-house-erp-worker 2>nul | findstr /x /c:"running" >nul || goto :preparing
docker inspect --format "{{.State.Status}}" toefl-house-erp-scheduler 2>nul | findstr /x /c:"running" >nul || goto :preparing
goto :ready
:preparing
echo  Still preparing... site setup can take 15-40 minutes on first run.
set /a READY_TRIES-=1
if READY_TRIES GTR 0 goto :waitready
echo  The first run did not finish within 50 minutes.
goto :failed
:ready

if not exist data\sites\toeflhouse.localhost\private\first-run-credentials.txt goto :nowelcome
echo.
echo  --------------------------------------------------------------
echo  Your Administrator login is below. Write it down and keep it private.
echo  --------------------------------------------------------------
type data\sites\toeflhouse.localhost\private\first-run-credentials.txt
echo  --------------------------------------------------------------
:nowelcome

start "" "http://127.0.0.1:8000/"
echo.
echo  Install finished. From now on use the "Start TOEFL House ERP" shortcut.
pause
exit /b 0

:secretaclfailed
echo.
echo  Windows could not restrict access to the local secrets and activation receipt folders.
echo  No database password was generated. Check this account's local permissions and try again.
pause
exit /b 1

:sourcefailed
echo.
echo  Product source files could not be safely normalized. No product data was changed.
echo  Send a photo of this window and the product source folder to support.
pause
exit /b 1

:failed
echo.
echo  ------------------------------------------------------------------
echo  Something went wrong. Current service state:
docker compose ps
echo  Last lines of the application log:
docker compose logs --tail 5 bootstrap web worker scheduler socketio 2>&1
echo.
echo  Double-click "Repair TOEFL House ERP.cmd"; it restarts the system
echo  and finishes the unfinished setup safely. If it repeats, send a
echo  photo of this window plus the data\logs folder to TOEFL House
echo  support.
echo  ------------------------------------------------------------------
:pause
pause
exit /b 1
