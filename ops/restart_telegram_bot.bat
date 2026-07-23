@echo off
REM Wellperion report bot restart - self-elevating (triggers UAC prompt)
REM Double-click this file, then click "Yes" on the admin prompt.
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','%~dp0restart_telegram_bot_core.ps1'"
