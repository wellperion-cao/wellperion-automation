@echo off
REM ============================================================
REM Wellperion - Register Engagement Collector as Scheduled Task
REM Task: Wellperion-Engagement-Collect-0930 (DAILY 09:30)
REM
REM What it does:
REM   Launches engagement_collect_hidden.vbs (hidden window) which
REM   runs ops\start_engagement_collect.bat to collect danggn + blog
REM   engagement metrics without login. Appends to logs\engagement_collect.log.
REM
REM Why hidden VBS (not /IT interactive):
REM   danggn and blog collectors use urllib/RSS - no browser session
REM   needed. VBS hidden launcher works fine in non-interactive context.
REM   /RL LIMITED to avoid UAC desktop isolation.
REM
REM RUN AS ADMINISTRATOR (right-click -> Run as administrator).
REM ASCII only (no Korean - CP949 encoding safety).
REM ============================================================

SET ROOT=C:\Users\jjky0\welperion-automation
SET LAUNCHER=%ROOT%\launchers\engagement_collect_hidden.vbs
SET TASK_NAME=Wellperion-Engagement-Collect-0930
SET RUN_USER=%USERDOMAIN%\%USERNAME%

echo.
echo [1/3] Removing old task if present ...
schtasks /Delete /TN "%TASK_NAME%" /F 1>nul 2>nul && echo   OK: old task removed. || echo   (skip) not present.

echo.
echo [2/3] Registering %TASK_NAME% (DAILY 09:30, hidden) ...
schtasks /Create /TN "%TASK_NAME%" /TR "wscript \"%LAUNCHER%\"" /SC DAILY /ST 09:30 /RU "%RUN_USER%" /IT /RL LIMITED /F
if %ERRORLEVEL% EQU 0 (
    echo   OK: %TASK_NAME% registered.
) else (
    echo   FAIL: please Run as administrator.
)

echo.
echo [3/3] Registered task details:
schtasks /Query /TN "%TASK_NAME%" /FO LIST

echo.
echo Done. Engagement collector runs daily at 09:30.
echo Collects: danggn (public HTML) + blog (RSS) - no login required.
echo Logs: %ROOT%\logs\engagement_collect.log
echo To test manually: "%ROOT%\.venv\Scripts\python.exe" "%ROOT%\scripts\engagement_collector.py" --channel danggn --dry-run
pause
