@echo off
:: ============================================================
:: reorg_tasks_admin.bat  (AI CTO, 2026-06-15, rev2)
:: RUN AS ADMINISTRATOR. This rev SELF-CHECKS elevation and
:: refuses to run (with a clear message) if not elevated -- that
:: is why rev1 left an empty result file (it was not elevated).
::   (A) Delete dead tasks (idempotent; 3 already removed, this
::       finishes Wellperion-CEO-Verify-Watcher which needs admin).
::   (B) Repoint IG producer task to the new ig\ path (needs admin).
:: ============================================================
net session >nul 2>&1
if %errorlevel% NEQ 0 (
  echo.
  echo [STOP] This window is NOT elevated.
  echo        Close it, then RIGHT-CLICK this file and choose
  echo        "Run as administrator". Press a key to close.
  echo.
  pause
  exit /b 1
)
echo [OK] Running elevated.
set ROOT=C:\Users\jjky0\welperion-automation
set RESULT=%~dp0reorg_tasks_result.txt
echo ===== reorg_tasks rev2 run %DATE% %TIME% ===== > "%RESULT%"

echo.
echo [A] Deleting dead tasks (idempotent) ...
call :del "CEO_DAILY_CLEVEL_CHECK"
call :del "\Welperion\CTO-008-MetaTokenRefresh"
call :del "\Welperion\CMO-001-Calendar-Dispatcher"
call :del "Wellperion-CEO-Verify-Watcher"

echo.
echo [B] Repointing IG producer to ig\ ...
schtasks /Change /TN "Wellperion-IG-Series-Produce-0730" /TR "\"%ROOT%\ig\start_ig_series_producer.bat\"" >>"%RESULT%" 2>&1
if %errorlevel% EQU 0 (echo   OK: IG-0730 repointed to ig\.) else (echo   FAIL: IG-0730 repoint - see result.txt)

echo.
echo [verify] IG-0730 current definition:
schtasks /Query /TN "Wellperion-IG-Series-Produce-0730" /FO LIST
echo.
echo Done. Full log in reorg_tasks_result.txt
pause
exit /b 0

:del
schtasks /Delete /TN %1 /F >>"%RESULT%" 2>&1 && echo   deleted %1 || echo   (skip/absent) %1
exit /b 0
