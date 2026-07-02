@echo off
REM Wellperion GM Aide Scan - 06:30 live runner (ASCII only)
REM Called by launchers\gm_aide_scan_hidden.vbs (hidden window).
REM Scans observation ledger + task queue + GM profile for capture events,
REM registers irreversible/gated captures as [GM Aide Proposal] PENDING ships in status\_queue.json.
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\gm_aide_scan.py --commit >> logs\gm_aide_scan.log 2>&1
