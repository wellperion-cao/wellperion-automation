@echo off
:: ============================================================
:: reorg_tasks_admin.bat  (AI CTO, 2026-06-15, rev3)
:: RUN AS ADMINISTRATOR. Self-checks elevation.
:: Only job left: repoint IG-0730 producer to the ig\ path.
:: Uses PowerShell Set-ScheduledTask (preserves trigger +
:: interactive principal, NO password prompt) instead of
:: schtasks /Change (which prompts for a password and hangs).
:: The 4 dead tasks are already deleted.
:: ============================================================
net session >nul 2>&1
if %errorlevel% NEQ 0 (
  echo.
  echo [STOP] This window is NOT elevated.
  echo        Close it, RIGHT-CLICK this file, "Run as administrator".
  echo.
  pause
  exit /b 1
)
echo [OK] Running elevated. Repointing IG-0730 to ig\ ...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='C:\Users\jjky0\welperion-automation\ig\start_ig_series_producer.bat'; $a=New-ScheduledTaskAction -Execute $p; try { Set-ScheduledTask -TaskName 'Wellperion-IG-Series-Produce-0730' -Action $a -ErrorAction Stop | Out-Null; Write-Host '  OK: repointed.' } catch { Write-Host ('  FAIL: '+$_.Exception.Message) }; $x=(Get-ScheduledTask -TaskName 'Wellperion-IG-Series-Produce-0730').Actions[0]; Write-Host ('  now exec = '+$x.Execute)"
echo.
echo Done. The 'now exec' line above should end with \ig\start_ig_series_producer.bat
pause
exit /b 0
