@echo off
REM ============================================================
REM Wellperion - register AI series PRODUCER as a Windows
REM Scheduled Task: DAILY at 07:30, INTERACTIVE.
REM
REM GM corrected design (2026-06-04): produce + review-card at
REM 07:30 (NOT 21:00 produce / NOT 07:30 dispatcher-publish).
REM
REM What it does at 07:30:
REM   Picks the next '기획예정' episode from
REM   instagram\_AI시리즈_로드맵.md, has Simo (headless claude)
REM   write its build_slides.py, builds the 6 slides, registers
REM   to the M5 review queue as '검수대기', auto-marks the roadmap
REM   row as '제작완료(자동생성)', and sends a Telegram card with
REM   [APPROVE]/[REJECT] buttons to GM.
REM   It NEVER publishes. Publishing happens ONLY when GM taps the
REM   Telegram [APPROVE] button -> bot pub: callback publishes that
REM   instant (no polling). No scheduled publish task.
REM
REM Why interactive (/IT, not hidden/session-0):
REM   It spawns `claude -p` (Simo) which needs the logged-on
REM   GM user's CLI auth/session. A hidden vbs / session-0 task
REM   cannot reach it. /RL LIMITED to share the interactive
REM   desktop (elevated tasks can land on a separate desktop).
REM
REM This SUPERSEDES Wellperion-IG-Series-Produce-2100 (disabled)
REM and Wellperion-IG-Publish-0730 (disabled, scheduled publish
REM is retired under the approve-to-publish design).
REM
REM RUN AS ADMINISTRATOR (right click -> Run as administrator).
REM ASCII only (no encoding issues).
REM ============================================================

SET ROOT=C:\Users\jjky0\welperion-automation
SET LAUNCHER=%ROOT%\ig\start_ig_series_producer.bat
SET TASK_NAME=Wellperion-IG-Series-Produce-0730
SET OLD_PRODUCE=Wellperion-IG-Series-Produce-2100
SET OLD_PUBLISH=Wellperion-IG-Publish-0730
SET OLD_WATCHER=Wellperion-IG-Publish-Watcher
SET RUN_USER=%USERDOMAIN%\%USERNAME%

echo.
echo [1/3] Deleting retired tasks (21:00 produce, 07:30 publish, publish-watcher) ...
schtasks /Delete /TN "%OLD_PRODUCE%" /F 1>nul 2>nul && echo   OK: %OLD_PRODUCE% deleted. || echo   (skip) %OLD_PRODUCE% not present.
schtasks /Delete /TN "%OLD_PUBLISH%" /F 1>nul 2>nul && echo   OK: %OLD_PUBLISH% deleted. || echo   (skip) %OLD_PUBLISH% not present.
schtasks /Delete /TN "%OLD_WATCHER%" /F 1>nul 2>nul && echo   OK: %OLD_WATCHER% deleted. || echo   (skip) %OLD_WATCHER% not present.

echo.
echo [2/3] Registering %TASK_NAME% (DAILY 07:30, interactive) ...
schtasks /Delete /TN "%TASK_NAME%" /F 1>nul 2>nul
schtasks /Create /TN "%TASK_NAME%" /TR "\"%LAUNCHER%\"" /SC DAILY /ST 07:30 /RU "%RUN_USER%" /IT /RL LIMITED /F
if %ERRORLEVEL% EQU 0 (echo   OK: %TASK_NAME% registered.) else (echo   FAIL: please Run as administrator.)

echo.
echo [3/3] Registered task:
schtasks /Query /TN "%TASK_NAME%" /FO LIST /V 1>nul 2>nul && schtasks /Query /TN "%TASK_NAME%" /FO LIST

echo.
echo Done. Producer runs daily at 07:30 ONLY while %RUN_USER% is logged on.
echo It produces the next episode, registers to M5 (검수대기), auto-marks the
echo roadmap row, and sends a Telegram [APPROVE] card - it NEVER publishes.
echo Publish = GM taps Telegram [APPROVE] -> bot publishes that instant (no polling).
echo To test selection only (no production): "%ROOT%\.venv\Scripts\python.exe" "%ROOT%\scripts\ig_series_producer.py" --plan-only
echo To dry-run (prompt preview, no headless call): "%ROOT%\.venv\Scripts\python.exe" "%ROOT%\scripts\ig_series_producer.py" --dry-run
pause
