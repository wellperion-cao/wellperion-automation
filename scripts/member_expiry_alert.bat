@echo off
REM Wellperion Member Expiry Alert - monthly runner (ASCII only)
REM Called by launchers\member_expiry_alert_hidden.vbs (hidden window).
REM Sends next-month expiry alert to GM personal chat only (8254867551) - see
REM scripts\member_expiry_alert.py GM_CHAT_ID (hardcoded, no other target).
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\member_expiry_alert.py --send >> logs\member_expiry_alert.log 2>&1
