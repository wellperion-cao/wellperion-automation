@echo off
REM ============================================================
REM Wellperion - register daily_scheduler.py + bot.py as
REM Windows Scheduled Tasks (auto-start ON LOGON).
REM RUN AS ADMINISTRATOR (right click -> Run as administrator).
REM Current manual processes keep running; auto-start applies
REM from the next reboot/logon. ASCII only (no encoding issues).
REM ============================================================

cd /d "%~dp0"
SET SCRIPT_DIR=%~dp0
SET PYTHON_EXE=C:\Python314\python.exe
SET TASK_SCHED=WellperionDailyScheduler
SET TASK_BOT=WellperionTelegramBot

echo.
echo [1/2] Registering %TASK_SCHED% (daily_scheduler.py) ...
schtasks /Delete /TN "%TASK_SCHED%" /F 1>nul 2>nul
schtasks /Create /TN "%TASK_SCHED%" /TR "\"%PYTHON_EXE%\" \"%SCRIPT_DIR%daily_scheduler.py\"" /SC ONLOGON /DELAY 0001:00 /RL HIGHEST /F
if %ERRORLEVEL% EQU 0 (echo   OK: %TASK_SCHED% registered.) else (echo   FAIL: please Run as administrator.)

echo.
echo [2/2] Registering %TASK_BOT% (bot.py) ...
schtasks /Delete /TN "%TASK_BOT%" /F 1>nul 2>nul
schtasks /Create /TN "%TASK_BOT%" /TR "\"%PYTHON_EXE%\" \"%SCRIPT_DIR%bot.py\"" /SC ONLOGON /DELAY 0001:00 /RL HIGHEST /F
if %ERRORLEVEL% EQU 0 (echo   OK: %TASK_BOT% registered.) else (echo   FAIL: please Run as administrator.)

echo.
echo [Registered tasks]
schtasks /Query /TN "%TASK_SCHED%" /FO LIST 1>nul 2>nul && schtasks /Query /TN "%TASK_SCHED%" /FO LIST
schtasks /Query /TN "%TASK_BOT%" /FO LIST 1>nul 2>nul && schtasks /Query /TN "%TASK_BOT%" /FO LIST

echo.
echo Done. Both tasks will auto-start on next logon.
pause
