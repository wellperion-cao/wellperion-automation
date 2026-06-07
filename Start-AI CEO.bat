@echo off
chcp 65001 >nul
title Wellperion GM Control
set "WORK=%USERPROFILE%\welperion-automation"

echo.
echo  ========================================
echo    Wellperion GM Control Room Starting
echo  ========================================
echo.

REM -- 0. Auto-update Claude Code + OMC --
REM    Windows locks a running .exe, so updating while ANY claude session is open
REM    silently fails. Guard: update ONLY when claude.exe count = 0, then verify
REM    and log, so we can always see whether the boot update actually happened.
echo  [0/1] Checking Claude Code and OMC updates...
set "UPDLOG=%WORK%\logs\claude_update.log"
if not exist "%WORK%\logs" mkdir "%WORK%\logs"
tasklist /fi "imagename eq claude.exe" 2>nul | find /i "claude.exe" >nul
if errorlevel 1 (
  echo [%DATE% %TIME%] no claude session - running update >> "%UPDLOG%"
  call claude update >> "%UPDLOG%" 2>&1
  call claude plugin marketplace update omc >> "%UPDLOG%" 2>&1
  call claude plugin update oh-my-claudecode@omc >> "%UPDLOG%" 2>&1
  for /f "tokens=*" %%v in ('claude --version 2^>nul') do echo [%DATE% %TIME%] now -^> %%v >> "%UPDLOG%"
  echo   update done. see logs\claude_update.log
) else (
  echo [%DATE% %TIME%] claude session active - update SKIPPED >> "%UPDLOG%"
  echo   skipped: a Claude session is already running ^(cannot replace a running exe^).
)
echo.

REM -- Telegram bot and scheduler are NO LONGER started here. --
REM    They run independently and ALWAYS-ON via Windows Task Scheduler
REM    logon triggers (WellperionTelegramBot / WellperionDailyScheduler ->
REM    launchers\bot_hidden.vbs / scheduler_hidden.vbs). This batch starts
REM    ONLY the Claude session, so closing Claude can never kill Telegram
REM    (blackout fix), and a duplicate bot can never cause getUpdates 409.

REM -- AI CEO Session (only thing this batch starts) --
echo  [1/1] AI CEO Claude Session starting...
echo.
echo  ----------------------------------------
echo   Telegram bot/scheduler keep running even after Claude exits.
echo   Exit: type /exit in Claude or close window.
echo  ----------------------------------------
echo.

cd /d "%WORK%"
git pull --rebase origin master
claude --remote-control "Wellperion GM" "C-Level 부팅: (1) wellperion-agents\.claude\agents\ai-ceo.md 읽고 페르소나·R/R 동적 조회·운영 원칙 숙지 (2) CLAUDE.md(인덱스) 로드 - 운영 원칙·R/R 상세는 S2 g10 공통탭+본인탭에서 흡수 (3) 웰페리온 ERP g10 공통 탭 + 본인 탭(data-panel=ceo)에서 최신 R/R·KPI 흡수 (SSOT는 웰페리온 ERP, Notion 사용 안 함) (4) status/ceo.json + status/_queue.json read → 본인 task 표 형식 표시 (5) 페르소나·KPI·권한 마크다운 표 선언 (6) 타 C-Level 침범 금지 선언 후 대기."

REM -- No cleanup: Telegram services are independent and must stay alive. --
echo.
echo  ========================================
echo    CEO session ended. Telegram stays ON.
echo  ========================================
echo.
timeout /t 3 /nobreak >nul
