@echo off
rem Stops all TOEFL House ERP services. Your data stays safe on this PC.
rem Style rule (proven on real Windows runs, 2026-09-30): fully linear flow -
rem single-line IF ... GOTO with dedicated labels, no multi-line
rem parenthesized blocks and no FOR commands, so the script parses
rem identically with LF or CRLF line endings regardless of how this folder
rem was delivered (Git checkout or GitHub ZIP).
cd /d "%~dp0.."
title Stopping TOEFL House ERP
echo [TH_STAGE] Stopping TOEFL House ERP while preserving all data...
docker compose down
if errorlevel 1 goto :downfailed
echo [TH_STAGE] TOEFL House ERP has stopped.
echo  TOEFL House ERP has stopped. You may close this window.
if not defined TH_GUI_MODE powershell -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 5" >nul 2>nul
exit /b 0
:downfailed
echo  Could not stop cleanly. If the problem repeats, use the Repair script.
if not defined TH_GUI_MODE pause
exit /b 1
