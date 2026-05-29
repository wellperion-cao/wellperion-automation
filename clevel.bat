@echo off
:: ============================================================
:: clevel.bat -- Unified C-Level post-action wrapper
:: Usage: clevel.bat <ROLE> [--dry-run] <task-id> <status> "<summary>" [<version>] ["<changelog>"]
:: Example: clevel.bat CTO CTO-002 done "PC auto ON/OFF v1.0" v1.0 "2026-04-26 launched"
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
set VENV_ACTIVATE=%BAT_DIR%notion-c-level-agents\venv\Scripts\activate.bat
set POST_ACTION=%BAT_DIR%notion-c-level-agents\scripts\clevel_post_action.py

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

echo [clevel.bat] Running post-action helper...
python "%POST_ACTION%" --clevel %ROLE% --task-id "%TASK_ID%" --status "%STATUS%" --summary "%SUMMARY%" --version "%VERSION%" --changelog "%CHANGELOG%" %DRY_RUN_FLAG%

set EXIT_CODE=%ERRORLEVEL%

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
    git push origin master
    echo [clevel.bat] Auto commit/push done.
) else (
    echo [clevel.bat] No changes to commit.
)

echo [clevel.bat] Done. Exit code: %EXIT_CODE%
exit /b %EXIT_CODE%
