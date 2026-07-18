# -*- coding: utf-8 -*-
"""
clevel_colors.py — C-Level 부서 색동그라미 단일 정의 (GM 피드백, 2026-07-18).

텔레그램은 글자 색을 지원하지 않는다 → 부서/C-Level 별 색 이모지 원(circle)을
닉네임 옆에 붙여 시각적으로 구분한다. 정본은 이 딕셔너리 하나뿐 — 다른 포맷터
(clevel_post_action.py의 build_telegram_message, module_reporter.py 등)는 이
값을 복사하지 말고 이 모듈을 import 해서 쓴다.

매핑(2026-07-18 GM 확정):
    웰리(CEO)=⚪ · 시모(CMO)=🟣 · 시우(COO)=🟢 · 시토(CTO)=🔵 ·
    시포(CPO)=🟠 · 시로(CHRO)=🟡 · 시뽀(CFO)=🔴
"""
from __future__ import annotations

# clevel 코드(대문자) → (닉네임, 색 이모지)
CLEVEL_INFO: dict[str, tuple[str, str]] = {
    "CEO": ("웰리", "⚪"),
    "CMO": ("시모", "🟣"),
    "COO": ("시우", "🟢"),
    "CTO": ("시토", "🔵"),
    "CPO": ("시포", "🟠"),
    "CHRO": ("시로", "🟡"),
    "CFO": ("시뽀", "🔴"),
}

DEFAULT_COLOR = "⚫"


def color_dot(clevel: str) -> str:
    """clevel 코드(대소문자 무관) → 색 이모지. 매핑 없으면 기본(⚫)."""
    info = CLEVEL_INFO.get(str(clevel or "").strip().upper())
    return info[1] if info else DEFAULT_COLOR


def nickname(clevel: str) -> str:
    """clevel 코드 → 닉네임. 매핑 없으면 원문(대문자) 그대로."""
    code = str(clevel or "").strip().upper()
    info = CLEVEL_INFO.get(code)
    return info[0] if info else code


def labeled(clevel: str) -> str:
    """'{색동그라미} {닉네임}' 조합 라벨. 예: '🔵 시토'. 매핑 없으면 '⚫ {원문}'."""
    code = str(clevel or "").strip().upper()
    info = CLEVEL_INFO.get(code)
    if info:
        return f"{info[1]} {info[0]}"
    return f"{DEFAULT_COLOR} {code}"
