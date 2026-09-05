"""work_room_agent.classify() 최소 자기검증 — 배1068 GM 지시 2026-09-05.
프레임워크 없음. `python test_work_room_agent.py` 로 직접 실행."""
from work_room_agent import classify

# 케이스 1: 완료 회신
assert classify("반영했습니다") == "done"

# 케이스 2: 등록 확인(TODO 번호 포함)
assert classify("등록했습니다 TODO-20260905171415092") == "register_confirm"

# 케이스 3: 질문(「확인 부탁」류)
assert classify("이거 확인 부탁드립니다") == "question"

# 케이스 4: 질문(물음표)
assert classify("이 문구 맞나요?") == "question"

# 케이스 5: 그 외(분류 대상 아님)
assert classify("네 알겠습니다 진행할게요") == "other"

# 케이스 6: TODO 번호가 있으면 "완료" 낱말이 같이 있어도 등록확인이 우선
assert classify("완료했습니다 TODO-999") == "register_confirm"

print("OK — work_room_agent.classify 6케이스 정상")
