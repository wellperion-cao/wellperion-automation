@echo off
REM Wellperion Telegram Health Check - 13:00 daily runner (ASCII only)
REM Called by launchers\telegram_health_check_hidden.vbs (hidden window).
REM Pings Telegram bot connectivity, logs result to logs\telegram_health_check.log.
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\telegram_health_check.py >> logs\telegram_health_check.log 2>&1

REM [2026-07-21 merge 9420 #1] Self-health watchdog daily digest (piggyback, no new task).
REM [2026-07-22 GM order - merge B into A] This 13:00 direct send now duplicates the
REM   self-health section folded into cto-automation-health's 09:10 daily digest
REM   (collectors/cto_automation_health.py reuses self_health_watchdog.build_digest()).
REM   Disabled here to stop the 2nd daily message in room 4. Rollback = uncomment next 2 lines.
REM set SELF_HEALTH_WATCHDOG_LIVE=1
REM C:\Python314\python.exe -u scripts\self_health_watchdog.py --live >> logs\self_health_watchdog.log 2>&1
