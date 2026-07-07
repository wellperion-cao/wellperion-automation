' Wellperion IG Token Refresh - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\ig_token_refresh.log
' Created by AI CTO (2026-07-07, ship588): weekly IG long-lived token
' (60-day) auto-refresh via Task Scheduler.
' Recommended trigger: every Monday 06:10 (Wellperion-IG-Token-Refresh-Weekly)
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\ig_token_refresh.bat", 0, False
