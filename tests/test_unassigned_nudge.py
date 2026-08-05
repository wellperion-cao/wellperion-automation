"""
test_unassigned_nudge.py — 담당배정 독려 독립 메시지 정합성 pytest (2026-08-05 GM 지시).

검증 대상: scripts/unassigned_nudge.py
  ① 재알림 가드가 "매일"로 도는지(오늘 재실행만 막고, 다음날은 다시 뜬다)
  ② 렌더된 메시지가 10줄 안쪽 + 총계/링크/서명을 담는지

★ 실제 네트워크 호출·텔레그램 발송은 하지 않는다 — R._fetch_list 를 monkeypatch 로
  가로채고, build_payload()/collect_unassigned()/_render_message() 만 직접 호출한다
  (main()·send() 는 테스트에서 부르지 않음).
"""

import os
import sys
from datetime import datetime, timedelta

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import unassigned_nudge as U  # noqa: E402

TODAY = "2026-08-05"


def _row(name, sport, days_ago, owner=""):
    d = datetime.strptime(TODAY, "%Y-%m-%d") - timedelta(days=days_ago)
    return {
        "name": name,
        "sport": sport,
        "owner": owner,
        "status": "신규",
        "contacts": [],
        "timestamp": d.strftime("%Y-%m-%d") + "T09:00:00",
    }


def _patch_fetch(monkeypatch, adult_rows, youth_rows):
    def fake_fetch(action, **params):
        assert action == "lesson_inquiry_list"
        return adult_rows if params.get("type") == "성인강습" else youth_rows

    monkeypatch.setattr(U.R, "_fetch_list", fake_fetch)


def test_renotify_guard_is_daily(monkeypatch):
    rows = [_row("홍길동", "성인 수영", days_ago=10)]
    _patch_fetch(monkeypatch, rows, [])
    items = U.collect_unassigned(TODAY)
    assert len(items) == 1
    key = items[0]["key"]

    # 오늘 이미 안내됨 → 같은 날 재실행은 제외(도배 방지)
    selected_today = U.select_daily(items, {key: TODAY}, TODAY)
    assert selected_today == []

    # 어제 안내됨 → 오늘은 다시 뜬다(RENOTIFY_GAP_DAYS=1, 배정될 때까지 매일)
    yesterday = (datetime.strptime(TODAY, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    selected_next_day = U.select_daily(items, {key: yesterday}, TODAY)
    assert len(selected_next_day) == 1


def test_render_message_within_10_lines_and_has_required_parts(monkeypatch):
    rows = [_row(f"회원{i}", "성인 수영", days_ago=3 + i) for i in range(15)]
    _patch_fetch(monkeypatch, rows, [])
    payload = U.build_payload(TODAY, notified={})
    text = payload["text"]
    lines = text.split("\n")

    assert len(lines) <= 10
    assert f"{len(payload['eligible'])}건" in lines[0]
    assert "가장 오래된 건" in lines[0]
    assert any(U.ASSIGN_URL_LESSON in ln for ln in lines)
    assert lines[-1] == U.AI_SIGNOFF
    # 상위 MSG_DISPLAY_N 건만 줄로 싣고 나머지는 "외 N건"으로 접힘
    item_lines = [ln for ln in lines if ln.startswith("· ")]
    assert len(item_lines) == U.MSG_DISPLAY_N
    assert any(ln.startswith("… 외 ") for ln in lines)


def test_render_message_empty_when_all_guarded_today(monkeypatch):
    rows = [_row("홍길동", "성인 수영", days_ago=10)]
    _patch_fetch(monkeypatch, rows, [])
    items = U.collect_unassigned(TODAY)
    key = items[0]["key"]
    payload = U.build_payload(TODAY, notified={key: TODAY})
    assert payload["text"] == ""


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
