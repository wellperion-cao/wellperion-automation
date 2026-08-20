' Wellperion CMO Content Intake to Review Queue plus GM Card - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\cmo_intake_to_review.log
' Created by AI CMO (2026-07-24, ship 9888): instructor content intake reaches GM as a
' telegram card without a separate screen. Idempotent - already-sent rows never resend.
' Card-only - never approves or publishes (intake status is outside both publish gates).
' Trigger: every 15 minutes via Task Scheduler (schtasks)
' 2026-08-20: wait=True + 자식 종료코드 전달로 변경 (예약작업 실패가 항상 성공 0으로 찍히던 문제 수정).
' 15분 주기지만 MultipleInstancesPolicy=IgnoreNew·ETL=10분 확인 — 겹침 없음.
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\cmo_intake_to_review.bat", 0, True)
WScript.Quit rc
