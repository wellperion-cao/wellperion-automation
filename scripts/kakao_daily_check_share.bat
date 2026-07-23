@echo off
REM Wellperion - Daily Check-Status Kakao Share (23:00). ASCII only (CP949 safety).
setlocal
set PYTHONIOENCODING=utf-8
set ROOT=C:\Users\jjky0\welperion-automation
set PY=C:\Python314\python.exe
if not exist "%PY%" set PY=python
cd /d "%ROOT%"
"%PY%" "%ROOT%\scripts\kakao_daily_check_share.py" >> "%ROOT%\logs\kakao_daily_check_share.log" 2>&1
endlocal
