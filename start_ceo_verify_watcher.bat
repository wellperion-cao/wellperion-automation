@echo off
chcp 65001 >nul

REM  CEO Verify Watcher launcher (0단계 인프라)
REM  git push 감지 → [DONE] 이중신호 → 2층 검증 → ceo_log + 텔레그램
REM  ONLOGON 예약작업으로 상시 가동. 종료는 PC 종료 시 자동.

set ROOT=C:\Users\jjky0\welperion-automation
set PY=%ROOT%\notion-c-level-agents\venv\Scripts\python.exe
set SCRIPT=%ROOT%\notion-c-level-agents\scripts\ceo_verify_watcher.py
set LOGDIR=%ROOT%\logs

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

cd /d "%ROOT%"
echo [start_ceo_verify_watcher] %DATE% %TIME% 가동 >> "%LOGDIR%\ceo_verify_watcher.log"
"%PY%" "%SCRIPT%" --watch --interval 60 >> "%LOGDIR%\ceo_verify_watcher.log" 2>&1
