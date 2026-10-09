@echo off
rem Creates a full encrypted backup and copies the verified backup set to
rem a different fixed drive on this same Windows computer.
rem Off-site, NAS, second-device and cloud backup are future scope, not a
rem current launch requirement.
cd /d "%~dp0.."
title Backing up TOEFL House ERP
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Backup TOEFL House ERP.ps1"
set "BACKUP_EXIT=%ERRORLEVEL%"
if "%BACKUP_EXIT%"=="2" goto :policyrequired
if not "%BACKUP_EXIT%"=="0" goto :backupfailed
echo.
echo  Backup completed, GPG encryption and integrity verified on a separate local drive.
echo  Owner-selected schedule and explicit preserve/delete retention behavior are installed.
pause
exit /b 0
:policyrequired
echo.
echo  No backup was created because the Owner backup policy is incomplete.
echo  Configure the local nightly time, retention count, explicit preserve/delete behavior, and public recovery key in the ERP Configuration desk.
echo  Keep the matching private key outside Frappe and the backup drive. Activation remains REFUSED until a complete backup is verified.
pause
exit /b 2
:backupfailed
echo.
echo  Backup failed or no separate local drive was available.
echo  No success is reported until actual GPG encryption, copy and SHA-256 verification pass.
pause
exit /b 1
