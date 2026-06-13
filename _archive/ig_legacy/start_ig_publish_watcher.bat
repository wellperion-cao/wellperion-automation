@echo off
chcp 65001 >nul

REM ============================================================
REM IG approval -> auto publish watcher launcher (CMO Phase 2)
REM GM clicks [approve] -> relay writes status=approved to GitHub
REM -> this watcher polls every 120s -> publishes -> commit/push
REM -> telegram report. ONLOGON scheduled, ends on PC shutdown.
REM ASCII only (Korean comments break cmd on CP949 Windows).
REM ============================================================

set ROOT=C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
set PY=%ROOT%\.venv\Scripts\python.exe
set SCRIPT=%ROOT%\scripts\ig_review_publish_watcher.py
set LOGDIR=%ROOT%\logs

REM Load telegram token from .env (no stdout exposure, echo off)
for /f "usebackq tokens=1,* delims==" %%a in ("%ROOT%\telegram_bot\.env") do (
    if /i "%%a"=="TELEGRAM_BOT_TOKEN" set "TELEGRAM_BOT_TOKEN=%%b"
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

cd /d "%ROOT%"
echo [start_ig_publish_watcher] %DATE% %TIME% launch >> "%LOGDIR%\ig_publish_watcher.log"
"%PY%" -u "%SCRIPT%" --interval 120 >> "%LOGDIR%\ig_publish_watcher.log" 2>&1
