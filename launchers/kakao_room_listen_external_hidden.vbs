' Wellperion Kakao External Room Listen - hidden launcher (no console window). Created by AI CTO
' (2026-09-08, ship 1137, GM decision 20:2x). Once a day 06:30 via Task Scheduler
' (Wellperion-Kakao-External-0630 · GM 2026-09-11: hourly saving was too noisy). Window style 0 = hidden, wait=True so the exit code
' reflects the real result (same reasoning as kakao_auto_daily_report_hidden.vbs 2026-08-19 note).
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\kakao_room_listen_external.bat", 0, True)
WScript.Quit rc
