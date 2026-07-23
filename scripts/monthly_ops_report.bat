@echo off
REM Wellperion Monthly Ops Report - start/end live runner (ASCII only)
REM Called by launchers\monthly_ops_report_hidden.vbs (hidden window).
REM Arg %1 = start (month begin, day 1 09:00) or end (month last day 21:00).
REM Builds card from status\monthly_ops_plan.json (+ home_kpi sales for end),
REM sends Telegram card to GM, logs to status\monthly_ops_log.jsonl.
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\monthly_ops_report.py --mode %1 --send >> logs\monthly_ops_report.log 2>&1
