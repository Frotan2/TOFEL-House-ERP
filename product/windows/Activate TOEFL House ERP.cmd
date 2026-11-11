@echo off
setlocal DisableDelayedExpansion
rem Switches this site into operational PRODUCTION mode only; it is not production authorization.
rem All activation safety gates run in the app; verify the secondary-drive copy on the host first.
cd /d "%~dp0.."
title Activating TOEFL House ERP
docker compose exec web python3 /product/activate.py status
if errorlevel 1 goto :notrunning
powershell -NoProfile -File "%~dp0Backup TOEFL House ERP.ps1" -VerifyExisting
if errorlevel 1 goto :backupmissing
echo.
echo  This changes the site operational mode from SYNTHETIC/REFUSED to PRODUCTION.
echo  It does NOT authorize release or approve production go-live.
echo  Release status remains REJECTED until all external evidence gates and Owner approval pass.
echo  Before continuing, verify that the fresh encrypted backup is on a separate local drive.
echo  Public internet hosting is not enabled; the desktop port stays loopback-only.
echo.
choice /C YN /N /M "Switch site mode after backup verification? [Y/N] "
if errorlevel 2 goto :cancelled
if not errorlevel 1 goto :cancelled
docker compose exec web python3 /product/activate.py activate --confirm toeflhouse.localhost
if errorlevel 1 goto :failed
echo.
echo  Optional: Finance's placement-fee Item code (the Item must already exist in
echo  ERPNext with a price on "TOEFL House Standard"). Press Enter to skip; you can
echo  run this file again later to set it.
set "TOEFL_ACTIVATION_ITEM="
set /p "TOEFL_ACTIVATION_ITEM=Placement fee Item code: "
if not defined TOEFL_ACTIVATION_ITEM goto :done
rem Read the value as data. Never interpolate console input into CMD syntax.
powershell -NoProfile -Command "$item=$env:TOEFL_ACTIVATION_ITEM; if($item.Contains([char]34)){[Console]::Error.WriteLine('An Item code containing a double quote requires technical support.'); exit 2}; & docker compose exec web python3 /product/activate.py fee-item --confirm toeflhouse.localhost $item; exit $LASTEXITCODE"
if errorlevel 1 goto :itemfailed
:done
echo.
echo  Site operational mode is PRODUCTION.
echo  Production authorization remains REJECTED until release evidence and Owner approval pass.
pause
exit /b 0
:itemfailed
echo.
echo  Activation succeeded, but the placement fee Item was not set (see the reason above).
echo  Run this file again after Finance fixes the Item.
pause
exit /b 1
:notrunning
echo.
echo  TOEFL House ERP is not running. Double-click "Start TOEFL House ERP.cmd" first.
pause
exit /b 1
:backupmissing
echo.
echo  The current encrypted backup, separate local drive, Owner policy or manifest did not verify.
echo  Operational mode was not changed. Do not run the backup helper until the Owner backup policy is complete in ERP Configuration.
echo  Enter the keep count, nightly time and public recovery key in ERP Configuration (retention behavior was decided by the Owner on 2026-10-14, decision D17), then retry.
pause
exit /b 1
:cancelled
echo  Cancelled. Nothing was changed.
pause
exit /b 0
:failed
echo.
echo  Activation did NOT complete; the reason is shown above. Nothing was left half-changed.
pause
exit /b 1
