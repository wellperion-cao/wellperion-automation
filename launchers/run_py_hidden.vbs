' run_py_hidden.vbs - 예약작업용 공용 숨김 실행기 (2026-09-15 시토 · GM 「셸 창이 켜졌다 꺼졌다」).
' 예약작업이 python.exe 를 바로 부르면 콘솔 창이 뜨고, pythonw.exe 로 부르면 그 스크립트가 띄우는
' 자식(python·git·CLI)이 저마다 새 콘솔을 열어 깜빡인다. 숨긴 셸 하나 아래에서 돌리면 자식이 그 콘솔을 물려받아 안 뜬다.
' 사용: wscript.exe run_py_hidden.vbs <스크립트 절대경로> [인자...]   · 종료코드는 그대로 넘긴다.
Dim sh, args, cmd, i
Set sh = CreateObject("WScript.Shell")
Set args = WScript.Arguments
If args.Count < 1 Then WScript.Quit 2
cmd = """C:\Python314\python.exe"" """ & args(0) & """"
For i = 1 To args.Count - 1
  cmd = cmd & " """ & args(i) & """"
Next
sh.CurrentDirectory = "C:\Users\jjky0\welperion-automation"
WScript.Quit sh.Run(cmd, 0, True)
