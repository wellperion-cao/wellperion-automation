' 2026-08-20: wait=True + 자식 종료코드 전달로 변경 (예약작업 실패가 항상 성공 0으로 찍히던 문제 수정).
Set sh = CreateObject("WScript.Shell")
' 2026-08-21(시토 · 배738): --contact 추가. P20(운영 현황)에 더해 I16(금일 예상 컨택 —
'   그날 투어·체험 예약자 + 전날 LOSS)까지 채운다. 지금까지 사람이 손으로 치던 칸이고,
'   09:30 보고에 그대로 실린다. 원천을 못 읽으면 아무것도 쓰지 않는다(사람 글을 빈 값으로 지우지 않음).
'   새 예약작업을 만들지 않고 이미 09:00 에 도는 이 자리에 얹었다(약속 L21).
rc = sh.Run("cmd /c ""C:\Python314\python.exe"" ""C:\Users\jjky0\welperion-automation\scripts\sales_report_ops_summary.py"" --contact >> ""C:\Users\jjky0\welperion-automation\logs\sales_ops_summary.log"" 2>&1", 0, True)
WScript.Quit rc
