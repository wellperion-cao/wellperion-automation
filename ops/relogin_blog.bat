@echo off
REM 파트너 블로그(네이버) 로그인 세션이 풀렸을 때 원클릭 재로그인.
REM 사용법: relogin_blog.bat jo  (조재오 부장님 · 고척골프)
REM        relogin_blog.bat dc  (이승기 대표님 · 다이어트캠프)
setlocal
if "%~1"=="" (
    echo 사용법: relogin_blog.bat jo   ^(조재오 부장님 · 고척골프^)
    echo        relogin_blog.bat dc   ^(이승기 대표님 · 다이어트캠프^)
    pause
    exit /b 1
)
cd /d "%USERPROFILE%\welperion-automation"
set WP_TENANT=%~1
C:\Python314\python.exe scripts\naver_blog_upload_playwright.py --mode setup
echo.
echo === 종료 코드: %ERRORLEVEL% ===
pause
