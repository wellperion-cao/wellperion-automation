"""_sales_rows '남은 개월' 계산 자기검사. 2026-08-01 GM 지적(off-by-one) 재발 방지.

python scripts/test_northstar_reach.py 로 실행.
"""
from northstar_reach import _sales_rows


def _home(cur, has_cur, year, year_target):
    return {"data": {"sales": {
        "curMonth": cur, "hasCurMonth": has_cur,
        "year": year, "yearTarget": year_target,
        "yearRate": year / year_target * 100,
    }}}


def _find(rows, prefix):
    for label, _, detail in rows:
        if label.startswith(prefix):
            return detail
    return None


# 8월 1일, 7월까지만 누계(hasCurMonth False) -> 8월도 남은 달에 포함 = 5개월, 월 6.31억
rows = _sales_rows(_home(8, False, 4045070913, 7200000000), None, "2026-08")
detail = _find(rows, "남은 5개월")
assert detail is not None, rows
assert "6.31" in detail, detail

# 이번 달 누계에 이미 반영(hasCurMonth True) -> 기존대로 4개월
rows = _sales_rows(_home(8, True, 4045070913, 7200000000), None, "2026-08")
assert _find(rows, "남은 4개월") is not None, rows

# 12월 경계: hasCurMonth False -> 1개월(0/음수 금지)
rows = _sales_rows(_home(12, False, 4045070913, 7200000000), None, "2026-12")
assert _find(rows, "남은 1개월") is not None, rows

# 12월 경계: hasCurMonth True -> 0개월, 가드에 걸려 줄 자체가 안 나옴(0으로 안 나눔)
rows = _sales_rows(_home(12, True, 7200000000, 7200000000), None, "2026-12")
assert not any(label.startswith("남은") for label, _, _ in rows), rows

print("OK: northstar_reach 남은 개월 self-check 통과")
