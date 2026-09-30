@echo off
rem One-time production activation (docs/engineering/LAUNCH-RUNBOOK.md, steps 0-7).
rem All safety gates run inside the app; on any failure the old settings are restored.
cd /d "%~dp0.."
title Activating TOEFL House ERP
docker compose exec web python3 /product/activate.py status
if errorlevel 1 goto :notrunning
echo.
echo  This switches TOEFL House ERP from test-safe mode to REAL operation.
echo  Before continuing you must have:
echo    - run "Backup TOEFL House ERP.cmd" today and copied the backup to an external drive
echo    - kept this PC off the public internet (the app only listens on this PC)
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
echo  TOEFL House ERP is ACTIVE for real operation.
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
:cancelled
echo  Cancelled. Nothing was changed.
pause
exit /b 0
:failed
echo.
echo  Activation did NOT complete; the reason is shown above. Nothing was left half-changed.
pause
exit /b 1
