@echo off
REM ============================================================
REM Wellperion - Register Weekly Page Hygiene as Scheduled Task (PROPOSAL ONLY)
REM Task: Wellperion-Weekly-Page-Hygiene-Sun-0900 (WEEKLY, Sunday 09:00)
REM
REM What it does:
REM   Launches launchers\weekly_page_hygiene_hidden.vbs (hidden window) which runs
REM   scripts\weekly_page_hygiene.bat -> scripts\weekly_page_hygiene.py --clevel all.
REM   Default = PROPOSAL MODE (PAGE_HYGIENE_APPLY unset in the .bat). Registering this task
REM   is safe on its own: every week it audits all 47 ERP pages (COO/CPO/CMO/CTO/CFO/CHRO/
REM   shared, config: scripts\weekly_page_hygiene.py PAGE_TARGETS) via headless claude, writes
REM   status\page_hygiene_proposal_<date>.md, and sends a Telegram summary. Category A (dead
REM   code) auto-delete stays OFF (preview-only) until PAGE_HYGIENE_APPLY=1 is uncommented in
REM   scripts\weekly_page_hygiene.bat (separate GM go step, after reviewing several weeks of
REM   proposals - see task note CTO-2026-07-14-WEEKLY-PAGE-HYGIENE).
REM
REM THIS SCRIPT IS NOT EXECUTED AUTOMATICALLY. GM must run it manually
REM (as administrator) to actually register the scheduled task.
REM
REM Why hidden VBS (not /IT interactive): same pattern as
REM   ops\register_welly_auto_runner.bat / launchers\welly_auto_runner_hidden.vbs.
REM
REM RUN AS ADMINISTRATOR (right-click -> Run as administrator).
REM ASCII only (no Korean - CP949 encoding safety).
REM ============================================================

SET ROOT=C:\Users\jjky0\welperion-automation
SET LAUNCHER=%ROOT%\launchers\weekly_page_hygiene_hidden.vbs
SET TASK_NAME=Wellperion-Weekly-Page-Hygiene-Sun-0900
SET RUN_USER=%USERDOMAIN%\%USERNAME%

echo.
echo [1/3] Removing old task if present ...
schtasks /Delete /TN "%TASK_NAME%" /F 1>nul 2>nul && echo   OK: old task removed. || echo   (skip) not present.

echo.
echo [2/3] Registering %TASK_NAME% (WEEKLY, Sunday 09:00, hidden) ...
schtasks /Create /TN "%TASK_NAME%" /TR "wscript \"%LAUNCHER%\"" /SC WEEKLY /D SUN /ST 09:00 /RU "%RUN_USER%" /IT /RL LIMITED /F
if %ERRORLEVEL% EQU 0 (
    echo   OK: %TASK_NAME% registered.
) else (
    echo   FAIL: please Run as administrator.
)

echo.
echo [3/3] Registered task details:
schtasks /Query /TN "%TASK_NAME%" /FO LIST

echo.
echo Done. weekly_page_hygiene runs every Sunday at 09:00 (PROPOSAL MODE by default).
echo Live auto-delete activation is a SEPARATE step: uncomment "set PAGE_HYGIENE_APPLY=1" in
echo scripts\weekly_page_hygiene.bat only after GM reviews several weeks of proposal output.
echo Logs: %ROOT%\logs\weekly_page_hygiene.log
echo Proposal files: %ROOT%\status\page_hygiene_proposal_YYYYMMDD.md
echo Run log: %ROOT%\status\weekly_page_hygiene_log.jsonl
echo To test manually (proposal-mode unless PAGE_HYGIENE_APPLY=1 is set in env):
echo   "C:\Python314\python.exe" "%ROOT%\scripts\weekly_page_hygiene.py" --clevel all --dry-run
echo To remove: schtasks /Delete /TN "%TASK_NAME%" /F
pause
