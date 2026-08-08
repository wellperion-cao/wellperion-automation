"""점검 마감 카드 — 본문에서 숫자 뽑기 자기검사 (2026-08-08 · GM 지시).

이 카드는 밤 22:30 에 89줄로 나가던 글을 한 장으로 줄인 것이다. 위험한 지점:
  ① 0건인 조를 놓치면 카드가 존재할 이유가 사라진다(그게 유일한 행동 요청이다).
  ② 0/0 인 조(할 일이 아예 없던 조)를 '아직 0건'으로 잘못 올리면 헛경보가 된다.

python scripts/test_check_card.py 로 실행.
"""
from kakao_summary_card import collect_check

SAMPLE = """🏗 시설부 현황 3회차 · 이상 없음
  📋 회차별 일지
    · 1회차 06:07~06:18(11분) · 이정헌 · (추가 작업 없음)

🛠 지원부 현황 25/78(32%)
  남성구역 25/40(62%) — 오전조 25/25 · 마감조 0/15
  여성구역 0/38(0%) — 오전조 0/24 · 마감조 0/14
  📝 이슈 상세 1건
    · [남/오전조] 샤워기 벽. 물절약. 스티커. 교체요함 (이정한)

🅿 주차부 이슈사항: 없음 (자체점검 준비 중)
"""

S = collect_check(SAMPLE)

assert S["facility"] == {"rounds": 3, "state": "이상 없음"}, S["facility"]
assert S["support"] == {"done": 25, "total": 78, "pct": 32}, S["support"]
assert S["parking"].startswith("없음"), S["parking"]

# 아직 0건인 조 세 곳을 다 잡는다 — 이게 카드의 존재 이유다
zero = [z["name"] for z in S["zero_groups"]]
assert zero == ["남성구역 마감조", "여성구역 오전조", "여성구역 마감조"], zero
assert S["zero_groups"][0]["total"] == 15

# 다 채운 조는 따로 모은다
full = [f["name"] for f in S["full_groups"]]
assert full == ["남성구역 오전조"], full

# 이슈는 어디서 올라왔는지와 함께
assert S["issues"][0]["where"] == "남/오전조", S["issues"]

# ── 0/0 인 조는 '아직 0건'으로 올리지 않는다(할 일이 없던 조는 독려 대상이 아니다)
S2 = collect_check("🛠 지원부 현황 0/0(0%)\n  남성구역 0/0(0%) — 오전조 0/0\n")
assert S2["zero_groups"] == [], S2["zero_groups"]
assert S2["full_groups"] == [], S2["full_groups"]

# ── 본문에 없는 항목은 지어내지 않고 비운다
S3 = collect_check("🛠 지원부 현황 10/10(100%)\n  남성구역 10/10(100%) — 오전조 10/10\n")
assert S3["facility"] is None and S3["parking"] is None, S3
assert [f["name"] for f in S3["full_groups"]] == ["남성구역 오전조"]

print("OK — 점검 마감 카드 판정 10건 통과")
