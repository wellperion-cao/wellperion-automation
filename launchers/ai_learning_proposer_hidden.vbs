' Wellperion AI Learning Proposer - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\ai_learning_proposer.log
' Created by AI CTO (2026-06-23): weekly proposal generation, runs after ai_education_auto_learner (09:30)
' Recommended trigger: every Monday 09:45 via Task Scheduler (schtasks)
CreateObject("WScript.Shell").Run "cmd /c cd /d C:\Users\jjky0\welperion-automation& set PYTHONIOENCODING=utf-8& C:\Python314\python.exe -u scripts\ai_learning_proposer.py >> logs\ai_learning_proposer.log 2>&1", 0, False
