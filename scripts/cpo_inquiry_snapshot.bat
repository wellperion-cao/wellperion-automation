@echo off
REM Wellperion CPO Inquiry Snapshot (every 3 minutes) - ASCII only (CP949 safety).
REM Called by launchers\cpo_inquiry_snapshot_hidden.vbs (hidden window).
REM Read-only accelerator job - fetches member/lesson inquiry lists via GAS and
REM publishes status/inquiry_snapshot_member.json + status/inquiry_snapshot_lesson.json
REM for instant cold-load rendering in member/document.html. Fail-soft (never blocks
REM the live gviz/GAS re-verify path on the page - see design spec).
setlocal
set PYTHONIOENCODING=utf-8
set ROOT=C:\Users\jjky0\welperion-automation
set PY=C:\Python314\python.exe
if not exist "%PY%" set PY=python
cd /d "%ROOT%"
echo ===== %DATE% %TIME% cpo-inquiry-snapshot start ===== >> "%ROOT%\logs\cpo_inquiry_snapshot.log"
"%PY%" "%ROOT%\scripts\cpo_inquiry_snapshot.py" >> "%ROOT%\logs\cpo_inquiry_snapshot.log" 2>&1
REM Staff feedback watcher (2026-07-25 GM) - rides this 3-minute slot instead of a new
REM scheduled task. New staff feedback becomes a CPO ship immediately so nothing sits
REM unattended in the sheet. Fail-soft: never blocks the snapshot job above.
"%PY%" "%ROOT%\scripts\collectors\cpo_staff_feedback_watch.py" >> "%ROOT%\logs\cpo_staff_feedback_watch.log" 2>&1
endlocal
