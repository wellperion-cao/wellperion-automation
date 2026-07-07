' Wellperion IG Reach Collector - hidden launcher (no console window)
' Window style 0 = hidden. Output appended to logs\ig_reach_collect.log
' Runs ops\start_ig_reach_collect.bat silently (IG account+media reach via Graph API).
' Created by AI CTO (2026-07-07, ship588): daily 09:45 IG reach/impressions collection.
CreateObject("WScript.Shell").Run "cmd /c cd /d C:\Users\jjky0\welperion-automation& ops\start_ig_reach_collect.bat >> logs\ig_reach_collect.log 2>&1", 0, False
