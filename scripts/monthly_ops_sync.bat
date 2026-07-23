@echo off
REM Wellperion monthly-ops auto-sync (daily live) - ship 9678
REM Pulls real work/task SSOT status into monthly_ops_plan.json (advisory: sync.auto_value only), then commits.
REM Gate: MONTHLY_SYNC_APPLY=1 (this file). Rollback = disable scheduled task.
REM 2026-07-23 (siwoo truth-check): added run log + path-scoped commit.
REM   - No log before: a 07:00 run left zero evidence (task result 0 only proves wscript launched).
REM   - Bare "git commit" swept whatever else another process had staged in the shared index.
cd /d C:\Users\jjky0\welperion-automation
set MONTHLY_SYNC_APPLY=1
set LOGFILE=C:\Users\jjky0\welperion-automation\logs\monthly_ops_sync.log
echo. >> "%LOGFILE%"
echo ===== RUN %date% %time% ===== >> "%LOGFILE%"
C:\Python314\python.exe scripts\monthly_ops_sync.py --apply >> "%LOGFILE%" 2>&1
if exist ".git\index.lock" (
  echo [SKIP] index.lock present - commit skipped >> "%LOGFILE%"
  goto :skipcommit
)
git commit -m "chore(coo): monthly-ops auto-sync daily (ship9678)" -- status/monthly_ops_plan.json >> "%LOGFILE%" 2>&1
:skipcommit
echo ===== END %date% %time% ===== >> "%LOGFILE%"
exit /b 0
