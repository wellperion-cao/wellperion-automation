' Wellperion Daily NorthStar Recommender - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\northstar_recommender.log
' Created by AI CTO (2026-06-29): daily 06:30 northstar top3 card via Task Scheduler.
' Recommended trigger: every day 06:30 via Task Scheduler (schtasks / register_northstar.ps1)
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\northstar_recommender.bat", 0, False
