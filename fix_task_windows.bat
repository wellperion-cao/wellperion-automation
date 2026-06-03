@echo off
REM ============================================================
REM Wellperion - hide scheduled-task black windows (A-plan)
REM Double-click this file. It self-elevates (UAC prompt = Yes).
REM Re-points bot/scheduler/IG-watcher/morning-update to hidden
REM launchers, disables the orphan CEO-Verify task, and restarts
REM the daemons so the windows disappear right now.
REM ASCII only (Korean breaks .bat on CP949 Windows).
REM ============================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator privileges...
  powershell -Command "Start-Process '%~f0' -Verb RunAs"
  exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\jjky0\welperion-automation\scripts\fix_task_windows.ps1"
