' Wellperion IG Publish Watcher - hidden launcher (no console window)
' Calls the existing .bat (which has its own env setup + log redirect) hidden.
' Window style 0 = hidden. Created by AI CTO (2026-06-03).
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\start_ig_publish_watcher.bat", 0, False
