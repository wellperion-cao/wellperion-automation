@echo off
REM Wellperion GM Aide Scan - 06:30 live runner (ASCII only)
REM Called by launchers\gm_aide_scan_hidden.vbs (hidden window).
REM Step 1: refresh status\gm_profile.md (spec = daily refresh, was stale since 2026-07-02).
REM Step 2: scan observation ledger + task queue + refreshed GM profile for capture events,
REM registers irreversible/gated captures as [GM Aide Proposal] PENDING ships in status\_queue.json.
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\gm_profile_builder.py >> logs\gm_profile_builder.log 2>&1
REM phase2 live activation (GM go 2026-07-02): reversible auto-exec ON for the
REM scheduled 06:30 run (drift ship next auto-augment only; irreversible stays proposal-only).
REM Rollback (1-stage): delete or comment out the line below to return to phase1 dry-run.
set GM_AIDE_AUTO_EXEC=1
REM bae237(b) HALF-HALF live activation (GM go 2026-07-08): RESUMABLE gap auto ON
REM (depends_on resolved by prior DONE ship -> tag + nudge + resolve_structural_depends).
REM STALL gap stays surface-only (NO auto write) - do NOT add any stall gate here.
REM Rollback (1-stage): delete or comment out the single line below to return to resumable dry-run.
set AIDE_RESUMABLE_APPLY=1
C:\Python314\python.exe -u scripts\gm_aide_scan.py --commit >> logs\gm_aide_scan.log 2>&1
