@echo off
REM Wellperion Reception/Lost-found health - every 15 min (ASCII only)
REM Called by launchers\reception_health_hidden.vbs. Alerts GM room only when state changes.
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\telegram_health_check.py --only reception >> logs\reception_health.log 2>&1
