' Wellperion Hangro Review Brain - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\hangro_review.log
' Created by AI CTO: Daily checkpoint verification for 오늘의 항로 (G1 task board).
' Default: --dry-run reports only; live applies require GM approval.
' Recommended trigger: daily via Task Scheduler (schtasks)
' 2026-08-20: wait=True + 자식 종료코드 전달로 변경 (예약작업 실패가 항상 성공 0으로 찍히던 문제 수정).
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\hangro_review.bat", 0, True)
WScript.Quit rc
