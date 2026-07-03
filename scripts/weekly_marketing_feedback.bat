@echo off
REM Wellperion Weekly Marketing Feedback - Monday 09:00 live runner (ASCII only)
REM Called by launchers\weekly_marketing_feedback_hidden.vbs (hidden window).
REM Generates CMO weekly marketing feedback brief (status\briefs\CMO-weekly-feedback-<YYYYMMDD>.md)
REM from review_queue.json (official @wellperion channel only) + funnel measurement signals.
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\weekly_marketing_feedback.py >> logs\weekly_marketing_feedback.log 2>&1
