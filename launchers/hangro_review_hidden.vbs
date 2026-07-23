' Wellperion Hangro Review Brain - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\hangro_review.log
' Created by AI CTO: Daily checkpoint verification for 오늘의 항로 (G1 task board).
' Default: --dry-run reports only; live applies require GM approval.
' Recommended trigger: daily via Task Scheduler (schtasks)
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\hangro_review.bat", 0, False
