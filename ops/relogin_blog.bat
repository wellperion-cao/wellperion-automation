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
echo.
echo ============================================================
echo  브라우저가 곧 열립니다. 네이버 로그인 화면에서
echo.
echo    ★ "로그인 상태 유지" 를 반드시 켜고 로그인하십시오.
echo.
echo  켜지 않으면 브라우저를 닫는 순간 로그인이 사라져서
echo  내일 아침 블로그 글이 또 안 올라갑니다.
echo  (2026-09-15 확인 - 세 계정 모두 이것 때문에 풀려 있었습니다)
echo ============================================================
echo.
pause
set WP_TENANT=%~1
C:\Python314\python.exe scripts\naver_blog_upload_playwright.py --mode setup
echo.
echo === 로그인 결과 확인 ===
C:\Python314\python.exe scripts\check_blog_session.py --tenant %~1
echo.
pause
