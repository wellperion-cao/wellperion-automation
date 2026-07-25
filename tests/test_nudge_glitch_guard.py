# -*- coding: utf-8 -*-
"""지원부 점검 독려 — 17:00·22:00 별도 슬롯 폐지 회귀 고정 (2026-07-23 시토).

경위(짧게):
  - 07-16 에 "today_live 가 0 으로 잘못 비는" 오작동 때문에 가짜 독려를 막는 가드를
    넣었는데, 판정이 "오늘 아무 활동이나 있었나"라 **진짜 미완까지 삼켰다.**
    07-17·07-22 이틀에 걸쳐 오후조·마감조 독려 4건이 조용히 사라졌다(로그로 확인).
  - 가드 범위를 좁히고 억제 시 알림까지 붙였으나, GM 판단으로 **독려 경로 자체를 폐지**
    했다("알림·현황 보고가 너무 많다"). 17:00·22:00 슬롯 제거 → 22:30 하루 일과 정리
    하나로 통합. 독려 정보(미완 회차 + 미체크 항목명)는 22:30 이 상시 포함한다.
  - 그래서 이 파일은 이제 "가드가 잘 동작하는가"가 아니라 **"폐지가 유지되는가"**를
    지킨다. 슬롯이 다시 살아나면 여기서 깨진다.

daily_scheduler 는 임포트하지 않는다(임포트만으로 봇 환경이 딸려온다) — 소스 텍스트로 고정.
"""
from __future__ import annotations

from pathlib import Path

import pytest

SCHEDULER = Path(__file__).resolve().parent.parent / "telegram_bot" / "daily_scheduler.py"
SUMMARY = Path(__file__).resolve().parent.parent / "scripts" / "support_check_summary.py"


@pytest.fixture(scope="module")
def scheduler_src() -> str:
    return SCHEDULER.read_text(encoding="utf-8", errors="replace")


def test_nudge_slots_are_not_registered(scheduler_src):
    """17:00·22:00 독려 잡이 다시 등록되면 실패 — GM 2026-07-23 통합 결정 고정."""
    assert '"nudge_pm"' not in scheduler_src, "17:00 독려 슬롯이 되살아났다"
    assert '"nudge_close"' not in scheduler_src, "22:00 독려 슬롯이 되살아났다"


def test_dead_nudge_functions_removed(scheduler_src):
    """폐지와 함께 지운 전용 함수가 되살아나면 실패(주석 언급은 허용)."""
    for name in ("_build_nudge_body", "run_nudge", "_notify_nudge_suppressed"):
        assert f"def {name}(" not in scheduler_src, f"{name} 가 되살아났다"


def test_2230_report_still_carries_nudge_content():
    """독려 내용을 22:30 이 대신 담는다 — 이 블록이 사라지면 정보가 통째로 증발한다."""
    src = SUMMARY.read_text(encoding="utf-8", errors="replace")
    assert "merged_unchecked_names" in src, "미체크 항목 접근자가 사라졌다"
    assert "독려 대상" in src, "22:30 지원부 섹션의 '독려 대상' 블록이 사라졌다"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
