' Wellperion Kakao Morning Summary Card - hidden launcher (no console window). Created by AI CTO (2026-07-14, 배906).
' Daily 07:30 via Task Scheduler. Window style 0 = hidden. Logs to logs\kakao_summary_card_auto.log
' 2026-08-20: wait=True + 자식 종료코드 전달로 변경 (예약작업 실패가 항상 성공 0으로 찍히던 문제 수정).
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\kakao_summary_card_auto.bat", 0, True)
WScript.Quit rc
