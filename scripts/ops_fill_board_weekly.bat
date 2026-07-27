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
REM
REM 2026-07-27 FIX (siwoo): this file used to be LF-only AND contained Korean text on the
REM   git commit line. cmd.exe chopped those lines into fragments, so the batch never ran -
REM   yet the scheduled task still reported exit code 0 (success) and nobody noticed.
REM   Measured: logs\ops_fill_board.log did not exist at all after the 10:00 run.
REM   Now: ASCII only + CRLF, and the commit moved into ops_fill_board.py --commit
REM   (Korean paths/messages are safe in Python, and it routes through safe_commit as required).
REM   Keep this file ASCII-only. Do not put Korean text in a .bat.
cd /d C:\Users\jjky0\welperion-automation
set LOGFILE=C:\Users\jjky0\welperion-automation\logs\ops_fill_board.log
echo. >> "%LOGFILE%"
echo ===== RUN %date% %time% ===== >> "%LOGFILE%"
C:\Python314\python.exe scripts\ops_fill_board.py --send --commit >> "%LOGFILE%" 2>&1
echo ===== END %date% %time% ===== >> "%LOGFILE%"
exit /b 0
