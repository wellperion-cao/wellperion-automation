@echo off
chcp 65001 > nul
title 웰페리온 키오스크 전원 설정
cd /d "%~dp0"

net session > nul 2>&1
if errorlevel 1 (
  echo 관리자 권한이 필요합니다. 권한 창이 뜨면 [예]를 눌러 주세요.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kiosk_install.ps1"
echo.
echo ────────────────────────────────────────────
echo  끝났습니다. 위 안내를 읽고 창을 닫으세요.
echo ────────────────────────────────────────────
pause
