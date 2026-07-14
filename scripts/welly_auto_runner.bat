@echo off
REM Wellperion Auto Runner (welly_auto_runner) - scheduled headless claude runner MVP.
REM Called by launchers\welly_auto_runner_hidden.vbs (hidden window).
REM bae237 phase3 (GM go 2026-07-13): selects 1 reversible/low-risk CTO ship from
REM status\_queue.json and (when RUNNER_LIVE=1) hands it to a headless claude session.
REM
REM DEFAULT = DRY-RUN (RUNNER_LIVE unset). Ship selection + prompt preview + log only.
REM No claude call, no commit, no _queue.json change while RUNNER_LIVE stays off.
REM
REM Rollback (1-stage): keep the line below commented out to stay dry-run.
REM Live activation (GM go only): uncomment "set RUNNER_LIVE=1".
REM
REM Telegram ping gate (ambiguous-ship escalation, separate 2-stage gate from
REM RUNNER_LIVE) - GM go 2026-07-13 ("notifications on"). Sends a low-frequency
REM GM-channel ping only when the runner parks an ambiguous ship (dedup + daily
REM cap enforced in welly_auto_runner.py). Rollback (1 line): comment out
REM "set RUNNER_PING_LIVE=1" below to silence pings again.
REM
REM bae237 phase4 (2026-07-14 GM ask): welly_auto_runner.py now supports
REM "--clevel all" to round-robin all 7 C-Level roles (cmo/coo/cto/cpo/ceo/cfo/
REM chro) in one cycle, capped per cycle (MAX_SHIPS_PER_CYCLE), with every
REM existing safety gate (reversible-only, low-risk, clean-tree, recursion
REM guard, cooldown, and the non-negotiable ambiguity park) applied per clevel
REM unchanged. This line still targets "--clevel cto" only - widening the
REM scheduled 07:30 live run from 1 domain to 7 is a separate scope expansion
REM that needs its own explicit GM go (design note:
REM docs/superpowers/specs/2026-07-14-welly-runner-all-clevel-autodrive-design.md).
REM Forward/rollback are both a 1-line flip: change "cto" to "all" below (or
REM back) whenever that go is given.
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
set RUNNER_LIVE=1
set RUNNER_PING_LIVE=1
C:\Python314\python.exe -u scripts\welly_auto_runner.py --clevel cto >> logs\welly_auto_runner.log 2>&1
