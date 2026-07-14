@echo off
REM Wellperion Weekly Page Hygiene (weekly_page_hygiene) - scheduled headless-claude page audit.
REM Called by launchers\weekly_page_hygiene_hidden.vbs (hidden window).
REM Task CTO-2026-07-14-WEEKLY-PAGE-HYGIENE (GM ask 2026-07-14): productizes today's manual
REM 47-page full-ERP audit (subagent -> A dead-code / B duplicate / C stale / D verbose -> GM
REM approval -> apply) into an unattended weekly pipe. Started as COO 14-only, expanded same
REM day to --clevel all (47 pages: COO/CPO/CMO/CTO/CFO/CHRO/shared) once the rest of the ERP
REM was audited.
REM
REM DEFAULT = PROPOSAL MODE (PAGE_HYGIENE_APPLY unset). The audit still runs every week and
REM writes status\page_hygiene_proposal_<date>.md + sends the Telegram summary, but category A
REM (dead code) is only PREVIEWED (grep-0 gate computed, file untouched) until GM reviews a few
REM weeks of proposals and gives the go to flip live.
REM
REM Live activation (GM go only, after reviewing several weeks of proposals): uncomment
REM "set PAGE_HYGIENE_APPLY=1" below. Rollback (1-stage): comment it back out.
REM
REM Even when live, only category A candidates that pass the 3-gate check (grep-0 zero
REM consumers + unique snippet match + post-removal parse integrity) are auto-applied and
REM committed per-file. B/C/D are always proposal-only. Design: scripts\weekly_page_hygiene.py
REM module docstring.
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
REM set PAGE_HYGIENE_APPLY=1
C:\Python314\python.exe -u scripts\weekly_page_hygiene.py --clevel all >> logs\weekly_page_hygiene.log 2>&1
