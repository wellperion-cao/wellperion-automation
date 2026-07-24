@echo off
REM Wellperion CMO Content Intake to Review Queue plus GM Card - ASCII only (CP949 safety).
REM ASCII only and NO redirection chars in REM lines: a bare gt sign inside REM is still
REM parsed as redirection by cmd and silently creates junk files (hit 2026-07-24).
REM Called by launchers\cmo_intake_to_review_hidden.vbs (hidden window).
REM Reads instructor content intake rows from the GAS endpoint, registers new ones into
REM review_queue.json with the intake-review status and sends one GM card each.
REM NEVER publishes: that status is outside both publish gates (see .py footer note).
setlocal
set PYTHONIOENCODING=utf-8
set ROOT=C:\Users\jjky0\welperion-automation
set PY=C:\Python314\python.exe
if not exist "%PY%" set PY=python
cd /d "%ROOT%"
echo ===== %DATE% %TIME% cmo-intake-to-review start ===== >> "%ROOT%\logs\cmo_intake_to_review.log"
"%PY%" "%ROOT%\scripts\cmo_intake_to_review.py" --once >> "%ROOT%\logs\cmo_intake_to_review.log" 2>&1
endlocal
