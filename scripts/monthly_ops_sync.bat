@echo off
REM Wellperion monthly-ops auto-sync (daily live) - ship 9678
REM Pulls real work/task SSOT status into monthly_ops_plan.json, then commits.
REM Gate: MONTHLY_SYNC_APPLY=1 (this file). Rollback = disable scheduled task.
REM 2026-07-23 (siwoo truth-check): added run log + path-scoped commit.
REM   - No log before: a 07:00 run left zero evidence (task result 0 only proves wscript launched).
REM 2026-07-24 (GM fix): commit is now owned by monthly_ops_sync.py itself, via safe_commit.py
REM   with retry-on-lock (5s x 12 tries) - the old bare "git commit" here used to silently
REM   skip on .git\index.lock and lose that day's sync with zero visible failure signal.
cd /d C:\Users\jjky0\welperion-automation
set MONTHLY_SYNC_APPLY=1
set LOGFILE=C:\Users\jjky0\welperion-automation\logs\monthly_ops_sync.log
echo. >> "%LOGFILE%"
echo ===== RUN %date% %time% ===== >> "%LOGFILE%"
C:\Python314\python.exe scripts\monthly_ops_sync.py --apply >> "%LOGFILE%" 2>&1
echo ===== END %date% %time% ===== >> "%LOGFILE%"
exit /b 0
