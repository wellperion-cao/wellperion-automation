@echo off
REM Wellperion Telegram Health Check - 13:00 daily runner (ASCII only)
REM Called by launchers\telegram_health_check_hidden.vbs (hidden window).
REM Pings Telegram bot connectivity, logs result to logs\telegram_health_check.log.
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\telegram_health_check.py >> logs\telegram_health_check.log 2>&1

REM [2026-07-21 merge 9420 #1] Self-health watchdog daily digest (piggyback, no new task). Rollback=delete next 2 lines.
set SELF_HEALTH_WATCHDOG_LIVE=1
C:\Python314\python.exe -u scripts\self_health_watchdog.py --live >> logs\self_health_watchdog.log 2>&1
