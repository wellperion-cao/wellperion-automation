' Wellperion Monthly Check Report - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\monthly_check_report.log
' Created by AI COO (2026-07-04): support dept monthly check report via Task Scheduler.
' Usage: wscript monthly_check_report_hidden.vbs
'   - runs day 1 09:00 (Wellperion-MonthlyCheckReport-0900-D1)
' 2026-08-20: wait=True + 자식 종료코드 전달로 변경 (예약작업 실패가 항상 성공 0으로 찍히던 문제 수정).
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\monthly_check_report.bat", 0, True)
WScript.Quit rc
