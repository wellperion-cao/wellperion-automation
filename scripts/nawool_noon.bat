@echo off
REM Wellperion - noon unreplied digest for 나우열M (ship 2541). Weekdays 12:10 via Task Scheduler.
REM Sends one message to the Telegram work room from the GM account. Same-day duplicate is blocked
REM inside send_ops_digest.py by a heartbeat, so a manual re-run is safe.
REM ASCII only (this file is read as CP949; Korean here reaches the child process mangled).
setlocal
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set ROOT=%USERPROFILE%\welperion-automation
set PY=C:\Python314\python.exe
if not exist "%PY%" set PY=python
cd /d "%ROOT%"
echo ===== %DATE% %TIME% nawool-noon start ===== >> "%ROOT%\logs\nawool_noon.log"
"%PY%" "%ROOT%\scripts\send_ops_digest.py" --nawool-noon >> "%ROOT%\logs\nawool_noon.log" 2>&1
set RC=%ERRORLEVEL%
echo ===== %DATE% %TIME% nawool-noon end rc=%RC% ===== >> "%ROOT%\logs\nawool_noon.log"
endlocal & exit /b %RC%
