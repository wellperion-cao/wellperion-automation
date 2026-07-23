@echo off
REM ============================================================
REM Wellperion - Register IG Token Refresh as Scheduled Task
REM Task: Wellperion-IG-Token-Refresh-Weekly (WEEKLY MON 06:10, ship588)
REM
REM What it does:
REM   Launches ig_token_refresh_hidden.vbs (hidden window) which runs
REM   scripts\ig_token_refresh.bat -> scripts\ig_token_refresh.py to
REM   refresh the 60-day IG long-lived access token (Meta allows
REM   refresh any time >=24h after issuance; refreshing resets the
REM   60-day clock, so weekly keeps it perpetually valid with wide
REM   margin). Updates scripts\.env in place (gitignored, no commit).
REM   On failure, sends an OWNER Telegram alert.
REM
REM RUN AS ADMINISTRATOR (right-click -> Run as administrator).
REM ASCII only (no Korean - CP949 encoding safety).
REM ============================================================

SET ROOT=C:\Users\jjky0\welperion-automation
SET LAUNCHER=%ROOT%\launchers\ig_token_refresh_hidden.vbs
SET TASK_NAME=Wellperion-IG-Token-Refresh-Weekly
SET RUN_USER=%USERDOMAIN%\%USERNAME%

echo.
echo [1/3] Removing old task if present ...
schtasks /Delete /TN "%TASK_NAME%" /F 1>nul 2>nul && echo   OK: old task removed. || echo   (skip) not present.

echo.
echo [2/3] Registering %TASK_NAME% (WEEKLY MON 06:10, hidden) ...
schtasks /Create /TN "%TASK_NAME%" /TR "wscript \"%LAUNCHER%\"" /SC WEEKLY /D MON /ST 06:10 /RU "%RUN_USER%" /IT /RL LIMITED /F
if %ERRORLEVEL% EQU 0 (
    echo   OK: %TASK_NAME% registered.
) else (
    echo   FAIL: please Run as administrator.
)

echo.
echo [3/3] Registered task details:
schtasks /Query /TN "%TASK_NAME%" /FO LIST

echo.
echo Done. IG token refresh runs weekly (Monday 06:10).
echo Refreshes: scripts\.env IG_ACCESS_TOKEN (60-day token, rolling).
echo Logs: %ROOT%\logs\ig_token_refresh.log
echo On failure: OWNER Telegram alert (telegram_bot\.env OWNER_ID).
echo To test manually: C:\Python314\python.exe "%ROOT%\scripts\ig_token_refresh.py" --dry-run
pause
