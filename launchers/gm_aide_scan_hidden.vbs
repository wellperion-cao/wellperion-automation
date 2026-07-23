' Wellperion GM Aide Scan - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\gm_aide_scan.log
' Created by AI CEO (2026-07-02): daily 06:30 GM aide capture scan via Task Scheduler.
' Recommended trigger: every day 06:30 via Task Scheduler (schtasks)
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\gm_aide_scan.bat", 0, False
