@echo off
REM Partner Instagram daily draft (ship 12718, GM directive 2026-09-17 "activate marketing automation").
REM One argument: jo=Gocheok golf, dc=Diet Camp. Runs after the blog draft (topic comes from the blog state).
REM Sends one photo + caption to the partner Kakao room for OK; publishing happens later with --publish.
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
exit /b %RC%
