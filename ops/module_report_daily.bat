@echo off
REM ============================================================
REM Wellperion - Module Auto-Report (ALL cadences - auto by date)
REM Calls module_reporter.py --cadence auto (single run).
REM ASCII only (CP949 safety). Scheduled-task registration NOT done here.
REM ============================================================
REM 2026-08-14 (ship 624): each python call's exit code is now remembered. Before this only
REM the LAST call's code survived, so Task Scheduler showed rc=0 on runs where a step had
REM actually failed. Fail-soft is unchanged - a failed step still does not stop the ones
REM after it; the task just ends non-zero so the failure is visible.
setlocal
set FAILED=
set PYTHONIOENCODING=utf-8
set ROOT=C:\Users\jjky0\welperion-automation
set PY=C:\Python314\python.exe
if not exist "%PY%" set PY=python

"%PY%" "%ROOT%\scripts\module_reporter.py" --cadence auto
if errorlevel 1 set FAILED=%FAILED% module_reporter

REM Voyage map (status/voyage_map.json) - feeds the northstar-progress view on
REM the autonomy page. 2026-08-03: it had no scheduler at all, so it went stale
REM for 9 days until someone ran it by hand. Attached to this existing daily job
REM instead of adding a new scheduled task. Runs last so a failure here cannot
REM affect the module report above.
"%PY%" "%ROOT%\scripts\build_voyage_map.py"
if errorlevel 1 set FAILED=%FAILED% build_voyage_map
if not "%FAILED%"=="" goto :wpfailed
endlocal & exit /b 0
:wpfailed
echo ===== %DATE% %TIME% module-report-daily FAILED steps:%FAILED% =====
endlocal & exit /b 1
