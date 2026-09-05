' Wellperion Ops Kakao Export 21:30/19:30 - hidden launcher (no console window). AI CTO (2026-09-05, ship988).
' Weekday 21:30 / weekend 19:30 via Task Scheduler. Window style 0 = hidden. Logs to logs\ops_kakao_export_2130.log
' Runs: kakao chat export only (ops room) - no digest, no send. CPO's evening report_stream_1 reads the export.
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\ops_kakao_export_2130.bat", 0, True)
WScript.Quit rc
