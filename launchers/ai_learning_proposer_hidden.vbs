' Wellperion AI Learning Proposer - hidden launcher (no console window)
' Window style 0 = hidden. Output preserved to logs\ai_learning_proposer.log
' Created by AI CTO (2026-06-23): weekly proposal generation, runs after ai_education_auto_learner (09:30)
' Updated by AI CTO (2026-07-10): trigger moved Monday 09:45 -> Sunday 10:00 (weekly self-review design).
'   --no-send: individual Telegram send OFF, absorbed into weekly_self_review.py card at 10:30.
' 2026-08-20: wait=True + 자식 종료코드 전달로 변경 (예약작업 실패가 항상 성공 0으로 찍히던 문제 수정).
rc = CreateObject("WScript.Shell").Run("cmd /c cd /d C:\Users\jjky0\welperion-automation& set PYTHONIOENCODING=utf-8& C:\Python314\python.exe -u scripts\ai_learning_proposer.py --no-send >> logs\ai_learning_proposer.log 2>&1", 0, True)
WScript.Quit rc
