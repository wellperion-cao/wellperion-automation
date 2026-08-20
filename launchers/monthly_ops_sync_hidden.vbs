' Wellperion monthly-ops auto-sync hidden launcher (ship 9678)
' Runs monthly_ops_sync.bat with no console window.
' 2026-08-20: wait=True + 자식 종료코드 전달로 변경 (예약작업 실패가 항상 성공 0으로 찍히던 문제 수정).
Set WShell = CreateObject("WScript.Shell")
rc = WShell.Run("cmd /c C:\Users\jjky0\welperion-automation\scripts\monthly_ops_sync.bat", 0, True)
WScript.Quit rc
