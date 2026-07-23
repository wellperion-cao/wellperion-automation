@echo off
REM ============================================================
REM Wellperion - Register IG Reach Collector as Scheduled Task
REM Task: Wellperion-IG-Reach-Collect-0945 (DAILY 09:45, ship588)
REM
REM What it does:
REM   Launches ig_reach_collect_hidden.vbs (hidden window) which
REM   runs ops\start_ig_reach_collect.bat to collect @wellperion IG
REM   account+media reach (Graph API insights, read-only) and commit
REM   the ledger/summary. Appends to logs\ig_reach_collect.log.
REM
REM Why hidden VBS (not /IT interactive):
REM   Mirrors ops\register_engagement_collect.bat pattern - HTTPS
REM   API calls need no browser session. /RL LIMITED avoids UAC
REM   desktop isolation.
REM
REM RUN AS ADMINISTRATOR (right-click -> Run as administrator).
REM ASCII only (no Korean - CP949 encoding safety).
REM ============================================================

SET ROOT=C:\Users\jjky0\welperion-automation
SET LAUNCHER=%ROOT%\launchers\ig_reach_collect_hidden.vbs
SET TASK_NAME=Wellperion-IG-Reach-Collect-0945
SET RUN_USER=%USERDOMAIN%\%USERNAME%

echo.
echo [1/3] Removing old task if present ...
schtasks /Delete /TN "%TASK_NAME%" /F 1>nul 2>nul && echo   OK: old task removed. || echo   (skip) not present.

echo.
echo [2/3] Registering %TASK_NAME% (DAILY 09:45, hidden) ...
schtasks /Create /TN "%TASK_NAME%" /TR "wscript \"%LAUNCHER%\"" /SC DAILY /ST 09:45 /RU "%RUN_USER%" /IT /RL LIMITED /F
if %ERRORLEVEL% EQU 0 (
    echo   OK: %TASK_NAME% registered.
) else (
    echo   FAIL: please Run as administrator.
)

echo.
echo [3/3] Registered task details:
schtasks /Query /TN "%TASK_NAME%" /FO LIST

echo.
echo Done. IG reach collector runs daily at 09:45.
echo Collects: @wellperion account + recent media reach (Graph API insights).
echo Logs: %ROOT%\logs\ig_reach_collect.log
echo To test manually: C:\Python314\python.exe "%ROOT%\scripts\ig_reach_collector.py" --dry-run
pause
