' Wellperion CPO Inquiry Snapshot - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\cpo_inquiry_snapshot.log
' Created by AI CTO (2026-07-16): 3-minute inquiry-list snapshot job for instant
' cold-load rendering on member/document.html. Read-only accelerator (design spec:
' docs/superpowers/specs/2026-07-16-inquiry-read-server-snapshot-design.md).
' Recommended trigger: every 3 minutes via Task Scheduler (schtasks)
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\cpo_inquiry_snapshot.bat", 0, False
