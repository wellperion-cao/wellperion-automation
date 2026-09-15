@echo off
REM 파트너 블로그 매일 임시저장 자동화 (GM 지시 2026-09-10 고척골프 · 2026-09-15 다이어트캠프 합류).
REM 인자 1개: jo=고척골프 · dc=다이어트캠프. 로그는 업체별 기존 파일 그대로 쌓인다.
setlocal
if "%~1"=="" (
    echo 사용법: partner_blog_daily.bat jo  ^(고척골프^)  또는  partner_blog_daily.bat dc  ^(다이어트캠프^)
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
    echo 알 수 없는 --client 값: %~1  ^(jo 또는 dc 만 지원^)
    exit /b 1
)
echo [%date% %time%] --- run --- >> %LOGFILE%
C:\Python314\python.exe scripts\partner_blog_daily.py --client %~1 >> %LOGFILE% 2>&1
echo [%date% %time%] exit=%ERRORLEVEL% >> %LOGFILE%
exit /b %ERRORLEVEL%
