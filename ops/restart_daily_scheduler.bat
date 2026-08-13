@echo off
REM Wellperion daily_scheduler restart
REM 2026-08-13 (bae596): admin elevation was not actually needed - Stop-Process +
REM Start-ScheduledTask both work as the normal user. The UAC prompt only made
REM people hesitate to restart. Runs directly now; no prompt.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart_daily_scheduler_core.ps1"
pause
