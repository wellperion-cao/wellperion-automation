@echo off
REM ops\home_pc_setup.bat - home PC: install the same Claude Code CLI environment as the office PC.
REM Double-click. Real work = home_pc_setup.ps1 (same folder). It elevates itself to admin.
REM Optional: pass the company config zip as the first argument.
REM   home_pc_setup.bat "C:\Users\me\Desktop\wellperion_claude_config.zip"
REM ASCII only on purpose (CP949 batch safety).
set "PS1=%~dp0home_pc_setup.ps1"
if not exist "%PS1%" (
  echo home_pc_setup.ps1 not found next to this file.
  pause
  exit /b 1
)
if "%~1"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -ConfigZip "%~1"
)
