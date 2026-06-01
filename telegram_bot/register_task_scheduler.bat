@echo off
REM 웰페리온 자동 보고 스케줄러 + 텔레그램 봇 — Windows 작업 스케줄러 OS 레벨 이중화 등록
REM 반드시 관리자 권한으로 실행. 봇(bot.py)+스케줄러(daily_scheduler.py) 둘 다 로그온 시 자동기동 등록.
REM 현재 수동 기동 프로세스는 유지되며 다음 재부팅부터 자동 적용.
REM APScheduler(소프트웨어 레벨) + 작업 스케줄러(OS 레벨) 이중화 구조

cd /d "%~dp0"
SET SCRIPT_DIR=%~dp0
SET PYTHON_EXE=C:\Python314\python.exe
SET TASK_NAME_SCHEDULER=WellperionDailyScheduler
SET TASK_NAME_BOT=WellperionTelegramBot

echo.
echo [작업 스케줄러 등록] 기존 태스크 삭제 후 재등록합니다...

REM ── 1. daily_scheduler.py (APScheduler 기반 시간 관리) ─────────────────────
schtasks /Delete /TN "%TASK_NAME_SCHEDULER%" /F 2>nul

REM PC 부팅 시 자동 실행 (로그온 트리거) — APScheduler가 내부에서 시간 관리
schtasks /Create ^
  /TN "%TASK_NAME_SCHEDULER%" ^
  /TR "\"%PYTHON_EXE%\" \"%SCRIPT_DIR%daily_scheduler.py\"" ^
  /SC ONLOGON ^
  /DELAY 0001:00 ^
  /RL HIGHEST ^
  /F

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo [완료] 태스크 "%TASK_NAME_SCHEDULER%" 등록 성공.
    echo        로그온 후 1분 뒤 자동 기동됩니다.
    echo        APScheduler가 06/08/18/22시 정각 트리거를 관리합니다.
) ELSE (
    echo.
    echo [경고] 태스크 "%TASK_NAME_SCHEDULER%" 등록 실패. 관리자 권한으로 다시 실행하세요.
)

REM ── 2. bot.py (텔레그램 보고봇 수신 루프) ────────────────────────────────
schtasks /Delete /TN "%TASK_NAME_BOT%" /F 2>nul

schtasks /Create ^
  /TN "%TASK_NAME_BOT%" ^
  /TR "\"%PYTHON_EXE%\" \"%SCRIPT_DIR%bot.py\"" ^
  /SC ONLOGON ^
  /DELAY 0001:00 ^
  /RL HIGHEST ^
  /F

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo [완료] 태스크 "%TASK_NAME_BOT%" 등록 성공.
    echo        로그온 후 1분 뒤 자동 기동됩니다.
    echo        텔레그램 봇 수신 루프가 상시 대기합니다.
) ELSE (
    echo.
    echo [경고] 태스크 "%TASK_NAME_BOT%" 등록 실패. 관리자 권한으로 다시 실행하세요.
)

echo.
echo [현재 등록된 태스크 확인]
schtasks /Query /TN "%TASK_NAME_SCHEDULER%" /FO LIST 2>nul
schtasks /Query /TN "%TASK_NAME_BOT%" /FO LIST 2>nul

pause
