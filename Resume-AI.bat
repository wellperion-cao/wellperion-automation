@echo off
chcp 65001 >nul
REM Resume-AI.bat — 역할의 최근 세션을 그대로 이어서 열고 원격제어(/rc)를 자동으로 붙인다.
REM   GM 지시 2026-09-05: "로그인 계정 변경 시 /rc 자동으로 붙여줘, 다른 계정 세션 작업 이어서 해줘"
REM   세션 기록은 로그인 계정과 무관하게 이 PC 한 곳(~/.claude/projects)에 있어 계정을 바꿔도 이어진다.
REM   원격제어는 세션을 여는 순간 로그인돼 있는 계정에 붙는다 — 계정을 바꿨으면 이 배치로 다시 열면 된다.
REM 사용: Resume-AI.bat CMO   (인자 없으면 물어본다)
set "WORK=%USERPROFILE%\welperion-automation"
cd /d "%WORK%"
set "CLAUDE_CODE_CHILD_SESSION="
set "ROLE=%~1"
if "%ROLE%"=="" set /p ROLE=역할 (CEO CMO CTO COO CPO CFO CHRO CBO):
for /f "delims=" %%r in ('powershell -NoProfile -Command "'%ROLE%'.ToUpper()"') do set "ROLE=%%r"
for /f "delims=" %%r in ('powershell -NoProfile -Command "'%ROLE%'.ToLower()"') do set "ROLEL=%%r"
for /f "delims=" %%s in ('C:\Python314\python.exe scripts\session_resume.py --role %ROLEL%') do set "SID=%%s"
if "%SID%"=="" (
  echo   [Resume-AI] %ROLE% 최근 세션을 못 찾았습니다 - 새로 부팅하려면 "Start-AI %ROLE%.bat" 을 쓰세요
  pause
  exit /b 1
)
echo   [Resume-AI] %ROLE% 세션 %SID:~0,8% 이어서 열기 + 원격제어 자동 부착
wt new-tab --title "%ROLE%" --suppressApplicationTitle -d "%WORK%" powershell -NoExit -Command "claude --resume %SID% --fork-session --remote-control '%ROLE%'"
REM --fork-session: 새 세션 ID 로 갈라져 옛 계정 창의 기록과 섞이지 않는다(웰리 원판 2026-09-05 설계 유지)
