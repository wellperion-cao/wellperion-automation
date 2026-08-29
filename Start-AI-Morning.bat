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
REM -- boot trace (2026-08-06 CTO, bae414) --
REM    No prior run of this batch left any evidence it fired. GM discovered the missing
REM    CTO tab only by noticing the window was gone at 08:55, hours after boot. One log
REM    line per phase (start / after-git / cto-launch) is enough to tell post-hoc whether
REM    the batch never ran, stalled in git pull, or reached the CTO launch line.
echo [%date% %time%] start >> logs\morning_boot.log

REM -- 0-a. Clear inherited child-session marker (GM 2026-08-04) --
REM    If this window is launched from inside another Claude session it inherits
REM    CLAUDE_CODE_CHILD_SESSION=1 and the transcript is never saved. Two things break:
REM    (1) the whole conversation is lost (942 bytes instead of ~12MB),
REM    (2) the status line reads the role FROM the transcript, so it drops to a grey
REM        "role unknown" line and looks like every colour vanished (GM 2026-08-04).
REM    Clearing it costs nothing when it was not set.
set "CLAUDE_CODE_CHILD_SESSION="

REM -- Quiet boot (GM 2026-08-04) --
REM    Decorative banners and progress lines removed. Only warnings a human must
REM    act on stay on screen, and the window is held 5s ONLY when one fired.
REM    Clean boot closes immediately.
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
  REM -- --autostash removed (bae10978, 2026-08-29) --
  REM    --autostash silently stashes whatever is dirty, rebases, then pops the
  REM    stash back on top - no matter how old that dirty diff is. Confirmed root
  REM    cause of files reverting to a stale committed version: files nobody ever
  REM    commits (chro/cfo, owned by Nawool M) sat dirty with an old diff for
  REM    weeks; this boot's autostash popped that old diff back over newer HEAD
  REM    content every morning, silently. Without --autostash, `git pull --rebase`
  REM    simply refuses when the tree is dirty for a touched path - same as the
  REM    DIRTY>200 branch above, an honest skip instead of a silent revert.
  git pull --rebase origin master
  if errorlevel 1 (
    echo   [warn] git pull failed - boot continues
    set "WPWARN=1"
  )
)

set WP_BOOT_SKIP_GIT=1

echo [%date% %time%] git step done (dirty=%DIRTY% warn=%WPWARN%) - launching CTO >> logs\morning_boot.log
call "%WORK%\Start-AI CTO.bat"
echo [%date% %time%] cto launch call returned >> logs\morning_boot.log

REM -- Welly (CEO) window no longer opens at boot. GM 2026-08-04:
REM    "Wellperion GM Control - just don't open it, the backend line can
REM     run the automated work." Only the WINDOW is gone. Welly's scheduled
REM    automation is untouched and still runs headless (08:00 brief task
REM    Wellperion-CEO-Morning-Brief-0800-Live, welly_auto_runner 07:30, etc).
REM    To open Welly by hand any time: double-click "Start-AI CEO.bat".
REM    Reverting = restore the one line below.
REM    start "Wellperion GM" "%WORK%\Start-AI CEO.bat"

if defined WPWARN timeout /t 5 >nul
