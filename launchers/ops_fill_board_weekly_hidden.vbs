' Wellperion weekly ops fill board - hidden launcher (COO / siwoo, 2026-07-23)
' Runs ops_fill_board_weekly.bat with no console window.
Set WShell = CreateObject("WScript.Shell")
WShell.Run "cmd /c C:\Users\jjky0\welperion-automation\scripts\ops_fill_board_weekly.bat", 0, False
