' Wellperion 예약 카톡 발송 - hidden launcher (콘솔 창 없음). 2026-08-25 시우.
' 매일 09:00 예약작업(Wellperion-Kakao-Pending-0900). 창 스타일 0 = 숨김. 로그 logs\pending_kakao.log
'
' 세 번째 인자 True = 배치가 끝날 때까지 기다린 뒤 종료코드를 그대로 돌려준다
' (기다리지 않으면 발송이 실패해도 예약작업은 늘 '성공'으로 기록돼 재시도가 안 걸린다 — 2026-08-19 실사례).
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\send_pending_kakao.bat", 0, True)
WScript.Quit rc
