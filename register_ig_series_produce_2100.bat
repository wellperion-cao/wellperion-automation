@echo off
REM ============================================================
REM Wellperion - register AI series PRODUCER as a Windows
REM Scheduled Task: DAILY at 21:00, INTERACTIVE.
REM
REM What it does at 21:00 (the evening before):
REM   Picks the next '기획예정' episode from
REM   instagram\_AI시리즈_로드맵.md, has Simo (headless claude)
REM   write its build_slides.py, builds the 6 slides, and
REM   registers to the M5 review queue as '검수대기'.
REM   It NEVER publishes. GM reviews in M5 overnight/morning,
REM   approves, then the 07:30 dispatcher publishes next day.
REM
REM Why interactive (/IT, not hidden/session-0):
REM   It spawns `claude -p` (Simo) which needs the logged-on
REM   GM user's CLI auth/session. A hidden vbs / session-0 task
REM   cannot reach it. /RL LIMITED to share the interactive
REM   desktop (elevated tasks can land on a separate desktop).
REM
REM RUN AS ADMINISTRATOR (right click -> Run as administrator).
REM ASCII only (no encoding issues).
REM ============================================================

SET ROOT=C:\Users\jjky0\welperion-automation
SET LAUNCHER=%ROOT%\start_ig_series_producer.bat
SET TASK_NAME=Wellperion-IG-Series-Produce-2100
SET RUN_USER=%USERDOMAIN%\%USERNAME%

echo.
echo [1/1] Registering %TASK_NAME% (DAILY 21:00, interactive) ...
schtasks /Delete /TN "%TASK_NAME%" /F 1>nul 2>nul
schtasks /Create /TN "%TASK_NAME%" /TR "\"%LAUNCHER%\"" /SC DAILY /ST 21:00 /RU "%RUN_USER%" /IT /RL LIMITED /F
if %ERRORLEVEL% EQU 0 (echo   OK: %TASK_NAME% registered.) else (echo   FAIL: please Run as administrator.)

echo.
echo [Registered task]
schtasks /Query /TN "%TASK_NAME%" /FO LIST /V 1>nul 2>nul && schtasks /Query /TN "%TASK_NAME%" /FO LIST

echo.
echo Done. Producer runs daily at 21:00 ONLY while %RUN_USER% is logged on.
echo It produces the next episode and registers to M5 (검수대기) - it NEVER publishes.
echo To test selection logic only (no production): "%ROOT%\.venv\Scripts\python.exe" "%ROOT%\scripts\ig_series_producer.py" --plan-only
echo To dry-run (prompt preview, no headless call): "%ROOT%\.venv\Scripts\python.exe" "%ROOT%\scripts\ig_series_producer.py" --dry-run
pause
