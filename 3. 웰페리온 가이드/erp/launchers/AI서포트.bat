@echo off
chcp 65001 >nul
title Wellperion AI Support

where node >nul 2>nul
if %errorlevel% neq 0 (
    where winget >nul 2>nul
    if %errorlevel% neq 0 (
        echo Node.js 가 없고 winget 도 없습니다.
        echo https://nodejs.org 에서 LTS 를 설치한 뒤 이 파일을 다시 더블클릭 해주세요.
        pause
        exit /b 1
    )
    echo Node.js 를 설치합니다. 잠시 기다려 주세요...
    winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
    echo Node.js 설치를 마쳤습니다.
    echo 이 창을 닫고 파일을 다시 한 번 더블클릭 해주세요.
    pause
    exit /b 0
)

where claude >nul 2>nul
if %errorlevel% neq 0 (
    echo 클로드(Claude) 를 설치합니다. 잠시 기다려 주세요...
    call npm install -g @anthropic-ai/claude-code
)

set "AI_DIR=%USERPROFILE%\Wellperion-AI"
if not exist "%AI_DIR%" mkdir "%AI_DIR%"

curl -fsSL "https://erp.wellperion.com/erp/launchers/ai_support_CLAUDE.md" -o "%AI_DIR%\CLAUDE.md"
if not exist "%AI_DIR%\CLAUDE.md" (
    echo 설정 파일을 받지 못했습니다. 인터넷 연결을 확인하고 다시 더블클릭 해주세요.
    pause
    exit /b 1
)

echo.
echo 첫 실행이면 브라우저 로그인 창이 뜹니다. 안내받은 클로드 계정으로 로그인 하세요.
echo 끝내려면 /exit 를 입력하세요.
echo 막히면 이 창을 그대로 캡처해서 카톡으로 보내주세요.
echo.

cd /d "%AI_DIR%"
claude

pause
