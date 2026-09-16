@echo off
REM Partner blog daily draft automation (GM directive 2026-09-10 Gocheok golf, 2026-09-15 Diet Camp joined).
REM One argument: jo=Gocheok golf, dc=Diet Camp. Logs go to the existing per-client file.
REM ASCII only: cmd.exe reads this file as CP949, so UTF-8 Korean here breaks parsing
REM when launched from the hidden VBS launcher (2026-09-16: scheduled runs returned 1 in 0.3 s).
setlocal
if "%~1"=="" (
    echo usage: partner_blog_daily.bat jo ^(Gocheok golf^)  or  partner_blog_daily.bat dc ^(Diet Camp^)
    exit /b 1
)
cd /d "%USERPROFILE%\welperion-automation"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
if /i "%~1"=="jo" (
    set LOGFILE=logs\gocheok_blog_daily.log
) else if /i "%~1"=="dc" (
    set LOGFILE=logs\dietcamp_blog_daily.log
) else (
    echo unknown --client value: %~1 ^(only jo or dc^)
    exit /b 1
)
echo [%date% %time%] --- run --- >> %LOGFILE%
C:\Python314\python.exe scripts\partner_blog_daily.py --client %~1 >> %LOGFILE% 2>&1
set BLOGRC=%ERRORLEVEL%
echo [%date% %time%] exit=%BLOGRC% >> %LOGFILE%
REM Marketing upload worker phase 1 (task 12680, 2026-09-16): drains the server queue for
REM naver-blog drafts. Own lock file makes repeat calls (jo then dc) harmless.
C:\Python314\python.exe scripts\marketing_upload_worker.py >> logs\marketing_upload_worker.log 2>&1
echo [%date% %time%] exit=%ERRORLEVEL% >> logs\marketing_upload_worker.log
exit /b %BLOGRC%
