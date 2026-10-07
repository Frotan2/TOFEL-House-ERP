@echo off
rem Creates a full database + files backup of TOEFL House ERP.
rem The backup files appear next to this folder under data\sites\...
rem Style rule (proven on real Windows runs, 2026-09-30): fully linear flow -
rem single-line IF ... GOTO with dedicated labels, no multi-line
rem parenthesized blocks and no FOR commands, so the script parses
rem identically with LF or CRLF line endings regardless of how this folder
rem was delivered (Git checkout or GitHub ZIP).
cd /d "%~dp0.."
title Backing up TOEFL House ERP
docker compose exec web /build/tools/bin/bench --site toeflhouse.localhost backup --with-files
if errorlevel 1 goto :backupfailed
echo.
echo  Backup finished. Backup files are in:
echo    %CD%\data\sites\toeflhouse.localhost\private\backups
echo  This is the current required local backup: keep the full backup on a separate local drive from the live data.
echo  Off-site, NAS, second-device or cloud backup is NOT required for the current launch and is deferred for a future Owner decision.
echo  Note: restore is a guided operator step and must be rehearsed.
pause
exit /b 0
:backupfailed
echo.
echo  Backup failed. Make sure the system is running, then try again.
pause
exit /b 1
