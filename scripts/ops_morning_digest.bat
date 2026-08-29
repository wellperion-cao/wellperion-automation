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
REM 2026-08-15 (GM): added foursplit(★운영+시설+지원+주차)/dept(★부서장) - export+digest only.
REM 2026-08-20 (GM): reverted to 2 rooms - ops(★운영부) + mgr(★중간관리자) only.
REM   GM: "현재는 운영부 및 중간관리자방만 수집해서 정리해주면 될 것 같아."
REM   Measured that day: foursplit export last succeeded 08-17 and produced nothing since,
REM   dept export ran but its digest never went anywhere. Two rooms is what is actually read.
REM   Rollback = re-add the --room-key foursplit / dept lines (this commit).
"%PY%" "%ROOT%\scripts\kakao_export_chat.py" >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% kakao_export_chat
"%PY%" "%ROOT%\scripts\kakao_export_chat.py" --room-key mgr >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% kakao_export_chat
REM 2026-08-25 (GM): the hourly manager-room listener was removed; its work runs here once a
REM   morning instead. GM: "오전에만 하고, 어제 중간관리자 정리하는 것처럼만 진행하면 안될까?
REM   그때 웰리 불렀던 내용이 있으면 같이 정리해주면 좋을 것 같아."
REM   Measured before the change: 13 runs a day, 2 new calls in 4 days, and every run pulled the
REM   KakaoTalk window to the front for 5s. Export already happened on the line above, so this
REM   reads the archive file (no --export) - no extra window, no extra token.
REM   Rollback = re-create task Wellperion-Kakao-Room-Listen-Hourly (definition kept in
REM   status/_removed_tasks/ 2026-08-25) and drop this line.
REM   --since-days 2: once a day means a skipped run (PC off) would lose that day's calls.
REM   Two days of overlap costs nothing - already-seen calls are skipped by fingerprint.
"%PY%" "%ROOT%\scripts\kakao_room_listen.py" --since-days 2 >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% kakao_room_listen
"%PY%" "%ROOT%\scripts\ops_daily_digest.py" >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% ops_daily_digest
"%PY%" "%ROOT%\scripts\ops_daily_digest.py" --room-key mgr >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% ops_daily_digest
"%PY%" "%ROOT%\scripts\send_ops_digest.py" >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
if errorlevel 1 set FAILED=%FAILED% send_ops_digest
if not "%FAILED%"=="" goto :wpfailed
endlocal & exit /b 0
:wpfailed
REM 2026-08-30 (CTO): this line used to go to a console that nobody sees (wscript window style 0),
REM so a failed run left rc=1 in Task Scheduler with no record of WHICH step failed. Now it lands
REM in the same log as everything else.
echo ===== %DATE% %TIME% ops-morning-digest FAILED steps:%FAILED% ===== >> "%ROOT%\logs\ops_morning_digest.log"
endlocal & exit /b 1
