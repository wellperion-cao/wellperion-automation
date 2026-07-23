@echo off
REM ============================================================================
REM evening_wrap_session_hook.cmd
REM Called from the AI CEO Claude Code SessionEnd hook.
REM Launches the evening wrap-up (ceo_evening_wrap.py) once per day, detached
REM in the background so it never blocks/delays session shutdown.
REM
REM  - Non-blocking: "start /b" detaches the python run (session ends instantly).
REM  - Once-per-day guard: --once-per-day. If today's marker
REM    status/evening_wraps/YYYY-MM-DD.json already exists, the wrap skips
REM    immediately (near-zero cost), so closing/reopening the CLI several times
REM    a day still triggers only one real end-of-day report.
REM  - Symmetric with morning_pipeline_session_hook.cmd (SessionStart).
REM
REM Exit code: always 0 (must not break session shutdown even on failure).
REM ASCII-only on purpose: avoids cmd.exe codepage mangling of comments.
REM ============================================================================
set "WORK=%USERPROFILE%\welperion-automation"
set "PY=C:\Python314\python.exe"
set "SCRIPT=%WORK%\wellperion-agents\scripts\ceo_evening_wrap.py"
set "LOGDIR=%WORK%\wellperion-agents\logs"

if not exist "%PY%" exit /b 0
if not exist "%SCRIPT%" exit /b 0
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1

start "WP_EVENING_WRAP" /b /min cmd /c ""%PY%" "%SCRIPT%" --once-per-day >> "%LOGDIR%\evening_wrap_session.log" 2>&1"

exit /b 0
