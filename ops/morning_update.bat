@echo off
chcp 65001 >nul

REM  Wellperion Morning Update - 세션 기동 前 Claude/OMC 자동 업데이트
REM  GM 로그온 3분 뒤 Task Scheduler 가동. 세션 미기동(순수 업데이트). EBUSY 방지.
REM  2026-07-04 하드닝(시토): 도구 PATH 미해결 컨텍스트에서도 실패로 안 뜨게 fail-soft(항상 exit 0).
REM    - npm/claude가 작업 실행 계정 PATH에 없으면 '건너뜀' 로그 후 정상 종료(건강판 실패 제거).
REM  2026-08-06 시토(배416 · GM 확인): 두 가지를 고쳤다.
REM    (1) 제목엔 'Claude/OMC' 라고 적혀 있었는데 실제로는 Claude 만 갱신하고 OMC 갱신 명령이
REM        없었다. OMC(전역 패키지 oh-my-claude-sisyphus) 갱신을 Step 3 로 추가.
REM    (2) 트리거가 매일 05:40 고정이었는데 그 시각엔 PC 가 꺼져 있거나 로그인 전이라
REM        작업이 뜨지 못했다(Last Result 0x80070520 = 로그온 세션 없음). 등록 2026-05-29 이후
REM        정규 실행 로그 0건 — 한 번도 안 돌았다. 로그온 3분 뒤 실행으로 변경.

set "LOGFILE=C:\Users\jjky0\welperion-automation\logs\morning_update.log"
if not exist "C:\Users\jjky0\welperion-automation\logs" mkdir "C:\Users\jjky0\welperion-automation\logs"

>>"%LOGFILE%" echo.
>>"%LOGFILE%" echo ========================================================
>>"%LOGFILE%" echo [%DATE% %TIME%] Morning Update START
>>"%LOGFILE%" echo ========================================================

REM  npm PATH 확인 — 없으면 fail-soft(실패 아님, 정상 종료)
where npm >nul 2>&1
if errorlevel 1 (
  >>"%LOGFILE%" echo [SKIP] npm PATH 미해결(작업 실행 계정) - 업데이트 건너뜀, 정상 종료
  goto :done
)

>>"%LOGFILE%" echo [Step 1] npm install -g @anthropic-ai/claude-code@latest
call npm install -g @anthropic-ai/claude-code@latest >>"%LOGFILE%" 2>&1
>>"%LOGFILE%" echo [Step 1] npm exit=%ERRORLEVEL%

REM  claude PATH 확인 — 없으면 fail-soft
where claude >nul 2>&1
if errorlevel 1 (
  >>"%LOGFILE%" echo [SKIP] claude PATH 미해결 - claude update 건너뜀, 정상 종료
  goto :done
)

>>"%LOGFILE%" echo [Step 2] claude update
call claude update >>"%LOGFILE%" 2>&1
>>"%LOGFILE%" echo [Step 2] claude update exit=%ERRORLEVEL%

REM  OMC(oh-my-claudecode) 최신화 — 전역 npm 패키지명은 oh-my-claude-sisyphus.
REM  npm 은 위 Step 1 에서 이미 PATH 확인됨(없으면 여기까지 안 온다).
>>"%LOGFILE%" echo [Step 3] npm install -g oh-my-claude-sisyphus@latest
call npm install -g oh-my-claude-sisyphus@latest >>"%LOGFILE%" 2>&1
>>"%LOGFILE%" echo [Step 3] omc exit=%ERRORLEVEL%

:done
>>"%LOGFILE%" echo [%DATE% %TIME%] Morning Update END
>>"%LOGFILE%" echo ========================================================
REM  업데이트 실패는 치명 아님 → 항상 정상 종료(건강판 실패 도배 방지)
exit /b 0
