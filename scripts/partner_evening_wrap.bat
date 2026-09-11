@echo off
REM Wellperion - partner rooms "day close" message (GM instruction 2026-09-11 21:00).
REM One message per partner room telling what we did today. No questions (asking happens at 07:00).
setlocal
cd /d "%USERPROFILE%\welperion-automation"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo [%date% %time%] --- run --- >> logs\partner_evening_wrap.log
C:\Python314\python.exe scripts\diet_camp_agent.py --evening >> logs\partner_evening_wrap.log 2>&1
echo [%date% %time%] exit=%ERRORLEVEL% >> logs\partner_evening_wrap.log
exit /b %ERRORLEVEL%
