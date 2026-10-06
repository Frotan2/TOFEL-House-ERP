@echo off
rem Stops all TOEFL House ERP services. Your data stays safe on this PC.
rem Style rule (proven on real Windows runs, 2026-09-30): fully linear flow -
rem single-line IF ... GOTO with dedicated labels, no multi-line
rem parenthesized blocks and no FOR commands, so the script parses
rem identically with LF or CRLF line endings regardless of how this folder
rem was delivered (Git checkout or GitHub ZIP).
cd /d "%~dp0.."
title Stopping TOEFL House ERP
docker compose down
if errorlevel 1 goto :downfailed
echo  TOEFL House ERP has stopped. You may close this window.
timeout /t 5 >nul
exit /b 0
:downfailed
echo  Could not stop cleanly. If the problem repeats, use the Repair script.
pause
exit /b 1
