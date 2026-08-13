@echo off
REM Wellperion - Kakao evening re-collect (18:30). Manager room only, COLLECT ONLY (no send).
REM
REM Why: the morning job (07:30) exports the manager room once a day. Replies that arrive
REM during working hours are therefore invisible until the next morning. On 2026-08-13 the
REM facility manager answered 7 items between 16:29 and 18:44; the AI CEO was still reading
REM the 13:05 snapshot and reported "no reply" to the GM. One extra read in the evening cuts
REM the reply loop from one day to half a day.
REM
REM Safe by design: this only exports the chat log. It never sends a message.
REM Rollback = disable the scheduled task (Wellperion-Kakao-Collect-Evening-1830).
setlocal
set PYTHONIOENCODING=utf-8
set ROOT=C:\Users\jjky0\welperion-automation
set PY=C:\Python314\python.exe
if not exist "%PY%" set PY=python
cd /d "%ROOT%"
echo ===== %DATE% %TIME% kakao-collect-evening start ===== >> "%ROOT%\logs\kakao_collect_evening.log"
REM Room name is passed as an ASCII alias (--room-key mgr). Korean text inside a .bat is read
REM as CP949 and reaches the child process mangled - that silently broke the manager room
REM export every morning until 2026-08-12.
"%PY%" "%ROOT%\scripts\kakao_export_chat.py" --room-key mgr >> "%ROOT%\logs\kakao_collect_evening.log" 2>&1
echo ===== %DATE% %TIME% kakao-collect-evening end ===== >> "%ROOT%\logs\kakao_collect_evening.log"
endlocal
