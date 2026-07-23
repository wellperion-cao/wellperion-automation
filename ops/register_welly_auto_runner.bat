@echo off
REM ============================================================
REM Wellperion - Register Auto Runner as Scheduled Task (PROPOSAL ONLY)
REM Task: Wellperion-Welly-Auto-Runner-0730 (DAILY 07:30)
REM
REM What it does:
REM   Launches welly_auto_runner_hidden.vbs (hidden window) which runs
REM   scripts\welly_auto_runner.bat -> scripts\welly_auto_runner.py --clevel cto.
REM   Default = DRY-RUN (RUNNER_LIVE unset in the .bat). Registering this task
REM   is harmless on its own: it only starts producing dry-run selection logs
REM   at status\welly_auto_runner_log.jsonl until RUNNER_LIVE=1 is uncommented
REM   in scripts\welly_auto_runner.bat (separate GM go step).
REM
REM THIS SCRIPT IS NOT EXECUTED AUTOMATICALLY. GM must run it manually
REM (as administrator) to actually register the scheduled task.
REM bae237 phase3 design doc: docs\superpowers\specs\2026-07-13-welly-auto-runner-design.md SS7/SS9.
REM
REM Why hidden VBS (not /IT interactive): same pattern as
REM   ops\register_engagement_collect.bat / launchers\gm_aide_scan_hidden.vbs.
REM
REM RUN AS ADMINISTRATOR (right-click -> Run as administrator).
REM ASCII only (no Korean - CP949 encoding safety).
REM ============================================================

SET ROOT=C:\Users\jjky0\welperion-automation
SET LAUNCHER=%ROOT%\launchers\welly_auto_runner_hidden.vbs
SET TASK_NAME=Wellperion-Welly-Auto-Runner-0730
SET RUN_USER=%USERDOMAIN%\%USERNAME%

echo.
echo [1/3] Removing old task if present ...
schtasks /Delete /TN "%TASK_NAME%" /F 1>nul 2>nul && echo   OK: old task removed. || echo   (skip) not present.

echo.
echo [2/3] Registering %TASK_NAME% (DAILY 07:30, hidden) ...
schtasks /Create /TN "%TASK_NAME%" /TR "wscript \"%LAUNCHER%\"" /SC DAILY /ST 07:30 /RU "%RUN_USER%" /IT /RL LIMITED /F
if %ERRORLEVEL% EQU 0 (
    echo   OK: %TASK_NAME% registered.
) else (
    echo   FAIL: please Run as administrator.
)

echo.
echo [3/3] Registered task details:
schtasks /Query /TN "%TASK_NAME%" /FO LIST

echo.
echo Done. welly_auto_runner runs daily at 07:30 (DRY-RUN by default).
echo Live activation is a SEPARATE step: uncomment "set RUNNER_LIVE=1" in
echo scripts\welly_auto_runner.bat only after reviewing several dry-run logs.
echo Logs: %ROOT%\logs\welly_auto_runner.log
echo Selection log: %ROOT%\status\welly_auto_runner_log.jsonl
echo To test manually (always dry-run unless RUNNER_LIVE=1 is set in env):
echo   "C:\Python314\python.exe" "%ROOT%\scripts\welly_auto_runner.py" --clevel cto
echo To remove: schtasks /Delete /TN "%TASK_NAME%" /F
pause
