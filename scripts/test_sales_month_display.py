"""이달 매출 표시 판정 자기검사. 2026-08-08 배446(6일 연속 빈칸) 재발 방지.

위험한 지점은 딱 하나 — 달이 바뀌는 순간이다. 진행중 누적은 '몇 월 것'인지를 달고 다니는데,
그 달 확인을 빼먹으면 9월 1일에 8월 누적이 9월 매출로 둔갑한다.

python scripts/test_sales_month_display.py 로 실행.
"""
from erp_status_publisher import pick_sales_month

# 마감값이 있으면 그대로 — 진행중 표시 없음
assert pick_sales_month({"month": 271488886}, 8) == ("2억 7,148만", False)

# 마감 전(month=null) — 당월 진행중 누적으로 떨어지고 진행중 표시가 붙는다
assert pick_sales_month(
    {"month": None, "monthInProgress": {"month": 8, "value": 160882061}}, 8
) == ("1억 6,088만", True)

# ★달 경계 — 9월인데 8월 누적만 남아 있으면 쓰지 않는다(지난달 값을 이달로 내보내지 않는다)
assert pick_sales_month(
    {"month": None, "monthInProgress": {"month": 8, "value": 160882061}}, 9
) == ("—", False)

# 마감값이 있으면 진행중 누적이 남아 있어도 마감값이 이긴다
assert pick_sales_month(
    {"month": 271488886, "monthInProgress": {"month": 8, "value": 160882061}}, 8
) == ("2억 7,148만", False)

# 둘 다 없음 — 지어내지 않고 '—'
assert pick_sales_month({}, 8) == ("—", False)
assert pick_sales_month({"month": None, "monthInProgress": {"month": 8, "value": None}}, 8) == ("—", False)

print("OK — 이달 매출 표시 판정 6건 통과")
