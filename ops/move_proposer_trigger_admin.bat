@echo off
:: ============================================================
:: move_proposer_trigger_admin.bat  (AI CTO, 2026-07-10)
:: RUN AS ADMINISTRATOR. Self-checks elevation.
:: Wellperion-AI-Learning-Proposer-Weekly task was registered under a
:: locked-down ACL (Set-ScheduledTask/Unregister-ScheduledTask/schtasks
:: all fail "Access is denied" from a non-elevated session — same class
:: of issue as reorg_tasks_admin.bat, memory: reference_powershell_scheduledtasks_limitation).
:: Only job: move its weekly trigger Monday 09:45 -> Sunday 10:00
:: (weekly self-review design, 2026-07-10). Action/vbs already updated
:: (launchers\ai_learning_proposer_hidden.vbs now runs --no-send).
:: Uses PowerShell Set-ScheduledTask (preserves interactive principal,
:: NO password prompt) instead of schtasks /Change (which hangs).
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
echo [OK] Running elevated. Moving proposer trigger Mon 09:45 -^> Sun 10:00 ...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$tr = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 10:00am; try { Set-ScheduledTask -TaskName 'Wellperion-AI-Learning-Proposer-Weekly' -Trigger $tr -ErrorAction Stop | Out-Null; Write-Host '  OK: trigger moved.' } catch { Write-Host ('  FAIL: '+$_.Exception.Message) }; $x = (Get-ScheduledTask -TaskName 'Wellperion-AI-Learning-Proposer-Weekly').Triggers[0]; Write-Host ('  now = '+$x.StartBoundary+' DaysOfWeek='+$x.DaysOfWeek)"
echo.
echo Done. The 'now' line above should read Sunday, StartBoundary time 10:00:00.
pause
exit /b 0
