# -*- coding: utf-8 -*-
"""schedule_ssot 계약 테스트 — 정직성(지어낸 날짜 0)·판정·게이트 OFF 고정."""
from datetime import date
import schedule_ssot as C


def test_ssot_valid():
    assert C.validate(C.load()) == []


def test_no_fabricated_dates():
    """뼈대 단계: 모든 next_due 빈칸(실제 날짜 미확인) — 지어내지 않음."""
    cal = C.load()
    assert all(not it["next_due"] for it in cal["items"])


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
