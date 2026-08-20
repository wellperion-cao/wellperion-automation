' Wellperion Daily Marketing Card - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\weekly_marketing_feedback.log
' Created by AI CMO (2026-07-06, GM go-live): daily marketing card, sent to the
' inquiry-alert room (same chat as the weekly report, WEEKLY_SUMMARY_CHAT_ID).
' Trigger: every day 21:00 (Wellperion-CMO-Daily-Marketing-2100)
' 2026-08-20: wait=True + 자식 종료코드 전달로 변경 (예약작업 실패가 항상 성공 0으로 찍히던 문제 수정).
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\weekly_marketing_feedback_daily.bat", 0, True)
WScript.Quit rc
