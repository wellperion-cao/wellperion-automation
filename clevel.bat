@echo off
:: ============================================================
:: clevel.bat -- Unified C-Level post-action wrapper
:: Usage: clevel.bat <ROLE> [--dry-run] <task-id> <status> "<summary>" [<version>] ["<changelog>"] ["<artifact-url>"]
:: Example: clevel.bat CTO CTO-002 done "PC auto ON/OFF v1.0" v1.0 "2026-04-26 launched" "https://.../proof.png"
:: NOTE: status=done/완료 requires <artifact-url> (evidence). Without it post-action rejects DONE (4-요건 ④증거).
:: ============================================================

chcp 65001 > nul

set ROLE=%~1
if "%ROLE%"=="" (
    echo [clevel.bat ERROR] role missing. Allowed: CEO / CFO / CHRO / CMO / COO / CPO / CTO
    exit /b 1
)
shift

set DRY_RUN_FLAG=
set ARG1=%~1
if /i "%ARG1%"=="--dry-run" (
    set DRY_RUN_FLAG=--dry-run
    shift
)

set TASK_ID=%~1
set STATUS=%~2
set SUMMARY=%~3
set VERSION=%~4
set CHANGELOG=%~5
set ARTIFACT_URL=%~6

if "%TASK_ID%"=="" (
    echo [clevel.bat ERROR] task-id missing.
    echo Usage: clevel.bat ^<ROLE^> [--dry-run] ^<task-id^> ^<status^> "^<summary^>" [^<version^>] ["^<changelog^>"]
    exit /b 1
)
if "%STATUS%"=="" (
    echo [clevel.bat ERROR] status missing. Allowed: done / inprogress / issue
    exit /b 1
)
if "%SUMMARY%"=="" (
    echo [clevel.bat ERROR] summary missing.
    exit /b 1
)

if "%VERSION%"=="" set VERSION=v1.0
if "%CHANGELOG%"=="" set CHANGELOG=auto-recorded %DATE%

set BAT_DIR=%~dp0
set VENV_ACTIVATE=%BAT_DIR%wellperion-agents\venv\Scripts\activate.bat
set POST_ACTION=%BAT_DIR%wellperion-agents\scripts\clevel_post_action.py

if not exist "%VENV_ACTIVATE%" (
    echo [clevel.bat ERROR] venv not found: %VENV_ACTIVATE%
    exit /b 1
)

call "%VENV_ACTIVATE%"

echo [clevel.bat] %ROLE% agent entry -- task-id: %TASK_ID%, status: %STATUS%

if defined DRY_RUN_FLAG (
    echo [DRY-RUN] Agent execution skipped -- running post-action helper only.
)

if not exist "%POST_ACTION%" (
    echo [clevel.bat ERROR] post-action helper not found: %POST_ACTION%
    exit /b 1
)

set ARTIFACT_FLAG=
if not "%ARTIFACT_URL%"=="" set ARTIFACT_FLAG=--artifact-url "%ARTIFACT_URL%"

echo [clevel.bat] Running post-action helper...
python "%POST_ACTION%" --clevel %ROLE% --task-id "%TASK_ID%" --status "%STATUS%" --summary "%SUMMARY%" --version "%VERSION%" --changelog "%CHANGELOG%" %ARTIFACT_FLAG% %DRY_RUN_FLAG%

set EXIT_CODE=%ERRORLEVEL%

REM 완료의 단일 정의 ④증거 — post-action이 DONE을 거부(exit 2)하면 [DONE] 커밋/푸시 금지.
REM 거짓완료가 watcher를 깨우지 않도록 여기서 중단(증거 URL 첨부 후 재실행 안내).
if "%EXIT_CODE%"=="2" (
    echo [clevel.bat ERROR] Completion REJECTED — evidence URL missing (4-요건 ④증거).
    echo   Re-run with artifact: clevel.bat %ROLE% %TASK_ID% %STATUS% "%SUMMARY%" "%VERSION%" "%CHANGELOG%" "^<artifact-url^>"
    exit /b 2
)

REM Auto commit + push (2026-05-28 GM 결재 — feedback_clevel_commit_on_completion)
REM 듀얼 시그널(dual-signal): 완료/DONE 시 watcher 트리거 태그 포함
set COMMIT_MSG=[%ROLE%] %TASK_ID% %STATUS% - %SUMMARY%
if /i "%STATUS%"=="완료" set COMMIT_MSG=[DONE][%ROLE%][%TASK_ID%] %SUMMARY%
if /i "%STATUS%"=="DONE"  set COMMIT_MSG=[DONE][%ROLE%][%TASK_ID%] %SUMMARY%

cd /d "%BAT_DIR%"
git add -A
git diff --cached --quiet
if not %ERRORLEVEL%==0 (
    git commit -m "%COMMIT_MSG%"
    REM 동시 다중 C-Level 세션 push 충돌 방지 — push 전 rebase (2026-06-01 GM 멀티세션 운영)
    git pull --rebase --autostash origin master
    git push origin master
    echo [clevel.bat] Auto commit/push done.
) else (
    echo [clevel.bat] No changes to commit.
)

echo [clevel.bat] Done. Exit code: %EXIT_CODE%
exit /b %EXIT_CODE%
