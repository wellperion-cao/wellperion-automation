' Wellperion Member Expiry Alert - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\member_expiry_alert.log
' Created by AI CTO (2026-07-20): monthly member expiry alert via Task Scheduler.
' Usage: wscript member_expiry_alert_hidden.vbs
'   - Task: Wellperion-CPO-MemberExpiry-Monthly-4thMon-1000 (4th Monday of month, 10:00)
'   - Sends to GM personal chat only (8254867551) - hardcoded in member_expiry_alert.py
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\member_expiry_alert.bat", 0, False
