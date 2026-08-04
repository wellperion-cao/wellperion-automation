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

REM ============================================================
REM  ★2026-08-04 GM 지시 — 「남의 작업이 통째로 지워지는 사고」 수리
REM
REM  사고: 커밋 425cbb58a(8/4 시설 점검)가 무관한 파일 10건을 삭제했다.
REM        (_assets/profile 5건 · 게시물_프로필월.html · 지원자 사진 4건)
REM        같은 유형으로 b7d4f3817 은 저장소 트리 전체를 날린 적이 있다(d591c95f8 로 복구).
REM
REM  원인: 아래 순서가 뒤집혀 있었다.
REM        (구) git add -A → commit → pull --rebase → push
REM        세션의 워킹트리가 낡아 있으면(= 다른 세션이 그 사이 추가한 파일이 없으면)
REM        git add -A 가 그 파일들을 "삭제됨"으로 기록해 커밋에 쓸어담는다.
REM        삭제 의도가 전혀 없어도 삭제 커밋이 만들어진다.
REM
REM  수리: ①먼저 최신본을 받고(pull) ②그 다음 add ③삭제가 섞였으면 커밋 자체를 만들지 않는다.
REM  ※ 의도적 삭제가 필요하면 실행 전 set CLEVEL_ALLOW_DELETE=1 로 우회.
REM ============================================================

REM ① 최신본 먼저 — 워킹트리를 원격과 맞춘 뒤에 add 해야 오탐 삭제가 생기지 않는다.
echo [clevel.bat] Syncing with origin/master before staging...
git pull --rebase --autostash origin master
if not %ERRORLEVEL%==0 goto :pull_failed

git add -A

REM ② 안전망 — 스테이징에 삭제(D)가 섞였는지 검사.
REM    ※ exit /b 를 중첩 블록 안에서 쓰면 종료코드가 유실되므로 goto 라벨로 빠져나간다(실측 확인).
git diff --cached --diff-filter=D --quiet
if not %ERRORLEVEL%==0 goto :deletion_detected
goto :do_commit

:deletion_detected
if "%CLEVEL_ALLOW_DELETE%"=="1" (
    echo [clevel.bat] CLEVEL_ALLOW_DELETE=1 — 삭제를 허용하고 진행합니다.
    goto :do_commit
)
echo.
echo [clevel.bat ABORT] 삭제로 기록된 파일이 있어 커밋을 중단했습니다.
echo   아래 파일이 이 커밋에서 사라집니다. 직접 지운 게 아니라면 워킹트리가 낡은 것입니다.
git diff --cached --diff-filter=D --name-only
echo.
echo   의도한 삭제라면: set CLEVEL_ALLOW_DELETE=1 을 먼저 실행한 뒤 재시도
git reset >nul
exit /b 3

:pull_failed
echo [clevel.bat ABORT] git pull failed — 커밋하지 않고 중단합니다.
echo   원격과 맞추지 못한 상태로 add 하면 남의 파일이 삭제로 기록될 수 있습니다.
exit /b 4

:do_commit
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
