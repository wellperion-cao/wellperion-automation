@echo off
REM ============================================================
REM Wellperion - Register Ops Morning Digest as Scheduled Task
REM Task: Wellperion-Ops-Morning-Digest-0800 (DAILY 08:00)
REM
REM What it does:
REM   Launches ops_morning_pipeline_hidden.vbs (hidden window) which runs
REM   scripts\ops_morning_pipeline.bat: exports the OperationsDept KakaoTalk
REM   chat -> AI digest -> sends a GM Telegram approval card.
REM   Room send NEVER happens automatically - only after GM taps the
REM   approval button (handled by telegram_bot\bot.py opsdig: callback).
REM
REM NOT executed automatically by any agent/AI. GM/CTO must review and run
REM this file manually (as Administrator) only after confirming the
REM pipeline is verified live (kakao export + telegram approval + room
REM send gate all tested end to end).
REM
REM RUN AS ADMINISTRATOR (right-click -> Run as administrator).
REM ASCII only (no Korean - CP949 encoding safety).
REM ============================================================

SET ROOT=C:\Users\jjky0\welperion-automation
SET LAUNCHER=%ROOT%\launchers\ops_morning_pipeline_hidden.vbs
SET TASK_NAME=Wellperion-Ops-Morning-Digest-0800
SET RUN_USER=%USERDOMAIN%\%USERNAME%

echo.
echo [1/3] Removing old task if present ...
schtasks /Delete /TN "%TASK_NAME%" /F 1>nul 2>nul && echo   OK: old task removed. || echo   (skip) not present.

echo.
echo [2/3] Registering %TASK_NAME% (DAILY 08:00, hidden) ...
schtasks /Create /TN "%TASK_NAME%" /TR "wscript \"%LAUNCHER%\"" /SC DAILY /ST 08:00 /RU "%RUN_USER%" /IT /RL LIMITED /F
if %ERRORLEVEL% EQU 0 (
    echo   OK: %TASK_NAME% registered.
) else (
    echo   FAIL: please Run as administrator.
)

echo.
echo [3/3] Registered task details:
schtasks /Query /TN "%TASK_NAME%" /FO LIST

echo.
echo Done. Ops morning digest will run daily at 08:00.
echo Room send is gated behind GM Telegram button approval (bot.py opsdig: handler).
echo Logs: %ROOT%\logs\ops_morning_pipeline.log
echo To test manually (no live kakao/telegram send): "%ROOT%\.venv\Scripts\python.exe" "%ROOT%\scripts\ops_morning_pipeline.py" --dry-run
pause
