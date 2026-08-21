@echo off
REM ★중간관리자 방 「웰리」 호출 접수 — 1시간마다 (GM 승인 2026-08-21 · 배733)
REM 한글 인자를 쓰지 않는다: .bat 은 CP949 로 읽혀 한글이 깨진다(2026-08-12 수리 기록).
REM 방 이름은 kakao_export_chat 의 --room-key mgr 별칭으로 넘어간다.
cd /d "C:\Users\jjky0\welperion-automation"
C:\Python314\python.exe scripts\kakao_room_listen.py --export >> logs\kakao_room_listen.log 2>&1
exit /b %ERRORLEVEL%
