"""점검 보고 「오늘 수고하신 곳」 자기검사 (2026-08-08 · GM 지적 "지원부는 왜 없어?").

이 줄은 실무진이 매일 읽는 첫 줄이다. 위험한 지점 두 가지:
  ① 없는 칭찬을 지어내는 것(약속 L05) — 다 안 채운 조를 칭찬하면 그 순간 아무도 안 믿는다.
  ② 한 부서만 계속 빠지는 것 — 격려가 아니라 낙인이 된다. GM 이 지적한 게 이것이다.

python scripts/test_praise_block.py 로 실행.
"""
from report_stream_2_check import _praise_block


def body(support_pct, groups_m, groups_f, facility_ok=True, parking_ok=True):
    t = ""
    if facility_ok:
        t += "🏗 시설부 현황 7회차 · 이상 없음\n"
    t += (f"🛠 지원부 현황 49/105({support_pct}%)\n"
          f"  남성구역 26/53(49%) — {groups_m}\n"
          f"  여성구역 23/52(44%) — {groups_f}\n")
    if parking_ok:
        t += "🅿 주차부 이슈사항: 없음\n"
    return t


# ── 실제 2026-08-07 값: 부서 전체는 47%지만 여성구역 오후조가 15/15 로 다 찼다
out = _praise_block(body(47, "오전조 0/25 · 오후조 13/14 · 마감조 13/14",
                            "오전조 8/24 · 오후조 15/15 · 마감조 0/13"))
assert "시설부" in out and "주차부" in out
assert "지원부 여성구역 오후조 — 15건 전부 완료" in out, out

# ── 다 채운 조가 하나도 없으면 지원부 줄은 안 넣는다(지어내기 금지)
out2 = _praise_block(body(40, "오전조 0/25 · 오후조 13/14", "오전조 8/24 · 마감조 0/13"))
assert "지원부" not in out2, out2

# ── 부서 전체가 90% 이상이면 조별 대신 부서 한 줄로
out3 = _praise_block(body(95, "오전조 25/25", "오전조 24/24"))
assert "지원부 — 오늘 95% 완료" in out3, out3
assert "오전조" not in out3, "부서 줄이 나오면 조별 줄은 겹쳐 넣지 않는다"

# ── 다 채운 조가 많아도 두 줄까지만(칭찬도 길면 안 읽힌다)
out4 = _praise_block(body(60, "오전조 25/25 · 오후조 14/14 · 마감조 14/14",
                             "오전조 24/24 · 오후조 15/15"))
assert out4.count("지원부") == 2, out4

# ── 0/0 인 조를 '전부 완료'로 치지 않는다(할 일이 없던 조는 칭찬 대상이 아니다)
out5 = _praise_block(body(40, "오전조 0/0", "오전조 8/24"))
assert "지원부" not in out5, out5

# ── 셋 다 없으면 블록 자체가 안 나온다(빈 제목만 남기지 않는다)
out6 = _praise_block(body(40, "오전조 0/25", "오전조 8/24",
                          facility_ok=False, parking_ok=False))
assert out6 == "", out6

# ── 2026-08-24 실측 오탐: "이슈사항: 없음" 문구는 실제 무이슈 제출과 미제출 폴백("자체점검
#   준비 중")이 똑같다. filled["parking"]=False(미제출)면 문구가 "없음"이어도 칭찬 안 나간다.
out7 = _praise_block(body(40, "오전조 0/25", "오전조 8/24", facility_ok=False),
                      filled={"parking": False})
assert "주차부" not in out7, out7

# ── filled["parking"]=True(실제 제출)면 칭찬 나간다
out8 = _praise_block(body(40, "오전조 0/25", "오전조 8/24", facility_ok=False),
                      filled={"parking": True})
assert "주차부" in out8, out8

print("OK — 수고하신 곳 판정 11건 통과")
