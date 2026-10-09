@echo off
rem Switches this site into operational PRODUCTION mode only; it is not production authorization.
rem All activation safety gates run in the app; verify the secondary-drive copy on the host first.
cd /d "%~dp0.."
title Activating TOEFL House ERP
docker compose exec web python3 /product/activate.py status
if errorlevel 1 goto :notrunning
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Backup TOEFL House ERP.ps1" -VerifyExisting
if errorlevel 1 goto :backupmissing
echo.
echo  This changes the site operational mode from SYNTHETIC/REFUSED to PRODUCTION.
echo  It does NOT authorize release or approve production go-live.
echo  Release status remains REJECTED until all external evidence gates and Owner approval pass.
echo  Before continuing, verify that the fresh encrypted backup is on a separate local drive.
echo  Public internet hosting is not enabled; the desktop port stays loopback-only.
echo.
set "ANSWER="
set /p "ANSWER=Type ACTIVATE and press Enter to continue, or just press Enter to cancel: "
if /i not "%ANSWER%"=="ACTIVATE" goto :cancelled
docker compose exec web python3 /product/activate.py activate --confirm toeflhouse.localhost
if errorlevel 1 goto :failed
echo.
echo  Optional: Finance's placement-fee Item code (the Item must already exist in
echo  ERPNext with a price on "TOEFL House Standard"). Press Enter to skip; you can
echo  run this file again later to set it.
set "ITEM="
set /p "ITEM=Placement fee Item code: "
if "%ITEM%"=="" goto :done
docker compose exec web python3 /product/activate.py fee-item --confirm toeflhouse.localhost "%ITEM%"
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
echo  Operational mode was not changed. Do not run the backup helper while the preservation decision is unresolved.
echo  Resolve the Owner retention choice and reconcile the implementation/docs before retrying.
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
