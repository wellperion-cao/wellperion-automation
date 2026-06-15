@echo off
chcp 65001 >nul

REM  Wellperion Morning Update — 세션 기동 前 클로드/OMC 자동 업데이트
REM  매일 05:40 Task Scheduler 가동. 세션 미기동(순수 업데이트). EBUSY 방지.

set "LOGFILE=C:\Users\jjky0\welperion-automation\logs\morning_update.log"
if not exist "C:\Users\jjky0\welperion-automation\logs" mkdir "C:\Users\jjky0\welperion-automation\logs"

>>"%LOGFILE%" echo.
>>"%LOGFILE%" echo ========================================================
>>"%LOGFILE%" echo [%DATE% %TIME%] Morning Update START
>>"%LOGFILE%" echo ========================================================

REM  npm·claude 는 .cmd 셸 → 반드시 call 로 호출해야 제어가 복귀함
>>"%LOGFILE%" echo [Step 1] npm i -g @anthropic-ai/claude-code@latest
call npm install -g @anthropic-ai/claude-code@latest >>"%LOGFILE%" 2>&1
>>"%LOGFILE%" echo [Step 1] npm exit=%ERRORLEVEL%

>>"%LOGFILE%" echo [Step 2] claude update
call claude update >>"%LOGFILE%" 2>&1
>>"%LOGFILE%" echo [Step 2] claude update exit=%ERRORLEVEL%

>>"%LOGFILE%" echo [%DATE% %TIME%] Morning Update END
>>"%LOGFILE%" echo ========================================================
exit /b 0
