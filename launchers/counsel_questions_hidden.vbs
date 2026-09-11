' Wellperion - 상담봇 질문 수집·가공 (hidden launcher). GM 지시 2026-09-11.
' Task Scheduler 매일 22:10. Window style 0 = hidden.
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\counsel_questions.bat", 0, True)
WScript.Quit rc
