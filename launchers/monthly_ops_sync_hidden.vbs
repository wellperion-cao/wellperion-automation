' Wellperion monthly-ops auto-sync hidden launcher (ship 9678)
' Runs monthly_ops_sync.bat with no console window.
Set WShell = CreateObject("WScript.Shell")
WShell.Run "cmd /c C:\Users\jjky0\welperion-automation\scripts\monthly_ops_sync.bat", 0, False
