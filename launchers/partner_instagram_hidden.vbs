' Wellperion - partner Instagram daily draft (hidden launcher). Ship 12718, GM directive 2026-09-17.
' One argument: jo = Gocheok golf / dc = Diet Camp. Window style 0 = hidden.
If WScript.Arguments.Count < 1 Then
  WScript.Quit 2
End If
client = WScript.Arguments(0)
cmd = """C:\Users\jjky0\welperion-automation\scripts\partner_instagram_daily.bat"" " & client
rc = CreateObject("WScript.Shell").Run(cmd, 0, True)
WScript.Quit rc
