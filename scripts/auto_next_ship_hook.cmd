@echo off
REM ============================================================================
REM auto_next_ship_hook.cmd
REM Called from the Claude Code "Stop" hook (all C-Level sessions).
REM Asks the existing selection gate whether a next ship is ready; if so the
REM session keeps going instead of idling for GM input (GM decision 2026-07-28,
REM option A). All the real logic lives in auto_next_ship_hook.py.
REM
REM  - stdin/stdout are passed straight through: the hook contract is JSON.
REM  - If anything is missing we print {"continue":true} so the session just
REM    stops as usual. A broken hook must never freeze a session.
REM  - Kill switch: create status\auto_continue.OFF (no code change needed).
REM ASCII-only on purpose: avoids cmd.exe codepage mangling of comments.
REM ============================================================================
set "WORK=%USERPROFILE%\welperion-automation"
set "PY=C:\Python314\python.exe"
set "SCRIPT=%WORK%\scripts\auto_next_ship_hook.py"

if not exist "%PY%" goto :justStop
if not exist "%SCRIPT%" goto :justStop

"%PY%" "%SCRIPT%"
exit /b 0

:justStop
echo {"continue":true}
exit /b 0
