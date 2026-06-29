@echo off
REM Wellperion Daily NorthStar Recommender - 06:30 live runner (ASCII only)
REM Called by launchers\northstar_recommender.vbs (hidden window).
REM Generates top3 candidates, expires previous unapproved (G2),
REM writes status\northstar_pending.json, sends Telegram card, logs closed-loop.
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\northstar_recommender.py --send >> logs\northstar_recommender.log 2>&1
