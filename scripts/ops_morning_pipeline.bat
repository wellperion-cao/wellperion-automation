@echo off
REM Wellperion Ops Morning Digest - daily 08:00 unattended pipeline (ASCII only)
REM Called by launchers\ops_morning_pipeline_hidden.vbs (hidden window).
REM Exports the OperationsDept KakaoTalk chat -> AI digest -> GM Telegram approval request.
REM Room send NEVER happens here (gate) - only after GM taps the approval button
REM (handled by telegram_bot\bot.py opsdig: callback).
cd /d C:\Users\jjky0\welperion-automation
set PYTHONIOENCODING=utf-8
C:\Python314\python.exe -u scripts\ops_morning_pipeline.py >> logs\ops_morning_pipeline.log 2>&1
