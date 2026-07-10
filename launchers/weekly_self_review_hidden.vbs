' Wellperion Weekly Self-Review - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\weekly_self_review.log
' Created by AI CTO (2026-07-10): 주간 AI 자기정리 Before/After 카드 (메모리+AI트렌드+C레벨컨텍스트).
' Trigger: every Sunday 10:30 via Task Scheduler (schtasks) - runs after ai_learning_proposer (10:00).
' Live send gate WEEKLY_REVIEW_LIVE_SEND defaults OFF - GM go required before real Telegram push.
CreateObject("WScript.Shell").Run "cmd /c cd /d C:\Users\jjky0\welperion-automation& set PYTHONIOENCODING=utf-8& C:\Python314\python.exe -u scripts\weekly_self_review.py >> logs\weekly_self_review.log 2>&1", 0, False
