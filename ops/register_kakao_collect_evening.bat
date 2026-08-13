@echo off
REM ============================================================
REM Wellperion - Register Kakao Evening Re-collect as Scheduled Task
REM Task: Wellperion-Kakao-Collect-Evening-1830 (DAILY 18:30)
REM
REM What it does:
REM   Launches kakao_collect_evening_hidden.vbs (hidden window) which runs
REM   scripts\kakao_collect_evening.bat: exports the MANAGER KakaoTalk room
REM   one more time in the evening. COLLECT ONLY - it never sends anything.
REM
REM Why (2026-08-13):
REM   The manager room was exported once a day at 07:30. Replies that arrive
REM   during working hours stayed invisible until the next morning. That day
REM   the facility manager answered 7 legal-inspection items between 16:29 and
REM   18:44, while the AI CEO was still reading the 13:05 snapshot and reported
REM   "no reply" to the GM. One extra evening read cuts the reply loop from a
REM   full day to half a day.
REM
REM Rollback: schtasks /Delete /TN "Wellperion-Kakao-Collect-Evening-1830" /F
REM
REM RUN AS ADMINISTRATOR (right-click -> Run as administrator).
REM ASCII only (no Korean - CP949 encoding safety).
REM ============================================================

SET ROOT=C:\Users\jjky0\welperion-automation
SET LAUNCHER=%ROOT%\launchers\kakao_collect_evening_hidden.vbs
SET TASK_NAME=Wellperion-Kakao-Collect-Evening-1830
SET RUN_USER=%USERDOMAIN%\%USERNAME%

echo.
echo [1/2] Removing old task if present ...
schtasks /Delete /TN "%TASK_NAME%" /F 1>nul 2>nul && echo   OK: old task removed. || echo   (skip) not present.

echo.
echo [2/2] Registering %TASK_NAME% (DAILY 18:30, hidden) ...
schtasks /Create /TN "%TASK_NAME%" /TR "wscript \"%LAUNCHER%\"" /SC DAILY /ST 18:30 /RU "%RUN_USER%" /IT /RL LIMITED /F
if %ERRORLEVEL% EQU 0 (
    echo   OK: %TASK_NAME% registered.
) else (
    echo   FAIL: please Run as administrator.
)

echo.
echo Done. Verify with:  schtasks /Query /TN "%TASK_NAME%"
