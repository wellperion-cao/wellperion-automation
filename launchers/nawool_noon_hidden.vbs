' Wellperion - 나우열M 낮 미회신 통 hidden launcher (배2541 · AI CTO 2026-09-11).
' 평일 12:10 예약작업. Window style 0 = hidden. 같은 날 중복은 파이썬 쪽 하트비트가 막는다.
' Runs: scripts\send_ops_digest.py --nawool-noon (GM 계정 텔레그램으로 업무관리 방 한 통)
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\nawool_noon.bat", 0, True)
WScript.Quit rc
