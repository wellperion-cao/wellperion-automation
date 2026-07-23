' Wellperion Ops Morning Digest - hidden launcher (no console window). AI CTO (2026-07-14).
' Daily 07:30 via Task Scheduler. Window style 0 = hidden. Logs to logs\ops_morning_digest.log
' Runs: kakao chat export -> ops daily digest build (NO send; send gated=GM go + member notice).
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\scripts\ops_morning_digest.bat", 0, False
