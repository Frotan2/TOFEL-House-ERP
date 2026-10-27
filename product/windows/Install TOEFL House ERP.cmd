@echo off
setlocal enableextensions
rem ============================================================
rem  TOEFL House ERP - one-time installer (double-click; no typing)
rem  Requires: Docker Desktop for Windows (free, installs with WSL2).
rem  What it does, automatically:
rem    1. Verifies Docker Desktop is installed and running
rem    2. Verifies the prebuilt, signed application image in this package
rem    3. Generates a private database password (stored locally only)
rem    4. Imports the verified image and starts every service
rem    5. Opens TOEFL House ERP in your browser when it is ready
rem  Nothing is compiled on this computer; a complete package always
rem  contains release\toefl-house-erp-app.tar.
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
rem Any prior local credentials or site config indicate an attempted
rem installation. Even an incomplete attempt may have preserved database data;
rem never treat it as a fresh install and never recreate a missing volume.
if exist "data\secrets\db.env" goto :alreadyinstalled
if exist "data\sites\toeflhouse.localhost\site_config.json" goto :alreadyinstalled

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
powershell -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 5" >nul 2>nul
docker info >nul 2>nul && goto :dockerup
set /a DAEMON_TRIES-=1
if DAEMON_TRIES GTR 0 goto :waitdaemon
echo  Docker Desktop did not finish starting within 5 minutes.
goto :failed
:dockerup

rem A customer kit always ships one prebuilt, verified image.  There is no
rem source-build path: compiling Frappe or frontend assets on a customer PC
rem needs developer tools, is not reproducible, and can silently replace a
rem working installation with an unverified build.
if not exist "release\toefl-house-erp-app.tar" goto :packagemissing
echo [TH_STAGE] Checking package integrity before local installation...
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Verify Package Image.ps1"
if errorlevel 1 goto :packageinvalid

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
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Test Fresh Installation.ps1"
if errorlevel 1 goto :storagecheckfailed
echo  Generating a private database password for this computer...
powershell -NoProfile -Command "[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')" > data\secrets\.dbpw.tmp
set /p DBPW=<data\secrets\.dbpw.tmp
del data\secrets\.dbpw.tmp >nul 2>nul
if not defined DBPW goto :failed
>data\secrets\db.env echo MARIADB_ROOT_PASSWORD=%DBPW%
:secretok
attrib +h data\secrets >nul 2>nul

echo.
echo [TH_STAGE] Verifying the supplied application image...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Verify Package Image.ps1"
if errorlevel 1 goto :packagechanged
echo [TH_STAGE] Loading the ready-to-run application. This can take several minutes.
docker load -i "release\toefl-house-erp-app.tar"
if errorlevel 1 goto :failed
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Verify Package Image.ps1" -VerifyLoadedImage
if errorlevel 1 goto :failed
echo [TH_STAGE] Starting TOEFL House ERP...
docker compose up -d --no-build
if errorlevel 1 goto :failed
:waitboot

echo.
echo [TH_STAGE] Preparing the first ERP site, database, and services...
echo  First launch is finishing inside the app - site setup and data install.
echo  You can watch progress in Docker Desktop, or simply wait for the browser.
set READY_TRIES=300
:waitready
powershell -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 10" >nul 2>nul
curl --fail --silent http://127.0.0.1:8000/ >nul 2>nul || goto :preparing
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Test Existing Installation.ps1" -CheckServices >nul 2>nul
if errorlevel 1 goto :preparing
goto :ready
:preparing
echo  Still preparing... site setup can take 15-40 minutes on first run.
set /a READY_TRIES-=1
if READY_TRIES GTR 0 goto :waitready
echo  The first run did not finish within 50 minutes.
goto :failed
:ready

if defined TH_GUI_MODE goto :nowelcome
if not exist data\sites\toeflhouse.localhost\private\first-run-credentials.txt goto :nowelcome
echo.
echo  --------------------------------------------------------------
echo  Your Administrator login is below. Write it down and keep it private.
echo  --------------------------------------------------------------
type data\sites\toeflhouse.localhost\private\first-run-credentials.txt
echo  --------------------------------------------------------------
:nowelcome

echo [TH_STAGE] TOEFL House ERP is ready.
if not defined TH_GUI_MODE start "" "http://127.0.0.1:8000/"
echo.
echo  Install finished. From now on use the "Start TOEFL House ERP" shortcut.
if not defined TH_GUI_MODE pause
exit /b 0

:alreadyinstalled
echo [TH_STAGE] Existing TOEFL House ERP site detected - no installation attempted.
echo  This computer has ERP site files or previously created credentials.
echo  If setup is complete, use Open / Start for daily work.
echo  If setup was interrupted, STOP and contact trusted support.
echo  Never run Install over existing or partially initialized storage.
echo  If the system cannot start,
echo  choose Check This PC and share only Copy Safe Support Status with support.
if not defined TH_GUI_MODE pause
exit /b 1
:packageinvalid
echo  Package integrity verification failed before credential setup.
echo  Do NOT install from this package. Request a complete trusted copy.
if not defined TH_GUI_MODE pause
exit /b 1

:packagechanged
echo  Package verification failed after local setup started.
echo  The package changed or became unreadable during installation.
echo  A partial installation was preserved: do NOT run Install again,
echo  do not delete data and do not create a replacement password.
echo  In the Windows launcher choose Check This PC, then share only
echo  Copy Safe Support Status with trusted support. No raw logs.
if not defined TH_GUI_MODE pause
exit /b 1

:packagemissing
echo.
echo  This folder is not a complete TOEFL House ERP customer package.
echo  The verified application image release\toefl-house-erp-app.tar is missing.
echo  Nothing was built, started or changed on this computer.
echo  Ask authorized TOEFL House support for a complete package download.
echo  Do not build the application yourself on this computer.
if not defined TH_GUI_MODE pause
exit /b 1

:storagecheckfailed
echo  Installation stopped safely. Existing data was not changed.
echo  Recover the original database password file before continuing.
if not defined TH_GUI_MODE pause
exit /b 1

:secretaclfailed
echo.
echo  Windows could not restrict access to the local secrets and activation receipt folders.
echo  No database password was generated. Check this account's local permissions and try again.
if not defined TH_GUI_MODE pause
exit /b 1

:failed
echo.
echo  ------------------------------------------------------------------
echo  Something went wrong. Current service state:
docker compose ps
echo  Last lines of the application log:
docker compose logs --tail 5 bootstrap web worker scheduler socketio 2>&1
echo.
echo  Stop here and contact authorized TOEFL House support.
echo  A partially initialized installation must be diagnosed before any
echo  Repair or retry. In the Windows launcher, choose Check This PC,
echo  then Copy Safe Support Status. Do not send raw log folders,
echo  passwords, student records, site files or backups.
echo  ------------------------------------------------------------------
:pause
if not defined TH_GUI_MODE pause
exit /b 1
