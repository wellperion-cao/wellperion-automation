# -*- coding: utf-8 -*-
"""check_incomplete_detector 단위 테스트 — 반복 판정·콜드스타트·제안 포맷·원장 멱등. GM 2026-07-15."""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import check_incomplete_detector as D  # noqa: E402


def _d(base: str, back: int) -> str:
    return (datetime.strptime(base, "%Y-%m-%d") - timedelta(days=back)).strftime("%Y-%m-%d")


def _ledger_with(today: str, item: str, shift: str, ndays: int, total_days: int = 7) -> dict:
    """총 total_days개 날짜 원장 — 그중 최근 ndays일에 item(해당 shift)이 미완료."""
    led = {}
    for i in range(total_days):
        date = _d(today, i)
        if i < ndays:
            led[date] = {"support": {shift: [item], "pm": [], "close": [], "night": []} if shift not in ("pm", "close", "night") else {shift: [item]}}
        else:
            led[date] = {"support": {}}
    return led


# ── 반복 판정 ────────────────────────────────────────────────────────────────
def test_recurring_flagged_at_threshold():
    today = "2026-07-15"
    led = _ledger_with(today, "A-1 사우나 탕", "pm", ndays=5)
    rec = D.detect_recurring(led, today)
    assert len(rec) == 1
    assert rec[0]["item"] == "A-1 사우나 탕"
    assert rec[0]["days"] == 5
    assert rec[0]["shift"] == "pm"
    assert rec[0]["shift_label"] == "오후조"


def test_below_threshold_not_flagged():
    today = "2026-07-15"
    led = _ledger_with(today, "B-2 락커", "close", ndays=3)  # 3일 < 4 → 미반복
    assert D.detect_recurring(led, today) == []


def test_top_shift_is_most_common():
    today = "2026-07-15"
    led = {}
    for i in range(7):
        date = _d(today, i)
        if i < 5:
            # 4일 pm, 1일 close → 최빈 pm
            sh = "pm" if i < 4 else "close"
            led[date] = {"support": {sh: ["샤워부스"]}}
        else:
            led[date] = {"support": {}}
    rec = D.detect_recurring(led, today)
    assert rec[0]["days"] == 5
    assert rec[0]["shift"] == "pm"


# ── 콜드스타트 정직 ──────────────────────────────────────────────────────────
def test_cold_start_empty_ledger():
    assert D.detect_recurring({}, "2026-07-15") == []


def test_cold_start_insufficient_days():
    today = "2026-07-15"
    # 원장 3일치만 — window(7) 미만 → 정직 생략(반복 있어 보여도 []).
    led = {}
    for i in range(3):
        led[_d(today, i)] = {"support": {"pm": ["항목X"]}}
    assert D.detect_recurring(led, today) == []


# ── 제안 포맷 ────────────────────────────────────────────────────────────────
def test_format_suggestion_lines():
    rec = [{"item": "A-1 사우나 탕", "days": 5, "shift": "pm", "shift_label": "오후조"}]
    lines = D.format_suggestion_lines(rec)
    assert lines[0] == "🔁 반복 미완료 — 일정 조율 검토"
    assert "'A-1 사우나 탕'" in lines[1]
    assert "(오후조)" in lines[1]
    assert "최근 7일 中 5일 미완료" in lines[1]
    assert "오전조 이동" in lines[1]


def test_format_empty_when_no_recurring():
    assert D.format_suggestion_lines([]) == []


def test_format_caps_at_max_items():
    rec = [{"item": f"항목{i}", "days": 5, "shift": "pm", "shift_label": "오후조"} for i in range(5)]
    lines = D.format_suggestion_lines(rec, max_items=3)
    assert len(lines) == 1 + 3  # 헤더 + 3항목


# ── 원장 멱등·조립·정리 ──────────────────────────────────────────────────────
def test_build_daily_record_merges_gender():
    ubs = {"pm": {"m": ["남탕"], "f": ["여탕"]}, "close": {"m": [], "f": ["여락커"]}}
    rec = D.build_daily_record(ubs)
    assert rec["support"]["pm"] == ["남탕", "여탕"]
    assert rec["support"]["close"] == ["여락커"]
    assert rec["support"]["night"] == []


def test_append_today_idempotent():
    led = {}
    rec = {"support": {"pm": ["X"]}}
    led = D.append_today(led, "2026-07-15", rec)
    # 같은 날 재적재 — 다른 내용이어도 덮어쓰지 않음(멱등).
    led2 = D.append_today(led, "2026-07-15", {"support": {"pm": ["Y"]}})
    assert led2["2026-07-15"]["support"]["pm"] == ["X"]
    assert len(led2) == 1


def test_append_today_prunes_old_dates():
    led = {"2026-05-01": {"support": {}}}  # 30일 초과 과거
    led = D.append_today(led, "2026-07-15", {"support": {}}, keep_days=30)
    assert "2026-05-01" not in led
    assert "2026-07-15" in led


def test_suggestion_lines_for_today_missing_file():
    # 없는 경로 → 예외 없이 [](콜드스타트 안전)
    assert D.suggestion_lines_for_today("Z:/nonexistent/ledger.json", "2026-07-15") == []
