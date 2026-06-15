' Wellperion Engagement Collector - hidden launcher (no console window)
' Window style 0 = hidden. Output appended to logs\engagement_collect.log
' Runs ops\start_engagement_collect.bat silently (danggn + blog, no login needed).
CreateObject("WScript.Shell").Run "cmd /c cd /d C:\Users\jjky0\welperion-automation& ops\start_engagement_collect.bat >> logs\engagement_collect.log 2>&1", 0, False
