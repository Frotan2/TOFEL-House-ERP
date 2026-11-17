@echo off
setlocal
start "TOEFL House ERP Private HTTPS" "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -STA -WindowStyle Hidden -File "%~dp0Private HTTPS Setup.ps1"
