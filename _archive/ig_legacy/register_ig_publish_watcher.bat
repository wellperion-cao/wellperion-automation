@echo off
REM ============================================================
REM Wellperion - register IG approval->publish watcher as a
REM Windows Scheduled Task (auto-start ON LOGON, 120s polling).
REM RUN AS ADMINISTRATOR (right click -> Run as administrator).
REM GM clicks [approve] -> relay writes status=approved to GitHub
REM -> this watcher detects within ~2min -> auto-publishes to IG
REM -> updates queue + commit/push + telegram report.
REM ASCII only (no encoding issues).
REM ============================================================

SET ROOT=C:\Users\jjky0\welperion-automation
SET LAUNCHER=%ROOT%\start_ig_publish_watcher.bat
SET TASK_NAME=Wellperion-IG-Publish-Watcher

echo.
echo [1/1] Registering %TASK_NAME% ...
schtasks /Delete /TN "%TASK_NAME%" /F 1>nul 2>nul
schtasks /Create /TN "%TASK_NAME%" /TR "\"%LAUNCHER%\"" /SC ONLOGON /DELAY 0001:30 /RL HIGHEST /F
if %ERRORLEVEL% EQU 0 (echo   OK: %TASK_NAME% registered.) else (echo   FAIL: please Run as administrator.)

echo.
echo [Registered task]
schtasks /Query /TN "%TASK_NAME%" /FO LIST 1>nul 2>nul && schtasks /Query /TN "%TASK_NAME%" /FO LIST

echo.
echo Done. Watcher will auto-start on next logon (+90s).
echo To start NOW without reboot: run  schtasks /Run /TN "%TASK_NAME%"
pause
