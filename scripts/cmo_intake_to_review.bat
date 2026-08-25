@echo off
REM Wellperion CMO Content Intake to Review Queue plus GM Card - ASCII only (CP949 safety).
REM ASCII only and NO redirection chars in REM lines: a bare gt sign inside REM is still
REM parsed as redirection by cmd and silently creates junk files (hit 2026-07-24).
REM Called by launchers\cmo_intake_to_review_hidden.vbs (hidden window).
REM Reads instructor content intake rows from the GAS endpoint, registers new ones into
REM review_queue.json with the intake-review status and sends one GM card each.
REM The intake step itself NEVER publishes: its status is outside both publish gates
REM (see .py footer note). The publish sweep below is a separate step in the same run.
REM
REM 2026-08-25 (GM): approval and scheduled time must take effect right away, not once a
REM day. The publish watcher already honors both (empty publish_at means publish on
REM approval), but it only ran from ig\start_ig_series_producer.bat at 07:30, so an
REM approved post waited up to a day and several posts went out together in the morning.
REM This task already runs every 15 minutes, so the same watcher call rides along here
REM instead of getting its own scheduled task (promise L21: no new devices, reuse the
REM gate that already exists). Concurrent runs are safe: scripts\.publish.lock
REM serializes publishing, and the watcher only touches items GM has approved.
setlocal
set PYTHONIOENCODING=utf-8
set ROOT=C:\Users\jjky0\welperion-automation
set PY=C:\Python314\python.exe
if not exist "%PY%" set PY=python
cd /d "%ROOT%"
echo ===== %DATE% %TIME% cmo-intake-to-review start ===== >> "%ROOT%\logs\cmo_intake_to_review.log"
"%PY%" "%ROOT%\scripts\cmo_intake_to_review.py" --once >> "%ROOT%\logs\cmo_intake_to_review.log" 2>&1
REM The watcher drives a real browser, so it needs the venv interpreter that owns
REM playwright - the same one ig\start_ig_series_producer.bat uses. Plain python has no
REM playwright and would fail every 15 minutes with an import error.
set PUBPY=%ROOT%\.venv\Scripts\python.exe
if not exist "%PUBPY%" set PUBPY=%PY%
echo [ig_review_publish_watcher] %DATE% %TIME% launch >> "%ROOT%\logs\ig_review_publish_watcher.log"
"%PUBPY%" -u "%ROOT%\scripts\ig_review_publish_watcher.py" --once >> "%ROOT%\logs\ig_review_publish_watcher.log" 2>&1
echo [ig_review_publish_watcher] %DATE% %TIME% exit=%ERRORLEVEL% >> "%ROOT%\logs\ig_review_publish_watcher.log"
endlocal
