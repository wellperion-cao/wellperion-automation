' 매출보고 시트 09:00 자동 채움 - hidden launcher (콘솔창 없음). AI CTO.
' P20 = 시설·지원·주차 운영 현황 / I16 = 금일 예상 컨택(예약·LOSS, 2026-08-21 배738 추가).
' 2026-08-20: wait=True + 자식 종료코드 전달로 변경 (예약작업 실패가 항상 성공 0으로 찍히던 문제 수정).
' 2026-08-21(시토): cmd 한 줄에 따옴표를 겹쳐 넣던 방식이 실패해 3일간(8/19~8/21) 조용히 안 돌았다 —
'   예약작업은 매일 Ready 로 떴고 종료코드만 1, 로그 파일조차 안 생겼다. P20 이 8/18 에 멈춰 있었고
'   GM 이 먼저 발견했다. 이 저장소에서 이미 검증된 방식(ops_morning_digest_hidden.vbs)과 같게 .bat 호출로 바꾼다.
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\sales_ops_summary.bat", 0, True)
WScript.Quit rc
