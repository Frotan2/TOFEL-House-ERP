@echo off
rem Creates a full encrypted backup and copies the verified backup set to
rem a different fixed drive on this same Windows computer.
rem Off-site, NAS, second-device and cloud backup are future scope, not a
rem current launch requirement.
cd /d "%~dp0.."
title Backing up TOEFL House ERP
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Backup TOEFL House ERP.ps1"
if errorlevel 1 goto :backupfailed
echo.
echo  Backup completed and verified on a separate local drive.
pause
exit /b 0
:backupfailed
echo.
echo  Backup failed or no separate local drive was available.
echo  No success is reported until encryption, copy and SHA-256 verification pass.
pause
exit /b 1
