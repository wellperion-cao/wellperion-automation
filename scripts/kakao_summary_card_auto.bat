@echo off
REM Wellperion Kakao Morning Summary Card - daily 07:30 unattended sender (ASCII only)
REM Called by launchers\kakao_summary_card_hidden.vbs (hidden window).
REM Generates the morning summary card image and sends to KakaoTalk rooms (kill-switch gated).
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\kakao_summary_card_auto.py >> logs\kakao_summary_card_auto.log 2>&1
