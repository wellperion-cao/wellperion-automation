@echo off
REM Wellperion IG Token Refresh - weekly runner (ASCII only, ship588)
REM Called by launchers\ig_token_refresh_hidden.vbs (hidden window).
REM Refreshes the 60-day IG_ACCESS_TOKEN in scripts\.env; on failure
REM sends an OWNER Telegram alert (scripts\ig_token_refresh.py handles it).
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\ig_token_refresh.py >> logs\ig_token_refresh.log 2>&1
