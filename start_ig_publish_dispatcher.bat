@echo off
chcp 65001 >nul

REM ============================================================
REM IG approval -> local publish dispatcher launcher (07:30 batch)
REM Headful Instagram publisher MUST run in the logged-on user's
REM VISIBLE desktop session (NOT hidden vbs, NOT session 0).
REM This .bat is launched by the daily 07:30 scheduled task with
REM /IT (interactive) so a real desktop is present and Chromium
REM (headless=False) can render. Do NOT wrap this in a hidden vbs.
REM ASCII only (Korean comments break cmd on CP949 Windows).
REM ============================================================

set ROOT=C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
set PY=%ROOT%\.venv\Scripts\python.exe
set SCRIPT=%ROOT%\scripts\ig_publish_dispatcher.py
set LOGDIR=%ROOT%\logs

REM Load telegram token from .env (no stdout exposure, echo off)
for /f "usebackq tokens=1,* delims==" %%a in ("%ROOT%\telegram_bot\.env") do (
    if /i "%%a"=="TELEGRAM_BOT_TOKEN" set "TELEGRAM_BOT_TOKEN=%%b"
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

cd /d "%ROOT%"
echo [start_ig_publish_dispatcher] %DATE% %TIME% launch >> "%LOGDIR%\ig_publish_dispatcher.log"
"%PY%" -u "%SCRIPT%" >> "%LOGDIR%\ig_publish_dispatcher.log" 2>&1
echo [start_ig_publish_dispatcher] %DATE% %TIME% exit=%ERRORLEVEL% >> "%LOGDIR%\ig_publish_dispatcher.log"
