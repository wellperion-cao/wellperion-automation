' Wellperion - ★중간관리자 방 「웰리」 호출 접수 (hidden launcher). AI CTO 2026-08-21 · 배733.
' 매시 정각 08~20시. Window style 0 = hidden. 로그: logs\kakao_room_listen.log
' 하는 일: 카톡 대화 내보내기(kakao_export_chat --room-key mgr) -> 「웰리」 호출만 뽑아 웰리 배로.
' AI 호출 없음 — 호출이 0건이면 토큰 0.
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\kakao_room_listen.bat", 0, True)
WScript.Quit rc
