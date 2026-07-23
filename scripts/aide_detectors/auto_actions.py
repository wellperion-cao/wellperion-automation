# -*- coding: utf-8 -*-
"""가역 자율 조치 — 순수 뮤테이터 (US-003).

배 dict 를 in-place 로 바꾸고 bool(변경 여부) 반환. 원장 적재는 호출측
(gm_aide_scan.run)이 log_auto_exec 로 수행(순수함수 유지 → 테스트 부작용 0).

멱등 원칙:
  - 태그 = 구조필드 ship['aide_flags'](리스트) 존재검사(중복 no-op · note 미변경).
  - depends_on → depends_on_resolved 이전(원문 보존) · 재실행 no-op.
"""
from __future__ import annotations

from datetime import datetime


def apply_tag(ship: dict, tag: str) -> bool:
    """ship['aide_flags'] 에 tag 멱등 추가. 이미 있으면 no-op(False). note 미변경."""
    flags = ship.get("aide_flags")
    if not isinstance(flags, list):
        flags = []
        ship["aide_flags"] = flags
    if tag in flags:
        return False
    flags.append(tag)
    return True


def set_nudge(ship: dict, clevel: str) -> bool:
    """담당 C-Level aide_nudge 마커 설정. 동일 clevel 이미 있으면 no-op(False)."""
    existing = ship.get("aide_nudge")
    if isinstance(existing, dict) and existing.get("clevel") == clevel:
        return False
    ship["aide_nudge"] = {
        "clevel": clevel,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return True


def resolve_structural_depends(ship: dict) -> bool:
    """구조참조 해소 시 depends_on → depends_on_resolved 이전(원문 보존).
    depends_on 비면/이미 해소면 no-op(False). 멱등."""
    dep = ship.get("depends_on")
    if not (isinstance(dep, (str, int)) and str(dep).strip()):
        return False
    if str(ship.get("depends_on_resolved") or "").strip():
        return False  # 이미 해소됨
    ship["depends_on_resolved"] = dep
    ship["depends_on"] = ""
    return True
