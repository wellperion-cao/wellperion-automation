' Wellperion Kakao Sales Report - hidden launcher (no console window). Created by AI CTO (2026-07-07).
' Daily 09:30 via Task Scheduler. Window style 0 = hidden. Logs to logs\kakao_auto_daily_report.log
'
' 2026-08-19 (GM 지시): 세 번째 인자를 True 로 바꿔 배치가 끝날 때까지 기다린 뒤 그 종료코드를
' 그대로 돌려준다. 전에는 False(기다리지 않음)라 파이썬이 "0/4개 방 발송 실패"로 끝나도
' 예약작업은 항상 '성공(0)'으로 기록됐다 — 그래서 예약작업의 '실패 시 재시도'가 한 번도
' 발동할 수 없었다(2026-08-19 09:32 윈도우 업데이트로 4방 전부 실패한 회차가 실제 사례).
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\kakao_auto_daily_report.bat", 0, True)
WScript.Quit rc
