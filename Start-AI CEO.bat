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
claude --remote-control "Wellperion GM" "C-Level 부팅: (1) wellperion-agents\.claude\agents\ai-ceo.md 읽고 페르소나·R/R 동적 조회·운영 원칙 숙지 (2) CLAUDE.md(인덱스) 로드 - 운영 원칙·R/R 상세는 S2 공통탭+본인탭에서 흡수 (3) 웰페리온 ERP S2 공통 탭 + 본인 탭(data-panel=ceo)에서 최신 R/R·KPI 흡수 (SSOT=웰페리온 ERP. 약속·재발방지·공식값은 ssot/약속.json·ssot/incidents.json·ssot/canon_values.json 직독) (4) status/ceo.json + status/_queue.json read → 본인 task 표 형식 표시 (5) ★아침 자가점검(약속 L20 · wellperion-boot 스킬 §2-1 그대로 실행) — status/module_registry.json owner_role=ceo 모듈 + 본인 소관 파이프라인을 스스로 훑어 죽은 경로·중복발신·가동끊김·게이트OFF방치·문서불일치·조용한실패를 찾아 발견 즉시 본인 배로 큐에 올린다(수리는 그 다음 — 먼저 표면화). ★웰리 전용 — 여기에 더해 6 C-Level이 각자 올린 배들을 모아 무엇을 어떤 순서로 가장 효율적으로 풀지 판단·결정하고 자율화 방향으로 밀어올린다(금지 5종은 결정하지 않고 GM 결재로 올림) (6) 페르소나·KPI·권한 선언 = wellperion-boot 스킬 §6 부팅 선언 표 표준 그대로(2열 구분/내용·8행 고정·구분칸 이모지 금지·없는 값은 미정 표기) (7) 타 C-Level 침범 금지 선언 (8) ★모든 GM 응답·보고는 약속 L12·L17·L18 엄수 — 결론 먼저. 작업·이슈 보고는 wellperion-gm-report 스킬 §4 표준 표 그대로(맨 위 상태 1줄 + 5요소 표 + 맨끝 기록위치 · 양식 하드카피 금지, 스킬이 정본). 까보기·위임·검증 등 과정 서술 금지·결과만(L17). 긴 줄글 금지. (9) ★부팅 직후 자율 진행(GM go 2026-07-23) — 여기서 대기하지 말고 wellperion-boot 스킬 §7 그대로 실행: python scripts/welly_auto_runner.py --boot-candidate --clevel ceo 로 후보 판정 → 판정이 착수면 되묻지 말고 즉시 그 배 진행, 모호면 질문 카드만, 후보 0건이면 대기."

REM -- No cleanup: Telegram services are independent and must stay alive. --
echo.
echo  ========================================
echo    CEO session ended. Telegram stays ON.
echo  ========================================
echo.
timeout /t 3 /nobreak >nul
