@echo off
REM Wellperion weekly ops fill board - Monday 10:00 (COO / siwoo, 2026-07-23)
REM Regenerates the staff fill board and sends one card to KakaoTalk room "star operations".
REM
REM Why 10:00 Monday (measured 2026-07-23):
REM   - 07:30 already runs 3 tasks (welly runner / ops digest / IG series) -> git lock contention.
REM   - 09:30 runs the KakaoTalk sales report; the sender drives the KakaoTalk window,
REM     so two senders at once could paste into the wrong room. 10:00 is after it finishes.
REM   - Staff are at their desks by then, so the message is actually read.
REM Rollback = disable the scheduled task. Sending is skipped automatically when nothing is missing.
cd /d C:\Users\jjky0\welperion-automation
set LOGFILE=C:\Users\jjky0\welperion-automation\logs\ops_fill_board.log
echo. >> "%LOGFILE%"
echo ===== RUN %date% %time% ===== >> "%LOGFILE%"
C:\Python314\python.exe scripts\ops_fill_board.py --send >> "%LOGFILE%" 2>&1
if exist ".git\index.lock" (
  echo [SKIP] index.lock present - commit skipped >> "%LOGFILE%"
  goto :done
)
git commit -q -m "chore(coo): 주간 채움 보드 갱신 (ops_fill_board)" -- "3. 웰페리온 가이드/coo/todo/업무판 채움 보드.html" "status/boards/s3_cleanup_board.html" >> "%LOGFILE%" 2>&1
:done
echo ===== END %date% %time% ===== >> "%LOGFILE%"
exit /b 0
