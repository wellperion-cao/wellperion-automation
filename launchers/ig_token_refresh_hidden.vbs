' Wellperion IG Token Refresh - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\ig_token_refresh.log
' Created by AI CTO (2026-07-07, ship588): weekly IG long-lived token
' (60-day) auto-refresh via Task Scheduler.
' Recommended trigger: every Monday 06:10 (Wellperion-IG-Token-Refresh-Weekly)
' 2026-08-20: wait=True + 자식 종료코드 전달로 변경 (예약작업 실패가 항상 성공 0으로 찍히던 문제 수정).
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\ig_token_refresh.bat", 0, True)
WScript.Quit rc
