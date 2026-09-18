@echo off
REM Partner Instagram daily auto-post (ship 12718, GM directive 2026-09-18: post directly, no morning Kakao).
REM One argument: jo=Gocheok golf, dc=Diet Camp. Runs BEFORE the blog draft: the blog seeds from today's
REM Instagram topic/caption/photos (status\partner_instagram\{client}.json). No partner OK gate anymore.
REM ASCII only: cmd.exe reads this file as CP949 (2026-09-16 lesson, hidden VBS launcher).
setlocal
if "%~1"=="" (
    echo usage: partner_instagram_daily.bat jo  or  partner_instagram_daily.bat dc
    exit /b 1
)
cd /d "%USERPROFILE%\welperion-automation"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set LOGFILE=logs\partner_instagram_daily.log
echo [%date% %time%] --- run %~1 --- >> %LOGFILE%
C:\Python314\python.exe scripts\partner_instagram_daily.py %~1 >> %LOGFILE% 2>&1
set RC=%ERRORLEVEL%
echo [%date% %time%] exit=%RC% >> %LOGFILE%
REM waiting-list board (labs_waiting.json) refresh (2026-09-17)
C:\Python314\python.exe scripts\labs_waiting.py >> logs\labs_waiting.log 2>&1
exit /b %RC%
