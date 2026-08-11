@echo off
REM Wellperion - Ops Morning Digest (07:30): export kakao chat -> build digest -> send (gated). ASCII only (CP949 safety).
REM Send is gated by status/ops_digest_send.json {"enabled":bool}. Rollback = set false.
setlocal
set PYTHONIOENCODING=utf-8
set ROOT=C:\Users\jjky0\welperion-automation
set PY=C:\Python314\python.exe
if not exist "%PY%" set PY=python
cd /d "%ROOT%"
echo ===== %DATE% %TIME% ops-morning-digest start ===== >> "%ROOT%\logs\ops_morning_digest.log"
REM Room names are passed as ASCII aliases (--room-key ops|mgr). Korean text inside this .bat
REM is read as CP949 and reaches the child process mangled - that silently broke the manager
REM room export every morning until 2026-08-12. Alias table lives in ops_daily_digest.ROOM_KEYS.
"%PY%" "%ROOT%\scripts\kakao_export_chat.py" >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
"%PY%" "%ROOT%\scripts\kakao_export_chat.py" --room-key mgr >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
"%PY%" "%ROOT%\scripts\ops_daily_digest.py" >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
"%PY%" "%ROOT%\scripts\ops_daily_digest.py" --room-key mgr >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
"%PY%" "%ROOT%\scripts\send_ops_digest.py" >> "%ROOT%\logs\ops_morning_digest.log" 2>&1
endlocal
