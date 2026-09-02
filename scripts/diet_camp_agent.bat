@echo off
REM 다이어트캠프 이승기 대표님 대화 에이전트 — 2시간마다 방을 읽고, 새 말씀이 있으면 답장 1통.
REM 새 말씀이 없으면 아무것도 하지 않는다. 로그는 logs\diet_camp_agent.log 에 쌓인다.
setlocal
cd /d "C:\Users\jjky0\welperion-automation"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo [%date% %time%] --- run --- >> logs\diet_camp_agent.log
C:\Python314\python.exe scripts\diet_camp_agent.py >> logs\diet_camp_agent.log 2>&1
echo [%date% %time%] exit=%ERRORLEVEL% >> logs\diet_camp_agent.log
exit /b %ERRORLEVEL%
