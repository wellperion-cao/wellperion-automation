@echo off
REM Wellperion Telegram Health Check - 13:00 daily runner (ASCII only)
REM Called by launchers\telegram_health_check_hidden.vbs (hidden window).
REM Pings Telegram bot connectivity, logs result to logs\telegram_health_check.log.
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\telegram_health_check.py >> logs\telegram_health_check.log 2>&1
