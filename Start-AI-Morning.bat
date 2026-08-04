@echo off
chcp 65001 >nul
title Wellperion Morning Boot
set "WORK=%USERPROFILE%\welperion-automation"

REM ============================================================
REM  Morning boot - opens Welly (CEO) and Sito (CTO) together.
REM  GM decision 2026-08-03: open Welly + Sito only, when the PC starts.
REM
REM  Why only two: Welly owns the screens field staff use (frontend),
REM  Sito owns what runs behind them (backend). CHRO/CFO belong to
REM  Nawool M, so AI never opens them (ssot/kpi.json _excluded roles).
REM  COO/CPO/CMO stay manual - GM opens them when needed.
REM
REM  Why git runs here first: if both windows each run pull --rebase they
REM  collide on the single shared index (the 2026-07-23 incident class).
REM  Parent does it once; children skip their own block via WP_BOOT_SKIP_GIT.
REM
REM  Auto start: a Startup-folder shortcut calls this at logon.
REM  To turn it off, delete only that shortcut:
REM    %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Wellperion-Morning.lnk
REM
REM  ASCII only on purpose - Korean text in a .bat breaks under CP949.
REM ============================================================

cd /d "%WORK%"
REM -- 0-a. Clear inherited child-session marker (GM 2026-08-04) --
REM    If this window is launched from inside another Claude session it inherits
REM    CLAUDE_CODE_CHILD_SESSION=1 and the transcript is never saved. Two things break:
REM    (1) the whole conversation is lost (942 bytes instead of ~12MB),
REM    (2) the status line reads the role FROM the transcript, so it drops to a grey
REM        "role unknown" line and looks like every colour vanished (GM 2026-08-04).
REM    Clearing it costs nothing when it was not set.
set "CLAUDE_CODE_CHILD_SESSION="

REM -- 부팅 화면은 조용히 (GM 2026-08-04) --
REM    장식 배너·진행 안내를 뺐다. 남기는 것은 사람이 손대야 하는 경고뿐이고,
REM    경고가 하나라도 떴을 때만 창을 5초 붙잡아 GM 이 읽을 수 있게 한다.
REM    아무 문제 없으면 창은 바로 닫힌다.
set "WPWARN="

REM -- git boot self-heal (once) --
git symbolic-ref -q HEAD >nul 2>&1
if errorlevel 1 (
  echo   [self-heal] detached HEAD - returning to master
  set "WPWARN=1"
  git checkout -B master HEAD
)
set DIRTY=0
for /f %%c in ('git status --porcelain ^| find /c /v ""') do set DIRTY=%%c
if %DIRTY% GTR 200 (
  echo   [warn] %DIRTY% uncommitted files - skipping pull
  set "WPWARN=1"
) else (
  git pull --rebase --autostash origin master
  if errorlevel 1 (
    echo   [warn] git pull failed - boot continues
    set "WPWARN=1"
  )
)

set WP_BOOT_SKIP_GIT=1

call "%WORK%\Start-AI CTO.bat"

start "Wellperion GM" "%WORK%\Start-AI CEO.bat"

if defined WPWARN timeout /t 5 >nul
