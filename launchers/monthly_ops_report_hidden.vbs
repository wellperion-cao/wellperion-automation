' Wellperion Monthly Ops Report - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\monthly_ops_report.log
' Created by AI CTO (2026-07-02): monthly ops start/end card via Task Scheduler.
' Usage: wscript monthly_ops_report_hidden.vbs start   (or: end)
'   - start = day 1 09:00 (Wellperion-MonthlyOps-Start-0900)
'   - end   = month last day 21:00 (Wellperion-MonthlyOps-End-2100)
Dim mode
mode = "start"
If WScript.Arguments.Count > 0 Then mode = WScript.Arguments(0)
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\monthly_ops_report.bat " & mode, 0, False
