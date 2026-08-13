' Wellperion Kakao evening re-collect - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\kakao_collect_evening.log
' Created by AI CEO (2026-08-13): the manager room was exported only once a day (07:30),
' so replies arriving during working hours stayed invisible until the next morning.
' Collect only - this path never sends a message.
' Trigger: daily 18:30 via Task Scheduler (Wellperion-Kakao-Collect-Evening-1830)
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\kakao_collect_evening.bat", 0, False
