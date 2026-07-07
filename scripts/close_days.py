#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/close_days.py — 웰페리온 휴관일 판정 모듈 (2026-07-07 CTO, 배488)

GM 확정 규칙: 휴관일 = 신정(1/1) · 설날 · 추석 · 매월 2·4째 일요일.
    ①②는 코드로 자동 계산(달력 규칙 고정), ③(음력·기타 공휴일)은 자동계산이
    불가능해 status/close_days.json 의 dates 목록에 GM/시토가 수동 등록한다.

주의: 여기서 "휴관일"은 CLAUDE.md §0 공식 운영시간(둘째넷째 일요일 휴관)과
    동일한 값을 코드로 재현한 것 — 공식값 임의 변형 금지.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "status" / "close_days.json"


def _manual_close_dates() -> set[str]:
    """status/close_days.json 의 dates(음력·공휴일 수동 등록분) 로드. 파일 없음/파싱
    실패 시 빈 집합(안전측 기본값 — 수동 등록분 없으면 휴관 아님으로 판정)."""
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return set(cfg.get("dates", []))
    except Exception:
        return set()


def is_closed(d: date) -> bool:
    """d가 휴관일이면 True.

    ① 신정(1/1)
    ② 매월 2째·4째 일요일 — 그 달에서 몇 번째 일요일인가 = (d.day-1)//7 + 1
    ③ status/close_days.json 의 dates(음력 설/추석·임시휴관 등 수동 등록분)
    """
    if d.month == 1 and d.day == 1:
        return True
    if d.weekday() == 6:  # 일요일
        nth = (d.day - 1) // 7 + 1
        if nth in (2, 4):
            return True
    if d.strftime("%Y-%m-%d") in _manual_close_dates():
        return True
    return False


def next_business_day(d: date) -> date:
    """d부터 시작해 is_closed가 False인 첫 날 반환(멀티데이 휴관 대비)."""
    cur = d
    while is_closed(cur):
        cur += timedelta(days=1)
    return cur


if __name__ == "__main__":
    # 간이 유닛 검증(실행 시 2026년 2·4째 일요일·신정·평일 예시 출력)
    print("2026-01-01(신정):", is_closed(date(2026, 1, 1)))
    print("2026년 1월 일요일들:")
    for day in range(1, 32):
        d = date(2026, 1, day)
        if d.weekday() == 6:
            nth = (d.day - 1) // 7 + 1
            print(f"  {d} (몇째 일요일={nth}) is_closed={is_closed(d)}")
    print("평범한 평일(2026-01-07 수):", is_closed(date(2026, 1, 7)))
