@echo off
chcp 65001 >nul

REM  Wellperion Morning Update - 세션 기동 前 Claude/OMC 자동 업데이트
REM  매일 05:40 Task Scheduler 가동. 세션 미기동(순수 업데이트). EBUSY 방지.
REM  2026-07-04 하드닝(시토): 도구 PATH 미해결 컨텍스트에서도 실패로 안 뜨게 fail-soft(항상 exit 0).
REM    - npm/claude가 작업 실행 계정 PATH에 없으면 '건너뜀' 로그 후 정상 종료(건강판 실패 제거).

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

:done
>>"%LOGFILE%" echo [%DATE% %TIME%] Morning Update END
>>"%LOGFILE%" echo ========================================================
REM  업데이트 실패는 치명 아님 → 항상 정상 종료(건강판 실패 도배 방지)
exit /b 0
