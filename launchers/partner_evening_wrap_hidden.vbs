' Wellperion - 파트너 방 「하루의 마무리」 (hidden launcher). GM 지시 2026-09-11.
' Task Scheduler 매일 21:00. Window style 0 = hidden.
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\partner_evening_wrap.bat", 0, True)
WScript.Quit rc
