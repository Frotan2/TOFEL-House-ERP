@echo off
rem Rollback of production activation (docs/engineering/LAUNCH-RUNBOOK.md, step 8).
rem Data is untouched; TOEFL House commands are simply refused again.
cd /d "%~dp0.."
title Deactivating TOEFL House ERP
docker compose exec web python3 /product/activate.py status
if errorlevel 1 goto :notrunning
set "ANSWER="
set /p "ANSWER=Type DEACTIVATE and press Enter to continue, or just press Enter to cancel: "
if /i not "%ANSWER%"=="DEACTIVATE" goto :cancelled
docker compose exec web python3 /product/activate.py deactivate --confirm toeflhouse.localhost
if errorlevel 1 goto :failed
pause
exit /b 0
:notrunning
echo  TOEFL House ERP is not running. Double-click "Start TOEFL House ERP.cmd" first.
pause
exit /b 1
:cancelled
echo  Cancelled. Nothing was changed.
pause
exit /b 0
:failed
echo  Deactivation did not complete; the reason is shown above.
pause
exit /b 1
