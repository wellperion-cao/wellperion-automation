' Wellperion L-Series Daily Reservation Card - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\lesson_series_daily_card.log
' Created by AI CMO (2026-07-14): daily 08:45 L-series scheduled-day card send via Task Scheduler.
' Card-only - never approves or publishes (publish stays gated on GM's manual telegram approval).
' Recommended trigger: every day 08:45 via Task Scheduler (schtasks)
' 2026-08-20: wait=True + 자식 종료코드 전달로 변경 (예약작업 실패가 항상 성공 0으로 찍히던 문제 수정).
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\lesson_series_daily_card.bat", 0, True)
WScript.Quit rc
