@echo off
REM Wellperion Telegram Health Check - 13:00 daily runner (ASCII only)
REM Called by launchers\telegram_health_check_hidden.vbs (hidden window).
REM Pings Telegram bot connectivity, logs result to logs\telegram_health_check.log.
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\telegram_health_check.py >> logs\telegram_health_check.log 2>&1

REM [2026-07-31 GM order] Retired for good - the commented-out block that used to live here
REM   (SELF_HEALTH_WATCHDOG_LIVE + self_health_watchdog.py --live) is DELETED, not kept off.
REM   Reason: that 13:00 send was superseded on 2026-07-22 when the same self-health digest was
REM   folded into cto-automation-health's 09:10 message. Leaving it commented made it look like
REM   a feature "waiting for GM go" for 10 days - it was not waiting, it was already replaced.
REM   GM: "a week-plus of not running means it is pointless, careless, or duplicated - retire it."
REM   The useful part still lives: collectors/cto_automation_health.py reuses build_digest().
REM   Do NOT re-add a second daily send here. If self-health must be louder, change the 09:10 digest.
