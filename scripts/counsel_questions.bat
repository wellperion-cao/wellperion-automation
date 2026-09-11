@echo off
REM 상담봇 질문 수집·가공 (GM 지시 2026-09-11 「질문하는 것들 다 저장하고 가공해줘」). 로그는 logs\counsel_questions.log 에 쌓인다.
setlocal
cd /d "%USERPROFILE%\welperion-automation"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo [%date% %time%] --- run --- >> logs\counsel_questions.log
C:\Python314\python.exe scripts\counsel_questions.py >> logs\counsel_questions.log 2>&1
echo [%date% %time%] exit=%ERRORLEVEL% >> logs\counsel_questions.log
exit /b %ERRORLEVEL%
