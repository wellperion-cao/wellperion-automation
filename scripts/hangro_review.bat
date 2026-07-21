@echo off
REM Wellperion Hangro Review Brain (cron entry point) - ASCII only (CP949 safety).
REM Called by launchers\hangro_review_hidden.vbs (hidden window).
REM Default: --dry-run (safe report generation). Live mode requires GM approval.
REM Generates 오늘의 항로 checkpoint review and appends to status/_queue.json
setlocal
set PYTHONIOENCODING=utf-8
set ROOT=C:\Users\jjky0\welperion-automation
set PY=C:\Python314\python.exe
if not exist "%PY%" set PY=python
cd /d "%ROOT%"
echo ===== %DATE% %TIME% hangro-review start ===== >> "%ROOT%\logs\hangro_review.log"
"%PY%" "%ROOT%\scripts\hangro_review.py" --dry-run >> "%ROOT%\logs\hangro_review.log" 2>&1
endlocal
