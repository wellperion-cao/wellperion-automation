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
echo.
echo  == Wellperion morning boot - Welly + Sito ==
echo.

REM -- git boot self-heal (once) --
git symbolic-ref -q HEAD >nul 2>&1
if errorlevel 1 (
  echo   [self-heal] detached HEAD - returning to master
  git checkout -B master HEAD
)
set DIRTY=0
for /f %%c in ('git status --porcelain ^| find /c /v ""') do set DIRTY=%%c
if %DIRTY% GTR 200 (
  echo   [warn] %DIRTY% uncommitted files - skipping pull
) else (
  git pull --rebase --autostash origin master
  if errorlevel 1 echo   [warn] git pull failed - boot continues
)

set WP_BOOT_SKIP_GIT=1

echo   [1/2] opening Sito (CTO)...
call "%WORK%\Start-AI CTO.bat"

echo   [2/2] opening Welly (CEO)...
start "Wellperion GM" "%WORK%\Start-AI CEO.bat"

echo.
echo   Both windows opened. You can close this one.
timeout /t 5 >nul
