' Wellperion Morning Update - hidden launcher (no console window)
' Calls the existing morning_update.bat hidden (daily npm/claude update).
' Window style 0 = hidden. Created by AI CTO (2026-06-03).
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\ops\morning_update.bat", 0, False
