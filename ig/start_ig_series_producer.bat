@echo off
chcp 65001 >nul

REM ============================================================
REM AI series "next episode" PRODUCER launcher (21:00 batch)
REM Produces the next planned episode (Simo headless) -> builds
REM slides -> registers to M5 review queue (status='검수대기').
REM NEVER publishes. Publish stays GM-approved (07:30 dispatcher).
REM
REM This calls a headless `claude -p` (Simo) to write the new
REM build_slides.py, so it must run as the logged-on GM user (so
REM the claude CLI auth/session is available). Launched by the
REM daily 21:00 scheduled task with /IT (interactive).
REM ASCII only (Korean comments break cmd on CP949 Windows).
REM ============================================================

set ROOT=C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
set PY=%ROOT%\.venv\Scripts\python.exe
set SCRIPT=%ROOT%\scripts\ig_series_producer.py
set LOGDIR=%ROOT%\logs

REM Load telegram token from .env (no stdout exposure, echo off)
for /f "usebackq tokens=1,* delims==" %%a in ("%ROOT%\telegram_bot\.env") do (
    if /i "%%a"=="TELEGRAM_BOT_TOKEN" set "TELEGRAM_BOT_TOKEN=%%b"
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

cd /d "%ROOT%"
echo [start_ig_series_producer] %DATE% %TIME% launch >> "%LOGDIR%\ig_series_producer.log"
"%PY%" -u "%SCRIPT%" >> "%LOGDIR%\ig_series_producer.log" 2>&1
echo [start_ig_series_producer] %DATE% %TIME% exit=%ERRORLEVEL% >> "%LOGDIR%\ig_series_producer.log"

REM ============================================================
REM 실전사례(namuk case series) dispatcher — GM go 2026-07-10.
REM No headless claude call (design doc: creation-code-free by
REM construction). Reads inventory table only, renders/registers/
REM sends review card. Coexists with producer above (separate
REM inventory source, no interference either way).
REM ============================================================
echo [case_series_dispatch] %DATE% %TIME% launch >> "%LOGDIR%\case_series_dispatch.log"
"%PY%" -u "%ROOT%\scripts\case_series_dispatch.py" >> "%LOGDIR%\case_series_dispatch.log" 2>&1
echo [case_series_dispatch] %DATE% %TIME% exit=%ERRORLEVEL% >> "%LOGDIR%\case_series_dispatch.log"

REM ============================================================
REM AI daily series (namuk personal, "AIDAY") one-card-a-day drip.
REM Weekday only, sends at most 1 review card from the AIDAY01~10
REM pre-registered queue. GM approves manually each morning.
REM ============================================================
echo [ai_daily_series_card] %DATE% %TIME% launch >> "%LOGDIR%\ai_daily_series_card.log"
"%PY%" -u "%ROOT%\scripts\ai_daily_series_card.py" >> "%LOGDIR%\ai_daily_series_card.log" 2>&1
echo [ai_daily_series_card] %DATE% %TIME% exit=%ERRORLEVEL% >> "%LOGDIR%\ai_daily_series_card.log"
