@echo off
REM Wellperion L-Series Daily Reservation Card (08:45) - ASCII only (CP949 safety).
REM Called by launchers\lesson_series_daily_card_hidden.vbs (hidden window).
REM Sends today's scheduled L-series review card only. NEVER approves or publishes
REM (publish stays 100% gated on GM's manual telegram approval tap).
setlocal
set PYTHONIOENCODING=utf-8
set ROOT=C:\Users\jjky0\welperion-automation
set PY=C:\Python314\python.exe
if not exist "%PY%" set PY=python
cd /d "%ROOT%"
echo ===== %DATE% %TIME% lesson-series-daily-card start ===== >> "%ROOT%\logs\lesson_series_daily_card.log"
"%PY%" "%ROOT%\scripts\lesson_series_daily_card.py" >> "%ROOT%\logs\lesson_series_daily_card.log" 2>&1
endlocal
