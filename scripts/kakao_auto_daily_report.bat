@echo off
REM Wellperion Kakao Sales Report - daily 09:30 unattended sender (ASCII only)
REM Called by launchers\kakao_auto_daily_report_hidden.vbs (hidden window).
REM Generates report image (sheet range export) and sends to KakaoTalk rooms (kill-switch gated).
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\kakao_auto_daily_report.py >> logs\kakao_auto_daily_report.log 2>&1
