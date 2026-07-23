@echo off
REM Wellperion Monthly Check Report - day1 09:00 live runner (ASCII only)
REM Called by launchers\monthly_check_report_hidden.vbs (hidden window).
REM Fetches prev-month GAS monthly_report(dept=support), sends Telegram
REM summary card to check-room (-5136037543), logs to
REM status\support_monthly_report_log.jsonl.
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\monthly_check_report.py --send >> logs\monthly_check_report.log 2>&1
