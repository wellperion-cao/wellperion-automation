' 2026-08-20: wait=True + 자식 종료코드 전달로 변경 (예약작업 실패가 항상 성공 0으로 찍히던 문제 수정).
Set sh = CreateObject("WScript.Shell")
rc = sh.Run("cmd /c ""C:\Python314\python.exe"" ""C:\Users\jjky0\welperion-automation\scripts\sales_report_ops_summary.py"" >> ""C:\Users\jjky0\welperion-automation\logs\sales_ops_summary.log"" 2>&1", 0, True)
WScript.Quit rc
