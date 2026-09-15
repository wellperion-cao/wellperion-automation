' Wellperion - 파트너 블로그 매일 임시저장 자동화 (hidden launcher).
' 인자 1개: jo = 고척골프 조재오 부장님 / dc = 다이어트캠프 이승기 대표님.
' GM 지시 2026-09-10(고척) · 2026-09-15(다캠 합류). Window style 0 = hidden.
If WScript.Arguments.Count < 1 Then
  WScript.Quit 2
End If
client = WScript.Arguments(0)
cmd = """C:\Users\jjky0\welperion-automation\scripts\partner_blog_daily.bat"" " & client
rc = CreateObject("WScript.Shell").Run(cmd, 0, True)
WScript.Quit rc
