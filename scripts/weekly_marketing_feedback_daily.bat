@echo off
REM Wellperion Daily Marketing Card - 21:00 live runner (ASCII only)
REM Called by launchers\weekly_marketing_feedback_daily_hidden.vbs (hidden window).
REM Generates CMO daily marketing card (status\briefs\CMO-daily-feedback-<YYYYMMDD>.md)
REM from review_queue.json (official @wellperion channel only) + funnel measurement signals
REM + member_registered_list/lesson_registry_list registration detail, then sends the card
REM to the inquiry-alert room via the same send_telegram_summary() as the weekly report.
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\weekly_marketing_feedback.py --mode daily >> logs\weekly_marketing_feedback.log 2>&1
