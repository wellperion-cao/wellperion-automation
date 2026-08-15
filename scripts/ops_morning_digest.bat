@echo off
REM Wellperion - Ops Morning Digest (07:30): export kakao chat -> build digest -> send (gated). ASCII only (CP949 safety).
REM Send is gated by status/ops_digest_send.json {"enabled":bool}. Rollback = set false.
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
cd /d "%ROOT%"
echo ===== %DATE% %TIME% ops-morning-digest start ===== >> "%ROOT%\logs\ops_morning_digest.log"
REM Room names are passed as ASCII aliases (--room-key ops|mgr|foursplit|dept). Korean text inside
REM this .bat is read as CP949 and reaches the child process mangled - that silently broke the
REM manager room export every morning until 2026-08-12. Alias table = scripts/kakao_rooms.json
REM room_aliases (single SSOT - ops_daily_digest.py and kakao_export_chat.py both read it).
REM 2026-08-15 (GM): added foursplit(★운영+시설+지원+주차)/dept(★부서장) - export+digest only,
REM no send step (send_ops_digest.py stays ★운영부-only/gated - these two are collect+summarize).
"%PY%" "%ROOT%\scripts\kakao_export_chat.py" >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% kakao_export_chat
"%PY%" "%ROOT%\scripts\kakao_export_chat.py" --room-key mgr >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% kakao_export_chat
"%PY%" "%ROOT%\scripts\kakao_export_chat.py" --room-key foursplit >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% kakao_export_chat
"%PY%" "%ROOT%\scripts\kakao_export_chat.py" --room-key dept >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% kakao_export_chat
"%PY%" "%ROOT%\scripts\ops_daily_digest.py" >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% ops_daily_digest
"%PY%" "%ROOT%\scripts\ops_daily_digest.py" --room-key mgr >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% ops_daily_digest
"%PY%" "%ROOT%\scripts\ops_daily_digest.py" --room-key foursplit >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% ops_daily_digest
"%PY%" "%ROOT%\scripts\ops_daily_digest.py" --room-key dept >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% ops_daily_digest
"%PY%" "%ROOT%\scripts\send_ops_digest.py" >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% send_ops_digest
if not "%FAILED%"=="" goto :wpfailed
endlocal & exit /b 0
:wpfailed
echo ===== %DATE% %TIME% ops-morning-digest FAILED steps:%FAILED% =====
endlocal & exit /b 1
