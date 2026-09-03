@echo off
REM 다이어트캠프 이승기 대표님 대화 에이전트 — 매일 06:50 대화를 저장하고 초안을 만든 뒤 07:00 에 1통 보낸다(GM 지시 2026-09-03: 저장은 07시 전, 발신은 07시).
REM 새 말씀이 있으면 답장, 없으면 아침 질문 1통(대표님 생각 끌어내기 — GM 지시 2026-09-03). 종전(09-02)은 답장만·07:00 실행. 로그는 logs\diet_camp_agent.log 에 쌓인다.
setlocal
cd /d "C:\Users\jjky0\welperion-automation"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo [%date% %time%] --- run --- >> logs\diet_camp_agent.log
C:\Python314\python.exe scripts\diet_camp_agent.py --send-at 07:00 >> logs\diet_camp_agent.log 2>&1
echo [%date% %time%] exit=%ERRORLEVEL% >> logs\diet_camp_agent.log
exit /b %ERRORLEVEL%
