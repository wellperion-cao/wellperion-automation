"""멈춘 업무 카드 — 주차 세기·에스컬레이션 자기검사 (2026-08-08 · GM 지시).

GM 이 세 번 말한 것: "진행이 안된건에 대해서는 명확히 체크해서 진행이 되게끔 구조를 만들어줘."
그 구조의 핵심이 두 가지다 — ①같은 건이 몇 주째 뜨는지 세는 것 ②여러 주째인데 막힌 이유도
안 적힌 건을 GM 께 올리는 것. 이 둘이 틀리면 카드는 그냥 예쁜 목록으로 되돌아간다.

python scripts/test_stalled_card.py 로 실행.
"""
from kakao_summary_card import fold_stalled, ESCALATE_WEEKS


def row(key, days, reason="", who="최준용M"):
    return {"key": key, "who": who, "title": key, "days": days,
            "reason": reason, "resume": ""}


# ── 첫 회차: 지난 기록이 없으면 전부 1주째, 에스컬레이션 없음
r = fold_stalled([row("A", 10), row("B", 30)], {})
assert r["first_round"] is True
assert [x["weeks"] for x in r["rows"]] == [1, 1]
assert r["escalate"] == []

# ── 오래 밀린 것이 위로
assert [x["key"] for x in r["rows"]] == ["B", "A"]

# ── 다음 회차: 남아 있는 건은 주차가 오르고, 사라진 건은 기록에서 빠진다
r2 = fold_stalled([row("A", 17)], r["state"])
assert r2["rows"][0]["weeks"] == 2
assert "B" not in r2["state"], "해결된 건은 다음 회차 기록에 남기지 않는다"
assert r2["first_round"] is False

# ── 에스컬레이션: 기준 주차에 닿고 사유가 비어 있어야 올린다
prev = {"A": ESCALATE_WEEKS - 1}
assert len(fold_stalled([row("A", 40)], prev)["escalate"]) == 1
# 한 주 이르면 아직 안 올린다(경계)
assert fold_stalled([row("A", 40)], {"A": ESCALATE_WEEKS - 2})["escalate"] == []
# 사유가 적혔으면 몇 주째든 안 올린다 — 막힌 곳을 알려 준 사람을 재촉하지 않는다
assert fold_stalled([row("A", 40, reason="예산 결재 대기")], prev)["escalate"] == []

# ── 사유 안 적힌 건수 세기
r3 = fold_stalled([row("A", 5), row("B", 6, reason="자재 입고 대기")], {})
assert len(r3["no_reason"]) == 1

# ── ★집계는 사람이 아니라 부서 단위다 (GM 확정 2026-08-08)
#   개인 이름으로 부르면 방어부터 하게 된다. 최준용M·이경연 실장·윤병현AM 은 모두 운영부라
#   한 줄로 합쳐진다.
r4 = fold_stalled([row("A", 5, who="최준용M"), row("B", 6, who="이경연 실장"),
                   row("C", 7, who="나우열M")], {})
assert r4["by_who"][0] == ("운영부", 2), r4["by_who"]
assert ("인사·재무", 1) in r4["by_who"], r4["by_who"]

# ── 카드에 실릴 값 어디에도 개인 이름이 남으면 안 된다
for _r in r4["rows"]:
    assert _r["dept"] in ("운영부", "시설부", "인사·재무", "미분류"), _r

# ── 명단에 없는 이름은 지어내지 않고 '미분류'
r5 = fold_stalled([row("A", 5, who="홍길동")], {})
assert r5["by_who"] == [("미분류", 1)], r5["by_who"]

print("OK — 멈춘 업무 카드 판정 13건 통과")
