# -*- coding: utf-8 -*-
"""
종목 → 색 동그라미 매핑 단일 출처(SSOT) — 2026-07-20 GM 지시(만료임박 알림 가독성 개선).

⚠️ 이 표는 telegram_bot/daily_scheduler.py:2505 `_DIGEST_SPORT_DOT` 값을 그대로 옮긴
것이다(GM 확인한 사내 표준 — 새로 정하지 않음). 매칭 알고리즘도 동일(키워드가 문자열에
부분포함되는지, 대소문자 무시, 표 순서상 첫 매치 사용)하게 이식했다. 원본이 바뀌면 이
표도 함께 갱신해야 한다 — 두 곳이 어긋나면 사고(약속 L01 '한 곳만 본다').

daily_scheduler.py 는 이번 작업 시점에 다른 작업이 편집 중이라 수정하지 않았다.
daily_scheduler.py `_DIGEST_SPORT_DOT` 도 추후 이 모듈로 수렴 예정(후속 과제).
"""
from __future__ import annotations

# (키워드, 색 이모지) 순서 목록 — daily_scheduler.py _DIGEST_SPORT_DOT 과 동일.
SPORT_DOT: list[tuple[str, str]] = [
    ("아쿠아", "🔵"), ("수영", "🔵"), ("Swimming", "🔵"),
    ("P.T", "🔴"), ("PT", "🔴"), ("Personal Training", "🔴"),
    ("필라", "🟠"), ("Pilates", "🟠"),
    ("스쿼시", "🟩"), ("Squash", "🟩"),
    ("골프", "🟢"), ("Golf", "🟢"),
    ("트램폴린", "🟦"), ("체조", "🟦"), ("Gymnastics", "🟦"),
    ("멤버십", "🟡"), ("Membership", "🟡"),
    ("뮤지컬", "⚫"), ("Musical", "⚫"),
    ("발레", "🟣"), ("바레", "🟣"), ("루프", "🟣"), ("Ballet", "🟣"), ("Barre", "🟣"),
]


def sport_dot(name: str) -> str:
    """종목명 -> 색 동그라미 이모지(공백 없이 순수 이모지 1개). 매칭 실패 시 빈 문자열
    반환 — 없는 종목에 임의 색을 붙이지 않는다."""
    k = (name or "").strip().lower()
    if not k:
        return ""
    for kw, dot in SPORT_DOT:
        if kw.lower() in k:
            return dot
    return ""
