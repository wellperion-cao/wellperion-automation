@echo off
REM Wellperion - Ops Kakao Export 21:30 (weekday) / 19:30 (weekend): export room only, no digest/send.
REM Same command the 07:30 morning digest uses for the ops room (scripts\kakao_export_chat.py, default room = op room).
REM Purpose: let the evening report_stream_1 (22:30/20:00) see today's membership-share message
REM instead of waiting for tomorrow's 07:30 export (ship988, GM 2026-09-04, CPO handoff via queue 988 note).
setlocal
set PYTHONIOENCODING=utf-8
set ROOT=C:\Users\jjky0\welperion-automation
set PY=C:\Python314\python.exe
if not exist "%PY%" set PY=python
cd /d "%ROOT%"
echo ===== %DATE% %TIME% ops-kakao-export-2130 start ===== >> "%ROOT%\logs\ops_kakao_export_2130.log"
"%PY%" "%ROOT%\scripts\kakao_export_chat.py" >> "%ROOT%\logs\ops_kakao_export_2130.log" 2>&1
if errorlevel 1 (
  echo ===== %DATE% %TIME% ops-kakao-export-2130 FAILED ===== >> "%ROOT%\logs\ops_kakao_export_2130.log"
  endlocal & exit /b 1
)
endlocal & exit /b 0
