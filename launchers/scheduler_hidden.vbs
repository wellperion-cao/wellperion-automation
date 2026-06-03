' Wellperion Daily Scheduler - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\scheduler.log
' Created by AI CTO (2026-06-03): root-cause fix for visible cmd windows
CreateObject("WScript.Shell").Run "cmd /c cd /d C:\Users\jjky0\welperion-automation& set PYTHONIOENCODING=utf-8& C:\Python314\python.exe -u telegram_bot\daily_scheduler.py >> logs\scheduler.log 2>&1", 0, False
