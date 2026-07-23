# -*- coding: utf-8 -*-
"""지원부 점검 독려 — today_live 글리치 가드 회귀 테스트 (2026-07-23 시토).

배경: 2026-07-16 에 "today_live 가 0 으로 잘못 비는 사례" 때문에 가짜 독려를 막는
가드를 넣었는데, 판정 기준이 "오늘 아무 활동이나 있었나"라 **진짜 미완료까지 삼켰다.**
2026-07-22 실측 — 마감조 0/27(진짜 미완)인데 그날 오전조가 일해 시트 활동이 있었고
가드가 글리치로 오판해 침묵 → GM 이 마감조 독려를 못 받음.

수리: 글리치의 진짜 신호는 "today_live 가 통째로 죽어 전 회차 0". 한 회차라도 살아
있으면 today_live 는 정상이므로 가드를 적용하지 않는다.

여기서는 daily_scheduler 를 임포트하지 않는다(임포트만으로 봇 환경·스케줄러가 딸려온다).
가드 판정식 자체를 그대로 복제해 회귀를 고정한다 — 식이 바뀌면 이 테스트가 깨져야 한다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SCHEDULER = Path(__file__).resolve().parent.parent / "telegram_bot" / "daily_scheduler.py"


def glitch_guard_applies(live: dict, shift: str) -> bool:
    """수리된 판정: 해당 회차 done==0 이고 **다른 회차도 전부 0** 일 때만 글리치 의심."""
    done = int(live.get(shift, 0) or 0)
    live_elsewhere = any(int(live.get(k, 0) or 0) > 0 for k in ("am", "pm", "close", "night"))
    return done == 0 and not live_elsewhere


# 2026-07-22 실제 today_live 값 (GM 이 알림 못 받은 그날)
YESTERDAY = {
    "am": 46, "amTotal": 49,
    "pm": 16, "pmTotal": 32,
    "close": 0, "closeTotal": 27,
    "night": 0, "nightTotal": 0,
}


def test_real_incomplete_close_shift_is_not_silenced():
    """마감조 0/27 — 오전조가 살아 있으므로 글리치가 아니다. 독려가 나가야 한다."""
    assert glitch_guard_applies(YESTERDAY, "close") is False


def test_pm_shift_partially_done_is_not_silenced():
    """오후조 16/32 — done>0 이라 애초에 가드 대상이 아니다."""
    assert glitch_guard_applies(YESTERDAY, "pm") is False


def test_whole_day_zero_is_still_treated_as_glitch():
    """전 회차 0 = today_live 가 통째로 죽은 상태 → 가드 유지(가짜 독려 방지)."""
    dead = {"am": 0, "amTotal": 49, "pm": 0, "pmTotal": 32,
            "close": 0, "closeTotal": 27, "night": 0, "nightTotal": 0}
    assert glitch_guard_applies(dead, "close") is True


def test_completed_shift_never_reaches_guard():
    """완료된 회차는 done>0 이라 가드에 걸리지 않는다."""
    done_live = dict(YESTERDAY, close=27)
    assert glitch_guard_applies(done_live, "close") is False


def test_scheduler_source_still_uses_live_elsewhere_condition():
    """실제 스케줄러 코드가 이 조건을 계속 쓰는지 고정 — 다시 넓어지면 여기서 깨진다."""
    src = SCHEDULER.read_text(encoding="utf-8", errors="replace")
    assert "live_elsewhere" in src, "글리치 가드에서 live_elsewhere 조건이 사라졌다"
    assert re.search(r"if\s+done\s*==\s*0\s+and\s+not\s+live_elsewhere", src), \
        "가드 조건이 'done==0 and not live_elsewhere' 형태가 아니다"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
