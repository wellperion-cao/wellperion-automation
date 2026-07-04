' Wellperion Morning Update - hidden launcher (no console window)
' Calls the existing morning_update.bat hidden (daily npm/claude update).
' Window style 0 = hidden. Created by AI CTO (2026-06-03).
' 2026-07-04 하드닝(시토): wait=True로 변경 — bat 완료까지 대기해 task 결과가 bat의 fail-soft exit(항상 0)을 따르게.
'   (기존 False=비동기라 task가 bat 실제 종료값을 못 잡아 실패코드 오표기 → 건강판 실패 도배 원인)
CreateObject("WScript.Shell").Run "C:\Users\jjky0\welperion-automation\ops\morning_update.bat", 0, True
