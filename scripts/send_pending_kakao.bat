@echo off
REM 예약해 둔 카톡 발송 — 매일 09:00 (Wellperion-Kakao-Pending-0900). 2026-08-25 시우.
REM 큐(status\pending_kakao\*.json)에 보낼 시각이 지난 것이 있을 때만 보낸다. 비면 아무 일도 안 한다.
cd /d "C:\Users\jjky0\welperion-automation"
"C:\Python314\python.exe" "scripts\send_pending_kakao.py" --live >> "logs\pending_kakao.log" 2>&1
exit /b %ERRORLEVEL%
