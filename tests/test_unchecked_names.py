# -*- coding: utf-8 -*-
"""지원부 미체크 항목명 접근자·22:30 렌더 반영 — 회귀 테스트 (2026-07-23 시토).

배경: 17시·22시 개별 독려 알림에만 있던 '미체크 항목명'을 22:30 하루정리 보고
(scripts/support_check_summary.build_support_section)에도 상시 반영하라는 GM 지시.
정본 접근자 merged_unchecked_names()·렌더 함수 support_nudge_lines()를
support_check_summary.py 에 신설했다 — 외부(GAS) 호출 없이 딕셔너리 주입으로 검증한다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import support_check_summary as scs  # noqa: E402


def test_merged_unchecked_names_combines_m_and_f():
    """①m+f 병합 — 두 배열이 순서대로 이어붙는다."""
    live = {"uncheckedByShift": {"pm": {"m": ["A-1", "A-2"], "f": ["B-1"]}}}
    assert scs.merged_unchecked_names(live, "pm") == ["A-1", "A-2", "B-1"]


def test_merged_unchecked_names_missing_field_returns_empty():
    """②필드 없음 → 빈 리스트(지어내기 금지)."""
    assert scs.merged_unchecked_names({}, "pm") == []
    assert scs.merged_unchecked_names({"uncheckedByShift": {}}, "close") == []
    assert scs.merged_unchecked_names({"uncheckedByShift": {"pm": {}}}, "pm") == []


def _live_with_shifts(shifts: dict) -> dict:
    """{shift: (mDone, mTotal, fDone, fTotal)} → today_live 형태로 조립하는 헬퍼."""
    m, f = {}, {}
    for key, (mD, mT, fD, fT) in shifts.items():
        m[key], m[key + "Total"] = mD, mT
        f[key], f[key + "Total"] = fD, fT
    return {"byGender": {"m": m, "f": f}}


def test_support_nudge_lines_truncates_over_eight():
    """③8개 초과 시 '외 N' 축약이 렌더에 반영된다."""
    live = _live_with_shifts({"pm": (0, 16, 16, 16)})
    live["uncheckedByShift"] = {"pm": {"m": [f"항목{i}" for i in range(1, 12)], "f": []}}
    lines = scs.support_nudge_lines(live)
    body = "\n".join(lines)
    assert "외 3" in body  # 11개 중 8개 노출 + 나머지 3개
    assert "항목1" in body and "항목8" in body
    assert "항목9" not in body


def test_support_nudge_lines_omits_block_when_all_shifts_complete():
    """④미완 회차 없으면 블록 전체 미출력."""
    live = _live_with_shifts({"am": (25, 25, 24, 24), "pm": (16, 16, 16, 16)})
    assert scs.support_nudge_lines(live) == []


def test_support_nudge_lines_shows_shift_without_unchecked_field_silently():
    """uncheckedByShift 가 비어도 회차 진행 줄은 나오되 '— 미체크:' 부분만 조용히 생략."""
    live = _live_with_shifts({"close": (0, 14, 0, 13)})
    lines = scs.support_nudge_lines(live)
    body = "\n".join(lines)
    assert "마감조 남 0/14 · 여 0/13" in body
    assert "미체크" not in body


def test_build_support_section_includes_nudge_block_for_incomplete_shift():
    """build_support_section() 전체 렌더에서도 새 블록이 나온다(회귀 방지)."""
    live = _live_with_shifts({"am": (25, 25, 24, 24), "pm": (0, 16, 16, 16), "close": (0, 14, 0, 13)})
    live["uncheckedByShift"] = {
        "pm": {"m": ["A-1", "A-2", "A-3"], "f": []},
        "close": {"m": ["A-1"], "f": ["B-1"]},
    }
    live["total"] = sum(v for k, v in live["byGender"]["m"].items() if k.endswith("Total")) + \
        sum(v for k, v in live["byGender"]["f"].items() if k.endswith("Total"))
    live["done"] = sum(v for k, v in live["byGender"]["m"].items() if not k.endswith("Total")) + \
        sum(v for k, v in live["byGender"]["f"].items() if not k.endswith("Total"))

    lines, _filled = scs.build_support_section("2026-07-22", data=live)
    body = "\n".join(lines)
    assert "🔔 독려 대상 — 아직 안 된 항목" in body
    assert "오후조 남 0/16 · 여 16/16 — 미체크: A-1, A-2, A-3" in body
    assert "마감조 남 0/14 · 여 0/13 — 미체크: A-1, B-1" in body
    # 완료된 오전조는 독려 블록에 없어야 한다
    assert "오전조 남 25/25" not in body


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
