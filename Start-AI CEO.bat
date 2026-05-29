@echo off
chcp 65001 >nul
title Wellperion GM Control
set "WORK=%USERPROFILE%\welperion-automation"

echo.
echo  ========================================
echo    Wellperion GM Control Room Starting
echo  ========================================
echo.

REM -- 1. Telegram CEO Bot --
echo  [1/3] Telegram CEO Bot starting...
start "WP_CEO_BOT" /min cmd /c "cd /d "%WORK%\telegram_bot" && python bot.py"
timeout /t 2 /nobreak >nul

REM -- 2. AI Scheduler --
echo  [2/3] AI Scheduler starting...
start "WP_SCHEDULER" /min cmd /c "cd /d "%WORK%\telegram_bot" && python daily_scheduler.py"
timeout /t 2 /nobreak >nul

REM -- 3. AI CEO Session --
echo  [3/3] AI CEO Claude Session starting...
echo.
echo  ----------------------------------------
echo   When Claude exits, bot and scheduler stop too
echo   Exit: type /exit in Claude or close window
echo  ----------------------------------------
echo.

cd /d "%WORK%"
git pull --rebase origin master
claude --remote-control "Wellperion GM" "C-Level 부팅: (1) wellperion-agents\.claude\agents\ai-ceo.md 읽고 페르소나·R/R 동적 조회·운영 원칙 숙지 (2) 메인 CLAUDE.md 헌법 로드 (3) 가이드허브 g10 공통 탭 + 본인 탭(data-panel=ceo)에서 최신 R/R·KPI 흡수 (SSOT는 가이드허브, Notion 사용 안 함) (4) status/ceo.json + status/_queue.json read → 본인 task 표 형식 표시 (5) 페르소나·KPI·권한 마크다운 표 선언 (6) 타 C-Level 침범 금지 선언 후 대기."

REM -- Cleanup after Claude exits --
echo.
echo  CEO session ended. Cleaning up...
taskkill /fi "WINDOWTITLE eq WP_CEO_BOT" /f >/dev/null 2>&1
taskkill /fi "WINDOWTITLE eq WP_SCHEDULER" /f >/dev/null 2>&1

for /f "tokens=2" %%p in ('tasklist /v /fi "WINDOWTITLE eq WP_CEO_BOT" /fo list 2^>/dev/null ^| findstr PID') do taskkill /pid %%p /f >/dev/null 2>&1
for /f "tokens=2" %%p in ('tasklist /v /fi "WINDOWTITLE eq WP_SCHEDULER" /fo list 2^>/dev/null ^| findstr PID') do taskkill /pid %%p /f >/dev/null 2>&1

echo.
echo  ========================================
echo    All services stopped.
echo  ========================================
echo.
timeout /t 3 /nobreak >nul
