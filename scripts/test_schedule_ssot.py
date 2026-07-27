# -*- coding: utf-8 -*-
"""schedule_ssot 계약 테스트 — 정직성(지어낸 날짜 0)·판정·게이트 OFF 고정."""
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
    """
    cal = C.load()
    checks = [it for it in cal["items"] if it.get("type") == "정기점검"]
    assert checks, "정기점검 항목이 하나도 없다 — 이 파일의 존재 이유가 사라진 상태"
    assert all(not it["next_due"] for it in checks)


def test_workapproval_only_legal_checks():
    """결재 후보에는 정기점검만 오른다 — 이벤트가 '[정기점검]' 딱지를 달고 새 나가면 안 된다.

    2026-07-27 실측: 기한 도래 15건이 전부 이벤트였다. 필터가 없었다면 게이트를 켜는 순간
    팀 내부 기록 15건이 결재선에 올라갔다.
    """
    cal = C.load()
    cal = {**cal, "items": list(cal["items"]) + [{
        "id": "test-event", "type": "이벤트", "name": "테스트 이벤트", "dept": "운영부",
        "cycle": "수시", "next_due": date.today().isoformat(), "applies": "해당",
    }]}
    for p in C.plan_workapproval(cal)["proposals"]:
        assert p["item_id"] != "test-event"


def test_status_thresholds():
    base = {"next_due": "2026-07-25"}
    t = date(2026, 7, 10)
    assert C.status_of(base, t)["status"] == "due_soon"      # D-15
    assert C.status_of({"next_due": "2026-07-01"}, t)["status"] == "overdue"
    assert C.status_of({"next_due": "2026-12-01"}, t)["status"] == "scheduled"
    assert C.status_of({"next_due": ""}, t)["status"] == "tbd"


def test_gate_off_dry_run():
    cal = C.load()
    assert cal["gate"]["auto_workapproval"] is False
    assert C.plan_workapproval(cal)["dry_run"] is True


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
