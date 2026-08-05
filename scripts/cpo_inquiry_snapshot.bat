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
REM Feedback-only live runner (2026-08-05 GM - "just process it right away?"). Bottleneck
REM measured was ship-creation -> processing-START (median 20.5h, only because the sole
REM executor was the once-daily 07:30 Wellperion-Welly-Auto-Runner-0730 task). Reuses that
REM same runner engine (welly_auto_runner.py --feedback-only) on THIS existing 3-min slot
REM instead of a new scheduled task. Scope is narrowed to staff-feedback ships only
REM (ship["from"]=="staff") - every other ship still waits for the 07:30 all-clevel cycle,
REM unchanged. All existing gates stay on unchanged: reversible-only, work_type=="new"
REM exclusion, ambiguity park, per-cycle cap (MAX_SHIPS_PER_CYCLE=3, own budget since this
REM is a separate process from the 07:30 cycle - not raised). Windows Task Scheduler's
REM MultipleInstancesPolicy=IgnoreNew on this task (verified via schtasks /XML) already
REM prevents overlapping claude sessions if one run is still mid-flight at the next tick -
REM no extra locking code needed. Fail-soft: never blocks the jobs above.
set RUNNER_LIVE=1
set RUNNER_PING_LIVE=1
"%PY%" "%ROOT%\scripts\welly_auto_runner.py" --clevel all --feedback-only >> "%ROOT%\logs\welly_auto_runner.log" 2>&1
endlocal
