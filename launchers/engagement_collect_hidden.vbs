' Wellperion Engagement Collector - hidden launcher (no console window)
' Window style 0 = hidden. Logging is handled INSIDE start_engagement_collect.bat
' (each step does its own >> logs\engagement_collect.log 2>&1). Do NOT also
' redirect here -- double-redirecting the same log file (outer cmd /c ... >> log
' AND the bat's own per-line >> log) causes a Windows sharing violation
' ("the process cannot access the file because it is being used by another
' process") on every run, since two handles fight to open the same file for
' write. Fixed 2026-07-20 after 17 days of silent failure (root cause).
' Runs ops\start_engagement_collect.bat silently (danggn + blog, no login needed).
CreateObject("WScript.Shell").Run "cmd /c cd /d C:\Users\jjky0\welperion-automation& ops\start_engagement_collect.bat", 0, False
