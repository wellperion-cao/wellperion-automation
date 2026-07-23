' Wellperion AI CEO Claude Session - hidden launcher (no console window)
' Restarts the remote Claude session by invoking the cleaned Start-AI CEO.bat
' (which now starts ONLY Claude; Telegram bot/scheduler stay independent).
' Window style 0 = hidden -> no black cmd window. Output goes to logs\claude_session.log
' Used by the Telegram /복구 (/restart) command and for manual hidden start.
' Created by AI CTO (2026-06-07): remote session recovery from Telegram.
CreateObject("WScript.Shell").Run "cmd /c cd /d C:\Users\jjky0\welperion-automation& ""Start-AI CEO.bat"" >> logs\claude_session.log 2>&1", 0, False
