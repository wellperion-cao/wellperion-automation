# -*- coding: utf-8 -*-
"""schedule_ssot 계약 테스트 — 정직성(지어낸 날짜 0)·판정.
2026-07-30: gate.auto_workapproval 를 지키던 테스트는 그 키 자체를 삭제하며 함께 뺐다
(plan_workapproval() 실배선 0곳 확인 후 제거, 웰리 결정)."""
from datetime import date
import schedule_ssot as C


def test_ssot_valid():
    assert C.validate(C.load()) == []


def test_no_fabricated_dates():
    """정기점검(법정)은 실제 검사일을 확인하기 전까지 next_due 빈칸 — 지어내지 않는다.

    2026-07-27 수정: 원래는 '모든 items 의 next_due 가 빈칸' 이었다. 그 시절엔 이 파일에
    정기점검만 있었기 때문이다. 이후 이벤트(청소·회식 등 날짜가 실제로 정해진 일정)가 들어오면서
    이 단정이 실패했다 — 이벤트는 날짜를 아는 게 정상이라 '지어냄' 이 아니다.
    정직성 규칙이 겨눈 대상은 '아직 확인 못 한 법정 점검일' 이므로 그 범위로 좁힌다.

    2026-08-14 수정: '정기점검은 무조건 next_due 빈칸' 이 더 이상 사실이 아니다. 2026-08-13 에
    이정헌 소장이 실제 최종검사일을 회신해 주셨고(전기·승강기·정화조·가스), 차기일은 그 날짜와
    주기로 계산된 값이라 지어낸 것이 아니다. 규칙이 진짜 겨눈 것은 **모르면서 날짜를 쓰는 것**
    이므로 그렇게 좁힌다 — 최종검사일(last_done)을 모르는 항목은 차기일도 비어 있어야 한다.
    """
    cal = C.load()
    checks = [it for it in cal["items"] if it.get("type") == "정기점검"]
    assert checks, "정기점검 항목이 하나도 없다 — 이 파일의 존재 이유가 사라진 상태"
    unknown = [it for it in checks if not it.get("last_done")]
    bad = [it["id"] for it in unknown if it.get("next_due")]
    assert not bad, f"최종검사일을 모르는데 차기일이 채워진 항목: {bad}"


def test_status_thresholds():
    base = {"next_due": "2026-07-25"}
    t = date(2026, 7, 10)
    assert C.status_of(base, t)["status"] == "due_soon"      # D-15
    assert C.status_of({"next_due": "2026-07-01"}, t)["status"] == "overdue"
    assert C.status_of({"next_due": "2026-12-01"}, t)["status"] == "scheduled"
    assert C.status_of({"next_due": ""}, t)["status"] == "tbd"


def test_dept_filter_summary():
    cal = C.load()
    s = C.summarize(cal, "지원부")
    assert s["total"] == sum(1 for it in cal["items"] if it["dept"] == "지원부")


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("PASS", fn.__name__)
    print(f"ALL {len(fns)} PASS")
