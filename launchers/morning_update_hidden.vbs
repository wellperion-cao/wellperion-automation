' Wellperion Morning Update - hidden launcher (no console window)
' Calls the existing morning_update.bat hidden (daily npm/claude update).
' Window style 0 = hidden. Created by AI CTO (2026-06-03).
' 2026-07-04 하드닝(시토): wait=True로 변경 — bat 완료까지 대기해 task 결과가 bat의 fail-soft exit(항상 0)을 따르게.
'   (기존 False=비동기라 task가 bat 실제 종료값을 못 잡아 실패코드 오표기 → 건강판 실패 도배 원인)
' 2026-07-15 하드닝(시토): bat 완료까지 대기 후 wscript 도 명시적 exit 0.
'   bat 은 설계상 항상 exit /b 0(fail-soft)이라 프로세스 체인 종료코드는 0이다.
'   WScript.Quit 0 으로 못박아, 스케줄러가 프로세스 종료코드를 실패로 오독할 여지를 없앤다.
'   ※ 단, 부팅 직후 대화형 로그온 미완료 등으로 스케줄러가 실행 자체를 거절할 때 찍히는
'     0x800710E0(operator refused)은 프로세스 종료코드와 무관 — 이 착오는 발행기
'     (erp_status_publisher.py)에서 '정상(건너뜀)' 양성 분류로 정직 처리한다.
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\ops\morning_update.bat", 0, True
WScript.Quit 0
