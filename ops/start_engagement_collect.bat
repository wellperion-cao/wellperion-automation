@echo off
REM ============================================================
REM Wellperion - Engagement Collector runner (DAILY 09:30)
REM Collects danggn + blog engagement metrics (no login required).
REM Cafe / kakao are headful channels -> excluded (semi-manual).
REM
REM Steps:
REM   1. Collect danggn engagement -> log
REM   2. Collect blog   engagement -> log
REM   3. Commit + push the 3 engagement files via Python helper
REM      (scripts\commit_engagement.py handles Korean paths; git
REM       failures are non-fatal). NEVER git add -A.
REM
REM Launched headless via launchers\engagement_collect_hidden.vbs
REM ASCII ONLY - no Korean in this .bat (CP949 breaks Korean paths).
REM ============================================================

set ROOT=C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
set PY=%ROOT%\.venv\Scripts\python.exe
set SCRIPT=%ROOT%\scripts\engagement_collector.py
set COMMITTER=%ROOT%\scripts\commit_engagement.py
set LOGDIR=%ROOT%\logs
set LOGFILE=%LOGDIR%\engagement_collect.log

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

cd /d "%ROOT%"

echo [start_engagement_collect] %DATE% %TIME% START >> "%LOGFILE%"

REM ---- Step 1: danggn ----
"%PY%" -u "%SCRIPT%" --channel danggn >> "%LOGFILE%" 2>&1
echo [start_engagement_collect] %DATE% %TIME% danggn exit=%ERRORLEVEL% >> "%LOGFILE%"

REM ---- Step 2: blog ----
"%PY%" -u "%SCRIPT%" --channel blog >> "%LOGFILE%" 2>&1
echo [start_engagement_collect] %DATE% %TIME% blog exit=%ERRORLEVEL% >> "%LOGFILE%"

REM ---- Step 3: commit + push (Python, non-fatal) ----
"%PY%" -u "%COMMITTER%" >> "%LOGFILE%" 2>&1
echo [start_engagement_collect] %DATE% %TIME% commit exit=%ERRORLEVEL% >> "%LOGFILE%"

echo [start_engagement_collect] %DATE% %TIME% END >> "%LOGFILE%"
