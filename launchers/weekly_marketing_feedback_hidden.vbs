' Wellperion Weekly Marketing Feedback - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\weekly_marketing_feedback.log
' Created by AI CMO (2026-07-03, GM go live activation): weekly marketing loop
' step 5 (evaluation feedback) brief generation via Task Scheduler.
' Trigger: every Monday 09:00 (Wellperion-CMO-Weekly-Marketing-Feedback)
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\weekly_marketing_feedback.bat", 0, False
