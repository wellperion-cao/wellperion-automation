@echo off
REM ============================================================================
REM morning_pipeline_session_hook.cmd
REM Called from the AI CEO Claude Code SessionStart hook.
REM Launches the morning pipeline (ceo_morning_pipeline.py) once per day,
REM detached in the background so it never blocks/delays session start.
REM
REM  - Non-blocking: "start /b" detaches the python run.
REM  - Once-per-day guard: --once-per-day. If today's marker
REM    status/morning_plans/YYYY-MM-DD.json already exists, the pipeline
REM    skips immediately (near-zero cost), so multiple sessions per day
REM    trigger only one real run.
REM  - Replaces the fixed 08:00 scheduled run; fires when the GM opens the CLI.
REM
REM Exit code: always 0 (must not break session start even on failure).
REM ASCII-only on purpose: avoids cmd.exe codepage mangling of comments.
REM ============================================================================
set "WORK=%USERPROFILE%\welperion-automation"
set "PY=C:\Python314\python.exe"
set "SCRIPT=%WORK%\wellperion-agents\scripts\ceo_morning_pipeline.py"
set "LOGDIR=%WORK%\wellperion-agents\logs"

if not exist "%PY%" exit /b 0
if not exist "%SCRIPT%" exit /b 0
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1

start "WP_MORNING_PIPELINE" /b /min cmd /c ""%PY%" "%SCRIPT%" --once-per-day >> "%LOGDIR%\morning_pipeline_session.log" 2>&1"

exit /b 0
