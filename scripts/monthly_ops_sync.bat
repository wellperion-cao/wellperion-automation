@echo off
REM Wellperion monthly-ops auto-sync (daily live) - ship 9678
REM Pulls real work/task SSOT status into monthly_ops_plan.json, then commits.
REM Gate: MONTHLY_SYNC_APPLY=1 (this file). Rollback = disable scheduled task.
REM 2026-07-23 (siwoo truth-check): added run log + path-scoped commit.
REM   - No log before: a 07:00 run left zero evidence (task result 0 only proves wscript launched).
REM 2026-07-24 (GM fix): commit is now owned by monthly_ops_sync.py itself, via safe_commit.py
REM   with retry-on-lock (5s x 12 tries) - the old bare "git commit" here used to silently
REM   skip on .git\index.lock and lose that day's sync with zero visible failure signal.
cd /d %USERPROFILE%\welperion-automation
set MONTHLY_SYNC_APPLY=1
set LOGFILE=%USERPROFILE%\welperion-automation\logs\monthly_ops_sync.log
echo. >> "%LOGFILE%"
echo ===== RUN %date% %time% ===== >> "%LOGFILE%"
REM 2026-09-09 (cto, 배1158): 아래 exit /b 0 이 무조건 성공을 찍어, monthly_ops_sync.py 가
REM   9일 연속 크래시하는 동안 예약작업 결과가 매일 0(성공)으로 남았다. 아무 감시도 안 걸렸고
REM   월간운영계획 진척 칸이 9일간 굳어 있었다(웰리 진단 2026-09-09). 종료코드를 그대로 넘긴다.
C:\Python314\python.exe scripts\monthly_ops_sync.py --apply >> "%LOGFILE%" 2>&1
set SYNC_RC=%ERRORLEVEL%
REM 2026-09-01 (cto, ship 860): weekly chairman-report draft, Mondays only (script self-gates,
REM   non-Monday runs exit immediately). Piggybacks this daily 07:00 task per promise L21 -
REM   no new scheduled task. Sends DRAFT to GM report room via telegram_notifier; GM reviews
REM   before anything goes to the chairman.
C:\Python314\python.exe scripts\weekly_report_draft.py --send >> "%LOGFILE%" 2>&1
set DRAFT_RC=%ERRORLEVEL%
echo ----- 종료코드 sync=%SYNC_RC% draft=%DRAFT_RC% >> "%LOGFILE%"
echo ===== END %date% %time% ===== >> "%LOGFILE%"
REM 둘 중 하나라도 실패면 실패로 끝낸다 — 예약작업 결과가 진짜 결과를 말해야 한다.
REM   (weekly_report_draft.py 는 월요일이 아니면 스스로 0 으로 끝나므로 평일에 헛경보를 내지 않는다.
REM    실측 2026-09-09: 수요일 실행 종료코드 0)
if not "%SYNC_RC%"=="0" exit /b %SYNC_RC%
if not "%DRAFT_RC%"=="0" exit /b %DRAFT_RC%
exit /b 0
