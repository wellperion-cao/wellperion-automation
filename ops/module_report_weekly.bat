@echo off
REM ============================================================
REM Wellperion - Module Auto-Report (WEEKLY)
REM Calls module_reporter.py --cadence weekly (single run).
REM ASCII only (CP949 safety). Scheduled-task registration NOT done here.
REM ============================================================
setlocal
set PYTHONIOENCODING=utf-8
set ROOT=C:\Users\jjky0\welperion-automation
set PY=C:\Python314\python.exe
if not exist "%PY%" set PY=python

"%PY%" "%ROOT%\scripts\module_reporter.py" --cadence weekly
endlocal
