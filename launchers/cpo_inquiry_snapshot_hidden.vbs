' Wellperion CPO Inquiry Snapshot - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\cpo_inquiry_snapshot.log
' Created by AI CTO (2026-07-16): 3-minute inquiry-list snapshot job for instant
' cold-load rendering on member/document.html. Read-only accelerator (design spec:
' docs/superpowers/specs/2026-07-16-inquiry-read-server-snapshot-design.md).
' Recommended trigger: every 3 minutes via Task Scheduler (schtasks)
' 2026-08-20: wait=True + 자식 종료코드 전달로 변경 (예약작업 실패가 항상 성공 0으로 찍히던 문제 수정).
' 3분 주기지만 MultipleInstancesPolicy=IgnoreNew·ETL=30분 확인 — 겹침 없음.
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\cpo_inquiry_snapshot.bat", 0, True)
WScript.Quit rc
