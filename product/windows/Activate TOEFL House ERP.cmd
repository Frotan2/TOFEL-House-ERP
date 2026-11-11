@echo off
setlocal DisableDelayedExpansion
rem Requires a separately authorized internal release and the verified secondary-drive copy.
cd /d "%~dp0.."
title Activating TOEFL House ERP
docker compose exec web python3 /product/activate.py status
if errorlevel 1 goto :notrunning
powershell -NoProfile -File "%~dp0Verify Package Image.ps1" -VerifyLoadedImage
if errorlevel 1 goto :failed
choice /C AFN /N /M "Activate internal release [A], set placement fee on an active site [F], cancel [N]: "
if errorlevel 255 goto :failed
if errorlevel 3 goto :cancelled
if errorlevel 2 goto :feeitem
if not errorlevel 1 goto :cancelled
powershell -NoProfile -File "%~dp0Backup TOEFL House ERP.ps1" -VerifyExisting
if errorlevel 1 goto :backupmissing
echo.
echo  This switches a verified REFUSED installation into approved internal use.
echo  The signed public release remains separate.
echo  Before continuing, verify that the fresh encrypted backup is on a separate local drive.
echo  Public internet hosting is not enabled; the desktop port stays loopback-only.
echo.
docker compose exec -T web python3 /product/activate.py internal-context --confirm toeflhouse.localhost
if errorlevel 1 goto :failed
choice /C YN /N /M "Apply the approved internal release to this installation? [Y/N] "
if errorlevel 2 goto :cancelled
if not errorlevel 1 goto :cancelled
powershell -NoProfile -File "%~dp0Verify Package Image.ps1" -VerifyLoadedImage
if errorlevel 1 goto :failed
powershell -NoProfile -File "%~dp0Backup TOEFL House ERP.ps1" -VerifyExisting
if errorlevel 1 goto :backupmissing
docker compose exec -T web python3 /product/activate.py internal-activate --confirm toeflhouse.localhost
if errorlevel 1 goto :failed
echo  Internal approval applied. Public release authorization has not changed.
:feeitem
echo.
echo  Optional: Finance's placement-fee Item code (the Item must already exist in
echo  ERPNext with a price on "TOEFL House Standard"). Press Enter to skip; you can
echo  run this file again later to set it.
set "TOEFL_ACTIVATION_ITEM="
set /p "TOEFL_ACTIVATION_ITEM=Placement fee Item code: "
if not defined TOEFL_ACTIVATION_ITEM goto :cancelled
rem Read the value as data. Never interpolate console input into CMD syntax.
powershell -NoProfile -Command "$item=$env:TOEFL_ACTIVATION_ITEM; if($item.Contains([char]34)){[Console]::Error.WriteLine('An Item code containing a double quote requires technical support.'); exit 2}; & docker compose exec web python3 /product/activate.py fee-item --confirm toeflhouse.localhost $item; exit $LASTEXITCODE"
if errorlevel 1 goto :itemfailed
:done
echo.
echo  Site operational mode is PRODUCTION.
pause
exit /b 0
:itemfailed
echo.
echo  The placement fee Item was not set (see the reason above).
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
echo  No further action was taken.
pause
exit /b 0
:failed
echo.
echo  Activation did NOT complete; the reason is shown above. Nothing was left half-changed.
pause
exit /b 1
