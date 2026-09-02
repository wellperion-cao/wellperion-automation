' Wellperion - 다이어트캠프 이승기 대표님 대화 에이전트 (hidden launcher). AI CTO (2026-09-02).
' 09:20 ~ 21:20 사이 2시간 간격, Task Scheduler. Window style 0 = hidden.
' 방을 읽어 대표님 새 말씀이 있을 때만 답장 1통. 없으면 아무것도 안 함.
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\diet_camp_agent.bat", 0, True)
WScript.Quit rc
