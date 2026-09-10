' Wellperion - 고척골프 조재오부장님 블로그 매일 07:00 임시저장 자동화 (hidden launcher). GM 지시 2026-09-10.
' Task Scheduler 매일 07:00. Window style 0 = hidden.
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\gocheok_blog_daily.bat", 0, True)
WScript.Quit rc
