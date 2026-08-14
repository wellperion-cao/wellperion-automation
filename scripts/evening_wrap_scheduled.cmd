@echo off
REM ============================================================================
REM evening_wrap_scheduled.cmd
REM Called by Windows Scheduled Task: Wellperion-CEO-Evening-Wrap-2300-Live
REM Runs ceo_evening_wrap.py once per day at 23:00, synchronously (no start /b)
REM so the Task Scheduler can track exit code and retry on failure.
REM
REM  - Symmetric with morning_pipeline_session_hook.cmd (SessionStart) in pattern,
REM    but runs as a scheduled task, not a session hook, because SessionEnd does
REM    not fire when the PC shuts down at 23:30 (root cause: abrupt shutdown).
REM  - Once-per-day guard: --once-per-day skips if today's marker already exists.
REM
REM ASCII-only on purpose: avoids cmd.exe codepage mangling of comments.
REM ============================================================================
set "WORK=%USERPROFILE%\welperion-automation"
set "PY=C:\Python314\python.exe"
set "SCRIPT=%WORK%\wellperion-agents\scripts\ceo_evening_wrap.py"
set "LOGDIR=%WORK%\wellperion-agents\logs"

if not exist "%PY%" exit /b 0
if not exist "%SCRIPT%" exit /b 0
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1

"%PY%" "%SCRIPT%" --once-per-day >> "%LOGDIR%\evening_wrap_scheduled.log" 2>&1
exit /b %ERRORLEVEL%
