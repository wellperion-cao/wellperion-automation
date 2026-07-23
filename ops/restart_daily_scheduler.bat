@echo off
REM Wellperion daily_scheduler restart - self-elevating (triggers UAC prompt)
REM Double-click this file, then click "Yes" on the admin prompt.
REM Applies alert-text changes (nudge link removal + unchecked-items line).
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','%~dp0restart_daily_scheduler_core.ps1'"
