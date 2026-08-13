@echo off
rem 웰페리온 키오스크 전원 설정 - 두 번 클릭 설치
rem ★이 파일은 반드시 CP949(ANSI 한국어) + CRLF 로 저장한다.
rem   UTF-8 로 저장하고 chcp 65001 을 쓰면 cmd 가 줄 위치를 잃어
rem   "배치 파일이 아닙니다" 오류가 여러 줄 뜬다(2026-08-13 GM 실사고).
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 goto NEEDADMIN

if not exist "%~dp0kiosk_install.ps1" goto NOFILE

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kiosk_install.ps1"
echo.
echo 끝났습니다. 위 안내를 읽고 창을 닫으세요.
pause
exit /b

:NEEDADMIN
echo 관리자 권한이 필요합니다. 권한 창이 뜨면 [예]를 눌러 주세요.
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
exit /b

:NOFILE
echo 같은 폴더에 kiosk_install.ps1 이 없습니다.
echo USB 폴더 전체를 복사해서 실행해 주세요.
pause
exit /b
