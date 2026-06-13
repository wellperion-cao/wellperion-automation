@echo off
REM ============================================================
REM Wellperion - register IG approval->publish DISPATCHER as a
REM Windows Scheduled Task: DAILY at 07:30, INTERACTIVE.
REM
REM Why interactive (not the old hidden/ONLOGON watcher):
REM   The Instagram publisher runs headful (headless=False), so it
REM   needs a VISIBLE desktop. A hidden vbs / session-0 task cannot
REM   render Chromium -> publish fails (today's failure cause #2).
REM   /IT = run only when the user is logged on, in their desktop.
REM   /RL LIMITED (not HIGHEST) so it shares the interactive desktop
REM   (elevated tasks can land on a separate secure desktop).
REM
REM At 07:30 every day this publishes whatever GM approved in M5
REM (review_queue.json status='approved') up to that moment.
REM
REM RUN AS ADMINISTRATOR (right click -> Run as administrator).
REM ASCII only (no encoding issues).
REM ============================================================

SET ROOT=C:\Users\jjky0\welperion-automation
SET LAUNCHER=%ROOT%\start_ig_publish_dispatcher.bat
SET TASK_NAME=Wellperion-IG-Publish-0730
SET RUN_USER=%USERDOMAIN%\%USERNAME%

echo.
echo [1/1] Registering %TASK_NAME% (DAILY 07:30, interactive) ...
schtasks /Delete /TN "%TASK_NAME%" /F 1>nul 2>nul
schtasks /Create /TN "%TASK_NAME%" /TR "\"%LAUNCHER%\"" /SC DAILY /ST 07:30 /RU "%RUN_USER%" /IT /RL LIMITED /F
if %ERRORLEVEL% EQU 0 (echo   OK: %TASK_NAME% registered.) else (echo   FAIL: please Run as administrator.)

echo.
echo [Registered task]
schtasks /Query /TN "%TASK_NAME%" /FO LIST /V 1>nul 2>nul && schtasks /Query /TN "%TASK_NAME%" /FO LIST

echo.
echo Done. Dispatcher runs daily at 07:30 ONLY while %RUN_USER% is logged on (visible desktop).
echo To test NOW (publishes approved items): schtasks /Run /TN "%TASK_NAME%"
echo To test logic only (no publish): "%ROOT%\.venv\Scripts\python.exe" "%ROOT%\scripts\ig_publish_dispatcher.py" --dry-run
pause
