@echo off
:: ============================================================
:: reorg_tasks_admin.bat  (AI CTO, 2026-06-15)
:: One-shot. RUN AS ADMINISTRATOR (right click -> Run as administrator).
:: Reconciles Windows scheduled tasks with the ops/ ig/ .bat reorg:
::   (A) Delete 4 dead tasks (ghost audit 2026-06-13).
::   (B) Repoint IG producer task to the new ig\ path.
:: Idempotent: re-runnable, skips absent tasks.
:: ============================================================
chcp 65001 >nul
set ROOT=C:\Users\jjky0\welperion-automation
set RUN_USER=%USERDOMAIN%\%USERNAME%
set RESULT=%~dp0reorg_tasks_result.txt
echo ===== reorg_tasks run %DATE% %TIME% ===== > "%RESULT%"

echo.
echo [A] Deleting 4 dead tasks ...
for %%T in ("CEO_DAILY_CLEVEL_CHECK" "Wellperion-CEO-Verify-Watcher" "\Welperion\CTO-008-MetaTokenRefresh" "\Welperion\CMO-001-Calendar-Dispatcher") do (
  schtasks /Delete /TN %%T /F 1>>"%RESULT%" 2>&1 && echo   OK deleted %%T || echo   (skip) %%T not present
)

echo.
echo [B] Repoint IG producer to ig\ ...
set IGTASK=Wellperion-IG-Series-Produce-0730
set IGLAUNCHER=%ROOT%\ig\start_ig_series_producer.bat
schtasks /Delete /TN "%IGTASK%" /F 1>nul 2>nul
schtasks /Create /TN "%IGTASK%" /TR "\"%IGLAUNCHER%\"" /SC DAILY /ST 07:30 /RU "%RUN_USER%" /IT /RL LIMITED /F 1>>"%RESULT%" 2>&1
if %ERRORLEVEL% EQU 0 (echo   OK: %IGTASK% repointed to ig\) else (echo   FAIL: please Run as administrator.)

echo.
echo [verify] >> "%RESULT%"
schtasks /Query /TN "%IGTASK%" /FO LIST 1>nul 2>nul && schtasks /Query /TN "%IGTASK%" /FO LIST >> "%RESULT%"
type "%RESULT%"
echo.
echo Done. Review reorg_tasks_result.txt. Deleted 4 dead tasks; IG producer now runs from ig\.
pause
