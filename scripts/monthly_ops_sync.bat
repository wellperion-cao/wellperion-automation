@echo off
REM Wellperion monthly-ops auto-sync (daily live) - ship 9678
REM Pulls real work/task SSOT status into monthly_ops_plan.json progress, then commits.
REM Gate: MONTHLY_SYNC_APPLY=1 (this file). Rollback = disable scheduled task.
cd /d C:\Users\jjky0\welperion-automation
set MONTHLY_SYNC_APPLY=1
C:\Python314\python.exe scripts\monthly_ops_sync.py --apply
if exist ".git\index.lock" goto :skipcommit
git add status/monthly_ops_plan.json
git commit -m "chore(coo): monthly-ops auto-sync daily (ship9678)"
:skipcommit
exit /b 0
