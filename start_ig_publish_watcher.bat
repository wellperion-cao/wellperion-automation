@echo off
chcp 65001 >nul

REM  IG 검수 승인 → 자동 발행 감시기 launcher (CMO Phase 2)
REM  GM [승인] 클릭 → 중계가 review_queue.json status=승인 GitHub 기록
REM  → 이 감시기가 2분 주기로 감지 → 발행 → 발행완료+URL → 커밋/푸시 → 텔레그램.
REM  ONLOGON 예약작업으로 상시 가동. 종료는 PC 종료 시 자동.

set ROOT=C:\Users\jjky0\welperion-automation
set PY=%ROOT%\.venv\Scripts\python.exe
set SCRIPT=%ROOT%\scripts\ig_review_publish_watcher.py
set LOGDIR=%ROOT%\logs

REM  텔레그램 토큰 로드 (.env에서 — stdout 노출 금지, @echo off 상태 유지)
for /f "usebackq tokens=1,* delims==" %%a in ("%ROOT%\telegram_bot\.env") do (
    if /i "%%a"=="TELEGRAM_BOT_TOKEN" set "TELEGRAM_BOT_TOKEN=%%b"
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

cd /d "%ROOT%"
echo [start_ig_publish_watcher] %DATE% %TIME% 가동 >> "%LOGDIR%\ig_publish_watcher.log"
"%PY%" "%SCRIPT%" --interval 120 >> "%LOGDIR%\ig_publish_watcher.log" 2>&1
