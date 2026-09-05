"""bot.py 의 _may_reply() 최소 자기검증 — GM 지시 2026-09-05 그룹 무응답 게이트.
프레임워크 없음. `python test_may_reply.py` 로 직접 실행."""
from bot import _may_reply, _GM_CHAT_ID

# 케이스 1: 그룹(음수 chat_id, 업무관리-나우열M 예시) → 무응답
assert _may_reply(-5492623600) is False, "그룹 chat_id 는 무응답이어야 한다"

# 케이스 2: GM 개인 봇방(업무관리) → 응답 허용
assert _may_reply(_GM_CHAT_ID) is True, "GM 개인 봇방은 응답해야 한다"

print("OK — _may_reply 게이트 정상 (그룹=무응답, GM방=응답)")
