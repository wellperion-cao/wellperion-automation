# -*- coding: utf-8 -*-
"""가역성 라우터 (US-002).

route(gap): (revert_ok ∧ ¬external ∧ ¬data_loss) → 'auto', 아니면/불명(None) → 'propose'.
보수 폴백 — 3부울 중 하나라도 True 아님/False 아님/누락이면 제안으로.
"""
from __future__ import annotations


def route(gap: dict) -> str:
    """정확히 revert_ok=True · external=False · data_loss=False 일 때만 'auto'.
    그 외(누락·None·불명 포함)는 보수적으로 'propose'."""
    if (gap.get("revert_ok") is True
            and gap.get("external") is False
            and gap.get("data_loss") is False):
        return "auto"
    return "propose"
