' Wellperion Ops Morning Digest - hidden launcher (no console window). Created by AI CTO (2026-07-13).
' Daily 08:00 via Task Scheduler. Window style 0 = hidden. Logs to logs\ops_morning_pipeline.log
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\ops_morning_pipeline.bat", 0, False
