' Wellperion L-Series Daily Reservation Card - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\lesson_series_daily_card.log
' Created by AI CMO (2026-07-14): daily 08:45 L-series scheduled-day card send via Task Scheduler.
' Card-only - never approves or publishes (publish stays gated on GM's manual telegram approval).
' Recommended trigger: every day 08:45 via Task Scheduler (schtasks)
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\lesson_series_daily_card.bat", 0, False
