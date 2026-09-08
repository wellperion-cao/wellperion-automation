@echo off
REM Wellperion home-PC CLI setup launcher.
REM Double-click. Downloads home_pc_setup.ps1 from the ERP and runs it (it elevates itself).
REM Optional: drop the company config zip on this file to pass it through.
REM ASCII only on purpose (CP949 batch safety).
setlocal
set "SRC=https://erp.wellperion.com/erp/launchers/home_pc_setup.ps1"
set "PS1=%TEMP%\wellperion_home_pc_setup.ps1"

echo Downloading setup script...
curl -fsSL "%SRC%" -o "%PS1%"
if not exist "%PS1%" (
  echo Download failed. Check the internet connection and try again.
  pause
  exit /b 1
)

if "%~1"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -ConfigZip "%~1"
)
pause
