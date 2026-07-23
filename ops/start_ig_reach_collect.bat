@echo off
REM ============================================================
REM Wellperion - IG Reach Collector runner (DAILY 09:45, ship588)
REM Collects @wellperion IG account daily reach + recent media
REM reach via Graph API (read-only insights, no publish/edit),
REM then commits+pushes the ledger/summary (never git add -A).
REM
REM Steps:
REM   1. Collect IG reach -> scripts\ig_reach_collector.py
REM      (BLOCKED/no-op if IG_ACCESS_TOKEN missing or expired -
REM      non-fatal, logs only)
REM   2. Commit + push reach ledger/summary (scripts\commit_ig_reach.py,
REM      git failures non-fatal)
REM
REM Launched headless via launchers\ig_reach_collect_hidden.vbs
REM ASCII ONLY - no Korean in this .bat (CP949 breaks Korean paths).
REM ============================================================

set ROOT=C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
set PY=C:\Python314\python.exe
set SCRIPT=%ROOT%\scripts\ig_reach_collector.py
set COMMITTER=%ROOT%\scripts\commit_ig_reach.py
set LOGDIR=%ROOT%\logs
set LOGFILE=%LOGDIR%\ig_reach_collect.log

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

cd /d "%ROOT%"

echo [start_ig_reach_collect] %DATE% %TIME% START

REM ---- Step 1: IG reach (read-only, non-fatal if token missing/expired) ----
"%PY%" -u "%SCRIPT%"
echo [start_ig_reach_collect] %DATE% %TIME% reach exit=%ERRORLEVEL%

REM ---- Step 2: commit + push (Python, non-fatal) ----
"%PY%" -u "%COMMITTER%"
echo [start_ig_reach_collect] %DATE% %TIME% commit exit=%ERRORLEVEL%

echo [start_ig_reach_collect] %DATE% %TIME% END
