' Wellperion weekly ops fill board - hidden launcher (COO / siwoo, 2026-07-23)
' Runs ops_fill_board_weekly.bat with no console window.
'
' 2026-07-27 시우 수리 — 세 번째 인자를 False(안 기다림) → True(끝날 때까지 기다림).
'   증상: 예약작업 Wellperion-COO-FillBoard-Mon-1000 이 매주 월 10:00 에 '성공(코드 0)' 으로 찍히는데
'         산출물이 안 나왔다. 실측 2026-07-27 16:00 — 마지막 하트비트가 50시간 전(07-25 수동 실행분)이고,
'         이 배치가 남기는 logs\ops_fill_board.log 파일이 아예 존재하지 않았다(=배치 첫 줄도 못 씀).
'   원인: Run(..., 0, False) 는 배치를 띄우자마자 wscript 가 끝난다. 대화형으로 돌리면 배치가 살아남지만,
'         작업 스케줄러는 작업 프로세스를 job 으로 묶어서 부모(wscript)가 끝나면 자식(cmd·배치)도 함께
'         정리한다 → 배치가 시작하기도 전에 죽었다. 그런데 wscript 자체는 정상 종료라 작업 결과는
'         계속 0(성공)으로 찍혔다 — 성공을 가장한 실패라 아무도 몰랐다.
'   확인: 같은 구조의 probe 를 대화형으로 실행하면 로그가 남았다(체인 자체는 정상) → 예약 경로에서만 죽는다.
'   효과: True 면 wscript 가 배치 종료까지 살아 있어 자식이 죽지 않고, 작업 결과 코드도 실제 결과를 반영한다.
'         창은 여전히 숨김(두 번째 인자 0) — 실무진 화면에 콘솔이 뜨지 않는다.
Set WShell = CreateObject("WScript.Shell")
WShell.Run "cmd /c C:\Users\jjky0\welperion-automation\scripts\ops_fill_board_weekly.bat", 0, True
