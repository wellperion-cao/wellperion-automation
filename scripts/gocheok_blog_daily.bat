@echo off
REM 고척골프 조재오부장님 블로그 매일 07:00 임시저장 자동화 (GM 지시 2026-09-10). 로그는 logs\gocheok_blog_daily.log 에 쌓인다.
setlocal
cd /d "%USERPROFILE%\welperion-automation"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo [%date% %time%] --- run --- >> logs\gocheok_blog_daily.log
C:\Python314\python.exe scripts\gocheok_blog_daily.py >> logs\gocheok_blog_daily.log 2>&1
echo [%date% %time%] exit=%ERRORLEVEL% >> logs\gocheok_blog_daily.log
exit /b %ERRORLEVEL%
