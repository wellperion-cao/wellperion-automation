@echo off
REM 파트너 블로그(네이버) 로그인 정보(아이디·비밀번호)를 GM PC 로컬 비밀 파일에 저장한다.
REM 저장해 두면 로그인이 풀렸을 때 사람 손 없이 자동으로 다시 로그인한다(GM 결재 2026-09-15).
REM 사용법: set_blog_login.bat jo  (조재오 부장님 · 고척골프)
REM        set_blog_login.bat dc  (이승기 대표님 · 다이어트캠프)
setlocal
if "%~1"=="" (
    echo 사용법: set_blog_login.bat jo   ^(조재오 부장님 · 고척골프^)
    echo        set_blog_login.bat dc   ^(이승기 대표님 · 다이어트캠프^)
    pause
    exit /b 1
)
cd /d "%USERPROFILE%\welperion-automation"
C:\Python314\python.exe scripts\set_blog_login.py %~1
pause
