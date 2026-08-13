#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scripts/kiosk_calendar.py — 키오스크 PC 전원 스케줄이 읽을 달력을 뽑는다 (배 · GM 지시 2026-08-13).

왜 뽑아 주나: 키오스크 PC 에는 파이썬이 없다(있다고 가정하면 설치가 또 하나 늘어난다).
전원 스크립트는 PowerShell 로 도는데, 휴관 판정을 거기서 다시 구현하면 진실이 두 벌이 된다
(약속 L01). 그래서 **판정은 여기(close_days.py 정본)서 하고, 결과 날짜 목록만** 넘긴다.

산출: status/kiosk_calendar.json
    closed   — 휴관일(그날은 아예 안 켠다)
    holidays — 공휴일(주말과 같은 시각으로 운영)
    ※ 주말(토·일)은 날짜를 안 적는다 — PowerShell 이 요일만 보면 되기 때문.

실행:
    C:/Python314/python.exe scripts/kiosk_calendar.py            # 올해+내년 발행
    C:/Python314/python.exe scripts/kiosk_calendar.py --selftest
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import close_days as cd  # noqa: E402

OUT_PATH = Path(__file__).resolve().parent.parent / "status" / "kiosk_calendar.json"


def _public_holidays() -> list[str]:
    try:
        cfg = json.loads(cd.CONFIG_PATH.read_text(encoding="utf-8"))
        return sorted(set(cfg.get("public_holidays", [])))
    except Exception:  # noqa: BLE001
        return []


def build(years: list[int]) -> dict:
    closed = []
    for y in years:
        d = date(y, 1, 1)
        while d.year == y:
            if cd.is_closed(d):
                closed.append(d.isoformat())
            d += timedelta(days=1)
    return {
        "_doc": "키오스크 전원 스케줄용 달력. 정본=scripts/close_days.py + status/close_days.json. "
                "여기를 손으로 고치지 말고 kiosk_calendar.py 를 다시 돌린다.",
        "years": years,
        "closed": closed,
        "holidays": _public_holidays(),
    }


def main() -> int:
    if "--selftest" in sys.argv:
        data = build([2026])
        # 2·4째 일요일이 휴관으로 들어왔나 — 2026-08 은 9일(2째)·23일(4째)
        assert "2026-08-09" in data["closed"], "8/9(2째 일요일) 휴관 누락"
        assert "2026-08-23" in data["closed"], "8/23(4째 일요일) 휴관 누락"
        assert "2026-08-16" not in data["closed"], "8/16(3째 일요일)은 휴관이 아니다"
        # 공휴일은 휴관과 별개 목록이다(광복절은 운영한다)
        assert "2026-08-15" in data["holidays"], "광복절이 공휴일 목록에 없다"
        assert "2026-08-15" not in data["closed"], "광복절을 휴관으로 잘못 넣었다"
        print(f"OK — 휴관 {len(data['closed'])}일 · 공휴일 {len(data['holidays'])}일 (2026)")
        return 0

    this_year = date.today().year
    data = build([this_year, this_year + 1])
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"발행 {OUT_PATH.name} — 휴관 {len(data['closed'])}일 · 공휴일 {len(data['holidays'])}일")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
