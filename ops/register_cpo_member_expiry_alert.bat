@echo off
REM ============================================================
REM Wellperion - Register Member Expiry Alert as Scheduled Task (PROPOSAL ONLY)
REM Task: Wellperion-CPO-MemberExpiry-Monthly-4thMon-1000 (MONTHLY, 4th Monday, 10:00)
REM
REM What it does:
REM   Launches launchers\member_expiry_alert_hidden.vbs (hidden window) which runs
REM   scripts\member_expiry_alert.bat -> scripts\member_expiry_alert.py --send.
REM   Every month on the 4th Monday at 10:00, sends the next-calendar-month
REM   membership-expiry alert to GM personal chat ONLY (8254867551, hardcoded in
REM   member_expiry_alert.py GM_CHAT_ID - no other chat_id accepted). Staff-room
REM   delivery is a SEPARATE future step requiring explicit GM go-ahead.
REM
REM Why 4th Monday: matches the re-registration guideline cadence (GM/CPO 2026-07-20,
REM   status\_queue.json ship9253) - week 3-4 of the current month = analysis/contact
REM   window before next month's 1-10 day re-registration processing window.
REM
REM THIS SCRIPT IS NOT EXECUTED AUTOMATICALLY. GM must run it manually
REM (as administrator) to actually register the scheduled task.
REM
REM Why hidden VBS (not /IT interactive): same pattern as
REM   ops\register_weekly_page_hygiene.bat / launchers\weekly_page_hygiene_hidden.vbs.
REM
REM RUN AS ADMINISTRATOR (right-click -> Run as administrator).
REM ASCII only (no Korean - CP949 encoding safety).
REM ============================================================

SET ROOT=C:\Users\jjky0\welperion-automation
SET LAUNCHER=%ROOT%\launchers\member_expiry_alert_hidden.vbs
SET TASK_NAME=Wellperion-CPO-MemberExpiry-Monthly-4thMon-1000
SET RUN_USER=%USERDOMAIN%\%USERNAME%

echo.
echo [1/3] Removing old task if present ...
schtasks /Delete /TN "%TASK_NAME%" /F 1>nul 2>nul && echo   OK: old task removed. || echo   (skip) not present.

echo.
echo [2/3] Registering %TASK_NAME% (MONTHLY, 4th Monday, 10:00, hidden) ...
schtasks /Create /TN "%TASK_NAME%" /TR "wscript \"%LAUNCHER%\"" /SC MONTHLY /MO FOURTH /D MON /ST 10:00 /RU "%RUN_USER%" /IT /RL LIMITED /F
if %ERRORLEVEL% EQU 0 (
    echo   OK: %TASK_NAME% registered.
) else (
    echo   FAIL: please Run as administrator.
)

echo.
echo [3/3] Registered task details:
schtasks /Query /TN "%TASK_NAME%" /FO LIST

echo.
echo Done. member_expiry_alert runs every 4th Monday at 10:00, sends to GM personal
echo chat only (8254867551). Staff-room delivery requires a separate GM go-ahead step.
echo Logs: %ROOT%\logs\member_expiry_alert.log
echo To test manually (no send): "C:\Python314\python.exe" "%ROOT%\scripts\member_expiry_alert.py"
echo To test manually (send to GM chat): "C:\Python314\python.exe" "%ROOT%\scripts\member_expiry_alert.py" --send
echo To remove: schtasks /Delete /TN "%TASK_NAME%" /F
pause
